"""Presentación recuperada del Inicio aprobado. No modifica datos ni documentos."""
from pathlib import Path
import json, html, re
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import streamlit.components.v1 as components

MONTHS=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
def fecha(value):
 y,m,d=value.split('-');return f'{int(d)} de {MONTHS[int(m)-1]} de {y}'

def theme(dark):
 ink,bg,panel,muted,border=('#f4eee8','#201c20','#2e272d','#dbcbd1','#705d68') if dark else ('#252022','#f6f1e9','#fffdfa','#695762','#d5c9c0')
 st.markdown(f'''<style>
 .stApp,[data-testid="stAppViewContainer"]{{background:{bg};color:{ink};--text-color:{ink};--background-color:{bg};--secondary-background-color:{panel}}}
 [data-testid="stHeader"]{{background:{bg}}}
 [data-testid="stMain"] p,[data-testid="stMain"] label,[data-testid="stMain"] h1,[data-testid="stMain"] h2,[data-testid="stMain"] h3,[data-testid="stMain"] h4,[data-testid="stMain"] li,[data-testid="stMain"] [data-testid="stMetricValue"],[data-testid="stMain"] [data-testid="stMetricLabel"]{{color:{ink}}}
 h1,h2,h3{{font-family:Georgia,serif!important}}
 [data-testid="stCaptionContainer"] p{{color:{muted}!important}}
 [data-testid="stSidebar"]{{background:#221c20;color:#f4eee8}}
 [data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span,[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p{{color:#f4eee8!important}}
 [data-testid="stMain"] input,[data-testid="stMain"] textarea,[data-testid="stMain"] [data-baseweb="select"]>div,[data-testid="stMain"] [data-baseweb="input"],[data-testid="stMain"] [data-baseweb="textarea"]{{background:{panel}!important;color:{ink}!important;-webkit-text-fill-color:{ink};border-color:{border}}}
 [data-testid="stSidebar"] button{{background:#342b31;color:#fff;border-color:#705d68}}
 [data-testid="stMain"] [data-baseweb="select"] span{{color:{ink}!important}}
 [data-testid="stMain"] [data-testid="stAlert"]{{background:{panel};border:1px solid {border}}}
 [data-testid="stSidebar"] input{{background:#342b31!important;color:#fff!important;-webkit-text-fill-color:#fff}}
 [data-testid="stMain"] button{{color:{ink};border-color:{border};background:{panel};transition:transform .18s,box-shadow .18s}}
 [data-testid="stMain"] button p{{color:inherit!important}}
 [data-testid="stMain"] button:hover{{transform:translateY(-2px);box-shadow:0 6px 18px #211d2018;border-color:#b99461}}
 [data-testid="stMain"] button[kind="primary"]{{background:#211d20;color:white!important;border-color:#b99461}}
 [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"],[data-testid="stMain"] [data-testid="stForm"]{{border-color:{border}}}
 .atrio-hero{{background:linear-gradient(115deg,var(--soft),var(--strong));padding:24px;border-radius:14px;margin-bottom:22px;color:#21191d}}
 .atrio-hero h1,.atrio-hero p{{color:#21191d!important}}
 .atrio-badge{{display:inline-block;padding:5px 10px;border-radius:20px;font-size:12px;color:#252022;background:#e5d9e9}}
 .floating{{position:fixed;bottom:22px;right:22px;background:#211d20;color:#fff;padding:12px 18px;border:1px solid #d5b782;border-radius:24px;z-index:900;pointer-events:none}}
 @media(prefers-reduced-motion:reduce){{*{{transition:none!important}}button:hover{{transform:none!important}}}}
 </style>''',unsafe_allow_html=True)
 st.markdown('<style>\n/* ATRIO 10.4: SOLO el menú nativo, sin tocar widgets de otras hojas. */\n[data-testid="stSidebar"]{background:#211c21!important;color:#f8f3ef!important}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"]{margin-bottom:3px!important}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button{\n    width:100%!important;min-height:39px!important;padding:9px 13px!important;\n    border-radius:12px!important;border:1px solid transparent!important;\n    box-shadow:none!important;background:transparent!important;color:#f1e9e6!important;\n    display:flex!important;justify-content:flex-start!important;align-items:center!important;\n    gap:11px!important;text-align:left!important;transition:background .16s,border-color .16s!important\n}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button p{color:#f1e9e6!important;font-size:13px!important;font-weight:520!important}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button span[data-testid="stIconMaterial"],\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button .material-symbols-rounded{\n    color:#d8b58b!important;font-size:19px!important;flex:0 0 20px\n}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button:hover{\n    background:#392b34!important;border-color:#604552!important\n}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"],\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[kind="primary"]{\n    background:linear-gradient(105deg,#5c3146,#7c435d)!important;\n    border-color:#c887a6!important;box-shadow:inset 3px 0 #f2a8ca!important\n}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] p,\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[kind="primary"] p{color:white!important;font-weight:700!important}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] span[data-testid="stIconMaterial"],\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button[data-testid="stBaseButton-primary"] .material-symbols-rounded{color:#ffe1ee!important}\n.atrio-menu-eyebrow{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#c9bbaa;\n  margin:8px 0 12px;font-weight:700}\n@media(prefers-reduced-motion:reduce){[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button{transition:none!important}}\n\n/* ATRIO 10.5: icono y texto alineados a la IZQUIERDA, únicamente menú lateral. */\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button {\n  display:flex!important;\n  flex-direction:row!important;\n  justify-content:flex-start!important;\n  align-items:center!important;\n  text-align:left!important;\n  gap:12px!important;\n  padding-left:18px!important;\n  padding-right:12px!important;\n}\n/* Streamlit puede centrar el contenido en un contenedor interior. */\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button > div,\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button > span:not([data-testid="stIconMaterial"]),\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button [data-testid="stMarkdownContainer"] {\n  display:flex!important;\n  flex-direction:row!important;\n  justify-content:flex-start!important;\n  align-items:center!important;\n  text-align:left!important;\n  margin-left:0!important;\n  margin-right:0!important;\n  width:auto!important;\n  flex:0 1 auto!important;\n  gap:12px!important;\n}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button p,\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button [data-testid="stMarkdownContainer"] p {\n  text-align:left!important;\n  margin:0!important;\n  white-space:normal!important;\n  line-height:1.3!important;\n}\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button span[data-testid="stIconMaterial"],\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button span.material-symbols-rounded,\n[data-testid="stSidebar"] [class*="st-key-atrio_menu_"] button svg {\n  margin-left:0!important;\n  margin-right:0!important;\n  flex:0 0 20px!important;\n}\n\n</style>',unsafe_allow_html=True)
 st.sidebar.markdown('<h1 style="color:#d5b782;letter-spacing:5px">ATRIO</h1>',unsafe_allow_html=True)

def color(v,default):return v if re.fullmatch(r'#[0-9a-fA-F]{6}',str(v)) else default

def heading(title,soft,strong):
 st.markdown(f'<div class="atrio-hero" style="--soft:{color(soft,"#f5d8df")};--strong:{color(strong,"#ed78ab")}"><small>JEFATURA DE CAPACITACIÓN · CECATI 31</small><h1>{html.escape(title)}</h1><p>Tu gestión, bajo tu dirección.</p></div>',unsafe_allow_html=True)

def sisae_resume():
    """Compact total from active SISAE cut. Never leak any student PII."""
    import centro as C
    import cortes
    p=C.RES/'SISAE.zip'
    if not p.exists():
        return '<div class="sisae-data"><span>Inscripciones SISAE</span><span class="subtle">Sin corte cargado · Importa un ZIP en SISAE · Cortes.</span></div>'
    try:
        raw=p.read_bytes()
        tables=C.sisae_bytes(raw)
        n=len(tables['INSCRIPCION.DBF'])
        from collections import Counter
        by=Counter(x.get('PERIODO','').strip() for x in tables['INSCRIPCION.DBF'])
        digest=C.sha(raw)
        date_cut=C.setting('corte_'+digest,{}).get('date') or cortes.KNOWN.get(digest,'Fecha sin verificar')
        split=' · '.join('P'+str(k)+': '+str(by.get(str(k),0)) for k in range(1,5) if by.get(str(k),0))
        return ('<div class="sisae-data"><div><strong>Inscripciones registradas en SISAE</strong>'
                '<div class="subtle">Corte importado: '+html.escape(date_cut)+' · '+html.escape(split)+'</div></div>'
                '<span class="sisae-number">'+str(n)+'</span></div>')
    except Exception:
        return '<div class="sisae-data"><span>Inscripciones SISAE</span><span class="subtle">No se pudo leer el corte activo. Revisar en SISAE · Cortes.</span></div>'

def home_html(data,alerts,dark,soft,strong,today):
 messages={g['id']:message for g,message in alerts}
 rows=[dict(id=g['id'],docente=g['hoja'],curso=g['nombre'],tipo=g['tipo'].upper(),inicio=g['inicio'],fin=g['fin'],horas=g['duracion'],horario=g['horario'],alerta=messages.get(g['id'],'')) for g in data]
 text=(Path(__file__).parent/'inicio.html').read_text()
 now=datetime.now(ZoneInfo('America/Mexico_City'))
 dark_css='''#atrio-inicio-lab{--ink:#f4eee8;--paper:#201c20;--muted:#dbcbd1;--wine:#efc0d3}#atrio-inicio-lab .metric,#atrio-inicio-lab .progress-card,#atrio-inicio-lab .details,#atrio-inicio-lab input{background:#2e272d;color:#f4eee8;border-color:#705d68}#atrio-inicio-lab .track{background:#53454c}#atrio-inicio-lab .hero,#atrio-inicio-lab .hero h1{color:#21191d}''' if dark else ''
 replacements={'__COURSES__':json.dumps(rows,ensure_ascii=False).replace('<','\\u003c'),'__COUNT__':str(len(rows)),'__TODAY__':today.isoformat(),'__GREETING__':'Buenos días' if now.hour<12 else 'Buenas tardes' if now.hour<20 else 'Buenas noches','__ALERT_TEXT__':f'{len(alerts)} pendientes confirmados · consulta y atiende su seguimiento.' if alerts else 'Sin pendientes confirmados. Los estados sin verificar requieren revisión.','__SISAE_SUMMARY__':sisae_resume(),'__DARK_CSS__':dark_css,'__SOFT__':color(soft,'#f5d8df'),'__STRONG__':color(strong,'#ed78ab')}
 for key,value in replacements.items():text=text.replace(key,value)
 return text

def home(data,alerts,dark,soft,strong,today):
 components.html(home_html(data,alerts,dark,soft,strong,today),height=1250,scrolling=True)

def teacher_courses(data,status):
 teachers=sorted({g['hoja'] for g in data})
 selected=st.session_state.get('teacher')
 if selected not in teachers:
  st.subheader('¿Para qué docente?')
  st.caption('Selecciona su tarjeta para abrir sus cursos directamente.')
  cols=st.columns(3)
  for i,teacher in enumerate(teachers):
   total=sum(g['hoja']==teacher for g in data)
   if cols[i%3].button(f'{teacher}\n\n{total} cursos →',key='teacher_card_'+teacher,width='stretch'):
    st.session_state['teacher']=teacher;st.session_state.pop('pea_confirmed',None);st.rerun()
  st.stop()
 if st.button('← Elegir otro docente'):
  st.session_state.pop('teacher',None);st.session_state.pop('pea_confirmed',None);st.rerun()
 st.subheader('Cursos de '+selected)
 rows=sorted([g for g in data if g['hoja']==selected],key=lambda g:g['inicio'])
 ids=[g['id'] for g in rows]
 chosen=st.radio('Selecciona el curso y confirma para preparar',rows,index=ids.index(st.session_state['selected']) if st.session_state.get('selected') in ids else 0,format_func=lambda g:f"{g['nombre']} · {g['tipo']} · {g['duracion']:g} h · {fecha(g['inicio'])} → {fecha(g['fin'])}",key='pea_card_course')
 s=status(chosen['id']);shade='#d9eee0' if s['mce']=='Autorizado' else '#f5d4d4' if s['mce']=='Observado' else {'Regular':'#dbe8f1','Repositorio':'#deeadf','Extensión':'#e8ddeb'}[chosen['tipo']]
 st.markdown(f'<div class="atrio-badge" style="background:{shade}">{html.escape(chosen["tipo"])} · {html.escape(s["doc"])} · MCE: {html.escape(s["mce"])}</div>',unsafe_allow_html=True)
 if st.button('Continuar con este curso →',type='primary'):
  st.session_state['selected']=chosen['id'];st.session_state['pea_confirmed']=chosen['id']
 if st.session_state.get('pea_confirmed')!=chosen['id']:st.stop()
 return chosen

# ATRIO 10.4 · Navegación visual nativa de Streamlit.
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
    st.sidebar.markdown('<div class="atrio-menu-eyebrow">ATRIO · CECATI 31</div>',unsafe_allow_html=True)
    for indice, pagina in enumerate(paginas):
        seleccionado = pagina == actual
        if st.sidebar.button(
            pagina,
            key='atrio_menu_'+str(indice),
            type='primary' if seleccionado else 'secondary',
            icon=_ICONOS_MENU.get(pagina, ':material/chevron_right:'),
            width='stretch',
        ):
            st.session_state['_atrio_pagina_actual'] = pagina
            st.rerun()
    return actual
