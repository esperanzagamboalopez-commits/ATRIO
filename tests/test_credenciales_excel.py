from io import BytesIO

from openpyxl import load_workbook

import credenciales


def test_excel_firmas_incluye_curso_alumnos_y_espacio_de_firma():
    rows = [
        {
            "NOMBRE": "García López Ana",
            "CURP": "NO DEBE APARECER",
            "NCONTROL": "|12345|",
        },
        {
            "NOMBRE": "Pérez Ruiz Luis",
            "CURP": "TAMPOCO DEBE APARECER",
            "NCONTROL": "|67890|",
        },
    ]

    raw = credenciales.excel_firmas(
        rows,
        curso="Informática básica",
        docente="Docente de prueba",
        inicio="2026-11-10",
        termino="2026-12-10",
        fecha_elaboracion="2026-11-06",
    )
    wb = load_workbook(BytesIO(raw), data_only=True)
    ws = wb["Firmas credenciales"]

    assert ws["A2"].value == "RELACIÓN DE CREDENCIALES ELABORADAS"
    assert ws["B4"].value == "Informática básica"
    assert ws["B5"].value == "Docente de prueba"
    assert ws["B9"].value == "12345"
    assert ws["C9"].value == "García López Ana"
    assert ws["D9"].value is None
    assert ws["B10"].value == "67890"
    assert ws["C10"].value == "Pérez Ruiz Luis"
    assert ws["D10"].value is None
    assert ws.print_area == "'Firmas credenciales'!$A$1:$D$10"
    assert ws.page_setup.orientation == "landscape"
    assert ws.page_setup.fitToWidth == 1
    assert ws.row_dimensions[9].height >= 32
    valores = " ".join(str(cell.value or "") for row in ws.iter_rows() for cell in row)
    assert "NO DEBE APARECER" not in valores
    assert "TAMPOCO DEBE APARECER" not in valores


def test_excel_firmas_rechaza_lista_vacia():
    try:
        credenciales.excel_firmas([], curso="Curso de prueba")
    except ValueError as exc:
        assert "No hay alumnos seleccionados" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError para una lista vacía.")
