"""Pruebas de integración funcional de Fase 2 con Excel y SQLite ficticios.

Estas pruebas ejercitan centro.import_program() de extremo a extremo sin
consultar ni modificar recursos institucionales.
"""
import json

import pytest
from openpyxl import Workbook

import centro as C
import reprogramacion as R


def _write_programming_book(path, groups):
    workbook = Workbook()
    first = True
    for item in groups:
        if first:
            sheet = workbook.active
            first = False
        else:
            sheet = workbook.create_sheet()
        sheet.title = item["docente"]
        sheet.cell(1, 1, "23-INFO-2026")
        sheet.cell(1, 2, item.get("especialidad", "INFORMÁTICA"))

        row = item.get("fila", 15)
        values = {
            1: item.get("tipo", "Extensión"),
            2: item["curso"],
            4: item.get("participantes", 10),
            5: item.get("inicio", "2026-11-10"),
            6: item.get("fin", "2026-12-10"),
            7: item.get("duracion", 60),
            9: item.get("horario", "MARTES A SÁBADO 09:00 - 12:00"),
            10: "Aula ficticia",
        }
        for column, value in values.items():
            sheet.cell(row, column, value)

    workbook.save(path)
    workbook.close()


@pytest.fixture
def fase2(tmp_path, monkeypatch):
    paths = {
        "ROOT": tmp_path,
        "DATA": tmp_path / "datos",
        "RES": tmp_path / "datos" / "recursos",
        "OUT": tmp_path / "datos" / "salidas",
        "ARCH": tmp_path / "datos" / "versiones",
    }
    for name, path in paths.items():
        monkeypatch.setattr(C, name, path)
        path.mkdir(parents=True, exist_ok=True)
    return paths["RES"]


def _course(teacher, name="INFORMÁTICA BÁSICA", **overrides):
    result = {
        "docente": teacher,
        "curso": name,
        "especialidad": "INFORMÁTICA",
        "tipo": "Extensión",
        "inicio": "2026-11-10",
        "fin": "2026-12-10",
        "duracion": 60,
        "horario": "MARTES A SÁBADO 09:00 - 12:00",
        "fila": 15,
    }
    result.update(overrides)
    return result


def _all_groups():
    with C.connect() as db:
        rows = db.execute(
            "SELECT id, fingerprint, payload, active FROM groups ORDER BY rowkey, id"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "fingerprint": row["fingerprint"],
            "payload": json.loads(row["payload"]),
            "active": row["active"],
        }
        for row in rows
    ]


def test_cambio_de_docente_conserva_group_id_y_estado(fase2):
    original = fase2 / "programacion_inicial.xlsx"
    updated = fase2 / "programacion_docente_nuevo.xlsx"
    _write_programming_book(original, [_course("DOCENTE A")])
    C.import_program(original)

    before = C.groups()[0]
    C.update_status(before["id"], "PEA elaborado", "Autorizado", "Seguimiento ficticio")

    _write_programming_book(updated, [_course("DOCENTE B")])
    C.import_program(updated)

    after = C.groups()
    assert len(after) == 1
    assert after[0]["id"] == before["id"]
    assert after[0]["hoja"] == "DOCENTE B"
    assert after[0]["_atrio"]["requiere_revision_docente"] is True

    saved_status = C.status(before["id"])
    assert saved_status["doc"] == "PEA elaborado"
    assert saved_status["mce"] == "Autorizado"
    assert saved_status["note"] == "Seguimiento ficticio"


def test_cambio_de_nombre_crea_grupo_nuevo_y_conserva_pea_anterior(fase2):
    original = fase2 / "programacion_inicial.xlsx"
    renamed = fase2 / "programacion_nombre_nuevo.xlsx"
    _write_programming_book(original, [_course("DOCENTE A")])
    C.import_program(original)

    before = C.groups()[0]
    C.update_status(before["id"], "PEA elaborado", "Autorizado", "Antecedente ficticio")

    with C.connect() as db:
        db.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,0)",
            (
                "pea-historico-ficticio",
                before["id"],
                C.now(),
                "datos/salidas/pea-historico-ficticio.docx",
                "datos/salidas/pea-historico-ficticio/contenido.json",
                before["fingerprint"],
            ),
        )

    _write_programming_book(
        renamed,
        [_course("DOCENTE A", "INSTALACIONES ELÉCTRICAS INDUSTRIALES")],
    )
    C.import_program(renamed)

    after = C.groups()
    assert len(after) == 1
    new_group = after[0]
    assert new_group["id"] != before["id"]
    assert new_group["_atrio"]["requiere_pea_nuevo"] is True
    assert new_group["_atrio"]["posible_grupo_anterior"] == before["id"]

    all_groups = {item["id"]: item for item in _all_groups()}
    old_group = all_groups[before["id"]]
    assert old_group["active"] == 0
    assert old_group["payload"]["_atrio"]["estado_programacion"].startswith(
        "Sustituido por cambio de nombre"
    )
    assert old_group["payload"]["_atrio"]["sustituido_por_grupo"] == new_group["id"]

    with C.connect() as db:
        artifact = db.execute(
            "SELECT group_id, fingerprint FROM artifacts WHERE id=?",
            ("pea-historico-ficticio",),
        ).fetchone()
    assert artifact["group_id"] == before["id"]
    assert artifact["fingerprint"] == before["fingerprint"]
    assert C.status(before["id"])["doc"] == "PEA elaborado"


def test_coincidencia_ambigua_no_se_operativiza_ni_se_reprograma(fase2):
    original = fase2 / "programacion_dos_candidatos.xlsx"
    ambiguous = fase2 / "programacion_coincidencia_ambigua.xlsx"
    _write_programming_book(
        original,
        [_course("DOCENTE A"), _course("DOCENTE B")],
    )
    C.import_program(original)
    previous_ids = {group["id"] for group in C.groups()}
    assert len(previous_ids) == 2

    _write_programming_book(ambiguous, [_course("DOCENTE C", fila=20)])
    C.import_program(ambiguous)

    all_groups = _all_groups()
    new_groups = [
        item for item in all_groups
        if item["payload"]["hoja"] == "DOCENTE C"
    ]
    assert len(new_groups) == 1
    unresolved = new_groups[0]
    assert unresolved["active"] == 1
    assert unresolved["payload"]["_atrio"]["estado_programacion"] == "Revisar identidad"
    assert unresolved["payload"]["_atrio"]["incluido_en_ultima_actualizacion"] is True

    # Los dos candidatos originales permanecen guardados como pendientes.
    old_groups = [item for item in all_groups if item["id"] in previous_ids]
    assert len(old_groups) == 2
    assert all(item["active"] == 1 for item in old_groups)
    assert all(
        item["payload"]["_atrio"]["estado_programacion"].startswith(
            "Pendiente de reprogramación"
        )
        for item in old_groups
    )

    assert C.operational_groups() == []
    with pytest.raises(ValueError, match="identidad.*pendiente de revisión"):
        C.validate_group_current({
            "id": unresolved["id"],
            "fingerprint": unresolved["fingerprint"],
        })

    with pytest.raises(ValueError, match="no participa en la actualización"):
        R._planificar_cascada(
            C.groups(), unresolved["id"], __import__("datetime").date(2026, 12, 20), []
        )
