"""interfaz.py — Sistema de diseño 'Rose Gold & Obsidian' de ATRIO."""
from __future__ import annotations

import html as _html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import centro as C

# =============================================================================
# SISTEMA DE COLORES
# =============================================================================
def _css_vars(dark=False):
    if dark:
        return """
        :root {
            --atrio-paper: #0F0F13; --atrio-paper-warm: #1A1A22; --atrio-panel: #1E1E24; --atrio-panel-raised: #2A2A35;
            --atrio-ink: #F4F4F5; --atrio-ink-soft: #A1A1AA; --atrio-ink-muted: #71717A; --atrio-border: #3F3F46;
            --atrio-primary: #FF1493; --atrio-primary-hover: #FF69B4; --atrio-gold: #D4AF37;
            --atrio-shadow: 0 8px 24px rgba(0,0,0,0.6);
        }
        """
    else:
        return """
        :root {
            --atrio-paper: #FCFAF8; --atrio-paper-warm: #F5F2EC; --atrio-panel: #FFFFFF; --atrio-panel-raised: #FFFFFF;
            --atrio-ink: #1A1A1A; --atrio-ink-soft: #52525B; --atrio-ink-muted: #8A8A93; --atrio-border: #E4E4E7;
            --atrio-primary: #FF1493; --atrio-primary-hover: #E11D74; --atrio-gold: #D4AF37;
            --atrio-shadow: 0 10px 30px rgba(0,0,0,0.05);
        }
        """

# =============================================================================
# ICONOS
# =============================================================================
_ICONOS_MENU = {
    "Inicio": ":material/space_dashboard:", "Mi Calendario": ":material/calendar_today:",
    "Pendientes": ":material/pending_actions:", "Reprogramación": ":material/update:",
    "Programación": ":material/table_view:", "Preparar PEA": ":material/description:",
    "Mis PEA": ":material/folder_open:", "PEA históricos": ":material/history:",
    "Seguimiento y MCE": ":material/track_changes:", "Revisor": ":material/find_in_page:",
    "Adaptar PDF": ":material/picture_as_pdf:", "Acciones Móviles": ":material/location_on:",
    "Control escolar": ":material/school:", "SISAE · Cortes": ":material/content_cut:",
    "Auditoría SISAE": ":material/fact_check:", "Evaluación trimestral": ":material/analytics:",
    "Constancias y folios": ":material/workspace_premium:", "Excel para MCE": ":material/table_chart:",
    "Asistente virtual": ":material/auto_awesome:", "Ajustes": ":material/settings:",
    "Respaldos": ":material/cloud_sync:",
}

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def fecha(value):
    try:
        y, m, d = str(value)[:10].split("-")
        return f"{int(d)} de {MONTHS[int(m) - 1]} de {y}"
    except Exception:
        return str(value or "")

def color(value, default):
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", str(value or "")) else default

# =============================================================================
# DETECCIÓN DE TEMA Y CSS
# =============================================================================
def _get_theme_name():
    saved = C.setting('tema_visual', None)
    if saved: return saved
    page = st.session_state.get("_atrio_pagina_actual", "Inicio")
    if "Asistente" in page: return "tech"
    if page in ("Mi Calendario", "Pendientes", "Reprogramación"): return "calm"
    if page in ("Preparar PEA", "Programación", "Mis PEA", "Revisor"): return "editorial"
    return "default"

def theme(dark=False):
    css_code = """
    /* Alineación de izquierda a derecha (Full Width) */
    .block-container { max-width: 100% !important; padding-left: 2rem !important; padding-right: 2rem !important; }
    
    .stApp, [data-testid="stAppViewContainer"] { background: var(--atrio-paper) !important; color: var(--atrio-ink) !important; transition: background 0.4s ease; }
    [data-testid="stHeader"] { background: transparent !important; }
    body, [data-testid="stMain"] { font-family: 'Inter', sans-serif !important; color: var(--atrio-ink) !important; }
    h1, h2, h3 { font-family: 'Playfair Display', Georgia, serif !important; color: var(--atrio-ink) !important; }
    
    /* Sidebar */
    [data-testid="stSidebar"] { background: #0D0D12 !important; border-right: 1px solid rgba(255,255,255,0.05); }
    [data-testid="stSidebar"] h1 { color: #D4AF37 !important; font-family: 'Playfair Display', serif !important; letter-spacing: 0.2em !important; font-size: 28px !important; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span { color: #A1A1AA !important; }
    .atrio-menu-eyebrow { color: #D4AF37 !important; font-size: 10px; letter-spacing: 0.15em; text-transform: uppercase; margin: 4px 0 14px 0; font-weight: 700; }
    
    /* Menú */
    [data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button { width: 100% !important; min-height: 44px !important; padding: 10px 16px !important; border-radius: 10px !important; border: 1px solid transparent !important; background: transparent !important; color: #A1A1AA !important; display: flex !important; justify-content: flex-start !important; align-items: center !important; gap: 12px !important; transition: all 0.3s ease !important; }
    [data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button p { color: inherit !important; font-size: 13px !important; font-weight: 500 !important; }
    [data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button:hover { background: rgba(255,20,147,0.1) !important; color: #FF1493 !important; transform: translateX(4px); }
    [data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] { background: linear-gradient(90deg, rgba(255,20,147,0.15) 0%, transparent 100%) !important; border-left: 3px solid #FF1493 !important; color: #FFF !important; }
    [data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] p { font-weight: 600 !important; color: #FF1493 !important; }
    
    /* Botones principales */
    [data-testid="stMain"] button { border-radius: 8px !important; border: 1px solid var(--atrio-border) !important; background: var(--atrio-panel) !important; color: var(--atrio-ink) !important; transition: all 0.3s ease !important; }
    [data-testid="stMain"] button:hover { border-color: var(--atrio-primary) !important; box-shadow: 0 4px 12px rgba(255,20,147,0.2) !important; transform: translateY(-2px) !important; }
    [data-testid="stMain"] button[kind="primary"] { background: var(--atrio-primary) !important; color: #FFF !important; border: none !important; font-weight: 600 !important; }
    [data-testid="stMain"] button[kind="primary"] p { color: #FFF !important; }
    
    /* Inputs */
    [data-testid="stMain"] input, [data-testid="stMain"] textarea, [data-testid="stMain"] [data-baseweb="select"]>div { background: var(--atrio-paper-warm) !important; color: var(--atrio-ink) !important; border: 1px solid var(--atrio-border) !important; border-radius: 8px !important; }
    
    /* ARREGLO DE LOS CUADROS AZULES/VERDES (Alertas) */
    [data-testid="stAlert"] { background-color: var(--atrio-panel) !important; border: 1px solid var(--atrio-border) !important; border-left: 5px solid var(--atrio-primary) !important; border-radius: 8px !important; box-shadow: var(--atrio-shadow) !important; }
    [data-testid="stAlert"] * { color: var(--atrio-ink) !important; background-color: transparent !important; }
    [data-testid="stAlert"] svg { fill: var(--atrio-primary) !important; color: var(--atrio-primary) !important; }
    
    /* Tarjetas y Métricas */
    [data-testid="stMain"] [data-testid="stMetric"] { background: var(--atrio-panel) !important; border: 1px solid var(--atrio-border) !important; border-radius: 12px !important; padding: 20px !important; box-shadow: var(--atrio-shadow) !important; transition: transform 0.3s ease !important; }
    [data-testid="stMain"] [data-testid="stMetric"]:hover { transform: translateY(-4px) !important; }
    [data-testid="stMain"] [data-testid="stMetricValue"] { font-family: 'Playfair Display', serif !important; color: var(--atrio-primary) !important; font-weight: 700; }
    
    /* Chat */
    [data-testid="stChatMessage"] { border-radius: 12px !important; padding: 16px !important; border: 1px solid var(--atrio-border) !important; background: var(--atrio-panel) !important; box-shadow: var(--atrio-shadow) !important; }
    [data-testid="stChatMessage"]:nth-child(even) { background: var(--atrio-paper-warm) !important; }
    
    /* HEADER PREMIUM (Blanco con borde Izquierdo Rosa) */
    .atrio-hero, .hero-pendientes {
        background: var(--atrio-panel) !important;
        padding: 24px 30px !important;
        border-radius: 12px !important;
        margin-bottom: 24px !important;
        border: 1px solid var(--atrio-border) !important;
        border-left: 6px solid var(--atrio-primary) !important;
        box-shadow: var(--atrio-shadow) !important;
    }
    .atrio-hero h1, .hero-pendientes h1 { font-family: 'Playfair Display', serif !important; font-size: 38px !important; margin: 8px 0 4px 0 !important; color: var(--atrio-ink) !important; }
    .atrio-hero small, .hero-pendientes small, .atrio-eyebrow { color: var(--atrio-primary) !important; letter-spacing: 0.15em; text-transform: uppercase; font-size: 11px; font-weight: 800; }
    
    /* Destructor de cajas viejas con gradientes */
    div[style*="linear-gradient(109deg, #f5d8df"], div[style*="linear-gradient(109deg,#f5d8df"] { 
        background: var(--atrio-panel) !important; 
        border: 1px solid var(--atrio-border) !important; 
        border-left: 6px solid var(--atrio-primary) !important; 
        box-shadow: var(--atrio-shadow) !important; 
        border-radius: 12px !important; 
    }
    div[style*="linear-gradient(109deg, #f5d8df"] h1, div[style*="linear-gradient(109deg, #f5d8df"] p, div[style*="linear-gradient(109deg, #f5d8df"] span, div[style*="linear-gradient(109deg, #f5d8df"] div,
    div[style*="linear-gradient(109deg,#f5d8df"] h1, div[style*="linear-gradient(109deg,#f5d8df"] p, div[style*="linear-gradient(109deg,#f5d8df"] span, div[style*="linear-gradient(109deg,#f5d8df"] div { 
        color: var(--atrio-ink) !important; 
    }
    div[style*="linear-gradient(109deg, #f5d8df"] h1, div[style*="linear-gradient(109deg,#f5d8df"] h1 { 
        color: var(--atrio-ink) !important; 
        font-family: 'Playfair Display', serif !important; 
    }
    
    /* Botones de Ajustes */
    [data-testid="stMain"] [data-testid="stHorizontalBlock"] button { padding: 0px !important; min-height: 32px !important; height: 32px !important; width: 32px !important; border-radius: 50% !important; display: flex !important; align-items: center !important; justify-content: center !important; font-size: 16px !important; box-shadow: none !important; }
    [data-testid="stMain"] [data-testid="stHorizontalBlock"] button:hover { background: var(--atrio-primary) !important; color: #FFF !important; }
    [data-testid="stMain"] .stMarkdown p { color: var(--atrio-ink) !important; }
    """
    
    clean_css = re.sub(r'\s+', ' ', css_code)
    fonts = "family=Playfair+Display:ital,wght@0,600;0,700;1,600&family=Inter:wght@400;500;600;700&display=swap"
    
    full_html = f'<link href="https://fonts.googleapis.com/css2?{fonts}" rel="stylesheet"><style>{_css_vars(dark)} {clean_css}</style>'
    st.markdown(full_html, unsafe_allow_html=True)
    st.sidebar.markdown('<h1 style="color:#D4AF37; letter-spacing:0.2em; margin-top: 10px;">ATRIO</h1>', unsafe_allow_html=True)

def heading(title, soft=None, strong=None):
    st.markdown(
        f'<div class="atrio-hero">'
        f'<small>Jefatura de Capacitación · CECATI 31</small>'
        f'<h1>{_html.escape(str(title))}</h1>'
        f'</div>', unsafe_allow_html=True
    )

def menu_visual(pages):
    if "_atrio_pagina_actual" not in st.session_state:
        st.session_state["_atrio_pagina_actual"] = "Inicio"
    st.sidebar.markdown('<div class="atrio-menu-eyebrow">DIRECCIÓN GENERAL</div>', unsafe_allow_html=True)
    for p in pages:
        icon = _ICONOS_MENU.get(p, ":material/circle:")
        is_active = st.session_state["_atrio_pagina_actual"] == p
        tipo = "primary" if is_active else "secondary"
        if st.sidebar.button(f"{p}", key=f"atrio_menu_{p}", icon=icon, use_container_width=True, type=tipo):
            st.session_state["_atrio_pagina_actual"] = p
            st.rerun()
    return st.session_state["_atrio_pagina_actual"]

# =============================================================================
# SISAE Y HOME
# =============================================================================
def sisae_resume():
    p = C.RES / "SISAE.zip"
    if not p.exists(): return '<div style="color:var(--atrio-ink-muted);">Sin corte cargado</div>'
    try:
        tables = C.sisae_bytes(p.read_bytes())
        n = len(tables["INSCRIPCION.DBF"])
        return f'<div style="font-size:32px; font-weight:bold; color:var(--atrio-primary); font-family:\'Playfair Display\', serif;">{n}</div>'
    except Exception: return '<div style="color:var(--atrio-ink-muted);">Error leyendo SISAE</div>'

@st.cache_data(ttl=60, show_spinner=False)
def get_sisae_cached(): return sisae_resume()

@st.cache_data(ttl=60, show_spinner=False)
def get_all_statuses_cached():
    with C.connect() as c:
        return {r["group_id"]: dict(r) for r in c.execute("SELECT * FROM status").fetchall()}

def home_html(data, alerts, dark, soft, strong, today):
    messages = {g["id"]: message for g, message in alerts}
    rows = [dict(id=g["id"], docente=g["hoja"], curso=g["nombre"], tipo=g["tipo"].upper(), inicio=g["inicio"], fin=g["fin"], horas=g["duracion"], horario=g["horario"], alerta=messages.get(g["id"], "")) for g in data]
    text = (Path(__file__).parent / "inicio.html").read_text()
    now = datetime.now(ZoneInfo("America/Mexico_City"))
    
    if dark:
        dark_css = "#atrio-inicio-lab{--ink:#F4F4F5;--paper:#0F0F13;--muted:#A1A1AA;--wine:#FF1493}#atrio-inicio-lab .metric,#atrio-inicio-lab .progress-card,#atrio-inicio-lab .details,#atrio-inicio-lab input{background:#1A1A22;color:#F4F4F5;border-color:#2A2A35}#atrio-inicio-lab .track{background:#2A2A35}#atrio-inicio-lab .hero,#atrio-inicio-lab .hero h1{color:#F4F4F5!important}#atrio-inicio-lab .hero{background:linear-gradient(135deg, #1A1A22 0%, #0F0F13 100%)!important}"
    else:
        dark_css = "#atrio-inicio-lab{--ink:#1A1A1A;--paper:#FCFAF8;--muted:#8A8A93;--wine:#FF1493}#atrio-inicio-lab .metric,#atrio-inicio-lab .progress-card,#atrio-inicio-lab .details,#atrio-inicio-lab input{background:#FFFFFF;color:#1A1A1A;border-color:#E4E4E7}#atrio-inicio-lab .track{background:#F5F2EC}#atrio-inicio-lab .hero{background:linear-gradient(135deg, #FCE7F3 0%, #F9A8D4 100%)!important}"

    total_mce = len(data)
    estatus_dict = get_all_statuses_cached()
    subidos = sum(1 for g in data if estatus_dict.get(g["id"], {}).get("mce", "") not in ("No subido", "Sin verificar", "Observado", ""))
    pct = int((subidos / total_mce) * 100) if total_mce > 0 else 0
    
    mce_bg = "#1A1A22" if dark else "#FFFFFF"
    mce_text = "#F4F4F5" if dark else "#1A1A1A"
    mce_border = "#2A2A35" if dark else "#E4E4E7"
    
    mce_html = f"""
    <div style="background:{mce_bg};border:1px solid {mce_border};border-radius:12px;padding:18px;margin-bottom:20px;">
        <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:700;color:{mce_text};margin-bottom:12px;">
            <span>MCE Global (Avance del Ciclo)</span>
            <span>{total_mce} cursos totales</span>
        </div>
        <div style="height:8px;background:{mce_border};border-radius:4px;overflow:hidden;margin-bottom:10px;">
            <div style="height:100%;width:{pct}%;background:#FF1493;border-radius:4px;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:#8A8A93;">
            <span>Subidos: {subidos}</span>
            <span>Faltantes: {total_mce - subidos}</span>
            <span>{pct}%</span>
        </div>
    </div>
    """

    replacements = {
        "__COURSES__": json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c"),
        "__COUNT__": str(len(rows)),
        "__TODAY__": today.isoformat(),
        "__GREETING__": "Buenos días" if now.hour < 12 else "Buenas tardes" if now.hour < 20 else "Buenas noches",
        "__ALERT_TEXT__": f"{len(alerts)} pendientes confirmados" if alerts else "Sin pendientes",
        "__SISAE_SUMMARY__": get_sisae_cached(),
        "__DARK_CSS__": dark_css,
        "__SOFT__": "#FCE7F3" if not dark else "#1A1A22",
        "__STRONG__": "#F9A8D4" if not dark else "#0F0F13",
        "__MCE_GLOBAL__": mce_html,
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text

def home(data, alerts, dark, soft, strong, today):
    components.html(home_html(data, alerts, dark, soft, strong, today), height=1250, scrolling=True)