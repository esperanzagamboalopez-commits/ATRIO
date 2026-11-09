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
    """Cuenta las inscripciones del corte SISAE activo, sin mostrar datos personales."""
    import centro as C

    ruta = C.RES / "SISAE.zip"
    if not ruta.is_file():
        return {
            "disponible": False,
            "inscripciones": None,
            "corte": "Sin corte cargado",
        }
    try:
        raw = ruta.read_bytes()
        tablas = C.sisae_bytes(raw)
        inscripciones = tablas["INSCRIPCION.DBF"]
        digest = C.sha(raw)
        fecha = C.setting("corte_" + digest, {}).get("date") or "Fecha sin verificar"
        return {
            "disponible": True,
            "inscripciones": len(inscripciones),
            "corte": str(fecha),
        }
    except Exception:
        return {
            "disponible": False,
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
        .atrio-panorama-heading{
          margin:0 0 5px;color:var(--atrio-titulo);
          font-family:Georgia,serif;font-size:26px;font-weight:600;
        }
        .atrio-panorama-subheading{
          margin:18px 0 8px;color:var(--atrio-titulo);
          font-family:Georgia,serif;font-size:20px;font-weight:600;
        }
        .atrio-panorama-grid{
          display:grid;grid-template-columns:repeat(5,minmax(0,1fr));
          gap:12px;margin:14px 0 18px;
        }
        .atrio-panorama-card{
          min-width:0;background:var(--atrio-surface);
          border:1px solid rgba(var(--atrio-oro-rgb),.48);
          border-radius:11px;padding:16px 17px;
          box-shadow:var(--atrio-sombra);
          transition:transform .2s,box-shadow .2s;
        }
        .atrio-panorama-card:hover{
          transform:translateY(-2px);
          box-shadow:0 10px 24px rgba(42,35,38,.12);
        }
        .st-key-inicio_panorama_programados button,
        .st-key-inicio_panorama_terminados button,
        .st-key-inicio_panorama_en_curso button,
        .st-key-inicio_panorama_por_iniciar button{
          width:100%;height:100%;min-height:154px;text-align:left;
          border:1px solid rgba(var(--atrio-oro-rgb),.48);
          border-radius:11px;background:var(--atrio-surface);
          color:var(--atrio-tinta);box-shadow:var(--atrio-sombra);
          padding:15px 17px;white-space:pre-wrap;
        }
        .st-key-inicio_panorama_programados button:hover,
        .st-key-inicio_panorama_terminados button:hover,
        .st-key-inicio_panorama_en_curso button:hover,
        .st-key-inicio_panorama_por_iniciar button:hover{
          border-color:var(--atrio-neon);color:var(--atrio-tinta);
          transform:translateY(-2px);
        }
        .st-key-inicio_panorama_programados button p,
        .st-key-inicio_panorama_terminados button p,
        .st-key-inicio_panorama_en_curso button p,
        .st-key-inicio_panorama_por_iniciar button p{
          line-height:1.45;margin:0;
        }
        .atrio-panorama-detail{
          border:1px solid var(--atrio-borde);border-left:4px solid var(--atrio-neon);
          border-radius:12px;padding:15px 18px;margin:4px 0 16px;
          background:var(--atrio-surface);box-shadow:var(--atrio-sombra);
        }
        .atrio-panorama-card-head{
          display:flex;justify-content:space-between;align-items:center;gap:8px;
          color:var(--atrio-tenue);font:700 10px/1.35 Inter,system-ui,sans-serif;
          letter-spacing:.7px;text-transform:uppercase;
        }
        .atrio-panorama-icon{
          width:36px;height:36px;display:grid;place-items:center;flex:0 0 36px;
          border-radius:11px;background:rgba(var(--atrio-neon-rgb),.12);
          border:1px solid rgba(var(--atrio-neon-rgb),.32);
          color:var(--atrio-neon);font:20px Georgia,serif;
        }
        .atrio-panorama-icon svg{
          width:21px;height:21px;stroke:currentColor;fill:none;
          stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;
        }
        .atrio-panorama-value{
          display:block;margin:9px 0 3px;color:var(--atrio-neon);
          font:44px/1.05 Georgia,serif;font-weight:400;
          font-variant-numeric:tabular-nums;
        }
        .atrio-panorama-note{
          margin:0;color:var(--atrio-tenue);
          font:11px/1.4 Inter,system-ui,sans-serif;
        }
        .atrio-panorama-progress-card{
          background:var(--atrio-surface);
          border:1px solid rgba(var(--atrio-oro-rgb),.48);
          border-radius:11px;padding:16px 18px;margin:11px 0 0;
          box-shadow:var(--atrio-sombra);
        }
        .atrio-panorama-progress-head{
          display:flex;justify-content:space-between;align-items:center;
          gap:10px;flex-wrap:wrap;color:var(--atrio-tinta);
          font:600 14px Inter,system-ui,sans-serif;
        }
        .atrio-panorama-progress-name{
          display:flex;align-items:center;font:600 18px Georgia,serif;
          color:var(--atrio-titulo);
        }
        .atrio-panorama-dot{
          display:inline-block;width:9px;height:9px;border-radius:50%;
          margin-right:9px;background:var(--tipo-color);
        }
        .atrio-panorama-track{
          height:7px;margin:12px 0 10px;overflow:hidden;
          background:rgba(var(--atrio-oro-rgb),.16);border-radius:9px;
        }
        .atrio-panorama-fill{
          height:100%;border-radius:9px;background:var(--tipo-color);
          transition:width .25s ease;
        }
        .atrio-panorama-states{
          display:flex;justify-content:space-between;align-items:center;
          flex-wrap:wrap;gap:6px 14px;color:var(--atrio-tenue);
          font:11px/1.4 Inter,system-ui,sans-serif;
        }
        @media(max-width:1100px){
          .atrio-panorama-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
        }
        @media(max-width:700px){
          .atrio-panorama-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
          .atrio-panorama-value{font-size:38px}
        }
        @media(max-width:430px){
          .atrio-panorama-grid{grid-template-columns:1fr}
        }
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

    st.markdown(
        '<div class="atrio-panorama-heading">Panorama de capacitación</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Programación activa y corte SISAE. Los cursos terminados se cuentan "
        "por su fecha de término, no por el cierre de constancias."
    )

    inscripciones = (
        f'{metricas["inscripciones"]:,}'
        if metricas.get("disponible") and metricas.get("inscripciones") is not None
        else "—"
    )
    tarjetas = [
        (
            "Programados",
            f'{resumen["total"]:,}',
            "Grupos en la programación",
            '<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
        ),
        (
            "Terminados",
            f'{resumen["terminados"]:,}',
            "Por fecha de término",
            '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="m7.5 12 3 3 6-6"/></svg>',
        ),
        (
            "En curso",
            f'{resumen["vigentes"]:,}',
            "Activos a la fecha de corte",
            '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
        ),
        (
            "Por iniciar",
            f'{resumen["por_iniciar"]:,}',
            "Con inicio en fecha futura",
            '<svg viewBox="0 0 24 24"><path d="M4 12h15M13 5l7 7-7 7"/></svg>',
        ),
        (
            "Total de inscritos",
            inscripciones,
            "Registros del corte SISAE",
            '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h10M7 17h6"/></svg>',
        ),
    ]
    detalle_key = "inicio_panorama_detalle"
    columnas_tarjetas = st.columns(5, gap="small")
    tarjetas_interactivas = [
        ("programados", "Programados", resumen["total"],
         "Grupos en la programación", "Todos los cursos programados"),
        ("terminados", "Terminados", resumen["terminados"],
         "Por fecha de término", "Cursos cuya fecha de término ya pasó"),
        ("en_curso", "En curso", resumen["vigentes"],
         "Activos a la fecha de corte", "Cursos activos hoy"),
        ("por_iniciar", "Por iniciar", resumen["por_iniciar"],
         "Con inicio en fecha futura", "Cursos con inicio posterior a hoy"),
    ]
    for columna, (clave, titulo, valor, nota, encabezado) in zip(
       columnas_tarjetas, tarjetas_interactivas
    ):
        with columna:
            etiqueta = f"**{titulo}**  \n\n{valor:,}  \n\n{nota}  \n\n↳ Tocar para ver cursos"
            if st.button(
                etiqueta,
                key=f"inicio_panorama_{clave}",
                use_container_width=True,
                help=f"Mostrar u ocultar el detalle de {titulo.lower()}",
            ):
                st.session_state[detalle_key] = (
                    None if st.session_state.get(detalle_key) == clave else clave
                )
    with columnas_tarjetas[4]:
        st.markdown(
            (
                '<article class="atrio-panorama-card">'
                '<div class="atrio-panorama-card-head">'
                '<span>Total de inscritos</span>'
                f'<span class="atrio-panorama-icon" aria-hidden="true">'
                '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/>'
                '<path d="M7 9h10M7 13h10M7 17h6"/></svg></span></div>'
                f'<strong class="atrio-panorama-value">{html.escape(inscripciones)}</strong>'
                '<p class="atrio-panorama-note">Registros del corte SISAE</p></article>'
            ),
            unsafe_allow_html=True,
        )

    detalle_activo = st.session_state.get(detalle_key)
    if detalle_activo:
        grupos_detalle = {
            "programados": grupos,
            "terminados": resumen["tipos"]["Extensión"] + resumen["tipos"]["Repositorio"] + resumen["tipos"]["Regular"],
            "en_curso": [],
            "por_iniciar": [],
        }
        # Los cuatro estados se obtienen con el mismo criterio de fechas del resumen.
        for grupo in grupos:
            inicio = date.fromisoformat(str(grupo["inicio"])[:10])
            fin = date.fromisoformat(str(grupo["fin"])[:10])
            if inicio <= hoy <= fin:
                grupos_detalle["en_curso"].append(grupo)
            elif inicio > hoy:
                grupos_detalle["por_iniciar"].append(grupo)
        # La tarjeta de terminados incluye también grupos de tipo no catalogado.
        if detalle_activo == "terminados":
            grupos_detalle["terminados"] = [
                g for g in grupos
                if date.fromisoformat(str(g["fin"])[:10]) < hoy
            ]
        seleccionados = grupos_detalle.get(detalle_activo, [])
        nombres = {
            "programados": "Todos los cursos programados",
            "terminados": "Cursos terminados",
            "en_curso": "Cursos en curso",
            "por_iniciar": "Cursos por iniciar",
        }
        st.markdown(f"**{nombres.get(detalle_activo, 'Detalle de cursos')}**")
        if st.button("Ocultar detalle", key="inicio_panorama_cerrar"):
            st.session_state[detalle_key] = None
        if not seleccionados:
            st.info("No hay cursos en esta categoría para la fecha de corte.")
        else:
            filas = []
            for grupo in seleccionados:
                filas.append({
                    "Curso": grupo.get("nombre") or "Sin nombre registrado",
                    "Docente": grupo.get("hoja") or "Sin docente registrado",
                    "Especialidad": grupo.get("especialidad_programada") or "Sin especialidad",
                    "Tipo": grupo.get("tipo") or "Sin tipo",
                    "Inicio": str(grupo.get("inicio") or "")[:10],
                    "Término": str(grupo.get("fin") or "")[:10],
                    "Horario": grupo.get("horario") or "Sin horario",
                })
            st.dataframe(filas, hide_index=True, use_container_width=True)
    st.caption(f'SISAE · {metricas.get("corte", "Sin corte cargado")}')

    st.markdown(
        '<div class="atrio-panorama-subheading">Avance por tipo de curso</div>',
        unsafe_allow_html=True,
    )
    colores_tipo = {
        "Extensión": "#C77D9E",
        "Repositorio": "#5B9188",
        "Regular": "#C39A50",
    }
    for etiqueta in ("Extensión", "Repositorio", "Regular"):
        total = len(resumen["tipos"][etiqueta])
        estados = resumen["por_tipo"][etiqueta]
        porcentaje = estados["terminados"] / total if total else 0
        color_tipo = colores_tipo[etiqueta]
        if total:
            ancho = porcentaje * 100
            detalle = (
                f'<div class="atrio-panorama-track" role="progressbar" '
                f'aria-label="{html.escape(etiqueta)} terminados" '
                f'aria-valuenow="{estados["terminados"]}" '
                f'aria-valuemin="0" aria-valuemax="{total}">'
                f'<div class="atrio-panorama-fill" '
                f'style="width:{ancho:.2f}%;--tipo-color:{color_tipo}"></div></div>'
            )
            estados_html = (
                f'<span>Terminados: <strong>{estados["terminados"]}</strong></span>'
                f'<span>En curso: <strong>{estados["en_curso"]}</strong></span>'
                f'<span>Por iniciar: <strong>{estados["por_iniciar"]}</strong></span>'
                f'<span>{porcentaje:.0%} completado</span>'
            )
        else:
            detalle = (
                '<div class="atrio-panorama-track" role="progressbar" '
                f'aria-label="{html.escape(etiqueta)} sin cursos" '
                'aria-valuenow="0" aria-valuemin="0" aria-valuemax="0">'
                '<div class="atrio-panorama-fill" style="width:0%"></div></div>'
            )
            estados_html = '<span>Sin cursos programados</span>'
        st.markdown(
            (
                f'<article class="atrio-panorama-progress-card" '
                f'style="--tipo-color:{color_tipo}">'
                '<div class="atrio-panorama-progress-head">'
                f'<span class="atrio-panorama-progress-name">'
                f'<i class="atrio-panorama-dot"></i>{html.escape(etiqueta)}</span>'
                f'<span>{total} curso(s)</span>'
                '</div>'
                f'{detalle}'
                f'<div class="atrio-panorama-states">{estados_html}</div>'
                '</article>'
            ),
            unsafe_allow_html=True,
        )
    st.caption(
        "El avance se calcula por fecha de término; el cierre de constancias "
        "se gestiona por separado."
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
