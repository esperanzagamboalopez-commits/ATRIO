# -*- coding: utf-8 -*-
"""Módulo de Simulación de Reprogramación."""
import streamlit as st
from datetime import datetime, date, timedelta
import json
import centro as C

DIAS_MAP = {
    'LUNES': 0, 'MARTES': 1, 'MIERCOLES': 2, 'MIÉRCOLES': 2,
    'JUEVES': 3, 'VIERNES': 4, 'SABADO': 5, 'SÁBADO': 5, 'DOMINGO': 6,
}
FESTIVOS_DEFAULT = [date(2026, 11, 2), date(2026, 11, 16), date(2026, 12, 25), date(2027, 1, 1)]
CIERRE_CICLO = date(2027, 6, 30)

def _fmt_fecha(f_str):
    """Convierte 2026-11-06 a 06/11/2026"""
    if not f_str: return ""
    try:
        return datetime.strptime(str(f_str)[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except:
        return str(f_str)

def _obtener_festivos():
    ruta = C.ruta_dias_sin_clase()
    if ruta is None:
        st.warning(
            "No se encontró DIAS_SIN_CLASE.json. Buscado en "
            f"{C.RES / 'DIAS_SIN_CLASE.json'} y {C.ROOT / 'DIAS_SIN_CLASE.json'}. "
            "Se usa una lista de respaldo con 4 festivos; la simulación puede no ser exacta."
        )
        return FESTIVOS_DEFAULT
    st.caption(f"Festivos tomados de: {ruta}")
    return [date.fromisoformat(x) for x in json.loads(ruta.read_text(encoding='utf-8'))]

def _parsear_dias(texto):
    if not isinstance(texto, str): return []
    texto = texto.upper()
    import re
    m = re.search(r'(\w+)\s+A\s+(\w+)', texto)
    if m and m.group(1) in DIAS_MAP and m.group(2) in DIAS_MAP:
        return list(range(DIAS_MAP[m.group(1)], DIAS_MAP[m.group(2)] + 1))
    m = re.search(r'(\w+)\s+Y\s+(\w+)', texto)
    if m and m.group(1) in DIAS_MAP and m.group(2) in DIAS_MAP:
        return [DIAS_MAP[m.group(1)], DIAS_MAP[m.group(2)]]
    for dia, num in DIAS_MAP.items():
        if dia in texto: return [num]
    return []

def _extraer_horario(horario_str):
    import re
    if not isinstance(horario_str, str): return []
    horario_str = horario_str.replace("<br>", "\n")
    bloques = []
    for linea in horario_str.split("\n"):
        linea = linea.strip()
        if not linea: continue
        matches = list(re.finditer(r'(\d{1,2}):(\d{2})\s*(?:A|-)\s*(\d{1,2}):(\d{2})', linea, re.IGNORECASE))
        for i, m in enumerate(matches):
            h_ini, m_ini, h_fin, m_fin = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            if i == 0: parte_dias = linea[:m.start()].strip()
            else: parte_dias = linea[matches[i-1].end():m.start()].strip()
            dias = _parsear_dias(parte_dias)
            if dias:
                dur = ((h_fin*60 + m_fin) - (h_ini*60 + m_ini)) / 60
                bloques.append({'dias': dias, 'duracion': dur, 'hora_ini_min': h_ini*60 + m_ini})
    return bloques

def _clave_carril(horario_str):
    bloques = _extraer_horario(horario_str)
    if not bloques: return None
    b = bloques[0]
    return (tuple(sorted(b['dias'])), round(b['duracion'], 2), b['hora_ini_min'])

def _siguiente_dia_habil(desde, dias, festivos):
    d = desde
    for _ in range(365):
        if d.weekday() in dias and d not in festivos:
            return d
        d += timedelta(days=1)
    return None

def _calcular_fecha_fin(inicio, horas_req, bloques, festivos):
    sim, actual, horas_acum = [], inicio, 0
    while horas_acum < horas_req:
        if actual > CIERRE_CICLO + timedelta(days=365): break
        if actual not in festivos:
            h_dia = sum(b['duracion'] for b in bloques if actual.weekday() in b['dias'])
            if h_dia > 0:
                horas_acum += h_dia
                sim.append({'fecha': actual, 'horas_acum': horas_acum})
        actual += timedelta(days=1)
    if not sim: return None, 0
    ultimo = next((r for r in sim if r['horas_acum'] >= horas_req), sim[-1])
    return ultimo['fecha'], ultimo['horas_acum']

def render_reprogramacion(data, today):
    st.markdown("""
    <div class="hero-pendientes" style="background: linear-gradient(109deg, rgba(255,20,147,.12) 0%, var(--atrio-surface) 55%, rgba(212,175,55,.16) 100%); border-radius: 14px; padding: 24px 26px; color: var(--atrio-titulo); border: 1px solid rgba(212,175,55,.35); box-shadow: var(--atrio-sombra); margin-bottom: 20px;">
        <div>
            <div style="font-size:10px; font-weight:800; letter-spacing:1.5px; color:#D4AF37; margin-bottom:8px;">JEFATURA DE CAPACITACIÓN</div>
            <h1 style="margin: 0; font-family: Georgia, serif; font-size: 32px;">Reprogramación</h1>
            <p style="margin: 5px 0 0 0; font-family: Georgia, serif; color: var(--atrio-tinta);">Simulador de cascada por carril (mismos días y horas).</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    festivos = _obtener_festivos()

    # 1. Selección
    c1, c2 = st.columns(2)
    with c1:
        docentes = sorted(list(set(g['hoja'] for g in data)))
        docente = st.selectbox("Seleccionar Docente", docentes)
    
    cursos_docente = sorted([g for g in data if g['hoja'] == docente], key=lambda x: x['inicio'])
    if not cursos_docente:
        st.warning("Este docente no tiene cursos.")
        return

    with c2:
        curso_sel = st.selectbox("Curso a mover", cursos_docente, format_func=lambda x: f"{x['nombre']} ({_fmt_fecha(x['inicio'])} a {_fmt_fecha(x['fin'])})")

    st.markdown("---")
    
    c3, c4 = st.columns(2)
    with c3:
        # Cambiamos el date_input por un text_input para forzar el formato DD/MM/AAAA
        fecha_actual_str = _fmt_fecha(curso_sel['fin'])
        fecha_ingresada = st.text_input("Nueva fecha de término (DD/MM/AAAA)", value=fecha_actual_str, help="Escribe la fecha en formato Día/Mes/Año. Ejemplo: 06/11/2026")
    with c4:
        st.write("")
        st.write("")
        simular = st.button("🔍 Simular Reprogramación", type="primary", use_container_width=True)

    if simular:
        # Validar el formato de la fecha ingresada
        try:
            nueva_fin_str = datetime.strptime(fecha_ingresada, '%d/%m/%Y').date()
        except ValueError:
            st.error("El formato de fecha es incorrecto. Por favor usa DD/MM/AAAA (ejemplo: 06/11/2026).")
            return

        clave = _clave_carril(curso_sel['horario'])
        if not clave:
            st.error("El horario de este curso no es válido para simular.")
            return

        # Filtrar el mismo carril
        carril = [g for g in cursos_docente if _clave_carril(g['horario']) == clave]
        carril.sort(key=lambda x: x['inicio'])
        
        idx = next((i for i, g in enumerate(carril) if g['id'] == curso_sel['id']), None)
        if idx is None:
            st.error("Error ubicando el curso en su carril.")
            return

        afectados = carril[idx:]
        cursor_fin = nueva_fin_str
        cambios, advertencias = [], []

        for i, g in enumerate(afectados):
            bloques = _extraer_horario(g['horario'])
            if not bloques: continue

            if i == 0:
                nuevo_inicio = datetime.strptime(str(g['inicio'])[:10], '%Y-%m-%d').date()
                nuevo_fin = nueva_fin_str
                if nuevo_fin < nuevo_inicio:
                    st.error(f"La nueva fecha fin ({_fmt_fecha(nuevo_fin)}) es menor al inicio ({_fmt_fecha(nuevo_inicio)}).")
                    return
            else:
                base = cursor_fin + timedelta(days=1)
                nuevo_inicio = _siguiente_dia_habil(base, bloques[0]['dias'], festivos)
                nuevo_fin, horas = _calcular_fecha_fin(nuevo_inicio, g['duracion'], bloques, festivos)
                if not nuevo_fin: break

            if nuevo_fin > CIERRE_CICLO:
                advertencias.append(f"El curso '{g['nombre']}' termina el {_fmt_fecha(nuevo_fin)}, fuera del ciclo ({_fmt_fecha(CIERRE_CICLO)}).")

            cambios.append({
                "curso": g['nombre'],
                "inicio_ant": _fmt_fecha(g['inicio']),
                "fin_ant": _fmt_fecha(g['fin']),
                "inicio_nuevo": _fmt_fecha(nuevo_inicio),
                "fin_nuevo": _fmt_fecha(nuevo_fin),
                "horas_req": g['duracion']
            })
            cursor_fin = nuevo_fin

        # Mostrar Resultados
        st.markdown("### Resultado de la Simulación")
        for c in cambios:
            with st.container(border=True):
                st.markdown(f"**{c['curso']}**")
                st.caption(f"{c['horas_req']} horas · Carril: {curso_sel['horario']}")
                st.write(f"Inicio: {c['inicio_ant']} ➡️ **{c['inicio_nuevo']}**")
                st.write(f"Fin: {c['fin_ant']} ➡️ **{c['fin_nuevo']}**")
        
        if advertencias:
            for adv in advertencias:
                st.warning(adv)
        
        st.info("Esta es solo una simulación. Para aplicar los cambios, deberás actualizar manualmente la Programación y el PEA de cada curso.")