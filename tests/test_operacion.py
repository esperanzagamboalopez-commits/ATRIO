import io
import json
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import centro as C


def _dbf(rows):
    """Construye un DBF dBase III mínimo para pruebas, sin datos SISAE reales."""
    fields = list(rows[0]) if rows else []
    widths = {name: max(16, max(len(str(row.get(name, ""))) for row in rows) + 1)
              for name in fields}
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + sum(widths.values())
    header = bytearray(32)
    header[0] = 3
    struct.pack_into("<I", header, 4, len(rows))
    struct.pack_into("<H", header, 8, header_len)
    struct.pack_into("<H", header, 10, record_len)
    descriptors = bytearray()
    for name in fields:
        field = bytearray(32)
        field[:11] = name.encode("ascii")[:10].ljust(11, b"\0")
        field[11] = ord("C")
        field[16] = widths[name]
        descriptors.extend(field)
    records = bytearray()
    for row in rows:
        record = bytearray(b" ")
        for name in fields:
            value = str(row.get(name, "")).encode("cp1252")[:widths[name]]
            record.extend(value.ljust(widths[name], b" "))
        records.extend(record)
    return bytes(header + descriptors + b"\r" + records + b"\x1a")


def _programming_book(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "DOCENTE PRUEBA"
    ws.cell(1, 1, "23-INFO-2026")
    ws.cell(1, 2, "INFORMÁTICA")
    row = 15
    values = {
        1: "Extensión",
        2: "INFORMÁTICA BÁSICA",
        4: 10,
        5: "2026-11-10",
        6: "2026-12-10",
        7: 60,
        9: "MARTES A SÁBADO 09:00 - 12:00",
        10: "Aula de prueba",
    }
    for col, value in values.items():
        ws.cell(row, col, value)
    wb.save(path)
    wb.close()


def _teacher_book(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "DOCENTES"
    headers = [
        "ID DOCENTE", "NOMBRE COMPLETO", "CURP", "CORREO INSTITUCIONAL",
        "TELÉFONO", "TIPO DOCENTE", "RUTA FIRMA (PNG/JPG)",
        "USO DE FIRMA AUTORIZADO", "OBSERVACIONES", "ESPECIALIDAD DOCENTE",
    ]
    ws.append(headers)
    ws.append([
        "DOC-TEST", "DOCENTE PRUEBA", "CURP-FICTICIA", "docente@example.invalid",
        "0000000000", "Interno", "", "No", "Registro ficticio", "INFORMÁTICA",
    ])
    wb.save(path)
    wb.close()


def _sisae_zip():
    program = _dbf([{"CLAVE_CURS": "CURSO-TEST"}])
    enrollment = _dbf([{"CLV_CURSO": "CURSO-TEST"}])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("PROG_CURSOS1.DBF", program)
        archive.writestr("INSCRIPCION.DBF", enrollment)
    return out.getvalue()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    paths = {
        "ROOT": tmp_path,
        "DATA": tmp_path / "datos",
        "RES": tmp_path / "datos" / "recursos",
        "OUT": tmp_path / "datos" / "salidas",
        "ARCH": tmp_path / "datos" / "versiones",
    }
    for name, path in paths.items():
        monkeypatch.setattr(C, name, path)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    _programming_book(C.RES / "PROGRAMACION DE CURSOS.xlsx")
    _teacher_book(C.RES / "Plantilla_Datos_Docentes_PEA_CECATI31.xlsx")
    Document().save(C.RES / "PEA_final en blanco.docx")
    (C.RES / "DIAS_SIN_CLASE.json").write_text("[]", encoding="utf-8")
    (C.RES / "SISAE.zip").write_bytes(_sisae_zip())

    C.import_program(C.RES / "PROGRAMACION DE CURSOS.xlsx")
    return C


def test_import_and_identity(isolated):
    before = {g["fingerprint"]: g["id"] for g in C.groups()}
    C.import_program(C.RES / "PROGRAMACION DE CURSOS.xlsx")
    after = {g["fingerprint"]: g["id"] for g in C.groups()}
    assert before == after
    assert len(before) == 1
    assert sum(g["tipo"] == "Extensión" for g in C.groups()) == 1


def test_resource_validation_is_atomic(isolated):
    resource = C.RES / "DIAS_SIN_CLASE.json"
    old = resource.read_bytes()
    with pytest.raises(ValueError):
        C.save_resource("DIAS_SIN_CLASE.json", b'["2026-99-99"]')
    assert resource.read_bytes() == old

    C.save_resource("DIAS_SIN_CLASE.json", b'["2026-11-16"]')
    assert len(list(C.ARCH.iterdir())) == 1
    assert C.setting("calendario_confirmado") is False


def test_sqlite_usa_synchronous_full(isolated):
    with C.connect() as db:
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2


def test_save_programacion_confirma_importacion_y_limpia_journal(isolated):
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    raw = resource.read_bytes()

    result = C.save_resource("PROGRAMACION DE CURSOS.xlsx", raw)

    assert result[0] == 1
    assert not C._ruta_journal_programacion().exists()
    with C.connect() as db:
        row = db.execute(
            "SELECT payload FROM events WHERE action='Importación programación' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert json.loads(row["payload"])["operation_id"]


def test_save_programacion_conserva_commit_si_falla_una_vez_el_borrado_del_journal(isolated, monkeypatch):
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    raw = resource.read_bytes()
    journal = C._ruta_journal_programacion()
    unlink_real = Path.unlink
    calls = {"journal": 0}

    def fail_once(path, *args, **kwargs):
        if path == journal:
            calls["journal"] += 1
            if calls["journal"] == 1:
                raise OSError("fallo simulado al limpiar journal")
        return unlink_real(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_once)
    result = C.save_resource("PROGRAMACION DE CURSOS.xlsx", raw)

    assert result[0] == 1
    assert calls["journal"] >= 2
    assert not journal.exists()
    with C.connect() as db:
        rows = db.execute(
            "SELECT payload FROM events WHERE action='Importación programación'"
        ).fetchall()
    assert len(rows) >= 2
    assert any(json.loads(row["payload"]).get("operation_id") for row in rows)


def test_save_programacion_recupera_si_falla_fsync_del_directorio_excel(isolated, monkeypatch):
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    fsync_real = C._fsync_directorio
    failed = {"value": False}

    def fail_once(path):
        if Path(path) == C.RES and not failed["value"]:
            failed["value"] = True
            raise OSError("fallo fsync simulado")
        return fsync_real(path)

    monkeypatch.setattr(C, "_fsync_directorio", fail_once)
    with pytest.raises(OSError, match="fallo fsync simulado"):
        C.save_resource("PROGRAMACION DE CURSOS.xlsx", original)

    assert failed["value"]
    assert resource.read_bytes() == original
    assert not C._ruta_journal_programacion().exists()
    with C.connect() as db:
        rows = db.execute(
            "SELECT payload FROM events WHERE action='Importación programación'"
        ).fetchall()
    assert all(not json.loads(row["payload"] or "{}").get("operation_id") for row in rows)


def test_save_programacion_confirma_si_falla_fsync_despues_de_eliminar_journal(isolated, monkeypatch):
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    raw = resource.read_bytes()
    fsync_real = C._fsync_directorio
    calls = {"archive": 0}

    def fail_after_journal_unlink(path):
        if Path(path) == C.ARCH:
            calls["archive"] += 1
            # Respaldo, journal y limpieza final: el tercer fsync ocurre después del unlink.
            if calls["archive"] == 3:
                raise OSError("fallo fsync tras borrar journal")
        return fsync_real(path)

    monkeypatch.setattr(C, "_fsync_directorio", fail_after_journal_unlink)
    result = C.save_resource("PROGRAMACION DE CURSOS.xlsx", raw)

    assert result[0] == 1
    assert calls["archive"] >= 3
    assert not C._ruta_journal_programacion().exists()
    with C.connect() as db:
        rows = db.execute(
            "SELECT payload FROM events WHERE action='Importación programación'"
        ).fetchall()
    assert any(json.loads(row["payload"] or "{}").get("operation_id") for row in rows)
    assert C._validar_excel_programacion(resource)


def test_save_programacion_sincroniza_respaldo_excel_y_directorios(isolated, monkeypatch):
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    raw = resource.read_bytes()
    with monkeypatch.context() as patcher:
        original_file = C._fsync_archivo
        original_dir = C._fsync_directorio
        file_calls = []
        dir_calls = []

        def sync_file(path):
            file_calls.append(Path(path))
            return original_file(path)

        def sync_dir(path):
            dir_calls.append(Path(path))
            return original_dir(path)

        patcher.setattr(C, "_fsync_archivo", sync_file)
        patcher.setattr(C, "_fsync_directorio", sync_dir)
        result = C.save_resource("PROGRAMACION DE CURSOS.xlsx", raw)

    assert result[0] == 1
    assert any("PROGRAMACION" in path.name for path in file_calls)
    assert C.ARCH in dir_calls
    assert C.RES in dir_calls
    assert not C._ruta_journal_programacion().exists()


def test_save_programacion_no_reporta_fallo_si_falla_evento_secundario_tras_commit(isolated, monkeypatch):
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    raw = resource.read_bytes()
    event_real = C.event

    def fail_secondary_event(group_id, action, payload):
        if action == "Recurso actualizado":
            raise OSError("fallo del evento secundario")
        return event_real(group_id, action, payload)

    monkeypatch.setattr(C, "event", fail_secondary_event)
    result = C.save_resource("PROGRAMACION DE CURSOS.xlsx", raw)

    assert result[0] == 1
    assert not C._ruta_journal_programacion().exists()
    assert C._validar_excel_programacion(resource)
    with C.connect() as db:
        rows = db.execute(
            "SELECT payload FROM events WHERE action='Importación programación'"
        ).fetchall()
    assert any(json.loads(row["payload"] or "{}").get("operation_id") for row in rows)


def test_save_programacion_revierte_si_falla_importacion(isolated, monkeypatch):
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    workbook = load_workbook(resource)
    workbook["DOCENTE PRUEBA"].cell(15, 6).value = "2026-12-20"
    from io import BytesIO
    updated = BytesIO()
    workbook.save(updated)
    workbook.close()

    def fail_import(*args, **kwargs):
        raise RuntimeError("fallo de importación simulado")

    monkeypatch.setattr(C, "_import_program_impl", fail_import)
    with pytest.raises(RuntimeError, match="fallo de importación simulado"):
        C.save_resource("PROGRAMACION DE CURSOS.xlsx", updated.getvalue())

    assert resource.read_bytes() == original
    assert not C._ruta_journal_programacion().exists()


def test_recupera_guardado_tras_cierre_abrupto_antes_de_importar(isolated, tmp_path):
    """Simula la terminación del proceso justo después de sustituir el Excel."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    workbook = load_workbook(resource)
    workbook["DOCENTE PRUEBA"].cell(15, 6).value = "2026-12-20"
    updated_path = tmp_path / "programacion_actualizada.xlsx"
    workbook.save(updated_path)
    workbook.close()

    repo_root = Path(__file__).resolve().parents[1]
    child_script = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import centro as C
C.ROOT = Path(sys.argv[2])
C.DATA = Path(sys.argv[3])
C.RES = Path(sys.argv[4])
C.ARCH = Path(sys.argv[5])
C._import_program_impl = lambda *args, **kwargs: os._exit(73)
C.save_resource("PROGRAMACION DE CURSOS.xlsx", Path(sys.argv[6]).read_bytes())
"""
    result = subprocess.run(
        [
            sys.executable, "-c", child_script, str(repo_root), str(C.ROOT),
            str(C.DATA), str(C.RES), str(C.ARCH), str(updated_path),
        ],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 73
    assert resource.read_bytes() != original
    assert C._ruta_journal_programacion().exists()

    assert C.recuperar_programacion() is True
    assert resource.read_bytes() == original
    assert not C._ruta_journal_programacion().exists()


def test_conserva_guardado_confirmado_tras_cierre_abrupto(isolated, tmp_path):
    """Si SQLite confirmó, un cierre antes de borrar el journal conserva el Excel nuevo."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    workbook = load_workbook(resource)
    workbook["DOCENTE PRUEBA"].cell(15, 6).value = "2026-12-20"
    updated_path = tmp_path / "programacion_confirmada.xlsx"
    workbook.save(updated_path)
    workbook.close()
    expected_new = updated_path.read_bytes()

    repo_root = Path(__file__).resolve().parents[1]
    child_script = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import centro as C
C.ROOT = Path(sys.argv[2])
C.DATA = Path(sys.argv[3])
C.RES = Path(sys.argv[4])
C.ARCH = Path(sys.argv[5])
original_import = C._import_program_impl
def commit_then_exit(path, operation_id=None):
    result = original_import(path, operation_id=operation_id)
    os._exit(74)
C._import_program_impl = commit_then_exit
C.save_resource("PROGRAMACION DE CURSOS.xlsx", Path(sys.argv[6]).read_bytes())
"""
    result = subprocess.run(
        [
            sys.executable, "-c", child_script, str(repo_root), str(C.ROOT),
            str(C.DATA), str(C.RES), str(C.ARCH), str(updated_path),
        ],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 74
    assert resource.read_bytes() == expected_new
    assert C._ruta_journal_programacion().exists()

    assert C.recuperar_programacion() is True
    assert resource.read_bytes() == expected_new
    assert not C._ruta_journal_programacion().exists()
    with C.connect() as db:
        row = db.execute(
            "SELECT payload FROM events WHERE action='Importación programación' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert json.loads(row["payload"])["operation_id"]


def test_recupera_confirmacion_aunque_falte_respaldo(isolated):
    """Una operación confirmada conserva el Excel nuevo aunque ya no exista el backup."""
    operation_id = "op-confirmada-sin-respaldo"
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    expected = resource.read_bytes()
    journal = C._ruta_journal_programacion()
    C._escribir_journal_programacion({
        "operation_id": operation_id,
        "commit_action": "Importación programación",
        "excel": str(resource.resolve()),
        "backup": str((C.ARCH / "respaldo_que_no_existe.xlsx").resolve()),
        "created": C.now(),
    })
    with C.connect() as db:
        db.execute(
            "INSERT INTO events(at,action,payload) VALUES(?,?,?)",
            (C.now(), "Importación programación",
             json.dumps({"operation_id": operation_id}, ensure_ascii=False)),
        )

    assert C.recuperar_programacion() is True
    assert resource.read_bytes() == expected
    assert not journal.exists()


def test_journal_corrupto_no_modifica_programacion(isolated):
    """Un journal ilegible detiene la recuperación sin tocar el Excel ni borrarlo."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    journal = C._ruta_journal_programacion()
    journal.write_text('{"operation_id":', encoding="utf-8")

    with pytest.raises(RuntimeError, match="no pudo completar su recuperación"):
        C.recuperar_programacion()

    assert resource.read_bytes() == original
    assert journal.exists()


def test_respaldo_faltante_sin_confirmacion_no_modifica_programacion(isolated):
    """Sin confirmación y sin backup, ATRIO se detiene conservando Excel y journal."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    journal = C._ruta_journal_programacion()
    C._escribir_journal_programacion({
        "operation_id": "operacion-sin-confirmar",
        "commit_action": "Importación programación",
        "excel": str(resource.resolve()),
        "backup": str((C.ARCH / "respaldo_ausente.xlsx").resolve()),
        "created": C.now(),
    })

    with pytest.raises(RuntimeError, match="respaldo necesario"):
        C.recuperar_programacion()

    assert resource.read_bytes() == original
    assert journal.exists()


def test_sisae(isolated):
    tables = C.sisae_bytes((C.RES / "SISAE.zip").read_bytes())
    assert len(tables["PROG_CURSOS1.DBF"]) == 1
    assert len(tables["INSCRIPCION.DBF"]) == 1
    keys = {g["CLAVE_CURS"] for g in tables["PROG_CURSOS1.DBF"]}
    assert all(row["CLV_CURSO"] in keys for row in tables["INSCRIPCION.DBF"])


def test_status_and_backup(isolated):
    group = C.groups()[0]
    C.update_status(group["id"], "Revisado", "Observado", "Revisar temática")
    assert C.status(group["id"])["mce"] == "Observado"

    backup = zipfile.ZipFile(io.BytesIO(C.backup()))
    assert "datos/atrio.sqlite3" in backup.namelist()
    assert not any("key" in name.lower() for name in backup.namelist())


def test_mce_export_regular_and_formula(isolated):
    group = C.groups()[0]
    group["tipo"] = "Regular"
    output = C.mce_excel(
        group,
        {"Nombre del curso": '=HYPERLINK("x")', "Duración": "60 HORAS"},
    )
    workbook = load_workbook(io.BytesIO(output))
    assert workbook.active.max_column == 20
    assert workbook.active["A2"].data_type != "f"
    assert C.status(group["id"])["mce"] == "Sin verificar"


def test_generation_preconditions(isolated):
    extension = C.groups()[0]
    with pytest.raises(ValueError, match="calendario"):
        C.generate(extension, 10, academic={})

    regular = dict(extension, tipo="Regular")
    with pytest.raises(ValueError, match="solo para extensión"):
        C.generate(regular, 10, academic={})


def test_generation_pipeline_uses_word_output_without_network(isolated, monkeypatch):
    """Prueba el registro de un PEA usando recursos ficticios y sin invocar Gemini."""
    group = C.groups()[0]
    C.set_setting("calendario_confirmado", True)

    # Se aíslan las validaciones/renderizado propios del motor institucional:
    # esta prueba comprueba el flujo de centro.generate, no certifica el formato PEA.
    monkeypatch.setattr(C.motor, "comprobar_plantilla", lambda _base: None)
    monkeypatch.setattr(C.motor, "revisar_calendario", lambda _course, _base: "COINCIDE: prueba sintética")
    monkeypatch.setattr(C.motor, "validator", lambda _content, _hours, _total: None)
    monkeypatch.setattr(C.motor.qa_v7, "validar_o_rechazar", lambda _content, _course, _hours: None)

    def create_synthetic_word(_course, _content, _base, output, _signature=False):
        document = Document()
        for index in range(28):
            table = document.add_table(rows=1, cols=1)
            table.cell(0, 0).text = "12 participantes" if index == 11 else f"Tabla {index + 1}"
        document.save(output)

    monkeypatch.setattr(C.motor, "crear_docx", create_synthetic_word)

    academic = {"unidades": [], "recursos": {}}
    output = C.generate(group, 12, academic=academic)

    assert output.is_file()
    generated = Document(output)
    assert len(generated.tables) == 28
    assert "12" in generated.tables[11].cell(0, 0).text
    assert C.status(group["id"])["doc"] == "Generado"

    artifact = C.artifacts(group["id"])[0]
    C.mark_reviewed(artifact["id"])
    assert C.status(group["id"])["doc"] == "Revisado"

@pytest.mark.parametrize("ruta_insegura", ["excel", "backup"])
def test_journal_con_rutas_fuera_de_directorios_permitidos_no_modifica_archivos(
    isolated, tmp_path, ruta_insegura
):
    """Las rutas externas a RES/ARCH se rechazan antes de leer o sustituir archivos."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    outside = tmp_path / "archivo_externo.xlsx"
    outside.write_bytes(b"CONTENIDO EXTERNO INTACTO")
    journal = C._ruta_journal_programacion()

    data = {
        "operation_id": f"ruta-externa-{ruta_insegura}",
        "commit_action": "Importación programación",
        "excel": str(resource.resolve()),
        "backup": str((C.ARCH / "respaldo_valido.xlsx").resolve()),
        "created": C.now(),
    }
    if ruta_insegura == "excel":
        data["excel"] = str(outside.resolve())
    else:
        data["backup"] = str(outside.resolve())
    C._escribir_journal_programacion(data)

    with pytest.raises(RuntimeError, match="rutas fuera de los directorios permitidos"):
        C.recuperar_programacion()

    assert resource.read_bytes() == original
    assert outside.read_bytes() == b"CONTENIDO EXTERNO INTACTO"
    assert journal.exists()

@pytest.mark.parametrize("campo_faltante", ["operation_id", "excel", "backup"])
def test_journal_incompleto_no_modifica_programacion(isolated, campo_faltante):
    """Un journal JSON válido pero incompleto se conserva y no altera la programación."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    journal = C._ruta_journal_programacion()
    data = {
        "operation_id": "journal-incompleto",
        "commit_action": "Importación programación",
        "excel": str(resource.resolve()),
        "backup": str((C.ARCH / "respaldo_ausente.xlsx").resolve()),
        "created": C.now(),
    }
    data.pop(campo_faltante)
    C._escribir_journal_programacion(data)

    with pytest.raises(RuntimeError, match="no pudo completar su recuperación"):
        C.recuperar_programacion()

    assert resource.read_bytes() == original
    assert journal.exists()


@pytest.mark.parametrize(
    ("campo", "valor", "mensaje"),
    [
        ("operation_id", "", "operation_id vacío o inválido"),
        ("commit_action", "Acción arbitraria", "commit_action no permitido"),
    ],
)
def test_journal_rechaza_identificador_o_accion_invalidos(isolated, campo, valor, mensaje):
    """No se acepta una confirmación SQLite basada en metadatos inválidos del journal."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    original = resource.read_bytes()
    backup = C.ARCH / "respaldo_validacion_journal.xlsx"
    shutil.copy2(resource, backup)
    journal = C._ruta_journal_programacion()
    data = {
        "operation_id": "journal-validacion",
        "commit_action": "Importación programación",
        "excel": str(resource.resolve()),
        "backup": str(backup.resolve()),
        "created": C.now(),
    }
    data[campo] = valor
    C._escribir_journal_programacion(data)

    with pytest.raises(RuntimeError, match=mensaje):
        C.recuperar_programacion()

    assert resource.read_bytes() == original
    assert journal.exists()


def test_excel_ausente_se_restaura_desde_respaldo(isolated):
    """Si no hubo confirmación y falta el Excel, la recuperación lo repone desde backup."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    backup = C.ARCH / "respaldo_programacion.xlsx"
    shutil.copy2(resource, backup)
    expected = backup.read_bytes()
    resource.unlink()
    journal = C._ruta_journal_programacion()
    C._escribir_journal_programacion({
        "operation_id": "excel-ausente-sin-confirmar",
        "commit_action": "Importación programación",
        "excel": str(resource.resolve()),
        "backup": str(backup.resolve()),
        "created": C.now(),
    })

    assert C.recuperar_programacion() is True
    assert resource.is_file()
    assert resource.read_bytes() == expected
    assert not journal.exists()

def test_excel_ausente_tras_confirmacion_conserva_journal(isolated):
    """No se declara recuperada una operación confirmada si desapareció su Excel."""
    resource = C.RES / "PROGRAMACION DE CURSOS.xlsx"
    backup = C.ARCH / "respaldo_programacion_confirmada.xlsx"
    shutil.copy2(resource, backup)
    journal = C._ruta_journal_programacion()
    operation_id = "excel-ausente-tras-confirmacion"
    C._escribir_journal_programacion({
        "operation_id": operation_id,
        "commit_action": "Importación programación",
        "excel": str(resource.resolve()),
        "backup": str(backup.resolve()),
        "created": C.now(),
    })
    with C.connect() as db:
        db.execute(
            "INSERT INTO events(at,action,payload) VALUES(?,?,?)",
            (C.now(), "Importación programación",
             json.dumps({"operation_id": operation_id}, ensure_ascii=False)),
        )
    resource.unlink()

    with pytest.raises(RuntimeError, match="Excel de programación no existe"):
        C.recuperar_programacion()

    assert not resource.exists()
    assert journal.exists()
