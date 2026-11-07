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
