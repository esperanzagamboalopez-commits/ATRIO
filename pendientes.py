# -*- coding: utf-8 -*-
"""Centro de Pendientes: vista única del trabajo real del Área de Capacitación."""
from collections import defaultdict
from datetime import date, datetime
import streamlit as st

from motor_pendientes import filtrar_pendientes
from tablero_inicio import cargar_tareas


def _fecha_legible(value):
    try:
        d = date.fromisoformat(str(value)[:10])
        return d.strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "Sin fecha"


def _ir_a(modulo):
    destinos = {
        "Preparar PEA": "Preparar PEA",
        "Mis PEA": "Mis PEA",
        "Seguimiento y MCE": "Seguimiento y MCE",
        "Control escolar": "Control escolar",
        "Acciones Móviles": "Acciones Móviles",
        "Mi Calendario": "Mi Calendario",
    }
    st.session_state["jump"] = destinos.get(modulo, "Pendientes")
    st.rerun()


def render_pendientes(data, today):
    today = today if isinstance(today, date) else datetime.fromisoformat(str(today)[:10]).date()
    st.markdown(
        """
        <style>
        .pendientes-hero{
          background:linear-gradient(108deg,rgba(var(--atrio-neon-rgb),.13),var(--atrio-surface) 62%,rgba(var(--atrio-oro-rgb),.12));
          border:1px solid var(--atrio-borde);border-left:5px solid var(--atrio-neon);
          border-radius:15px;padding:20px 23px;margin-bottom:17px;box-shadow:var(--atrio-sombra)
        }
        .pendientes-hero h1{font-family:Georgia,serif;color:var(--atrio-titulo);margin:3px 0;font-size:29px}
        .pendientes-hero p{color:var(--atrio-tenue);margin:0;font-size:13px}
        .pendientes-eyebrow{font-size:10px;letter-spacing:1.5px;color:var(--atrio-neon);font-weight:700}
        .pendiente-titulo{font-weight:700;color:var(--atrio-titulo);font-size:15px}
        .pendiente-meta{font-size:12px;color:var(--atrio-tenue)}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <section class="pendientes-hero">
          <div class="pendientes-eyebrow">JEFATURA DE CAPACITACIÓN · CECATI 31</div>
          <h1>Centro de Pendientes</h1>
          <p>Seguimiento de procesos reales, fechas de atención y compromisos del área.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    try:
        tareas = cargar_tareas(data, today)
    except Exception as exc:
        st.error(f"No fue posible reunir el seguimiento con las fuentes actuales: {exc}")
        st.caption("No se muestran pendientes simulados ni se alteraron estados.")
        return

    vencidos = sum(1 for t in tareas if t.get("estado") == "Vencido")
    bloqueados = sum(1 for t in tareas if t.get("estado") == "Bloqueado")
    por_verificar = sum(1 for t in tareas if t.get("estado") == "Por verificar")
    en_espera = sum(1 for t in tareas if t.get("responsable") == "Esperando respuesta")
    me_corresponde = sum(
        1 for t in tareas
        if t.get("responsable") == "Me corresponde"
        and t.get("estado") not in {"Por verificar", "Aviso", "En espera"}
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Vencidos", vencidos)
    c2.metric("Bloqueados", bloqueados)
    c3.metric("Me corresponde", me_corresponde)
    c4.metric("Esperando respuesta", en_espera)
    c5.metric("Por verificar", por_verificar)
    st.caption(
        "Los registros sin confirmar se separan de los atrasos. "
        "El término de un curso no significa que su acreditación o constancias estén cerradas."
    )

    st.markdown("### Filtros de seguimiento")
    f1, f2, f3, f4 = st.columns([1.0, 1.4, 1.2, 1.0])
    with f1:
        periodo = st.selectbox(
            "Cuándo",
            ["Todos", "Hoy", "Mañana", "7 días", "Este mes", "Fecha"],
            index=0,
            key="pendientes_periodo_nuevo",
        )
    with f2:
        procesos = ["Todos"] + sorted({str(t.get("proceso") or "Sin proceso") for t in tareas})
        proceso = st.selectbox("Proceso", procesos, key="pendientes_proceso_nuevo")
    with f3:
        responsables = ["Todos", "Me corresponde", "Esperando respuesta", "Por verificar"]
        otros = sorted({
            str(t.get("responsable"))
            for t in tareas
            if t.get("responsable") and t.get("responsable") not in responsables
        })
        responsables.extend(otros)
        responsable = st.selectbox("Responsable", responsables, key="pendientes_responsable_nuevo")
    with f4:
        estados = ["Todos"] + sorted({str(t.get("estado") or "Pendiente") for t in tareas})
        estado_sel = st.selectbox("Situación", estados, key="pendientes_estado_nuevo")
    fecha_personal = None
    if periodo == "Fecha":
        fecha_personal = st.date_input("Día específico", value=today, key="pendientes_fecha_nueva")

    filtrados = filtrar_pendientes(
        tareas,
        today,
        periodo=periodo,
        proceso=proceso,
        responsable=responsable,
        fecha_personal=fecha_personal,
    )
    if estado_sel != "Todos":
        filtrados = [t for t in filtrados if str(t.get("estado") or "Pendiente") == estado_sel]
    st.caption(f"{len(filtrados)} tarea(s) en esta vista · {len(tareas)} en seguimiento total.")

    por_proceso = defaultdict(list)
    for tarea in filtrados:
        por_proceso[tarea.get("proceso") or "Sin proceso"].append(tarea)

    orden_preferido = [
        "Elaboración de PEAs",
        "Preparación de PEA de Repositorio",
        "Subir PEAs al MCE",
        "Altas de cursos regulares en MCE",
        "Listas de asistencia",
        "Acreditaciones",
        "Credenciales",
        "Cursos ACM",
        "Mi Calendario",
        "Por verificar",
    ]
    nombres = sorted(
        por_proceso,
        key=lambda x: (orden_preferido.index(x) if x in orden_preferido else len(orden_preferido), x),
    )
    if not nombres:
        st.caption("No hay tareas que coincidan con estos filtros.")
    for nombre in nombres:
        elementos = por_proceso[nombre]
        with st.expander(f"{nombre} · {len(elementos)}", expanded=len(nombres) == 1):
            for indice, tarea in enumerate(elementos):
                with st.container(border=True):
                    a, b = st.columns([4, 1])
                    with a:
                        st.markdown(f'<div class="pendiente-titulo">{tarea.get("curso", "Actividad")}</div>', unsafe_allow_html=True)
                        st.markdown(
                            f'<div class="pendiente-meta">{tarea.get("docente", "")} · '
                            f'{tarea.get("tipo_curso", "")} · Fecha objetivo: {_fecha_legible(tarea.get("fecha"))}</div>',
                            unsafe_allow_html=True,
                        )
                    with b:
                        estado = tarea.get("estado", "Pendiente")
                        if estado == "Vencido":
                            st.error("Vencido")
                        elif estado == "Bloqueado":
                            st.error("Bloqueado")
                        elif estado == "Por verificar":
                            st.info("Por verificar")
                        elif estado == "En espera":
                            st.info("En espera")
                        elif estado == "Aviso":
                            st.info("Aviso")
                        else:
                            st.caption("Pendiente")
                    st.write(tarea.get("motivo", ""))
                    st.markdown(f"**Siguiente acción:** {tarea.get('accion', '')}")
                    st.caption(
                        f'Responsable: {tarea.get("responsable", "Me corresponde")} · '
                        f'Fuente: {tarea.get("fuente", "ATRIO")}'
                    )
                    modulo = tarea.get("modulo", "Pendientes")
                    key = f'pendiente_ir_{tarea.get("id", indice)}'
                    if st.button(f"Ir a {modulo} →", key=key):
                        _ir_a(modulo)

    # El historial consulta eventos ya registrados; no modifica ni reabre procesos.
    try:
        import centro as C
        grupos_por_id = {str(g.get("id")): g for g in data}
        with st.expander("Historial reciente de gestión", expanded=False):
            db = C.connect()
            try:
                historial = db.execute(
                    "SELECT at, group_id, action FROM events ORDER BY id DESC LIMIT 40"
                ).fetchall()
            finally:
                db.close()
            if not historial:
                st.caption("Todavía no hay movimientos registrados.")
            else:
                for registro in historial:
                    grupo = grupos_por_id.get(str(registro["group_id"] or ""))
                    referencia = grupo.get("nombre") if grupo else "ATRIO · movimiento general"
                    st.write(
                        f'{_fecha_legible(str(registro["at"] or "")[:10])} · '
                        f'{referencia} · {registro["action"]}'
                    )
    except Exception:
        st.caption("No fue posible consultar el historial de movimientos.")
    
    # El historial personal de Mi Calendario permanece separado.
    try:
        import calendario as CAL
        with st.expander("Historial de actividades de Mi Calendario", expanded=False):
            historial_cal = CAL.obtener_historial(limite=30)
            if not historial_cal:
                st.caption("No hay actividades concluidas o canceladas registradas.")
            else:
                for evento in historial_cal:
                    st.write(
                        f'{_fecha_legible(evento.get("fecha_inicio"))} · '
                        f'{evento.get("titulo", "Actividad")} · {evento.get("estado", "")}'
                    )
    except Exception:
        st.caption("No fue posible consultar el historial del calendario.")
