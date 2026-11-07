from datetime import date

from tablero_inicio import _resumen_cursos
from motor_pendientes import identificador_control_escolar


def test_panorama_cuenta_cursos_vigentes_por_iniciar_terminados_y_tipos():
    grupos = [
        {
            "id": "a",
            "tipo": "Extensión",
            "inicio": "2026-11-01",
            "fin": "2026-11-30",
        },
        {
            "id": "b",
            "tipo": "Repositorio",
            "inicio": "2026-11-10",
            "fin": "2026-12-10",
        },
        {
            "id": "c",
            "tipo": "Regular",
            "inicio": "2026-09-01",
            "fin": "2026-10-31",
        },
        {
            "id": "d",
            "tipo": "Extensión",
            "inicio": "2026-12-01",
            "fin": "2027-01-15",
        },
    ]

    resumen = _resumen_cursos(grupos, date(2026, 11, 6))

    assert resumen["total"] == 4
    assert resumen["vigentes"] == 1
    assert resumen["por_iniciar"] == 2
    assert resumen["terminados"] == 1
    assert len(resumen["tipos"]["Extensión"]) == 2
    assert len(resumen["tipos"]["Repositorio"]) == 1
    assert len(resumen["tipos"]["Regular"]) == 1
    assert resumen["por_tipo"]["Extensión"] == {
        "terminados": 0, "en_curso": 1, "por_iniciar": 1
    }
    assert resumen["por_tipo"]["Repositorio"] == {
        "terminados": 0, "en_curso": 0, "por_iniciar": 1
    }
    assert resumen["por_tipo"]["Regular"] == {
        "terminados": 1, "en_curso": 0, "por_iniciar": 0
    }


def test_demo_distingue_dos_cursos_por_iniciar_de_cero_en_curso():
    grupos = [
        {
            "id": "ext",
            "tipo": "Extensión",
            "inicio": "2026-11-10",
            "fin": "2026-12-10",
        },
        {
            "id": "rep",
            "tipo": "Repositorio",
            "inicio": "2026-11-17",
            "fin": "2026-12-17",
        },
        {
            "id": "reg",
            "tipo": "Regular",
            "inicio": "2026-10-01",
            "fin": "2026-10-30",
        },
    ]

    resumen = _resumen_cursos(grupos, date(2026, 11, 7))

    assert resumen["total"] == 3
    assert resumen["terminados"] == 1
    assert resumen["vigentes"] == 0
    assert resumen["por_iniciar"] == 2
    assert resumen["por_tipo"]["Extensión"]["por_iniciar"] == 1
    assert resumen["por_tipo"]["Repositorio"]["por_iniciar"] == 1
    assert resumen["por_tipo"]["Regular"]["terminados"] == 1


def test_identificador_control_escolar_coincide_con_conversion_de_hojas():
    grupo = {"id": "01234567-89ab-cdef-0123-456789abcdef"}
    esperado = str(int(grupo["id"].replace("-", "")[:13], 16))
    assert identificador_control_escolar(grupo) == esperado
