from pathlib import Path
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import html, json, os
import streamlit as st
import centro as C
import trabajos as J
import interfaz as UI
import hojas
import orden_menu as OM
import acm_oficios as ACM
import salida
import pea_biblioteca_109 as P109
import pea_wizard_112 as F112
import pea_historicos_101212 as H1212
import revisor_pea_112 as R112
import asistente_atrio_101214 as AI214
import validaciones_1013
import modulo_pendientes
import modulo_reprogramacion
import modulo_adaptar_pdf
import modulo_auditoria_sisae
import modulo_calendario

def safe_error(exc):
 key=os.getenv('GEMINI_API_KEY')
 return str(exc).replace(key,'[CLAVE OCULTA]') if key else str(exc)

st.set_page_config(page_title='ATRIO · Capacitación',page_icon='◈',layout='wide')

# ---------------- INICIALIZACIÓN Y TEMA ----------------
if not C.groups():
    try:
        C.import_program(C.RES/'PROGRAMACION DE CURSOS.xlsx')
    except Exception as e:
        st.warning(f"No se pudo cargar el Excel inicial: {e}")

DARK = st.sidebar.toggle('Modo oscuro', value=C.setting('dark', False))
if DARK != C.setting('dark', False):
    C.set_setting('dark', DARK)

UI.theme(DARK)
a = C.setting('header_soft', '#f5d8df')
b = C.setting('header_strong', '#ed78ab')

# ---------------- BUSCADOR (ARRIBA) ----------------
st.sidebar.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
query = st.sidebar.text_input('🔍 Buscar curso, docente o acción', placeholder='Escribe aquí…', label_visibility="collapsed")

# ---------------- MENÚ REORGANIZADO ----------------
PAGES = [
    'Inicio', 'Mi Calendario', 'Pendientes', 'Reprogramación',
    'Programación', 'Preparar PEA', 'Mis PEA', 'PEA históricos',
    'Seguimiento y MCE', 'Revisor', 'Adaptar PDF', 'Acciones Móviles',
    'Control escolar', 'SISAE · Cortes', 'Auditoría SISAE',
    'Evaluación trimestral', 'Constancias y folios', 'Excel para MCE',
    'Asistente virtual', 'Ajustes', 'Respaldos'
]

if 'jump' in st.session_state:
    st.session_state['_atrio_pagina_actual'] = st.session_state.pop('jump')

orden_guardado = C.setting('orden_menu', [])
for p in PAGES:
    if p not in orden_guardado:
        orden_guardado.append(p)

nav = UI.menu_visual(OM.orden_actual(PAGES, orden_guardado))

if query:
    actions={'Generar PEA':'Preparar PEA','Alta de regulares y exportación MCE':'Seguimiento y MCE','Subir ZIP SISAE':'SISAE · Cortes','Cambiar calendario y días inhábiles':'Ajustes','Actualizar plantilla Word':'Ajustes','Editar perfil docente':'Ajustes','Cambiar colores de títulos':'Ajustes','Descargar respaldo':'Respaldos'}
    for label,target in actions.items():
        if C.motor.normal(query) in C.motor.normal(label):
            if st.sidebar.button(label,key='search_action_'+label):
                st.session_state['jump']=target
                st.rerun()
    hits=[g for g in C.groups() if C.motor.normal(query) in C.motor.normal(g['nombre']+' '+g['hoja'])]
    if hits:
        found=st.sidebar.selectbox('Resultados',hits,format_func=lambda g:f"{g['hoja']} · {g['nombre']} · {g['inicio']}")
        if st.sidebar.button('Abrir curso'):
            st.session_state['selected']=found['id']
            st.session_state['teacher']=found['hoja']
            st.session_state['editor_group']=found['id']
            st.session_state['pea110_stage']='contenido'
            st.session_state['jump']='Preparar PEA'
            st.rerun()

if nav=='Preparar PEA' and st.session_state.get('pea110_stage') in ('validacion','contenido','salida'):
    nav='Preparar documento'

today=datetime.now(ZoneInfo('America/Mexico_City')).date()
data=C.groups()

# ---------------- ALERTAS ----------------
alerts=[]
deadline_dias = int(C.setting('deadline_days', 11))
for g in data:
    s = C.status(g['id'])
    dias_para_inicio = 999
    try:
        inicio_date = datetime.strptime(str(g['inicio'])[:10], '%Y-%m-%d').date()
        dias_para_inicio = (inicio_date - today).days
    except Exception: pass
    if 0 <= dias_para_inicio <= deadline_dias:
        if s['doc'] == 'Sin PEA': alerts.append((g, f'🚨 URGENTE: PEA sin elaborar, inicia en {dias_para_inicio} días'))
        elif s['mce'] == 'No subido': alerts.append((g, f'🚨 URGENTE: PEA sin subir al MCE, inicia en {dias_para_inicio} días'))
        elif s['mce'] == 'Observado': alerts.append((g, f'⚠️ PEA Observado, inicia en {dias_para_inicio} días'))
    else:
        if s['mce'] == 'Observado': alerts.append((g, 'PEA devuelto con observaciones'))
        elif g['tipo'] != 'Regular' and s['mce'] == 'No subido': alerts.append((g, 'PEA pendiente de subir al MCE'))
        elif s['doc'] == 'Sin PEA': alerts.append((g, 'PEA confirmado por elaborar'))

errores_logicos = validaciones_1013.validar_datos_grupos(data)
for err in errores_logicos:
    g_match = next((g for g in data if g['nombre'] == err['grupo']), None)
    if g_match: alerts.append((g_match, f"⚠️ {err['tipo']}: {err['detalle']}"))

st.sidebar.caption(f'{len(alerts)} pendientes confirmados')
if alerts:
    st.markdown(f'<div class="floating">● {len(alerts)} pendientes por atender</div>',unsafe_allow_html=True)
    with st.sidebar.expander('Ver pendientes (Rápido)',expanded=False):
        for g,msg in alerts: st.write(f"{g['nombre']} · {msg}")

# ---------------- ENCABEZADO GLOBAL UNIFICADO ----------------
# Excluimos TODAS las páginas que ya dibujan su propio encabezado en su módulo interno.
if nav in ('Ajustes', 'Respaldos', 'Excel para MCE', 'SISAE · Cortes'):
    UI.heading(nav, a, b)

def show_group(g):
    st.subheader(g['nombre'])
    st.caption(f"{g['hoja']} · {g['tipo']} · {g['duracion']:g} horas")
    st.write(f"Inicio: {UI.fecha(g['inicio'])} · Término: {UI.fecha(g['fin'])}")
    st.write('Días y horario: '+g['horario'])

def select_group(key='select'):
    teachers=sorted({g['hoja'] for g in data})
    teacher=st.selectbox('Docente',teachers,index=teachers.index(st.session_state.get('teacher')) if st.session_state.get('teacher') in teachers else 0,key=key+'_teacher')
    rows=sorted([g for g in data if g['hoja']==teacher],key=lambda g:g['inicio'])
    ids=[g['id'] for g in rows]
    chosen=st.selectbox('Curso · todos los tipos',rows,index=ids.index(st.session_state.get('selected')) if st.session_state.get('selected') in ids else 0,format_func=lambda g:f"{g['nombre']} · {g['tipo']} · {g['inicio']} → {g['fin']} · {g['horario']}",key=key+'_group')
    return chosen

# ---------------- RUTEO DE PÁGINAS ----------------
if nav=='Inicio':
    UI.home(data,alerts,DARK,a,b,today)
    if st.button('Abrir seguimiento de PEA y MCE →',key='home_follow'):
        st.session_state['jump']='Seguimiento y MCE'
        st.rerun()

elif nav=='Mi Calendario':
    modulo_calendario.render_calendario()

elif nav=='Pendientes':
    modulo_pendientes.render_pendientes(data, today)

elif nav=='Reprogramación':
    modulo_reprogramacion.render_reprogramacion(data, today)

elif nav=='Adaptar PDF':
    modulo_adaptar_pdf.render_adaptar_pdf()

elif nav=='Auditoría SISAE':
    modulo_auditoria_sisae.render_auditoria_sisae()

elif nav in ('Programación','Preparar PEA','Control escolar','Constancias y folios','Seguimiento y MCE'):
    if nav == 'Seguimiento y MCE':
        st.markdown("""
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #8d405e; margin-bottom: 20px;">
            <h4 style="margin-top:0;">Acceso Rápido a Plataformas</h4>
            <p style="font-size: 14px; color: #555;">Usa estos botones para ir directo al portal institucional. Tu navegador autocompletará tus credenciales.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col_mce1, col_mce2 = st.columns(2)
        with col_mce1:
            st.link_button("🌐 Ir al MCE (Regulares y Extensión)", "https://www.dgcft.sems.gob.mx/intranet_dg.html", use_container_width=True)
        with col_mce2:
            st.caption("*(Recuerda tener tus contraseñas guardadas en tu navegador para que el acceso sea automático).*")
    
    number={'Programación':2,'Preparar PEA':3,'Seguimiento y MCE':3,'Control escolar':4,'Constancias y folios':5}[nav]
    hojas.show(number,data,today,tracking=nav=='Seguimiento y MCE')

elif nav=='PEA históricos':
    H1212.panel_historicos()

elif nav=='Preparar documento':
    UI.heading('Preparar PEA',a,b)
    uid=st.session_state.get('editor_group')
    g=next((x for x in data if x['id']==uid),None)
    if g is None:
        st.info('Selecciona primero un docente y un curso en Preparar PEA.')
        if st.button('Abrir selección de cursos',key='pea111_open'):
            st.session_state.pop('pea110_stage',None)
            st.session_state['jump']='Preparar PEA'
            st.rerun()
    else:
        F112.panel(g)

elif nav=='Acciones Móviles':
    ACM.panel_oficios(data,C)

elif nav=='Revisor':
    R112.panel(data)

elif nav=='Asistente virtual':
    AI214.panel(data,C)

elif nav=='Excel para MCE':
    g=select_group('mce03')
    show_group(g)
    salida.present(g)

elif nav=='Mis PEA':
    P109.panel_mis_pea(J,data)

elif nav=='Evaluación trimestral':
    import evaluacion_sisae as ES
    ES.panel()

elif nav=='SISAE · Cortes':
    import cortes
    cortes.panel()

elif nav=='Ajustes':
    OM.panel_ajustes(PAGES,C)
    
    st.subheader("🎨 Apariencia Visual Global")
    st.caption("Selecciona la atmósfera visual. Esto cambiará los colores y tipos de letra en toda la aplicación.")
    temas_disp = {
        "default": "Obsidiana & Oro (Autoridad)",
        "tech": "Cyber-Executive (Tecnología)",
        "calm": "Japandi Minimalista (Calma)",
        "editorial": "Editorial Premium (Académico)"
    }
    tema_actual = C.setting('tema_visual', 'default')
    nuevo_tema = st.selectbox(
        "Estilo Visual", 
        options=list(temas_disp.keys()), 
        format_func=lambda x: temas_disp[x],
        index=list(temas_disp.keys()).index(tema_actual) if tema_actual in temas_disp else 0
    )
    if nuevo_tema != tema_actual:
        C.set_setting('tema_visual', nuevo_tema)
        st.rerun()

    with st.expander('Instituciones y sedes ACM · Catálogo editable',expanded=False):
        ACM.panel_catalogo(C)
    
    if st.button('Actualizar o comparar respaldos SISAE →'):
        st.session_state['jump']='SISAE · Cortes'
        st.rerun()
    
    with st.expander('Recursos · archivos y plantillas con respaldo',expanded=False):
        st.caption('Al actualizar un recurso se conserva su versión anterior. Los tres oficios ACM mantienen sus formatos independientes.')
        resources={'Programación':'PROGRAMACION DE CURSOS.xlsx','Padrón docente':'Plantilla_Datos_Docentes_PEA_CECATI31.xlsx','Plantilla PEA institucional':'PEA_final en blanco.docx','Días inhábiles · JSON':'DIAS_SIN_CLASE.json','Hoja membretada · Word':'MEMBRETE.docx','Calendario oficial · PDF':'CALENDARIO.pdf','ACM · Oficio de Presentación':'acm:Presentación','ACM · Oficio de Vinculación':'acm:Vinculación','ACM · Oficio de Asignación':'acm:Asignación'}
        label=st.selectbox('Recurso a actualizar',list(resources),key='ajuste129_recurso')
        filename=resources[label]
        acm_kind=filename[4:] if filename.startswith('acm:') else None
        ext='docx' if acm_kind else filename.rsplit('.',1)[1]
        if acm_kind:
            st.caption('Sustituye únicamente el Word de '+acm_kind+'. Conserva {{GRUPOS}} y las demás variables del formato vigente; los documentos ya emitidos no cambiarán.')
        upload=st.file_uploader('Seleccionar archivo',type=[ext],key='ajuste129_upload')
        if upload is not None and st.button('Validar y guardar recurso',key='ajuste129_guardar'):
            try:
                if acm_kind:
                    result=ACM.actualizar_formato_acm(C,acm_kind,upload.getvalue())
                    st.success('Plantilla Word de '+acm_kind+' actualizada. La anterior quedó respaldada.')
                    st.caption('Marcadores conservados: '+', '.join(result['marcadores']))
                else:
                    result=C.save_resource(filename,upload.getvalue())
                    st.success('Recurso guardado con respaldo anterior.')
                    if result:
                        st.write(f'{result[0]} grupos importados')
                        st.write(result[1])
            except Exception as e:
                st.error(f'No se reemplazó el recurso: {e}')
        st.caption('El calendario PDF y el membrete general se almacenan como recursos; no se aplican automáticamente a documentos en esta entrega.')

    with st.expander('Completar o corregir perfil docente',expanded=False):
        st.caption('Especialidad y firma son datos independientes. La imagen no se inserta automáticamente en documentos.')
        names=sorted({g['hoja'] for g in data})
        if names:
            person=st.selectbox('Docente a editar',names)
            existing=C.profiles().get(C.motor.normal(person),{})
            ruta_firma=str(existing.get('firma') or '').strip()
            if ruta_firma:
                es_ruta_windows=(':\\' in ruta_firma or ruta_firma.startswith('\\\\'))
                if es_ruta_windows:
                    st.caption('Firma: referencia antigua de Windows. Cloud Shell no puede leerla. Puedes subir la imagen JPG/PNG cuando quieras.')
                else:
                    st.caption('Firma: archivo asociado al docente. Su aplicación en documentos requiere autorización expresa.')
            else:
                st.caption('Firma: todavía no hay una imagen asociada.')
            st.caption('La columna H del Padrón conserva la referencia de autorización existente, pero no autoriza automáticamente nuevos PEA.')
            import especialidades_101211 as E211
            sugeridas,problema=E211.sugerencias_docente(C.RES/'PROGRAMACION DE CURSOS.xlsx',person)
            guardada=str(existing.get('especialidad') or '').strip()
            if problema:
                st.caption(problema+' Puedes elegir del catálogo.')
            elif len(sugeridas)==1:
                st.caption('Programación propone: '+sugeridas[0]+'. Se guardará únicamente al confirmar el perfil.')
            elif len(sugeridas)>1:
                st.caption('Programación muestra varias especialidades para este docente: '+', '.join(sugeridas)+'. Elige la correspondiente.')
            else:
                st.caption('No se identificó una especialidad inequívoca en Programación; selecciona una del catálogo.')
            opciones_esp=['— Seleccionar especialidad —']+E211.opciones(guardada,sugeridas)
            if guardada and guardada in opciones_esp:
                especialidad_inicial=guardada
            elif len(sugeridas)==1:
                especialidad_inicial=sugeridas[0]
            else:
                especialidad_inicial=opciones_esp[0]
            with st.form('profile'):
                values={k:st.text_input(label,str(existing.get(k,'') or '')) for k,label in [('curp','CURP docente'),('correo','Correo docente'),('telefono','Teléfono docente'),('tipo','Tipo de docente')]}
                especialidad_seleccionada=st.selectbox('Especialidad docente',opciones_esp,index=opciones_esp.index(especialidad_inicial),key='esp_docente_101211_'+C.motor.normal(person),help='Sugerencias tomadas del Excel de Programación. Puedes elegir otra especialidad del catálogo.')
                values['especialidad']='' if especialidad_seleccionada==opciones_esp[0] else especialidad_seleccionada
                imagen=st.file_uploader('Actualizar imagen de firma (opcional)',type=['png','jpg','jpeg'],help='La firma se guardará en recursos protegidos y NO se insertará automáticamente en los PEA.')
                if st.form_submit_button('Guardar perfil docente'):
                    try:
                        if not values['especialidad']:
                            raise ValueError('Selecciona la especialidad antes de guardar el perfil.')
                        C.save_profile(person,values,imagen.getvalue() if imagen else None,Path(imagen.name).suffix.lower() if imagen else None)
                        st.success('Perfil guardado. Especialidad y firma se mantienen en columnas independientes.')
                    except Exception as e:
                        st.error(str(e))
        else:
            st.caption('Aún no hay docentes de Programación disponibles.')

    with st.expander('Días inhábiles efectivos',expanded=False):
        dates=json.loads((C.RES/'DIAS_SIN_CLASE.json').read_text())
        text=st.text_area('Fechas excluidas · una AAAA-MM-DD por línea','\n'.join(dates),height=180)
        if st.button('Guardar fechas excluidas'):
            try:
                C.save_resource('DIAS_SIN_CLASE.json',json.dumps([x.strip() for x in text.splitlines() if x.strip()]).encode())
                st.success('Guardado; confirma el calendario después de revisarlo.')
            except Exception as e:
                st.error(str(e))
        checked=st.checkbox('Confirmo que estos días corresponden al calendario que usaré',value=C.setting('calendario_confirmado',False))
        if st.button('Guardar confirmación del calendario'):
            C.set_setting('calendario_confirmado',checked)
            st.success('Confirmación guardada.')

    with st.expander('Autoridades y presentación',expanded=False):
        with st.form('settings'):
            valida=st.text_input('Valida',C.setting('valida','Lila Inurreta Fernández'))
            visto=st.text_input('Visto bueno',C.setting('visto','Lila Inurreta Fernández'))
            autoriza=st.text_input('Autoriza',C.setting('autoriza','Sergio López Hernández'))
            soft=st.color_picker('Título · color suave',a)
            strong=st.color_picker('Título · color intenso',b)
            deadline=st.number_input('Anticipación para aviso · días naturales',min_value=1,value=C.setting('deadline_days',11))
            anchor=st.selectbox('Referencia del plazo',['Inicio','Término'],index=0 if C.setting('deadline_anchor','Término')=='Inicio' else 1)
            if st.form_submit_button('Guardar ajustes'):
                for k,v in [('valida',valida),('visto',visto),('autoriza',autoriza),('header_soft',soft),('header_strong',strong),('deadline_days',deadline),('deadline_anchor',anchor)]:
                    C.set_setting(k,v)
                st.rerun()

    with st.expander('Servicio de contenido IA',expanded=False):
        key=st.text_input('Clave Gemini · solo memoria de esta sesión del servidor',type='password')
        model=st.text_input('Modelo Gemini',os.getenv('GEMINI_MODELO','gemini-1.5-flash'))
        if st.button('Usar configuración IA en esta sesión'):
            if key:
                os.environ['GEMINI_API_KEY']=key
                st.session_state['GEMINI_API_KEY'] = key
                try:
                    cfg_path = Path(__file__).parent / 'datos' / 'config_ia.json'
                    cfg_path.parent.mkdir(exist_ok=True)
                    cfg_path.write_text(json.dumps({"GEMINI_API_KEY": key, "GEMINI_MODELO": model}), encoding='utf-8')
                except Exception:
                    pass
            os.environ['GEMINI_MODELO']=model
            st.session_state['GEMINI_MODELO'] = model
            st.success('Configuración cargada y guardada de forma segura. Ve al Asistente.')
        st.caption('También se admite GEMINI_API_KEY como variable de entorno. No envíes tu clave por el chat. Usa esta instancia para tu trabajo individual.')

    with st.expander('Diagnóstico de recursos',expanded=False):
        try:
            st.write('Grupos:',len(data),'· perfiles docentes:',len(C.profiles()))
            st.write('Tablas plantilla:',C.motor.comprobar_plantilla(C.RES))
        except Exception as e:
            st.error(str(e))
        try:
            tables=C.sisae_bytes((C.RES/'SISAE.zip').read_bytes())
            st.write('SISAE · grupos:',len(tables['PROG_CURSOS1.DBF']),'· inscripciones:',len(tables['INSCRIPCION.DBF']))
        except Exception as e:
            st.error(str(e))

elif nav=='Respaldos':
    st.write('El trabajo se guarda en la carpeta datos: SQLite, recursos, versiones y documentos. Cerrar el navegador no borra esos archivos de Cloud Shell.')
    if st.button('Preparar respaldo completo de datos'):
        st.session_state['backup']=C.backup()
    if 'backup' in st.session_state:
        st.download_button('Descargar respaldo',st.session_state['backup'],file_name='ATRIO_RESPALDO_DATOS.zip')
    st.warning('No reemplaces la carpeta datos al actualizar el código. Conserva una descarga de respaldo antes de cada actualización.')

# ---------------- ASISTENTE FLOTANTE ----------------
st.markdown("""
<style>
div[class*="st-key-btn_flotante_asistente"] { position: fixed !important; bottom: 30px !important; right: 30px !important; z-index: 99999 !important; width: 65px !important; height: 65px !important; }
div[class*="st-key-btn_flotante_asistente"] button { background: linear-gradient(135deg, #FF1493 0%, #C71585 100%) !important; color: white !important; border-radius: 50% !important; width: 65px !important; height: 65px !important; box-shadow: 0 6px 20px rgba(255,20,147,0.6) !important; border: 3px solid white !important; display: flex !important; align-items: center !important; justify-content: center !important; padding: 0 !important; transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important; }
div[class*="st-key-btn_flotante_asistente"] button:hover { transform: scale(1.15) !important; box-shadow: 0 8px 25px rgba(255,20,147,0.8) !important; border-color: #fff !important; }
div[class*="st-key-btn_flotante_asistente"] button p { font-size: 30px !important; margin: 0 !important; line-height: 1 !important; }
div[class*="st-key-mini_chat_container"] { position: fixed !important; bottom: 110px !important; right: 30px !important; width: 360px !important; height: 480px !important; z-index: 99998 !important; background: #fffdfa !important; border-radius: 15px !important; box-shadow: 0 10px 40px rgba(0,0,0,0.2) !important; padding: 20px !important; overflow-y: auto !important; border: 1px solid #e0d6cb !important; }
</style>
""", unsafe_allow_html=True)

if st.button("✨", key="btn_flotante_asistente", help="Abrir Asistente Rápido"):
    st.session_state['show_mini_chat'] = not st.session_state.get('show_mini_chat', False)

if st.session_state.get('show_mini_chat'):
    with st.container(key="mini_chat_container"):
        st.markdown("<h3 style='margin-top:0'>✨ Asistente Rápido</h3>", unsafe_allow_html=True)
        st.caption("Pregunta por tu **Agenda** o **Programación**")
        
        if "mini_chat_history" not in st.session_state:
            st.session_state.mini_chat_history = []
        
        for msg in st.session_state.mini_chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        with st.form("mini_chat_form", clear_on_submit=True):
            q = st.text_input("Tu consulta:", placeholder="Escribe aquí...")
            submit = st.form_submit_button("Preguntar")
            if submit and q:
                st.session_state.mini_chat_history.append({"role": "user", "content": q})
                ans = AI214.responder_local(q, data, C)
                if ans:
                    st.session_state.mini_chat_history.append({"role": "assistant", "content": ans})
                else:
                    st.session_state.mini_chat_history.append({"role": "assistant", "content": "No encontré eso localmente. Abre el Asistente Virtual completo."})
                st.rerun()
        
        if st.button("Cerrar Chat", key="close_mini", use_container_width=True):
            st.session_state['show_mini_chat'] = False
            st.rerun()