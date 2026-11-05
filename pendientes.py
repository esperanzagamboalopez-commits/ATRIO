# -*- coding: utf-8 -*-
"""Centro de Pendientes C-01 con Tablero de Progreso (4 tarjetas) y filtro real."""
import streamlit as st
from datetime import datetime, date, timedelta
import json
import calendar
import centro as C
import validaciones_1013

MESES_MAP = {
    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
    "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12
}

def _obtener_festivos():
    ruta = C.ruta_dias_sin_clase()
    if ruta is None:
        st.warning(
            "No se encontró DIAS_SIN_CLASE.json. Buscado en "
            f"{C.RES / 'DIAS_SIN_CLASE.json'} y {C.ROOT / 'DIAS_SIN_CLASE.json'}. "
            "Sin esa lista, los festivos no se descuentan del cálculo."
        )
        return []
    return [date.fromisoformat(x) for x in json.loads(ruta.read_text(encoding='utf-8'))]

def _primer_dia_habil(anio, mes, festivos):
    for dia in range(1, 8):
        d = date(anio, mes, dia)
        if d.weekday() < 5 and d not in festivos:
            return d
    return date(anio, mes, 1)

def _meses_entre(inicio, fin):
    meses = []
    actual = date(inicio.year, inicio.month, 1)
    while actual <= fin:
        meses.append((actual.year, actual.month))
        if actual.month == 12:
            actual = date(actual.year + 1, 1, 1)
        else:
            actual = date(actual.year, actual.month + 1, 1)
    return meses

def render_pendientes(data, today):
    st.markdown("""
    <style>
    .hero-pendientes { background: linear-gradient(109deg, rgba(255,20,147,.12) 0%, var(--atrio-surface) 55%, rgba(212,175,55,.16) 100%); border-radius: 14px; padding: 24px 26px; color: var(--atrio-titulo); border: 1px solid rgba(212,175,55,.35); box-shadow: var(--atrio-sombra); margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
    .hero-pendientes h1 { margin: 0; font-family: Georgia, serif; font-size: 32px; }
    .hero-pendientes p { margin: 5px 0 0 0; font-family: Georgia, serif; color: var(--atrio-tinta); }
    
    .kpi-progreso { background: var(--atrio-surface); border: 1px solid rgba(212,175,55,.35); border-radius: 12px; padding: 15px; margin-bottom: 10px; box-shadow: var(--atrio-sombra); }
    .kpi-progreso .header { display: flex; justify-content: space-between; font-size: 13px; font-weight: 700; color: var(--atrio-titulo); margin-bottom: 10px; }
    .kpi-progreso .bar-bg { height: 8px; background: rgba(212,175,55,.18); border-radius: 4px; overflow: hidden; margin-bottom: 10px; }
    .kpi-progreso .bar-fill { height: 100%; background: #FF1493; border-radius: 4px; transition: width 0.5s ease; }
    .kpi-progreso .footer { display: flex; justify-content: space-between; font-size: 11px; color: var(--atrio-tenue); }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="hero-pendientes">
        <div>
            <div style="font-size:10px; font-weight:800; letter-spacing:1.5px; color:#D4AF37; margin-bottom:8px;">JEFATURA DE CAPACITACIÓN</div>
            <h1>Centro de Pendientes</h1>
            <p>Tu gestión, bajo tu dirección. Lo importante, en el momento adecuado.</p>
        </div>
        <div style="text-align:right;">
            <div style="font-size:10px; font-weight:700;">VISTA DE HOY</div>
            <strong style="font-size:25px;">{today.strftime('%d %b').upper()}</strong>
            <div style="font-size:10px;">{today.year} · Ciclo Activo</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- FILTROS (Sin selector de ciclo, fijo en 2026-2027) ---
    c1, c2 = st.columns(2)
    with c1:
        periodo_sel = st.selectbox("Periodo de inscripción", ["Todo el ciclo", "1 · Julio–Septiembre", "2 · Octubre–Diciembre"])
    with c2:
        if periodo_sel == "1 · Julio–Septiembre":
            opciones_fecha = ["Este mes", "Hoy", "Todo el periodo", "Julio", "Agosto", "Septiembre"]
        elif periodo_sel == "2 · Octubre–Diciembre":
            opciones_fecha = ["Este mes", "Hoy", "Todo el periodo", "Octubre", "Noviembre", "Diciembre"]
        else:
            opciones_fecha = ["Este mes", "Hoy", "Todo el ciclo", "Próximos 30 días"]
        fecha_sel = st.selectbox("Fecha de atención", opciones_fecha)
    
    st.markdown("---")

    # --- LÓGICA DE FILTRADO ---
    deadline_dias = int(C.setting('deadline_days', 11))
    festivos = _obtener_festivos()

    casos_pea_falta = []
    casos_mce_ext_falta = []
    casos_mce_reg_falta = []
    casos_mce_obs_falta = []
    casos_listas_falta = []
    casos_credenciales_falta = []
    casos_acreditaciones_falta = []
    casos_inconsistencias = []

    # Contadores de cursos ÚNICOS
    total_inician = 0
    total_terminan = 0
    total_ext = 0
    total_reg = 0

    # Ciclo fijo
    anio_inicio, anio_fin = 2026, 2027
    rango_ciclo = (date(2026, 8, 1), date(2027, 7, 31))

    def coincide_ciclo(d): return rango_ciclo[0] <= d <= rango_ciclo[1]
    
    def coincide_periodo(d):
        if periodo_sel == "Todo el ciclo": return True
        if periodo_sel == "1 · Julio–Septiembre": return (d.year == anio_inicio and 7 <= d.month <= 9)
        if periodo_sel == "2 · Octubre–Diciembre": return (d.year == anio_inicio and 10 <= d.month <= 12)
        return True

    def coincide_mes(d, opcion):
        if opcion == "Este mes":
            return d.month == today.month and d.year in (anio_inicio, anio_fin)
        if opcion == "Hoy":
            return d == today
        if opcion == "Todo el ciclo":
            return True
        if opcion not in MESES_MAP:
            return True 
        return d.month == MESES_MAP[opcion] and d.year in (anio_inicio, anio_fin)

    data_ciclo = [g for g in data if coincide_ciclo(datetime.strptime(str(g['inicio'])[:10], '%Y-%m-%d').date())]
    
    errores = validaciones_1013.validar_datos_grupos(data_ciclo)
    for e in errores:
        g = next((x for x in data_ciclo if x['nombre'] == e['grupo']), None)
        if g: casos_inconsistencias.append({"grupo": g, "motivo": e['detalle']})

    for g in data_ciclo:
        s = C.status(g['id'])
        try:
            inicio_date = datetime.strptime(str(g['inicio'])[:10], '%Y-%m-%d').date()
            fin_date = datetime.strptime(str(g['fin'])[:10], '%Y-%m-%d').date()
        except: continue

        dias_para_inicio = (inicio_date - today).days
        dias_para_fin = (fin_date - today).days

        # 1. ARRANQUE: PEA
        if coincide_mes(inicio_date, fecha_sel) and coincide_periodo(inicio_date):
            total_inician += 1
            if s['doc'] in ('Sin PEA', 'Sin verificar'):
                casos_pea_falta.append({"grupo": g, "motivo": "Elaborar y confirmar PEA", "dias": dias_para_inicio})
        
        # 2. CIERRE: MCE
        if coincide_mes(fin_date, fecha_sel) and coincide_periodo(fin_date):
            total_terminan += 1
            
            if g['tipo'] == 'Regular': total_reg += 1
            else: total_ext += 1

            if s['mce'] in ('No subido', 'Sin verificar', 'Observado'):
                if dias_para_fin <= 45:
                    item = {"grupo": g, "motivo": "", "dias": dias_para_fin}
                    if s['mce'] == 'Observado':
                        item["motivo"] = "Corregir Observaciones"
                        casos_mce_obs_falta.append(item)
                    else:
                        item["motivo"] = "Preparar y subir MCE"
                        if g['tipo'] == 'Regular': casos_mce_reg_falta.append(item)
                        else: casos_mce_ext_falta.append(item)

            # Acreditaciones (Solo para la agenda de abajo)
            if dias_para_fin <= 0:
                motivo = "Acreditar Curso"
                if g['tipo'] != 'Regular':
                    if s['mce'] in ('No subido', 'Sin verificar', 'Observado'): motivo += " (MCE Pendiente)"
                    else: motivo += " (MCE ya subido)"
                else: motivo += " (Curso Regular)"
                casos_acreditaciones_falta.append({"grupo": g, "motivo": motivo, "dias": dias_para_fin})

        # 3. TRANSCURSO: Listas
        if fecha_sel in MESES_MAP:
            mes_num = MESES_MAP[fecha_sel]
            if inicio_date <= date(anio_inicio, mes_num, 28) and fin_date >= date(anio_inicio, mes_num, 1):
                primer_habil = _primer_dia_habil(anio_inicio, mes_num, festivos)
                if today >= primer_habil:
                    casos_listas_falta.append({"grupo": g, "motivo": f"Entregar Lista de {fecha_sel} (Límite: {primer_habil.strftime('%d/%m')})", "dias": (primer_habil - today).days})
        elif fecha_sel in ["Todo el periodo", "Este mes", "Hoy", "Todo el ciclo", "Próximos 30 días"]:
            for (anio, mes) in _meses_entre(inicio_date, fin_date):
                if coincide_periodo(date(anio, mes, 1)):
                    if fecha_sel == "Este mes" and mes != today.month:
                        continue
                    primer_habil = _primer_dia_habil(anio, mes, festivos)
                    if today >= primer_habil and today >= inicio_date:
                        casos_listas_falta.append({"grupo": g, "motivo": f"Entregar Lista de {calendar.month_name[mes].capitalize()} (Límite: {primer_habil.strftime('%d/%m')})", "dias": (primer_habil - today).days})

        # 4. TRANSCURSO: Credenciales
        if coincide_mes(inicio_date, fecha_sel) and coincide_periodo(inicio_date) and today >= inicio_date:
            limite = inicio_date + timedelta(days=7)
            if today <= limite:
                casos_credenciales_falta.append({"grupo": g, "motivo": "Generar Credenciales (Semana de inicio)", "dias": (limite - today).days})
            else:
                casos_credenciales_falta.append({"grupo": g, "motivo": "Credenciales Vencidas", "dias": (limite - today).days})

    # --- CÁLCULOS DE PROGRESO ---
    pea_hechos = total_inician - len(casos_pea_falta)
    
    mce_ext_hechos = total_ext - len(casos_mce_ext_falta)
    mce_reg_hechos = total_reg - len(casos_mce_reg_falta)
    mce_totales = total_ext + total_reg
    mce_falta_total = len(casos_mce_ext_falta) + len(casos_mce_reg_falta) + len(casos_mce_obs_falta)
    mce_hechos_total = mce_totales - mce_falta_total

    def crear_tarjeta(titulo, total, faltantes, hechos):
        pct = int((hechos / total) * 100) if total > 0 else 0
        return f"""
        <div class="kpi-progreso">
            <div class="header">
                <span>{titulo}</span>
                <span>{total} cursos</span>
            </div>
            <div class="bar-bg">
                <div class="bar-fill" style="width: {pct}%;"></div>
            </div>
            <div class="footer">
                <span>Terminados: {hechos}</span>
                <span>Faltantes: {faltantes}</span>
                <span>{pct}% del total</span>
            </div>
        </div>
        """

    # --- RESUMEN EJECUTIVO (4 Tarjetas) ---
    st.markdown("### Resumen ejecutivo (Avance de Cursos)")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(crear_tarjeta("PEA (Arranque)", total_inician, len(casos_pea_falta), pea_hechos), unsafe_allow_html=True)
    with c2:
        st.markdown(crear_tarjeta("MCE Extensión", total_ext, len(casos_mce_ext_falta), mce_ext_hechos), unsafe_allow_html=True)
        
    c3, c4 = st.columns(2)
    with c3:
        st.markdown(crear_tarjeta("MCE Regulares", total_reg, len(casos_mce_reg_falta), mce_reg_hechos), unsafe_allow_html=True)
    with c4:
        st.markdown(crear_tarjeta("MCE Totales", mce_totales, mce_falta_total, mce_hechos_total), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Agenda de prioridades (Solo lo que falta)")
    
    def render_acordeon(titulo, lista, enlace_modulo, icono):
        if not lista: return
        with st.expander(f"{icono} {titulo} ({len(lista)} casos)", expanded=False):
            items_por_pagina = 10
            total_paginas = max(1, (len(lista) + items_por_pagina - 1) // items_por_pagina)
            key_pag = f"pag_{titulo.replace(' ', '_')}"
            if key_pag not in st.session_state: st.session_state[key_pag] = 1
                
            if total_paginas > 1:
                col_prev, col_info, col_next = st.columns([1, 2, 1])
                with col_prev:
                    if st.button("⬅️ Anterior", key=f"prev_{key_pag}", disabled=st.session_state[key_pag] == 1):
                        st.session_state[key_pag] -= 1; st.rerun()
                with col_info:
                    st.markdown(f"<div style='text-align:center; color:var(--atrio-tenue); font-size:12px; margin-top:10px;'>Página {st.session_state[key_pag]} de {total_paginas}</div>", unsafe_allow_html=True)
                with col_next:
                    if st.button("Siguiente ➡️", key=f"next_{key_pag}", disabled=st.session_state[key_pag] == total_paginas):
                        st.session_state[key_pag] += 1; st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)

            inicio_idx = (st.session_state[key_pag] - 1) * items_por_pagina
            lista_paginada = lista[inicio_idx : inicio_idx + items_por_pagina]

            for idx, item in enumerate(lista_paginada):
                g = item['grupo']
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**{g['nombre']}**")
                    st.caption(f"Docente: {g['hoja']} · {g['tipo']} · Inicia: {g['inicio']} | Termina: {g['fin']}")
                    st.write(f"↳ {item['motivo']}")
                with col2:
                    unique_key = f"btn_ir_{titulo}_{inicio_idx + idx}_{g.get('id', 'demo')}"
                    if st.button("Ir al módulo →", key=unique_key, use_container_width=True):
                        st.session_state['selected'] = g.get('id')
                        st.session_state['teacher'] = g.get('hoja')
                        st.session_state['jump'] = enlace_modulo
                        st.rerun()
                st.divider()

    render_acordeon("Acciones necesarias (PEA)", casos_pea_falta, "Preparar PEA", "📄")
    render_acordeon("MCE Extensión (Por subir)", casos_mce_ext_falta, "Seguimiento y MCE", "☁️")
    render_acordeon("MCE Regulares (Por subir)", casos_mce_reg_falta, "Seguimiento y MCE", "☁️")
    render_acordeon("MCE Observados", casos_mce_obs_falta, "Seguimiento y MCE", "⚠️")
    render_acordeon("Transcurso: Listas de Asistencia", casos_listas_falta, "Control escolar", "📅")
    render_acordeon("Inicio: Credenciales", casos_credenciales_falta, "Control escolar", "🪪")
    render_acordeon("Cierre: Acreditaciones", casos_acreditaciones_falta, "Control escolar", "🎓")
    render_acordeon("Inconsistencias de Datos", casos_inconsistencias, "Programación", "🛠️")
