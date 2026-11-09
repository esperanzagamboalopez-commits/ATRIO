from datetime import date
from io import BytesIO

from openpyxl import load_workbook

import acm_asistencia as asistencia


def test_reconoce_dias_individuales_y_rangos():
    assert asistencia._dias_programados("lunes a viernes") == {0, 1, 2, 3, 4}
    assert asistencia._dias_programados("martes y jueves") == {1, 3}


def test_fechas_de_sesion_respeta_vigencia_y_dias_inhabiles():
    result = asistencia._fechas_sesion(
        {"inicio": "2026-11-02", "fin": "2026-11-13"},
        2026, 11, {0, 2, 4}, {date(2026, 11, 4)}
    )
    assert result == [
        date(2026, 11, 2), date(2026, 11, 6),
        date(2026, 11, 9), date(2026, 11, 11), date(2026, 11, 13),
    ]


def test_identificador_sigue_formato_de_vinculo_de_hojas():
    assert asistencia._identificador_hojas(
        {"id": "0123456789abc-def012345678"}
    ) == str(int("0123456789abc", 16))


def test_genera_excel_imprimible_con_alumnos_y_firmas():
    group = {
        "nombre": "Excel básico",
        "especialidad_programada": "Ofimática",
        "hoja": "Docente de prueba",
        "inicio": "2026-11-02",
        "fin": "2026-11-30",
        "horario": "lunes y miércoles 09:00 a 12:00",
        "duracion": 30,
        "aula": "Sede de prueba",
    }
    students = [
        {"id": "1001", "nombre": "Alumno Uno"},
        {"id": "1002", "nombre": "Alumno Dos"},
    ]
    raw = asistencia.crear_libro_asistencia(
        group, students, [date(2026, 11, 2), date(2026, 11, 4)],
        sede="Aula de prueba", institucion="Institución de prueba",
        cut_label="Corte de prueba",
    )
    wb = load_workbook(BytesIO(raw), data_only=True)
    ws = wb["Lista de asistencia"]
    values = [cell.value for row in ws.iter_rows() for cell in row if cell.value is not None]
    assert "ACCIONES MÓVILES DE CAPACITACIÓN · LISTA DE ASISTENCIA" in values
    assert "Alumno Uno" in values and "Alumno Dos" in values
    assert "02/11" in values and "04/11" in values
    assert ws.page_setup.fitToWidth == 1
    wb.close()
