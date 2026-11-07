# -*- coding: utf-8 -*-
"""Inicio ejecutivo de ATRIO: bienvenida, calendario, panorama y prioridades."""
from __future__ import annotations

import hashlib
import html
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st
import tema

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
    periodos_sisae = {}
    try:
        # Reutiliza la conciliación estricta Programación ↔ SISAE de Control Escolar.
        import hojas
        _, _, _, vinculos, estudiantes, _ = hojas.snapshot(grupos)
        alumnos_por_grupo = {str(k): len(v) for k, v in estudiantes.items()}
        periodos_sisae = {
            str(k): v.get("periodo")
            for k, v in vinculos.items()
        }
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
        periodos_sisae=periodos_sisae,
    )
    return tareas


def _resumen_cursos(grupos, hoy):
    tipos = {
        "Extensión": [],
        "Repositorio": [],
        "Regular": [],
    }
    por_tipo = {
        etiqueta: {"terminados": 0, "en_curso": 0, "por_iniciar": 0}
        for etiqueta in tipos
    }
    vigentes = por_iniciar = terminados = 0
    for grupo in grupos:
        inicio = date.fromisoformat(str(grupo["inicio"])[:10])
        fin = date.fromisoformat(str(grupo["fin"])[:10])
        if inicio <= hoy <= fin:
            vigentes += 1
            estado = "en_curso"
        elif inicio > hoy:
            por_iniciar += 1
            estado = "por_iniciar"
        else:
            terminados += 1
            estado = "terminados"

        tipo = str(grupo.get("tipo") or "").strip().casefold()
        etiqueta = (
            "Extensión" if tipo in ("extensión", "extension")
            else "Repositorio" if tipo == "repositorio"
            else "Regular" if tipo == "regular"
            else None
        )
        if etiqueta:
            tipos[etiqueta].append(grupo)
            por_tipo[etiqueta][estado] += 1

    return {
        "total": len(grupos),
        "vigentes": vigentes,
        "por_iniciar": por_iniciar,
        "terminados": terminados,
        "tipos": tipos,
        "por_tipo": por_tipo,
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
    tokens = tema.variables()
    bienvenida = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
html,body{margin:0;padding:0;background:transparent}
*{box-sizing:border-box}
.atrio-live-welcome{
  width:100%;min-height:112px;display:flex;align-items:center;
  justify-content:space-between;gap:20px;padding:18px 24px;
  background:__HERO__;border:1px solid __BORDER__;
  border-left:6px solid __ACCENT__;border-radius:15px;
  box-shadow:__SHADOW__;color:__TEXT__;
  font-family:Inter,Arial,sans-serif
}
.atrio-live-eyebrow{font-size:10px;font-weight:700;letter-spacing:1.5px;
  text-transform:uppercase;color:__MUTED__}
.atrio-live-welcome h1{margin:8px 0 2px;font-family:Georgia,serif;
  font-size:32px;line-height:1.15;font-weight:600;color:__TITLE__}
.atrio-live-welcome p{margin:0;font-size:13px;color:__TEXT__}
.atrio-live-clock{text-align:right;white-space:nowrap;min-width:125px}
.atrio-live-clock time{display:block;font-variant-numeric:tabular-nums;
  font-size:27px;font-weight:650;letter-spacing:1px;color:__TITLE__}
.atrio-live-clock span{display:block;margin-top:3px;font-size:9px;
  font-weight:700;letter-spacing:1.4px;color:__MUTED__}
@media(max-width:520px){
 .atrio-live-welcome{padding:16px;gap:10px}
 .atrio-live-welcome h1{font-size:24px}
 .atrio-live-clock{min-width:92px}
 .atrio-live-clock time{font-size:21px}
}
</style>
</head>
<body>
<section class="atrio-live-welcome">
  <div>
    <div class="atrio-live-eyebrow">Jefatura de Capacitación · CECATI N.º 31</div>
    <h1>__GREETING__, Esperanza.</h1>
    <p>Tu gestión, bajo tu dirección.</p>
  </div>
  <div class="atrio-live-clock" aria-label="Reloj de hora local">
    <time id="atrio-live-clock">--:--:--</time>
    <span>HORA LOCAL</span>
  </div>
</section>
<script>
(function(){
  const node=document.getElementById("atrio-live-clock");
  const formatter=new Intl.DateTimeFormat("es-MX",{
    timeZone:"America/Mexico_City",hour:"2-digit",minute:"2-digit",
    second:"2-digit",hour12:false
  });
  function updateClock(){node.textContent=formatter.format(new Date());}
  updateClock();
  window.setInterval(updateClock,1000);
})();
</script>
</body>
</html>"""
    valores_bienvenida = {
        "__HERO__": tokens["--atrio-hero-gradient"],
        "__BORDER__": tokens["--atrio-borde"],
        "__ACCENT__": tokens["--atrio-neon"],
        "__SHADOW__": tokens["--atrio-sombra"],
        "__TEXT__": tokens["--atrio-tinta"],
        "__TITLE__": tokens["--atrio-titulo"],
        "__MUTED__": tokens["--atrio-tenue"],
        "__GREETING__": html.escape(_saludo()),
    }
    for marcador, valor in valores_bienvenida.items():
        bienvenida = bienvenida.replace(marcador, valor)
    st.components.v1.html(bienvenida, height=126, scrolling=False)

    if incluir_calendario:
        import calendario as CAL
        CAL.render_inicio_calendario(grupos, tareas=tareas)

    st.markdown("## Panorama de capacitación")
    st.caption("Programación activa y corte SISAE. Los cursos terminados se cuentan por su fecha de término, no por el cierre de constancias.")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Programados", resumen["total"])
    c2.metric("Terminados", resumen["terminados"])
    c3.metric("En curso", resumen["vigentes"])
    c4.metric("Por iniciar", resumen["por_iniciar"])
    if metricas.get("disponible"):
        c5.metric("Alumnos únicos", f'{metricas["alumnos_unicos"]:,}')
        c6.metric("Inscripciones", f'{metricas["inscripciones"]:,}')
    else:
        c5.metric("Alumnos únicos", "—")
        c6.metric("Inscripciones", "—")
    st.caption(f'SISAE · {metricas.get("corte", "Sin corte cargado")}')

    st.markdown("### Avance por tipo de curso")
    for etiqueta in ("Extensión", "Repositorio", "Regular"):
        registros = resumen["tipos"][etiqueta]
        total = len(registros)
        estados = resumen["por_tipo"][etiqueta]
        concluidos = estados["terminados"]
        porcentaje = concluidos / total if total else 0
        st.markdown(
            f'<div class="atrio-progress-label">{html.escape(etiqueta)}'
            f'<span style="float:right">{total} curso(s)</span></div>',
            unsafe_allow_html=True,
        )
        if total:
            st.progress(
                porcentaje,
                text=(
                    f'{estados["terminados"]} terminados · '
                    f'{estados["en_curso"]} en curso · '
                    f'{estados["por_iniciar"]} por iniciar · {porcentaje:.0%}'
                ),
            )
        else:
            st.progress(0.0, text="Sin cursos programados")
    st.caption("El avance se calcula por fecha de término; el cierre de constancias se gestiona por separado.")

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
