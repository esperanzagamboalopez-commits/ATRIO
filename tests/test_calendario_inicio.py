from datetime import date

import calendario as CAL


def test_eventos_de_fecha_identifica_actividad_y_vencimiento():
    fecha = date(2026, 11, 10)
    eventos = [
        {
            "id": 1, "titulo": "Actividad de ejemplo",
            "fecha_inicio": "2026-11-10", "fecha_fin": "2026-11-12",
            "fecha_limite": None,
        },
        {
            "id": 2, "titulo": "Vencimiento de ejemplo",
            "fecha_inicio": "2026-11-01", "fecha_fin": None,
            "fecha_limite": "2026-11-10",
        },
    ]

    resultado = CAL._eventos_de_fecha(fecha, eventos)

    assert [(tipo, evento["id"]) for tipo, evento in resultado] == [
        ("Actividad", 1),
        ("Fecha límite", 2),
    ]


def test_cursos_de_fecha_marca_inicio_y_termino_sin_crear_eventos():
    fecha = date(2026, 11, 10)
    cursos = [
        {
            "id": "grupo-demo-1", "nombre": "Curso uno",
            "hoja": "DOCENTE UNO", "inicio": "2026-11-10", "fin": "2026-11-20",
        },
        {
            "id": "grupo-demo-2", "curso": "Curso dos",
            "docente": "DOCENTE DOS", "inicio": "2026-11-01", "fin": "2026-11-10",
        },
    ]

    resultado = CAL._cursos_de_fecha(cursos, fecha)

    assert [(item["tipo"], item["nombre"]) for item in resultado] == [
        ("Inicio de curso", "Curso uno"),
        ("Término de curso", "Curso dos"),
    ]


def test_marcas_del_mes_combinan_agenda_y_fechas_de_cursos():
    eventos = [
        {
            "id": 1, "fecha_inicio": "2026-11-10",
            "fecha_fin": None, "fecha_limite": "2026-11-11",
        },
    ]
    cursos = [
        {"inicio": "2026-11-10", "fin": "2026-11-20"},
    ]

    marcas = CAL._marcas_inicio_mes(2026, 11, eventos, cursos)

    assert marcas[10].count("A") == 1
    assert marcas[10].count("C") == 1
    assert marcas[11].count("L") == 1
    assert marcas[20].count("T") == 1


def test_agenda_se_guarda_en_la_base_configurada_y_aislada(tmp_path, monkeypatch):
    ruta_temporal = tmp_path / "calendario_demo.sqlite3"
    monkeypatch.setattr(CAL, "DB_PATH", ruta_temporal)

    categorias = {item["nombre"]: item["id"] for item in CAL.obtener_categorias()}
    CAL.guardar_evento({
        "titulo": "Actividad temporal",
        "categoria_id": categorias["Notas personales"],
        "tipo": "Tarea",
        "prioridad": "Media",
        "fecha_inicio": date(2026, 11, 10),
        "todo_el_dia": True,
        "modulo_vinculado": "Ninguno",
        "recordatorio": "Ninguno",
        "repeticion": "No se repite",
    })

    resultado = CAL.obtener_eventos(2026, 11)

    assert ruta_temporal.is_file()
    assert [evento["titulo"] for evento in resultado] == ["Actividad temporal"]
    assert CAL.DB_PATH == ruta_temporal


def test_actividad_con_limite_el_mismo_dia_aparece_una_sola_vez():
    fecha = date(2026, 11, 10)
    eventos = [{
        "id": 7, "titulo": "Revisión",
        "fecha_inicio": "2026-11-10", "fecha_fin": None,
        "fecha_limite": "2026-11-10",
    }]

    resultado = CAL._eventos_de_fecha(fecha, eventos)

    assert len(resultado) == 1
    assert resultado[0][0] == "Actividad · fecha límite"
    assert resultado[0][1]["id"] == 7



def test_marcas_del_inicio_incluyen_fechas_objetivo_del_motor_de_pendientes():
    tareas = [
        {
            "id": "t-1",
            "proceso": "Elaboración de PEAs",
            "fecha": "2026-11-05",
            "fuente": "Programación",
        },
        {
            "id": "t-2",
            "proceso": "Mi Calendario",
            "fecha": "2026-11-06",
            "fuente": "Mi Calendario",
        },
    ]

    marcas = CAL._marcas_inicio_mes(2026, 11, [], [], tareas=tareas)

    assert marcas[5].count("L") == 1
    assert 6 not in marcas


def test_tareas_de_fecha_no_duplica_actividades_personales_del_calendario():
    from datetime import date

    tareas = [
        {
            "proceso": "Elaboración de PEAs",
            "fuente": "Programación",
            "fecha": "2026-11-05",
        },
        {
            "proceso": "Mi Calendario",
            "fuente": "Mi Calendario",
            "fecha": "2026-11-05",
        },
    ]

    resultado = CAL._tareas_de_fecha(tareas, date(2026, 11, 5))

    assert len(resultado) == 1
    assert resultado[0]["proceso"] == "Elaboración de PEAs"
