# -*- coding: utf-8 -*-
"""Motor determinista de seguimiento para ATRIO.

No escribe en bases de datos ni modifica fechas oficiales. Recibe estados y
registros como argumentos para que la misma lógica alimente Inicio y Pendientes.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta


CERRADOS_CALENDARIO = {"completada", "completado", "cancelado", "eliminado"}
CERRADO_CREDENCIALES = {"entrega documentada", "entregadas"}
CERRADO_ACREDITACION = {"resultados capturados"}
TIPOS_PEA = {"extension", "repositorio"}
ESTADOS_PEA_LISTO = {"generado", "revisado", "aprobado", "validado"}
ESTADOS_ACREDITACION_EN_CURSO = {
    "por imprimir", "por entregar", "entregada al docente",
    "recibida del docente", "revisada",
}


def como_fecha(value):
    """Convierte valores ISO/fecha a date; devuelve None si no son válidos."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    texto = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto[:10], fmt).date()
        except ValueError:
            pass
    return None


def primer_dia_trabajo_personal(anio, mes, dias_inhabiles=()):
    """Primer martes-viernes del mes que no esté marcado como inhábil."""
    excluidos = {como_fecha(x) for x in (dias_inhabiles or ())}
    ultimo = calendar.monthrange(int(anio), int(mes))[1]
    for dia in range(1, ultimo + 1):
        candidata = date(int(anio), int(mes), dia)
        if candidata.weekday() in (1, 2, 3, 4) and candidata not in excluidos:
            return candidata
    return None


def _meses_entre(inicio, fin):
    actual = date(inicio.year, inicio.month, 1)
    limite = date(fin.year, fin.month, 1)
    while actual <= limite:
        yield actual.year, actual.month
        if actual.month == 12:
            actual = date(actual.year + 1, 1, 1)
        else:
            actual = date(actual.year, actual.month + 1, 1)


def identificador_control_escolar(grupo):
    """Reproduce el identificador estable que usa hojas.snapshot para su UI."""
    raw = str(grupo.get("id", "")).replace("-", "")
    try:
        return str(int(raw[:13], 16))
    except (TypeError, ValueError):
        return str(grupo.get("id", ""))


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _es_acm(grupo):
    campos = ("modalidad", "subtipo", "tipo_accion", "observaciones", "aula", "nombre", "poblacion", "especialidad_programada")
    texto = " ".join(str(grupo.get(k, "") or "") for k in campos).casefold()
    return bool(re.search(r"(?<![a-z])acm(?![a-z])|acci[oó]n(?:es)? m[oó]vil(?:es)?", texto))


def _estado_por_fecha(fecha_objetivo, hoy, verificacion=False):
    if verificacion:
        return "Por verificar"
    if fecha_objetivo and fecha_objetivo < hoy:
        return "Vencido"
    return "Pendiente"


def _crear(
    *,
    proceso, grupo, fecha_objetivo, motivo, accion, modulo,
    hoy, certeza="Confirmado", estado_forzado=None, prioridad="Normal",
    responsable="Me corresponde", fuente="Programación", sufijo="",
):
    gid = str(grupo.get("id", ""))
    fecha_iso = fecha_objetivo.isoformat() if fecha_objetivo else ""
    estado = estado_forzado or _estado_por_fecha(
        fecha_objetivo, hoy, verificacion=(certeza == "Por verificar")
    )
    if certeza == "Por verificar" and responsable == "Me corresponde":
        responsable = "Por verificar"
    if estado == "Bloqueado":
        prioridad = "Alta"
    elif estado == "Vencido":
        prioridad = "Alta"
    elif fecha_objetivo and (fecha_objetivo - hoy).days <= 2 and prioridad == "Normal":
        prioridad = "Alta"
    elif fecha_objetivo and (fecha_objetivo - hoy).days <= 7 and prioridad == "Normal":
        prioridad = "Media"
    return {
        "id": "|".join((proceso, gid, sufijo or fecha_iso or "sin-fecha")),
        "proceso": proceso,
        "grupo_id": gid,
        "curso": str(grupo.get("nombre") or grupo.get("curso") or "Actividad"),
        "docente": str(grupo.get("hoja") or grupo.get("docente") or ""),
        "tipo_curso": str(grupo.get("tipo") or ""),
        "fecha": fecha_iso,
        "motivo": motivo,
        "accion": accion,
        "modulo": modulo,
        "estado": estado,
        "prioridad": prioridad,
        "responsable": responsable,
        "fuente": fuente,
        "certeza": certeza,
    }


def construir_pendientes(
    grupos,
    hoy,
    *,
    estados=None,
    estados_control_escolar=None,
    estados_credenciales=None,
    eventos_calendario=(),
    dias_inhabiles=(),
    alumnos_por_grupo=None,
    anticipacion_acm=10,
):
    """Construye tareas confirmadas y verificaciones sin alterar datos.

    estados usa C.status por grupo. estados_control_escolar conserva las claves
    id|AAAA-MM|lists y id|course|ends del módulo Control Escolar.
    estados_credenciales usa el grupo ATRIO como clave.
    """
    hoy = como_fecha(hoy) or date.today()
    estados = estados or {}
    school = estados_control_escolar or {}
    credenciales = estados_credenciales or {}
    alumnos = alumnos_por_grupo or {}
    inh = {como_fecha(x) for x in (dias_inhabiles or ())}
    tareas = []
    vistos = set()

    def agregar(item):
        if item["id"] not in vistos:
            vistos.add(item["id"])
            tareas.append(item)

    for g in grupos or ():
        inicio = como_fecha(g.get("inicio"))
        fin = como_fecha(g.get("fin"))
        gid = str(g.get("id", ""))
        control_id = identificador_control_escolar(g)
        if not inicio or not fin or not gid or fin < inicio:
            continue
        status = estados.get(gid) or {}
        doc = _norm(status.get("doc"))
        mce = _norm(status.get("mce"))
        tipo = _norm(g.get("tipo"))

        # 1. PEA: debe estar listo, como mínimo, cinco días antes del inicio.
        if tipo in TIPOS_PEA:
            fecha_pea = inicio - timedelta(days=5)
            if doc in {"sin pea", "no generado"}:
                es_repositorio = tipo == "repositorio"
                agregar(_crear(
                    proceso=(
                        "Preparación de PEA de Repositorio"
                        if es_repositorio else "Elaboración de PEAs"
                    ),
                    grupo=g,
                    fecha_objetivo=fecha_pea,
                    motivo=f"El curso inicia el {inicio:%d/%m/%Y}; el PEA debe estar listo con al menos cinco días de anticipación.",
                    accion=(
                        "Descargar y adaptar el PEA del repositorio institucional; actualizar únicamente los datos autorizados del grupo."
                        if es_repositorio else
                        "Elaborar el PEA del nombre de curso vigente."
                    ),
                    modulo="Preparar PEA", hoy=hoy, prioridad="Alta",
                    sufijo="preparar-pea-repositorio" if es_repositorio else "elaboracion-pea",
                ))
            elif doc in {"sin verificar", ""} and inicio <= hoy + timedelta(days=15):
                agregar(_crear(
                    proceso="Por verificar", grupo=g,
                    fecha_objetivo=fecha_pea,
                    motivo="El estado del PEA no está confirmado; ATRIO no lo considera un atraso.",
                    accion="Verificar el PEA en Mis PEA o en el expediente del curso.",
                    modulo="Mis PEA", hoy=hoy, certeza="Por verificar",
                    sufijo="verificar-pea",
                ))

            if doc in ESTADOS_PEA_LISTO and mce == "no subido":
                agregar(_crear(
                    proceso="Subir PEAs al MCE", grupo=g,
                    fecha_objetivo=None,
                    motivo="El PEA ya está elaborado/revisado y todavía no aparece como subido al MCE.",
                    accion="Subir el PEA y registrar el estado real del envío.",
                    modulo="Seguimiento y MCE", hoy=hoy, prioridad="Alta",
                    sufijo="subir-pea",
                ))
            elif doc in ESTADOS_PEA_LISTO and mce == "observado":
                agregar(_crear(
                    proceso="Subir PEAs al MCE", grupo=g,
                    fecha_objetivo=None,
                    motivo="El PEA tiene observaciones registradas y necesita corrección antes de continuar.",
                    accion="Revisar y atender las observaciones del MCE.",
                    modulo="Seguimiento y MCE", hoy=hoy, estado_forzado="Bloqueado",
                    sufijo="pea-observado",
                ))
            elif doc in ESTADOS_PEA_LISTO and mce in {"sin verificar", ""}:
                agregar(_crear(
                    proceso="Por verificar", grupo=g,
                    fecha_objetivo=None,
                    motivo="El PEA está listo, pero el estado de su carga al MCE no está confirmado.",
                    accion="Comprobar el estado de carga antes de considerarlo pendiente.",
                    modulo="Seguimiento y MCE", hoy=hoy, certeza="Por verificar",
                    sufijo="verificar-carga-pea",
                ))

        # 2. Cursos regulares: alta en MCE separada de la carga de PEAs.
        if tipo == "regular":
            if mce == "no subido":
                agregar(_crear(
                    proceso="Altas de cursos regulares en MCE", grupo=g,
                    fecha_objetivo=inicio,
                    motivo="El curso regular no aparece como dado de alta en el MCE.",
                    accion="Registrar el curso regular en el MCE antes de su inicio.",
                    modulo="Seguimiento y MCE", hoy=hoy, prioridad="Alta",
                    sufijo="alta-regular-mce",
                ))
            elif mce in {"sin verificar", ""} and inicio <= hoy + timedelta(days=20):
                agregar(_crear(
                    proceso="Por verificar", grupo=g,
                    fecha_objetivo=inicio,
                    motivo="No hay confirmación del alta de este curso regular en el MCE.",
                    accion="Verificar el alta; no se marca como atraso mientras siga sin confirmar.",
                    modulo="Seguimiento y MCE", hoy=hoy, certeza="Por verificar",
                    sufijo="verificar-regular-mce",
                ))

        # 3. Listas: todos los meses en que el curso está activo; jornada personal mar-vie.
        for anio, mes in _meses_entre(inicio, fin):
            primero = date(anio, mes, 1)
            ultimo = date(anio, mes, calendar.monthrange(anio, mes)[1])
            if inicio > ultimo or fin < primero:
                continue
            clave = f"{control_id}|{anio:04d}-{mes:02d}|lists"
            estado_lista = _norm(school.get(clave))
            if estado_lista == "entregada":
                continue
            limite = primer_dia_trabajo_personal(anio, mes, inh)
            if limite is None:
                continue
            agregar(_crear(
                proceso="Listas de asistencia", grupo=g,
                fecha_objetivo=limite,
                motivo=f"El curso tiene actividad durante {calendar.month_name[mes].capitalize()} y requiere su lista de asistencia.",
                accion=f"Entregar la lista del mes a partir del primer día de trabajo personal ({limite:%d/%m/%Y}).",
                modulo="Control escolar", hoy=hoy,
                prioridad="Alta" if limite <= hoy + timedelta(days=2) else "Normal",
                fuente="Control escolar", sufijo=f"lista-{anio:04d}-{mes:02d}",
            ))

        # 4. Acreditación: distinta del término del curso y del cierre de constancias.
        clave_acred = f"{control_id}|course|ends"
        estado_acred = _norm(school.get(clave_acred))
        if estado_acred not in CERRADO_ACREDITACION:
            if estado_acred in ESTADOS_ACREDITACION_EN_CURSO:
                if fin <= hoy + timedelta(days=14):
                    esperando = estado_acred == "entregada al docente"
                    agregar(_crear(
                        proceso="Acreditaciones", grupo=g,
                        fecha_objetivo=fin,
                        motivo=(
                            "La acreditación ya se entregó al docente y está pendiente su devolución."
                            if esperando else
                            f"El curso termina el {fin:%d/%m/%Y}; la acreditación todavía no concluye su recorrido."
                        ),
                        accion=(
                            "Dar seguimiento a la devolución de la acreditación."
                            if esperando else
                            "Continuar el trámite de acreditación y registrar el siguiente estado."
                        ),
                        modulo="Control escolar", hoy=hoy,
                        prioridad="Alta" if fin <= hoy + timedelta(days=3) else "Normal",
                        responsable="Esperando respuesta" if esperando else "Me corresponde",
                        estado_forzado="En espera" if esperando else None,
                        fuente="Control escolar", sufijo="acreditacion",
                    ))
            elif estado_acred in {"sin verificar", ""} and fin <= hoy + timedelta(days=10):
                agregar(_crear(
                    proceso="Por verificar", grupo=g,
                    fecha_objetivo=fin,
                    motivo="El curso se aproxima a su término o ya terminó, pero la acreditación no tiene estado confirmado.",
                    accion="Verificar el estado real de la acreditación en Control escolar.",
                    modulo="Control escolar", hoy=hoy, certeza="Por verificar",
                    fuente="Control escolar", sufijo="verificar-acreditacion",
                ))

        # 5. Credenciales: una semana máxima desde el inicio, con evidencia firmada.
        registro_cred = credenciales.get(control_id) or {}
        estado_cred = _norm(registro_cred.get("estado") or registro_cred.get("status"))
        limite_cred = inicio + timedelta(days=7)
        cantidad_alumnos = alumnos.get(control_id)
        if estado_cred == "elaboradas" and hoy <= limite_cred:
            agregar(_crear(
                proceso="Credenciales", grupo=g,
                fecha_objetivo=limite_cred,
                motivo="Las credenciales ya están elaboradas; falta la entrega respaldada por la relación de firmas.",
                accion="Entregar las credenciales, recuperar las firmas y registrar la evidencia.",
                modulo="Control escolar", hoy=hoy, prioridad="Alta",
                fuente="Control escolar", sufijo="entregar-credenciales",
            ))
        elif estado_cred not in CERRADO_CREDENCIALES and hoy >= inicio and hoy <= limite_cred:
            if cantidad_alumnos is None:
                agregar(_crear(
                    proceso="Credenciales", grupo=g,
                    fecha_objetivo=limite_cred,
                    motivo="El curso ya inició, pero no hay una vinculación confirmada de alumnos en SISAE para elaborar las credenciales.",
                    accion="Verificar la vinculación del grupo y su padrón en Control escolar.",
                    modulo="Control escolar", hoy=hoy, certeza="Por verificar",
                    fuente="Control escolar", sufijo="verificar-padron-credenciales",
                ))
            elif cantidad_alumnos > 0:
                agregar(_crear(
                    proceso="Credenciales", grupo=g,
                    fecha_objetivo=limite_cred,
                    motivo=f"Hay {cantidad_alumnos} alumno(s) vinculados; las credenciales aún no están registradas como elaboradas.",
                    accion="Generar las credenciales en PowerPoint y marcarlas como elaboradas.",
                    modulo="Control escolar", hoy=hoy, prioridad="Alta",
                    fuente="Control escolar", sufijo="elaborar-credenciales",
                ))
        elif estado_cred not in CERRADO_CREDENCIALES and hoy > limite_cred and hoy >= inicio:
            if cantidad_alumnos is None:
                agregar(_crear(
                    proceso="Credenciales", grupo=g,
                    fecha_objetivo=limite_cred,
                    motivo="Se rebasó la primera semana, pero no existe vínculo confirmado con el padrón SISAE para determinar el lote.",
                    accion="Verificar el padrón y el estado de entrega antes de registrar un atraso.",
                    modulo="Control escolar", hoy=hoy, certeza="Por verificar",
                    fuente="Control escolar", sufijo="verificar-credenciales-vencidas",
                ))
            elif cantidad_alumnos > 0:
                motivo = (
                    "Las credenciales están elaboradas, pero no se ha documentado su entrega y la primera semana ya concluyó."
                    if estado_cred == "elaboradas" else
                    "Se rebasó la primera semana desde el inicio y no está documentada la elaboración/entrega de credenciales."
                )
                agregar(_crear(
                    proceso="Credenciales", grupo=g,
                    fecha_objetivo=limite_cred,
                    motivo=motivo,
                    accion="Regularizar la entrega, recuperar firmas y registrar la evidencia.",
                    modulo="Control escolar", hoy=hoy, prioridad="Alta",
                    fuente="Control escolar", sufijo="credenciales-vencidas",
                ))

        # 6. Cursos ACM: aviso preventivo, no fecha oficial ni atraso.
        if _es_acm(g):
            inicio_aviso = inicio - timedelta(days=max(1, int(anticipacion_acm)))
            if inicio_aviso <= hoy <= inicio:
                agregar(_crear(
                    proceso="Cursos ACM", grupo=g,
                    fecha_objetivo=inicio,
                    motivo=f"Curso identificado como ACM; inicia el {inicio:%d/%m/%Y}.",
                    accion="Revisar el oficio, la sede y la preparación del curso en Acciones Móviles.",
                    modulo="Acciones Móviles", hoy=hoy, certeza="Aviso",
                    estado_forzado="Aviso", prioridad="Media",
                    fuente="Programación", sufijo="aviso-acm",
                ))

    # 7. Agenda personal: reuniones, entregas y compromisos registrados en Mi Calendario.
    for ev in eventos_calendario or ():
        estado = _norm(ev.get("estado") or "pendiente")
        if estado in CERRADOS_CALENDARIO:
            continue
        fecha_ref = (
            como_fecha(ev.get("fecha_limite"))
            or como_fecha(ev.get("fecha_fin"))
            or como_fecha(ev.get("fecha_inicio"))
        )
        if not fecha_ref:
            continue
        categoria = str(ev.get("cat_nombre") or "Mi Calendario")
        responsable = str(ev.get("responsable") or "").strip() or "Me corresponde"
        prioridad_ev = _norm(ev.get("prioridad") or "media")
        prioridad = "Alta" if prioridad_ev == "alta" else "Media" if prioridad_ev == "media" else "Normal"
        agregar({
            "id": f"Mi Calendario|{ev.get('id', '')}",
            "proceso": "Mi Calendario",
            "grupo_id": "",
            "curso": str(ev.get("titulo") or "Actividad personal"),
            "docente": "",
            "tipo_curso": "",
            "fecha": fecha_ref.isoformat(),
            "motivo": str(ev.get("descripcion") or categoria),
            "accion": "Atender el compromiso registrado en Mi Calendario.",
            "modulo": "Mi Calendario",
            "estado": "Vencido" if fecha_ref < hoy else "Pendiente",
            "prioridad": prioridad,
            "responsable": responsable,
            "fuente": "Mi Calendario",
            "certeza": "Confirmado",
        })

    orden_estado = {"Bloqueado": 0, "Vencido": 1, "Pendiente": 2, "Aviso": 3, "En espera": 4, "Por verificar": 5}
    orden_prioridad = {"Alta": 0, "Media": 1, "Normal": 2}
    tareas.sort(key=lambda x: (
        orden_estado.get(x["estado"], 5),
        orden_prioridad.get(x["prioridad"], 3),
        x["fecha"] or "9999-12-31",
        x["proceso"],
        x["curso"],
    ))
    return tareas


def filtrar_pendientes(tareas, hoy, periodo="Todos", proceso="Todos", responsable="Todos", fecha_personal=None):
    hoy = como_fecha(hoy) or date.today()
    manana = hoy + timedelta(days=1)
    fin_7 = hoy + timedelta(days=7)
    fin_mes = date(hoy.year, hoy.month, calendar.monthrange(hoy.year, hoy.month)[1])
    salida = []
    for tarea in tareas:
        f = como_fecha(tarea.get("fecha"))
        if periodo == "Hoy" and (not f or f > hoy):
            continue
        if periodo == "Mañana" and f != manana:
            continue
        if periodo == "7 días" and (not f or f > fin_7):
            continue
        if periodo == "Este mes" and (not f or f > fin_mes):
            continue
        if periodo == "Fecha" and f != como_fecha(fecha_personal):
            continue
        if proceso != "Todos" and tarea.get("proceso") != proceso:
            continue
        if responsable != "Todos" and tarea.get("responsable") != responsable:
            continue
        salida.append(tarea)
    return salida


def prioridades_del_dia(tareas, hoy, limite=3):
    """Devuelve hasta N prioridades inmediatas, ordenadas por riesgo y fecha."""
    hoy = como_fecha(hoy) or date.today()
    ventana = hoy + timedelta(days=7)
    candidatas = [
        t for t in tareas
        if t.get("estado") in {"Bloqueado", "Vencido", "Pendiente", "Aviso"}
        and t.get("responsable") != "Por verificar"
        and (not como_fecha(t.get("fecha")) or como_fecha(t.get("fecha")) <= ventana)
    ]
    orden = {"Bloqueado": 0, "Vencido": 1, "Pendiente": 2, "Aviso": 3}
    candidatas.sort(key=lambda t: (
        orden.get(t.get("estado"), 9),
        {"Alta": 0, "Media": 1, "Normal": 2}.get(t.get("prioridad"), 3),
        t.get("fecha") or "9999-12-31",
    ))
    return candidatas[:max(0, int(limite))]
