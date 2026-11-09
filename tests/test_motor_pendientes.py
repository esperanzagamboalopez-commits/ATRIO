from datetime import date

from motor_pendientes import (
    construir_pendientes,
    filtrar_pendientes,
    primer_dia_trabajo_personal,
    prioridades_del_dia,
)


def grupo(**extra):
    base = {
        "id": "g-1",
        "nombre": "Informática básica",
        "hoja": "DOCENTE UNO",
        "tipo": "Extensión",
        "inicio": "2026-11-10",
        "fin": "2026-12-10",
    }
    base.update(extra)
    return base


def test_primer_dia_personal_noviembre_2026_es_martes_3():
    assert primer_dia_trabajo_personal(2026, 11) == date(2026, 11, 3)


def test_primer_dia_personal_respeta_dias_inhabiles():
    assert primer_dia_trabajo_personal(
        2026, 12, [date(2026, 12, 1)]
    ) == date(2026, 12, 2)


def test_pea_se_programa_cinco_dias_antes_del_inicio():
    tareas = construir_pendientes(
        [grupo()], date(2026, 11, 6),
        estados={"g-1": {"doc": "Sin PEA", "mce": "Sin verificar"}},
    )
    pea = next(t for t in tareas if t["proceso"] == "Elaboración de PEAs")
    assert pea["fecha"] == "2026-11-05"
    assert pea["estado"] == "Vencido"
    assert "cinco días" in pea["motivo"]


def test_sin_verificar_no_se_convierte_en_atraso():
    tareas = construir_pendientes(
        [grupo()], date(2026, 11, 6),
        estados={"g-1": {"doc": "Sin verificar", "mce": "Sin verificar"}},
    )
    revisar = [t for t in tareas if t["proceso"] == "Por verificar"]
    assert revisar
    assert all(t["estado"] == "Por verificar" for t in revisar)
    assert not any(t["estado"] == "Vencido" for t in revisar)


def test_regular_tiene_alta_mce_separada_de_pea():
    regular = grupo(tipo="Regular")
    tareas = construir_pendientes(
        [regular], date(2026, 11, 6),
        estados={"g-1": {"doc": "Sin verificar", "mce": "No subido"}},
    )
    assert any(t["proceso"] == "Altas de cursos regulares en MCE" for t in tareas)
    assert not any(t["proceso"] == "Elaboración de PEAs" for t in tareas)


def test_lista_entregada_no_se_vuelve_a_generar_y_usa_el_primer_dia_personal():
    tareas = construir_pendientes(
        [grupo()], date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Subido"}},
        estados_control_escolar={"g-1|2026-11|lists": "Entregada"},
    )
    assert not any(t["proceso"] == "Listas de asistencia" and t["fecha"] == "2026-11-03" for t in tareas)


def test_lista_mensual_pendiente_se_ordena_en_el_primer_dia_personal():
    tareas = construir_pendientes(
        [grupo()], date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Subido"}},
    )
    lista = next(t for t in tareas if t["proceso"] == "Listas de asistencia")
    assert lista["fecha"] == "2026-11-03"
    assert lista["estado"] == "Vencido"


def test_credenciales_se_deben_atender_en_siete_dias_desde_inicio():
    tareas = construir_pendientes(
        [grupo(inicio="2026-11-03", fin="2026-11-30")], date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Subido"}},
        alumnos_por_grupo={"g-1": 8},
    )
    cred = next(t for t in tareas if t["proceso"] == "Credenciales")
    assert cred["fecha"] == "2026-11-10"
    assert "8 alumno" in cred["motivo"]


def test_credenciales_elaboradas_siguen_abiertas_hasta_evidencia_firmada():
    tareas = construir_pendientes(
        [grupo(inicio="2026-11-03", fin="2026-11-30")], date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Subido"}},
        estados_credenciales={"g-1": {"estado": "Elaboradas"}},
        alumnos_por_grupo={"g-1": 8},
    )
    cred = next(t for t in tareas if t["proceso"] == "Credenciales")
    assert "recuperar las firmas" in cred["accion"]


def test_credenciales_documentadas_salen_de_pendientes():
    tareas = construir_pendientes(
        [grupo(inicio="2026-11-03", fin="2026-11-30")], date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Subido"}},
        estados_credenciales={"g-1": {"estado": "Entrega documentada"}},
        alumnos_por_grupo={"g-1": 8},
    )
    assert not any(t["proceso"] == "Credenciales" for t in tareas)


def test_curso_acm_genera_aviso_preventivo_sin_atraso():
    tareas = construir_pendientes(
        [grupo(nombre="ACM · Informática básica", inicio="2026-11-16")],
        date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Subido"}},
    )
    aviso = next(t for t in tareas if t["proceso"] == "Cursos ACM")
    assert aviso["estado"] == "Aviso"
    assert aviso["fecha"] == "2026-11-16"


def test_filtros_hoy_manana_y_fecha_personal():
    hoy = date(2026, 11, 6)
    tareas = [
        {"proceso": "PEA", "responsable": "Me corresponde", "fecha": "2026-11-06"},
        {"proceso": "Listas", "responsable": "Me corresponde", "fecha": "2026-11-07"},
    ]
    assert len(filtrar_pendientes(tareas, hoy, "Hoy")) == 1
    assert len(filtrar_pendientes(tareas, hoy, "Mañana")) == 1
    assert len(filtrar_pendientes(tareas, hoy, "Fecha", fecha_personal=date(2026, 11, 7))) == 1


def test_prioridades_del_dia_prefiere_plazos_confirmados_antes_que_bloqueos():
    tareas = [
        {"id": "a", "estado": "Pendiente", "prioridad": "Alta", "fecha": "2026-11-06"},
        {"id": "b", "estado": "Bloqueado", "prioridad": "Alta", "fecha": "2026-11-09"},
        {"id": "c", "estado": "Vencido", "prioridad": "Alta", "fecha": "2026-11-01"},
    ]
    assert [x["id"] for x in prioridades_del_dia(tareas, date(2026, 11, 6))] == ["c", "b", "a"]



def test_repositorio_genera_tarea_de_adaptacion_no_de_elaboracion_desde_cero():
    tareas = construir_pendientes(
        [grupo(tipo="Repositorio")],
        date(2026, 11, 6),
        estados={"g-1": {"doc": "Sin PEA", "mce": "Sin verificar"}},
    )
    pea = next(t for t in tareas if t["proceso"] == "Preparación de PEA de Repositorio")
    assert "Descargar y adaptar" in pea["accion"]
    assert not any(t["proceso"] == "Elaboración de PEAs" for t in tareas)


def test_carga_de_pea_al_mce_no_inventa_fecha_limite_oficial():
    tareas = construir_pendientes(
        [grupo(inicio="2026-12-10")],
        date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "No subido"}},
    )
    carga = next(t for t in tareas if t["proceso"] == "Subir PEAs al MCE")
    assert carga["fecha"] == ""
    assert carga["estado"] == "Pendiente"
    assert carga["prioridad"] in {"Alta", "Media"}
    assert "MCE" in carga["accion"]


def test_tarea_de_credenciales_sin_padron_confirmado_es_solo_verificacion():
    tareas = construir_pendientes(
        [grupo(inicio="2026-11-03", fin="2026-11-30")],
        date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Subido"}},
    )
    cred = next(t for t in tareas if t["proceso"] == "Credenciales")
    assert cred["estado"] == "Por verificar"
    assert cred["responsable"] == "Por verificar"



def test_pea_listo_con_mce_sin_verificar_permanece_en_proceso_mce():
    tareas = construir_pendientes(
        [grupo(inicio="2026-12-10")],
        date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Sin verificar"}},
    )
    carga = next(t for t in tareas if t["proceso"] == "Subir PEAs al MCE")
    assert carga["estado"] == "Por verificar"
    assert carga["responsable"] == "Por verificar"
    assert "verificar primero" in carga["accion"]


def test_alta_regular_sin_verificar_permanece_en_seccion_de_regulares():
    tareas = construir_pendientes(
        [grupo(tipo="Regular", inicio="2026-11-20")],
        date(2026, 11, 6),
        estados={"g-1": {"doc": "Sin verificar", "mce": "Sin verificar"}},
    )
    alta = next(t for t in tareas if t["proceso"] == "Altas de cursos regulares en MCE")
    assert alta["estado"] == "Por verificar"
    assert alta["responsable"] == "Por verificar"


def test_acreditacion_sin_estado_confirmado_no_se_marca_atrasada():
    tareas = construir_pendientes(
        [grupo(inicio="2026-10-01", fin="2026-11-10")],
        date(2026, 11, 6),
        estados={"g-1": {"doc": "Generado", "mce": "Subido"}},
    )
    acreditacion = next(t for t in tareas if t["proceso"] == "Acreditaciones")
    assert acreditacion["estado"] == "Por verificar"
    assert acreditacion["responsable"] == "Por verificar"



def test_periodo_sisae_se_asigna_solo_a_grupos_vinculados_y_filtra():
    tareas = construir_pendientes(
        [grupo()],
        date(2026, 11, 6),
        estados={"g-1": {"doc": "Sin PEA", "mce": "Sin verificar"}},
        periodos_sisae={"g-1": "2"},
        eventos_calendario=[{
            "id": 88,
            "titulo": "Entrega de informe personal",
            "fecha_inicio": "2026-11-06",
            "estado": "Pendiente",
            "prioridad": "Media",
            "cat_nombre": "Notas personales",
        }],
    )

    curso = next(t for t in tareas if t.get("grupo_id") == "g-1")
    personal = next(t for t in tareas if t.get("proceso") == "Mi Calendario")

    assert curso["periodo_sisae"] == "P2"
    assert personal["periodo_sisae"] == ""
    filtrados = filtrar_pendientes(
        tareas,
        date(2026, 11, 6),
        periodo_sisae="P2",
    )
    assert filtrados
    assert all(t["periodo_sisae"] == "P2" for t in filtrados)
