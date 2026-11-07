# -*- coding: utf-8 -*-
"""Inicio ejecutivo de ATRIO: bienvenida, calendario, panorama y prioridades."""
from __future__ import annotations

import hashlib
import html
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st

from motor_pendientes import (
    construir_pendientes,
    identificador_control_escolar,
    prioridades_del_dia,
)


def _saludo():
    ahora = datetime.now(ZoneInfo("America/Mexico_City"))
    momento = "Buenos días" if ahora.hour < 12 else "Buenas tardes" if ahora.hour < 20 else "Buenas noches"
    return momento


def _metricas_sisae():
    """Cuenta alumnos únicos e inscripciones del corte SISAE activo, sin PII."""
    import centro as C

    ruta = C.RES / "SISAE.zip"
    if not ruta.is_file():
        return {
            "disponible": False,
            "alumnos_unicos": None,
            "inscripciones": None,
            "corte": "Sin corte cargado",
        }
    try:
        raw = ruta.read_bytes()
        tablas = C.sisae_bytes(raw)
        inscripciones = tablas["INSCRIPCION.DBF"]
        alumnos = {
            str(r.get("ID_ALUMNO", "")).strip()
            for r in inscripciones
            if str(r.get("ID_ALUMNO", "")).strip()
        }
        digest = C.sha(raw)
        fecha = C.setting("corte_" + digest, {}).get("date") or "Fecha sin verificar"
        return {
            "disponible": True,
            "alumnos_unicos": len(alumnos),
            "inscripciones": len(inscripciones),
            "corte": str(fecha),
        }
    except Exception:
        return {
            "disponible": False,
            "alumnos_unicos": None,
            "inscripciones": None,
            "corte": "No se pudo leer el corte",
        }


def cargar_tareas(grupos, hoy):
    """Reúne fuentes reales para el motor común, sin modificar sus registros."""
    import centro as C
    import calendario as CAL

    estados = {str(g["id"]): C.status(g["id"]) for g in grupos}
    school = C.setting("hojas03_school", {}) or {}
    credenciales = C.setting("hojas03_credentials", {}) or {}
    festivos = []
    ruta_festivos = C.ruta_dias_sin_clase()
    if ruta_festivos and ruta_festivos.is_file():
        try:
            import json
            festivos = json.loads(ruta_festivos.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            festivos = []

    alumnos_por_grupo = {}
    try:
        # Reutiliza la conciliación estricta Programación ↔ SISAE de Control Escolar.
        import hojas
        _, _, _, _, estudiantes, _ = hojas.snapshot(grupos)
        alumnos_por_grupo = {str(k): len(v) for k, v in estudiantes.items()}
    except Exception:
        # Sin vínculo inequívoco no se inventa el padrón ni se asignan alumnos.
        alumnos_por_grupo = {}

    eventos = []
    try:
        eventos = CAL.obtener_pendientes(limite=1500)
    except Exception:
        eventos = []

    tareas = construir_pendientes(
        grupos,
        hoy,
        estados=estados,
        estados_control_escolar=school,
        estados_credenciales=credenciales,
        eventos_calendario=eventos,
        dias_inhabiles=festivos,
        alumnos_por_grupo=alumnos_por_grupo,
    )
    return tareas


def _resumen_cursos(grupos, hoy):
    tipos = {
        "Extensión": [],
        "Repositorio": [],
        "Regular": [],
    }
    vigentes = por_iniciar = terminados = 0
    for grupo in grupos:
        inicio = date.fromisoformat(str(grupo["inicio"])[:10])
        fin = date.fromisoformat(str(grupo["fin"])[:10])
        if inicio <= hoy <= fin:
            vigentes += 1
        elif inicio > hoy:
            por_iniciar += 1
        elif fin < hoy:
            terminados += 1
        tipo = str(grupo.get("tipo") or "").strip().casefold()
        if tipo in ("extensión", "extension"):
            tipos["Extensión"].append(grupo)
        elif tipo == "repositorio":
            tipos["Repositorio"].append(grupo)
        elif tipo == "regular":
            tipos["Regular"].append(grupo)
    return {
        "total": len(grupos),
        "vigentes": vigentes,
        "por_iniciar": por_iniciar,
        "terminados": terminados,
        "tipos": tipos,
    }


def _abrir_modulo(modulo):
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


def render(grupos, hoy, *, metricas_sisae=None, tareas=None, incluir_calendario=True):
    """Renderiza Inicio operativo o una vista previa con datos ficticios inyectados."""
    hoy = hoy if isinstance(hoy, date) else date.fromisoformat(str(hoy)[:10])
    resumen = _resumen_cursos(grupos, hoy)
    metricas = metricas_sisae if metricas_sisae is not None else _metricas_sisae()
    tareas = tareas if tareas is not None else cargar_tareas(grupos, hoy)

    st.markdown(
        """
        <style>
        .atrio-inicio-welcome{
          background:var(--atrio-hero-gradient);
          border:1px solid var(--atrio-borde);
          border-left:6px solid var(--atrio-neon);
          border-radius:15px;padding:22px 26px;margin:2px 0 18px;
          box-shadow:var(--atrio-sombra)
        }
        .atrio-inicio-welcome .eyebrow{
          color:var(--atrio-tenue);font-size:10px;font-weight:700;
          letter-spacing:1.5px;text-transform:uppercase
        }
        .atrio-inicio-welcome h1{
          margin:9px 0 3px;color:var(--atrio-titulo);
          font-family:Georgia,serif;font-size:clamp(28px,3.5vw,38px)
        }
        .atrio-inicio-welcome p{margin:0;color:var(--atrio-tinta);font-size:13px}
        .atrio-priority-title{font-family:Georgia,serif;font-size:22px;font-weight:600}
        .atrio-priority-meta{color:var(--atrio-tenue);font-size:12px}
        .atrio-priority-card{
          border:1px solid var(--atrio-borde);border-left:4px solid var(--atrio-neon);
          border-radius:12px;background:var(--atrio-surface);
          padding:13px 15px;margin:9px 0;box-shadow:var(--atrio-sombra)
        }
        .atrio-progress-label{font-size:13px;font-weight:650;color:var(--atrio-titulo)}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <section class="atrio-inicio-welcome">
          <div class="eyebrow">Jefatura de Capacitación · CECATI N.º 31</div>
          <h1>{html.escape(_saludo())}, Esperanza.</h1>
          <p>Tu gestión, bajo tu dirección.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if incluir_calendario:
        import calendario as CAL
        CAL.render_inicio_calendario(grupos, tareas=tareas)

    st.markdown("## Panorama de capacitación")
    st.caption("Programación activa y corte SISAE. Los cursos terminados se cuentan por su fecha de término, no por el cierre de constancias.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cursos programados", resumen["total"])
    if metricas.get("disponible"):
        c2.metric("Alumnos únicos", f'{metricas["alumnos_unicos"]:,}')
        c3.metric("Inscripciones", f'{metricas["inscripciones"]:,}')
    else:
        c2.metric("Alumnos únicos", "—")
        c3.metric("Inscripciones", "—")
    c4.metric("Cursos vigentes", resumen["vigentes"])
    st.caption(f'SISAE · {metricas.get("corte", "Sin corte cargado")}')

    st.markdown("### Avance por tipo de curso")
    for etiqueta in ("Extensión", "Repositorio", "Regular"):
        registros = resumen["tipos"][etiqueta]
        total = len(registros)
        concluidos = sum(
            1 for g in registros
            if date.fromisoformat(str(g["fin"])[:10]) < hoy
        )
        porcentaje = concluidos / total if total else 0
        st.markdown(
            f'<div class="atrio-progress-label">{html.escape(etiqueta)}'
            f'<span style="float:right">{total} curso(s)</span></div>',
            unsafe_allow_html=True,
        )
        if total:
            st.progress(
                porcentaje,
                text=f"{concluidos} terminados por fecha · {total - concluidos} vigentes o por iniciar · {porcentaje:.0%}",
            )
        else:
            st.progress(0.0, text="Sin cursos programados")
    st.caption(
        f'{resumen["terminados"]} terminados por fecha · '
        f'{resumen["vigentes"]} vigentes · {resumen["por_iniciar"]} por iniciar.'
    )

    st.markdown("## Prioridades de hoy")
    prioridades = prioridades_del_dia(tareas, hoy, limite=3)
    if not prioridades:
        st.markdown("**Sin prioridades inmediatas.**")
        st.caption("Los demás seguimientos siguen disponibles en Centro de Pendientes.")
        return

    for indice, tarea in enumerate(prioridades, 1):
        fecha = tarea.get("fecha") or "Sin fecha"
        estado = tarea.get("estado", "Pendiente")
        modulo = tarea.get("modulo", "Pendientes")
        identificador = hashlib.sha256(str(tarea.get("id", indice)).encode()).hexdigest()[:12]
        st.markdown(
            f"""
            <article class="atrio-priority-card">
              <div class="atrio-priority-meta">PRIORIDAD {indice} · {html.escape(estado.upper())} · {html.escape(fecha)}</div>
              <strong>{html.escape(tarea.get("curso", tarea.get("proceso", "Actividad")))}</strong>
              <div>{html.escape(tarea.get("motivo", ""))}</div>
              <div class="atrio-priority-meta" style="margin-top:5px">
                Siguiente acción: {html.escape(tarea.get("accion", ""))}
              </div>
            </article>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            f'Ir a {modulo} →',
            key=f"inicio_prioridad_{identificador}",
        ):
            _abrir_modulo(modulo)
