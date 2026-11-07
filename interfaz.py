"""ATRIO · Tema Editorial Rosa (claro).
Presentación únicamente: no modifica datos, documentos ni lógica de negocio.
"""
from pathlib import Path
import json, html, re
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import tema

MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

# Tokens de presentación compartidos. Los colores llegan por variables CSS desde tema.py.
NEON = '#FF1493'
ORO = '#D4AF37'


def fecha(value):
    y, m, d = value.split('-')
    return f'{int(d)} de {MONTHS[int(m) - 1]} de {y}'


GLASS_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@500;700&display=swap');

/* Fondo hueso y tipografía base */
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--atrio-bg)!important;color:var(--atrio-tinta)!important;font-family:'Inter',system-ui,sans-serif}
[data-testid="stHeader"]{background:rgba(var(--atrio-bg-rgb),0.9)!important;backdrop-filter:blur(12px)}
[data-testid="stMain"] p,[data-testid="stMain"] label,[data-testid="stMain"] li,[data-testid="stMain"] span,[data-testid="stMain"] [data-testid="stMetricValue"],[data-testid="stMain"] [data-testid="stMetricLabel"]{color:var(--atrio-tinta)}
[data-testid="stCaptionContainer"] p,[data-testid="stMain"] small{color:var(--atrio-tenue)!important}
h1,h2,h3,h4{font-family:'Playfair Display',Georgia,serif!important;color:var(--atrio-titulo)!important;letter-spacing:.2px}

/* Ancho completo */
[data-testid="stMainBlockContainer"],[data-testid="stAppViewBlockContainer"],.block-container{max-width:100%!important;padding-left:2.5rem!important;padding-right:2.5rem!important}

/* Barra lateral marfil */
[data-testid="stSidebar"]{background:var(--atrio-sidebar)!important;border-right:1px solid var(--atrio-borde)}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span,[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p{color:var(--atrio-tinta)!important}
[data-testid="stSidebar"] input{background:var(--atrio-surface)!important;color:var(--atrio-tinta)!important;-webkit-text-fill-color:var(--atrio-tinta)!important;border:1px solid var(--atrio-borde)!important}
[data-testid="stSidebar"] button{background:var(--atrio-surface);color:var(--atrio-tinta);border:1px solid var(--atrio-borde)}

/* Tarjetas, expansores y formularios: blancos con sombra suave */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stMain"] [data-testid="stForm"],
[data-testid="stMain"] [data-testid="stExpander"]{background:var(--atrio-surface)!important;box-shadow:var(--atrio-sombra);border:1px solid var(--atrio-borde)!important;border-radius:14px}
[data-testid="stMain"] [data-testid="stExpander"] summary{color:var(--atrio-tinta)!important}

/* Campos */
[data-testid="stMain"] input,[data-testid="stMain"] textarea,[data-testid="stMain"] [data-baseweb="select"]>div,[data-testid="stMain"] [data-baseweb="input"],[data-testid="stMain"] [data-baseweb="textarea"]{background:var(--atrio-surface)!important;color:var(--atrio-tinta)!important;-webkit-text-fill-color:var(--atrio-tinta);border-color:var(--atrio-borde)!important}
[data-testid="stMain"] [data-baseweb="select"] span{color:var(--atrio-tinta)!important}
[data-baseweb="popover"] [data-baseweb="menu"],[data-baseweb="popover"] li{background:var(--atrio-surface)!important;color:var(--atrio-tinta)!important}
[data-baseweb="popover"] li:hover{background:var(--atrio-acento-suave)!important}

/* Botones: blancos; primarios en rosa neón con texto oscuro */
[data-testid="stMain"] button{color:var(--atrio-tinta);background:var(--atrio-surface);border:1px solid var(--atrio-borde);border-radius:10px;box-shadow:0 2px 8px rgba(42,35,38,.06);transition:transform .18s,box-shadow .18s,border-color .18s}
[data-testid="stMain"] button p{color:inherit!important}
[data-testid="stMain"] button:hover{transform:translateY(-2px);border-color:var(--atrio-neon);box-shadow:0 6px 16px rgba(255,20,147,.18)}
[data-testid="stMain"] button[kind="primary"],[data-testid="stMain"] button[data-testid="stBaseButton-primary"]{background:var(--atrio-neon)!important;border-color:var(--atrio-neon)!important;color:var(--atrio-sobre-acento)!important;box-shadow:0 4px 14px rgba(255,20,147,.28)}
[data-testid="stMain"] button[kind="primary"]:hover,[data-testid="stMain"] button[data-testid="stBaseButton-primary"]:hover{box-shadow:0 6px 20px rgba(255,20,147,.38)}
[data-testid="stMain"] button[kind="primary"] p,[data-testid="stMain"] button[data-testid="stBaseButton-primary"] p{color:var(--atrio-sobre-acento)!important}
[data-testid="stMain"] button:disabled{opacity:.45}

/* Alertas: blanco con borde rosa */
[data-testid="stAlert"]{background:var(--atrio-surface)!important;box-shadow:var(--atrio-sombra);border:1px solid var(--atrio-borde)!important;border-left:4px solid var(--atrio-neon)!important;border-radius:12px!important;color:var(--atrio-tinta)!important}
[data-testid="stAlert"] p,[data-testid="stAlert"] li,[data-testid="stAlert"] span{color:var(--atrio-tinta)!important}
[data-testid="stAlert"] svg{color:var(--atrio-neon)!important;fill:var(--atrio-neon)!important}

/* Encabezado tipo héroe */
.atrio-hero{background:var(--atrio-hero-gradient);box-shadow:var(--atrio-sombra);border:1px solid var(--atrio-borde);border-left:6px solid var(--atrio-neon);padding:28px 32px;border-radius:16px;margin-bottom:24px;color:var(--atrio-tinta)}
.atrio-hero small{display:block;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--atrio-oro);font-weight:700;margin-bottom:6px}
.atrio-hero h1{font-family:'Playfair Display',Georgia,serif!important;font-size:40px;line-height:1.15;color:var(--atrio-titulo)!important;margin:4px 0 8px}
.atrio-hero p{color:var(--atrio-tenue)!important;margin:0}

.atrio-badge{display:inline-block;padding:5px 11px;border-radius:20px;font-size:12px;color:var(--atrio-tinta);border:1px solid var(--atrio-oro);background:var(--atrio-surface)}
.floating{position:fixed;bottom:22px;right:22px;background:var(--atrio-surface);color:var(--atrio-tinta);padding:12px 18px;border:1px solid var(--atrio-neon);border-radius:24px;z-index:900;pointer-events:none;box-shadow:var(--atrio-sombra)}
.sisae-data{display:flex;justify-content:space-between;align-items:center;gap:16px}
.sisae-number{font-family:'Playfair Display',Georgia,serif;font-size:34px;color:var(--atrio-oro)}

@media(prefers-reduced-motion:reduce){*{transition:none!important}[data-testid="stMain"] button:hover{transform:none!important}}
"""

MENU_CSS = """
/* Menú lateral nativo: texto tinta, activo blanco con línea rosa neón. */
[data-testid="stSidebar"] .atrio-menu-eyebrow{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--atrio-oro);margin:8px 0 12px;font-weight:700}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"]{margin-bottom:3px!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button{
  width:100%!important;min-height:40px!important;padding:9px 13px 9px 18px!important;
  border-radius:12px!important;border:1px solid transparent!important;box-shadow:none!important;
  background:transparent!important;color:var(--atrio-tinta)!important;
  display:flex!important;flex-direction:row!important;justify-content:flex-start!important;align-items:center!important;
  gap:12px!important;text-align:left!important;backdrop-filter:none!important;
  transition:background .16s,border-color .16s,box-shadow .16s!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button p{color:var(--atrio-tinta)!important;font-size:13px!important;font-weight:500!important;text-align:left!important;margin:0!important;white-space:normal!important;line-height:1.3!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button span[data-testid="stIconMaterial"],
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button .material-symbols-rounded,
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button svg{color:var(--atrio-oro)!important;font-size:19px!important;flex:0 0 20px!important;margin:0!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button:hover{background:var(--atrio-acento-suave)!important;border-color:transparent!important;transform:none!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[kind="primary"]{
  background:var(--atrio-surface)!important;border-color:var(--atrio-borde)!important;
  box-shadow:var(--atrio-sombra),inset 3px 0 0 var(--atrio-neon)!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] p,
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[kind="primary"] p{color:var(--atrio-tinta)!important;font-weight:700!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] span[data-testid="stIconMaterial"],
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] .material-symbols-rounded,
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] svg{color:var(--atrio-neon)!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button > div,
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button [data-testid="stMarkdownContainer"]{display:flex!important;flex-direction:row!important;justify-content:flex-start!important;align-items:center!important;gap:12px!important;width:auto!important;margin:0!important;text-align:left!important}
@media(prefers-reduced-motion:reduce){[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button{transition:none!important}}
"""


OVERRIDE_CSS = """
/* Ajustes finales del tema claro: sin cuadros oscuros ni texto blanco sobre blanco. */
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span{color:var(--atrio-tinta)!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button,
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button p,
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button span,
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button svg{color:var(--atrio-tinta)!important;fill:var(--atrio-tinta)!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button span[data-testid="stIconMaterial"]{color:var(--atrio-oro)!important}
[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] span[data-testid="stIconMaterial"]{color:var(--atrio-neon)!important}

/* Pestañas: blanco, subrayado rosa en la activa. */
[data-testid="stTabs"] [data-baseweb="tab-list"]{background:var(--atrio-surface)!important;border-radius:12px 12px 0 0!important;border-bottom:1px solid var(--atrio-borde)!important}
[data-testid="stTabs"] [data-baseweb="tab"]{background:var(--atrio-surface)!important;color:var(--atrio-tinta)!important;border-radius:0!important}
[data-testid="stTabs"] [data-baseweb="tab"] p,[data-testid="stTabs"] [data-baseweb="tab"] span,[data-testid="stTabs"] [data-baseweb="tab"] div{color:var(--atrio-tinta)!important}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"]{border-bottom:3px solid var(--atrio-neon)!important;color:var(--atrio-tinta)!important}
[data-testid="stTabs"] [data-baseweb="tab-highlight"]{background-color:var(--atrio-neon)!important;height:3px!important}
[data-testid="stTabs"] [data-baseweb="tab-border"]{background-color:var(--atrio-borde)!important}

/* Métricas, campos y selectores: blanco, texto tinta. */
[data-testid="stMetric"],[data-testid="stMetricLabel"],[data-testid="stMetricValue"],[data-testid="stMetricDelta"]{background:transparent!important;color:var(--atrio-tinta)!important}
[data-testid="stMetric"]{background:var(--atrio-surface)!important;box-shadow:var(--atrio-sombra);border:1px solid var(--atrio-borde)!important;border-radius:14px!important;padding:12px 16px!important}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-testid="stDateInput"] input,[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] [data-baseweb="select"] > div,[data-testid="stMultiSelect"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-baseweb="input"],[data-testid="stMain"] [data-baseweb="textarea"]{background:var(--atrio-surface)!important;background-color:var(--atrio-surface)!important;color:var(--atrio-tinta)!important;-webkit-text-fill-color:var(--atrio-tinta)!important;border:1px solid var(--atrio-borde)!important}
[data-testid="stTextInput"] input::placeholder,[data-testid="stTextArea"] textarea::placeholder{color:var(--atrio-tenue)!important;-webkit-text-fill-color:var(--atrio-tenue)!important}
[data-testid="stSelectbox"] [data-baseweb="select"] span,[data-testid="stMultiSelect"] [data-baseweb="select"] span,[data-testid="stSelectbox"] [data-baseweb="select"] div{color:var(--atrio-tinta)!important}

/* Botones secundarios y expanders: blancos, texto tinta. */
[data-testid="stMain"] button[kind="secondary"],[data-testid="stMain"] button[data-testid="stBaseButton-secondary"],
[data-testid="stMain"] button[kind="secondaryFormSubmit"],[data-testid="stMain"] button[data-testid="stBaseButton-secondaryFormSubmit"]{background:var(--atrio-surface)!important;background-color:var(--atrio-surface)!important;border:1px solid var(--atrio-borde)!important;color:var(--atrio-tinta)!important}
[data-testid="stMain"] button[kind="secondary"] p,[data-testid="stMain"] button[data-testid="stBaseButton-secondary"] p{color:var(--atrio-tinta)!important}
[data-testid="stExpander"],[data-testid="stExpander"] details,[data-testid="stExpander"] summary{background:var(--atrio-surface)!important;background-color:var(--atrio-surface)!important;color:var(--atrio-tinta)!important;border:1px solid var(--atrio-borde)!important;border-radius:14px!important}
[data-testid="stExpander"] summary p,[data-testid="stExpander"] summary span{color:var(--atrio-tinta)!important}
"""


def theme(dark=False):
    """Tema claro Editorial Rosa (por defecto). El parámetro dark se conserva por compatibilidad."""
    st.markdown('<style>' + tema.root_css() + '</style>', unsafe_allow_html=True)
    st.markdown('<style>' + tema.tematizar(GLASS_CSS) + '</style>', unsafe_allow_html=True)
    st.markdown('<style>' + tema.tematizar(MENU_CSS) + '</style>', unsafe_allow_html=True)
    st.markdown('<style>' + OVERRIDE_CSS + '</style>', unsafe_allow_html=True)
    st.sidebar.markdown('<h1 style="font-family:\'Playfair Display\',Georgia,serif;color:var(--atrio-oro);letter-spacing:6px;margin-bottom:0">ATRIO</h1>', unsafe_allow_html=True)


def color(v, default):
    return v if re.fullmatch(r'#[0-9a-fA-F]{6}', str(v)) else default


def heading(title, soft, strong):
    """Encabezado héroe. Los colores de título ya no cambian el tema; se conservan los parámetros por compatibilidad."""
    st.markdown(
        '<div class="atrio-hero"><small>JEFATURA DE CAPACITACIÓN · CECATI 31</small>'
        f'<h1>{html.escape(title)}</h1><p>Tu gestión, bajo tu dirección.</p></div>',
        unsafe_allow_html=True)


def sisae_resume():
    """Compact total from active SISAE cut. Never leak any student PII."""
    import centro as C
    import cortes
    p = C.RES / 'SISAE.zip'
    if not p.exists():
        return '<div class="sisae-data"><span>Inscripciones SISAE</span><span class="subtle">Sin corte cargado · Importa un ZIP en SISAE · Cortes.</span></div>'
    try:
        raw = p.read_bytes()
        tables = C.sisae_bytes(raw)
        n = len(tables['INSCRIPCION.DBF'])
        from collections import Counter
        by = Counter(x.get('PERIODO', '').strip() for x in tables['INSCRIPCION.DBF'])
        digest = C.sha(raw)
        date_cut = C.setting('corte_' + digest, {}).get('date') or cortes.KNOWN.get(digest, 'Fecha sin verificar')
        split = ' · '.join('P' + str(k) + ': ' + str(by.get(str(k), 0)) for k in range(1, 5) if by.get(str(k), 0))
        return ('<div class="sisae-data"><div><strong>Inscripciones registradas en SISAE</strong>'
                '<div class="subtle">Corte importado: ' + html.escape(date_cut) + ' · ' + html.escape(split) + '</div></div>'
                '<span class="sisae-number">' + str(n) + '</span></div>')
    except Exception:
        return '<div class="sisae-data"><span>Inscripciones SISAE</span><span class="subtle">No se pudo leer el corte activo. Revisar en SISAE · Cortes.</span></div>'


def home_html(data, alerts, dark, soft, strong, today):
    messages = {g['id']: message for g, message in alerts}
    rows = [dict(id=g['id'], docente=g['hoja'], curso=g['nombre'], tipo=g['tipo'].upper(), inicio=g['inicio'], fin=g['fin'], horas=g['duracion'], horario=g['horario'], alerta=messages.get(g['id'], '')) for g in data]
    text = (Path(__file__).parent / 'inicio.html').read_text()
    text = '<style>' + tema.root_css() + '</style>' + text
    now = datetime.now(ZoneInfo('America/Mexico_City'))
    dark_css = ''  # El tema llega por variables CSS (tema.root_css).
    replacements = {
        '__COURSES__': json.dumps(rows, ensure_ascii=False).replace('<', '\\u003c'),
        '__COUNT__': str(len(rows)),
        '__TODAY__': today.isoformat(),
        '__GREETING__': 'Buenos días' if now.hour < 12 else 'Buenas tardes' if now.hour < 20 else 'Buenas noches',
        '__ALERT_TEXT__': f'{len(alerts)} pendientes confirmados · consulta y atiende su seguimiento.' if alerts else 'Sin pendientes confirmados. Los estados sin verificar requieren revisión.',
        '__SISAE_SUMMARY__': sisae_resume(),
        '__DARK_CSS__': dark_css,
        '__TEMA_CSS__': tema.root_css(),
        '__SOFT__': color(soft, '#f5d8df'),
        '__STRONG__': color(strong, '#ed78ab'),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def home(data, alerts, dark, soft, strong, today):
    st.iframe(home_html(data, alerts, dark, soft, strong, today), height=1250)


# ATRIO · Navegación visual nativa de Streamlit.
# Únicamente cambia el control gráfico; conserva nombres y rutas originales.
_ICONOS_MENU = {
    'Inicio': ':material/home:',
    'Programación': ':material/calendar_month:',
    'Acciones Móviles': ':material/record_voice_over:',
    'Preparar PEA': ':material/edit_document:',
    'PEA históricos': ':material/history_edu:',
    'Seguimiento y MCE': ':material/fact_check:',
    'Control escolar': ':material/school:',
    'Constancias y folios': ':material/workspace_premium:',
    'Preparar documento': ':material/description:',
    'Excel para MCE': ':material/table_chart:',
    'Mis PEA': ':material/folder_open:',
    'SISAE · Cortes': ':material/database:',
    'Auditoría histórica': ':material/troubleshoot:',
    'Evaluación trimestral': ':material/monitoring:',
    'Revisor': ':material/manage_search:',
    'Ajustes': ':material/settings:',
    'Respaldos': ':material/backup:',
}


def menu_visual(paginas):
    """Menú con iconos reales: conserva literalmente los nombres y destinos de ATRIO."""
    actual = st.session_state.get('_atrio_pagina_actual', 'Inicio')
    if actual not in paginas:
        actual = paginas[0]
    st.sidebar.markdown('<div class="atrio-menu-eyebrow">ATRIO · CECATI 31</div>', unsafe_allow_html=True)
    for indice, pagina in enumerate(paginas):
        seleccionado = pagina == actual
        if st.sidebar.button(
            pagina,
            key='atrio_menu_' + str(indice),
            type='primary' if seleccionado else 'secondary',
            icon=_ICONOS_MENU.get(pagina, ':material/chevron_right:'),
            width='stretch',
        ):
            st.session_state['_atrio_pagina_actual'] = pagina
            st.rerun()
    return actual
