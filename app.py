from pathlib import Path
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import html, json, os
import streamlit as st
import centro as C
import trabajos as J
import interfaz as UI
import tema
import hojas
import orden_menu as OM
import acm_oficios as ACM
import salida
import pea_biblioteca_109 as P109
import pea_wizard_112 as F112
import pea_historicos_101212 as H1212
import revisor_pea_112 as R112
import asistente_atrio_101214 as AI214
import acceso as AC
import calendario as CAL
import pendientes as PEND
import reprogramacion as REPRO
import adaptar_pdf as ADP
import asistente_flotante as FLOT
def safe_error(exc):
 key=os.getenv('GEMINI_API_KEY')
 return str(exc).replace(key,'[CLAVE OCULTA]') if key else str(exc)
st.set_page_config(page_title='ATRIO · Capacitación',page_icon='◈',layout='wide')
# Tema claro Editorial Rosa (fondo hueso). Migración única: el tema guardado pasa a Editorial Rosa.
DARK=False
if not C.setting('tema_migrado_claro',False):
 C.set_setting('tema_visual',tema.DEFECTO)
 C.set_setting('tema_migrado_claro',True)
# La paleta de Órbita se conserva en Ajustes y se previsualiza en vivo desde los color pickers.
_PALETA_KEY_PREFIX = '_atrio_orbita_paleta_'
_paleta_base = tema.paleta_predeterminada()
_paleta_guardada = tema.validar_paleta(C.setting('tema_paleta_personalizada',{}))
for _campo, _valor in _paleta_base.items():
 st.session_state.setdefault(_PALETA_KEY_PREFIX + _campo, _paleta_guardada.get(_campo,_valor))
_paleta_previa = {
 _campo: st.session_state.get(_PALETA_KEY_PREFIX + _campo,_valor)
 for _campo,_valor in _paleta_base.items()
}
tema.fijar(C.setting('tema_visual',tema.DEFECTO),_paleta_previa)
UI.theme(DARK)
AC.exigir()  # Acceso privado: nada se muestra antes de la contraseña.
try:
 if not C.groups():C.import_program(C.RES/'PROGRAMACION DE CURSOS.xlsx')
except FileNotFoundError as e:
 st.error('Falta el archivo PROGRAMACION DE CURSOS.xlsx. Por favor, súbelo en Ajustes · Recursos.')
except Exception as e:
 st.error(f'No se pudo leer la programación: {safe_error(e)}. Revisa el archivo en Ajustes · Recursos; la aplicación sigue disponible.')
a=tema.PRESETS[tema.activo()]['accent'];b=tema.PRESETS[tema.activo()]['gold']
PAGES=['Inicio','Programación','Mi Calendario','Pendientes','Reprogramación','Adaptar PDF','Acciones Móviles','Preparar PEA','PEA históricos','Seguimiento y MCE','Control escolar','Constancias y folios','Excel para MCE','Mis PEA','SISAE · Cortes','Auditoría histórica','Evaluación trimestral','Revisor','Asistente virtual','Ajustes','Respaldos']
if 'jump' in st.session_state:st.session_state['_atrio_pagina_actual']=st.session_state.pop('jump')
UI._ICONOS_MENU['Asistente virtual']=':material/auto_awesome:'
nav=UI.menu_visual(OM.orden_actual(PAGES,C.setting('orden_menu',[])))
if nav=='Preparar PEA' and st.session_state.get('pea110_stage') in ('validacion','contenido','salida'):
 nav='Preparar documento'  # Subetapa integrada: el menú sigue resaltando Preparar PEA.
today=datetime.now(ZoneInfo('America/Mexico_City')).date();data=C.groups();data_operativos=C.operational_groups(data)
query=st.text_input('Buscar curso, docente o acción',placeholder='PEA, calendario, nombre…',key='atrio_buscador')
if query:
 actions={'Generar PEA':'Preparar PEA','Alta de regulares y exportación MCE':'Seguimiento y MCE','Subir ZIP SISAE':'SISAE · Cortes','Cambiar calendario y días inhábiles':'Ajustes','Actualizar plantilla Word':'Ajustes','Editar perfil docente':'Ajustes','Cambiar colores de títulos':'Ajustes','Descargar respaldo':'Respaldos'}
 for label,target in actions.items():
  if C.motor.normal(query) in C.motor.normal(label):
   if st.button(label,key='search_action_'+label):st.session_state['jump']=target;st.rerun()
 hits=[g for g in data_operativos if C.motor.normal(query) in C.motor.normal(g['nombre']+' '+g['hoja'])]
 if hits:
  found=st.selectbox('Resultados',hits,format_func=lambda g:f"{g['hoja']} · {g['nombre']} · {g['inicio']}")
  if st.button('Abrir curso'):
   st.session_state['selected']=found['id'];st.session_state['teacher']=found['hoja'];st.session_state['editor_group']=found['id'];st.session_state['pea110_stage']='contenido';st.session_state['jump']='Preparar PEA';st.rerun()
alerts=[]  # El seguimiento se concentra en Inicio y Centro de Pendientes.
if nav not in ('Inicio','Programación','Mi Calendario','Pendientes','Reprogramación','Adaptar PDF','Acciones Móviles','Preparar PEA','PEA históricos','Preparar documento','Seguimiento y MCE','Control escolar','Constancias y folios','Revisor','Asistente virtual','Auditoría histórica'):UI.heading(nav,a,b)
def show_group(g):
 st.subheader(g['nombre']);st.caption(f"{g['hoja']} · {g['tipo']} · {g['duracion']:g} horas")
 st.write(f"Inicio: {UI.fecha(g['inicio'])} · Término: {UI.fecha(g['fin'])}")
 st.write('Días y horario: '+g['horario'])

def select_group(key='select'):
 teachers=sorted({g['hoja'] for g in data});teacher=st.selectbox('Docente',teachers,index=teachers.index(st.session_state.get('teacher')) if st.session_state.get('teacher') in teachers else 0,key=key+'_teacher')
 rows=sorted([g for g in data if g['hoja']==teacher],key=lambda g:g['inicio']);ids=[g['id'] for g in rows]
 chosen=st.selectbox('Curso · todos los tipos',rows,index=ids.index(st.session_state.get('selected')) if st.session_state.get('selected') in ids else 0,format_func=lambda g:f"{g['nombre']} · {g['tipo']} · {g['inicio']} → {g['fin']} · {g['horario']}",key=key+'_group')
 return chosen

if nav=='Inicio':
 UI.home(data_operativos,alerts,DARK,a,b,today)

elif nav in ('Programación','Preparar PEA','Control escolar','Constancias y folios','Seguimiento y MCE'):
 number={'Programación':2,'Preparar PEA':3,'Seguimiento y MCE':3,'Control escolar':4,'Constancias y folios':5}[nav]
 hojas.show(number,data_operativos if nav=='Preparar PEA' else data,today,tracking=nav=='Seguimiento y MCE')

elif nav=='PEA históricos':
 H1212.panel_historicos()

elif nav=='Mi Calendario':
 CAL.render_calendario()

elif nav=='Pendientes':
 PEND.render_pendientes(data_operativos,today)

elif nav=='Reprogramación':
 REPRO.render_reprogramacion(data,today)

elif nav=='Adaptar PDF':
 ADP.panel()

elif nav=='Preparar documento':
 UI.heading('Preparar PEA',a,b)
 uid=st.session_state.get('editor_group')
 g=next((x for x in data_operativos if x['id']==uid),None)
 if g is None:
  st.info('Selecciona primero un docente y un curso en Preparar PEA.')
  if st.button('Abrir selección de cursos',key='pea111_open'):
   st.session_state.pop('pea110_stage',None)
   st.session_state['jump']='Preparar PEA';st.rerun()
 else:F112.panel(g)

elif nav=='Acciones Móviles':
 ACM.panel_oficios(data,C)  # El encabezado se dibuja arriba, una sola vez.

elif nav=='Revisor':
 R112.panel(data)

elif nav=='Asistente virtual':
 AI214.panel(data,C)

elif nav=='Excel para MCE':
 g=select_group('mce03');show_group(g);salida.present(g)

elif nav=='Mis PEA':
 P109.panel_mis_pea(J,data)

elif nav=='Evaluación trimestral':
 import evaluacion_sisae as ES
 ES.panel()

elif nav=='SISAE · Cortes':
 import cortes
 cortes.panel()

elif nav=='Auditoría histórica':
 import modulo_auditoria_sisae as AUD
 AUD.render_auditoria_sisae()

elif nav=='Ajustes':
 OM.panel_ajustes(PAGES,C)
 if st.session_state.pop('_atrio_orbita_palette_saved',False):
  st.success('Paleta guardada y ATRIO Órbita aplicado.')
 with st.expander('Instituciones y sedes ACM · Catálogo editable',expanded=False):
  ACM.panel_catalogo(C)
 if st.button('Actualizar o comparar respaldos SISAE →'):st.session_state['jump']='SISAE · Cortes';st.rerun()
 with st.expander('Recursos · archivos y plantillas con respaldo',expanded=False):
  st.caption('Al actualizar un recurso se conserva su versión anterior. Los tres oficios ACM mantienen sus formatos independientes.')
  resources={'Programación':'PROGRAMACION DE CURSOS.xlsx','Padrón docente':'Plantilla_Datos_Docentes_PEA_CECATI31.xlsx','Plantilla PEA institucional':'PEA_final en blanco.docx','Días inhábiles · JSON':'DIAS_SIN_CLASE.json','Hoja membretada · Word':'MEMBRETE.docx','Calendario oficial · PDF':'CALENDARIO.pdf',
  'ACM · Oficio de Presentación':'acm:Presentación','ACM · Oficio de Vinculación':'acm:Vinculación','ACM · Oficio de Asignación':'acm:Asignación'}
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
     result=C.save_resource(filename,upload.getvalue());st.success('Recurso guardado con respaldo anterior.')
     if result:st.write(f'{result[0]} grupos importados');st.write(result[1])
   except Exception as e:st.error(f'No se reemplazó el recurso: {e}')
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
    if es_ruta_windows:st.caption('Firma: referencia antigua de Windows. Cloud Shell no puede leerla. Puedes subir la imagen JPG/PNG cuando quieras.')
    else:st.caption('Firma: archivo asociado al docente. Su aplicación en documentos requiere autorización expresa.')
   else:st.caption('Firma: todavía no hay una imagen asociada.')
   st.caption('La columna H del Padrón conserva la referencia de autorización existente, pero no autoriza automáticamente nuevos PEA.')
   import especialidades_101211 as E211
   sugeridas,problema=E211.sugerencias_docente(C.RES/'PROGRAMACION DE CURSOS.xlsx',person)
   guardada=str(existing.get('especialidad') or '').strip()
   if problema:st.caption(problema+' Puedes elegir del catálogo.')
   elif len(sugeridas)==1:
    st.caption('Programación propone: '+sugeridas[0]+'. Se guardará únicamente al confirmar el perfil.')
   elif len(sugeridas)>1:
    st.caption('Programación muestra varias especialidades para este docente: '+', '.join(sugeridas)+'. Elige la correspondiente.')
   else:st.caption('No se identificó una especialidad inequívoca en Programación; selecciona una del catálogo.')
   opciones_esp=['— Seleccionar especialidad —']+E211.opciones(guardada,sugeridas)
   if guardada and guardada in opciones_esp:
    especialidad_inicial=guardada
   elif len(sugeridas)==1:especialidad_inicial=sugeridas[0]
   else:especialidad_inicial=opciones_esp[0]
   with st.form('profile'):
    values={k:st.text_input(label,str(existing.get(k,'') or '')) for k,label in [('curp','CURP docente'),('correo','Correo docente'),('telefono','Teléfono docente'),('tipo','Tipo de docente')]}
    especialidad_seleccionada=st.selectbox('Especialidad docente',opciones_esp,index=opciones_esp.index(especialidad_inicial),key='esp_docente_101211_'+C.motor.normal(person),help='Sugerencias tomadas del Excel de Programación. Puedes elegir otra especialidad del catálogo.')
    values['especialidad']='' if especialidad_seleccionada==opciones_esp[0] else especialidad_seleccionada
    imagen=st.file_uploader('Actualizar imagen de firma (opcional)',type=['png','jpg','jpeg'],help='La firma se guardará en recursos protegidos y NO se insertará automáticamente en los PEA.')
    if st.form_submit_button('Guardar perfil docente'):
     try:
      if not values['especialidad']:raise ValueError('Selecciona la especialidad antes de guardar el perfil.')
      C.save_profile(person,values,imagen.getvalue() if imagen else None,Path(imagen.name).suffix.lower() if imagen else None)
      st.success('Perfil guardado. Especialidad y firma se mantienen en columnas independientes.')
     except Exception as e:st.error(str(e))
  else:st.caption('Aún no hay docentes de Programación disponibles.')
 with st.expander('Días inhábiles efectivos',expanded=False):
  dates=json.loads((C.RES/'DIAS_SIN_CLASE.json').read_text());text=st.text_area('Fechas excluidas · una AAAA-MM-DD por línea','\n'.join(dates),height=180)
  if st.button('Guardar fechas excluidas'):
   try:C.save_resource('DIAS_SIN_CLASE.json',json.dumps([x.strip() for x in text.splitlines() if x.strip()]).encode());st.success('Guardado; confirma el calendario después de revisarlo.')
   except Exception as e:st.error(str(e))
  checked=st.checkbox('Confirmo que estos días corresponden al calendario que usaré',value=C.setting('calendario_confirmado',False))
  if st.button('Guardar confirmación del calendario'):C.set_setting('calendario_confirmado',checked);st.success('Confirmación guardada.')
 with st.expander('Personalizar · Mi paleta',expanded=False):
  st.caption('Ajusta cuatro colores de ATRIO Órbita. Los cambios se previsualizan en vivo cuando ese tema está activo; la tipografía y las superficies de lectura se mantienen controladas para conservar el contraste.')
  if tema.activo()!=tema.ORBITA:
   st.info('Para ver los cambios en la aplicación, selecciona «ATRIO Órbita» en el apartado Autoridades y presentación.')
  if st.button('Restablecer paleta original de Órbita',key='orbita_palette_reset'):
   C.set_setting('tema_paleta_personalizada',{})
   for _campo in _paleta_base:
    st.session_state.pop(_PALETA_KEY_PREFIX + _campo,None)
   st.rerun()
  _cols_paleta=st.columns(4)
  _etiquetas_paleta=[
   ('fondo','Fondo general'),
   ('acento','Color principal'),
   ('secundario','Color secundario'),
   ('calendario','Calendario'),
  ]
  _paleta_borrador={}
  for _col,(_campo,_etiqueta) in zip(_cols_paleta,_etiquetas_paleta):
   with _col:
    _paleta_borrador[_campo]=st.color_picker(
     _etiqueta,
     value=st.session_state.get(_PALETA_KEY_PREFIX + _campo,_paleta_base[_campo]),
     key=_PALETA_KEY_PREFIX + _campo,
    )
  if st.button('Guardar paleta y aplicar ATRIO Órbita',key='orbita_palette_save',type='primary'):
   C.set_setting('tema_paleta_personalizada',tema.validar_paleta(_paleta_borrador))
   C.set_setting('tema_visual',tema.ORBITA)
   st.session_state['_atrio_orbita_palette_saved']=True
   st.rerun()
 with st.expander('Autoridades y presentación',expanded=False):
  with st.form('settings'):
   valida=st.text_input('Valida',C.setting('valida','Lila Inurreta Fernández'));visto=st.text_input('Visto bueno',C.setting('visto','Lila Inurreta Fernández'));autoriza=st.text_input('Autoriza',C.setting('autoriza','Sergio López Hernández'))
   tema_sel=st.selectbox('Tema visual',tema.OPCIONES,index=tema.OPCIONES.index(tema.activo()),help='Cambia colores de toda la aplicación. Se aplica al guardar.')
   deadline=st.number_input('Anticipación para aviso · días naturales',min_value=1,value=C.setting('deadline_days',11));anchor=st.selectbox('Referencia del plazo',['Inicio','Término'],index=0 if C.setting('deadline_anchor','Término')=='Inicio' else 1)
   if st.form_submit_button('Guardar ajustes'):
    for k,v in [('valida',valida),('visto',visto),('autoriza',autoriza),('tema_visual',tema_sel),('deadline_days',deadline),('deadline_anchor',anchor)]:C.set_setting(k,v)
    st.rerun()
 with st.expander('Servicio de contenido IA',expanded=False):
  key=st.text_input('Clave Gemini · solo memoria de esta sesión del servidor',type='password');model=st.text_input('Modelo Gemini',os.getenv('GEMINI_MODELO','gemini-2.5-flash'))
  if st.button('Usar configuración IA en esta sesión'):
   if key:os.environ['GEMINI_API_KEY']=key
   os.environ['GEMINI_MODELO']=model;st.success('Configuración cargada. No se escribe en el respaldo.')
  st.caption('También se admite GEMINI_API_KEY como variable de entorno. No envíes tu clave por el chat. Usa esta instancia para tu trabajo individual.')
 with st.expander('Diagnóstico de recursos',expanded=False):
  try:st.write('Grupos:',len(data),'· perfiles docentes:',len(C.profiles()));st.write('Tablas plantilla:',C.motor.comprobar_plantilla(C.RES))
  except Exception as e:st.error(str(e))
  try:
   tables=C.sisae_bytes((C.RES/'SISAE.zip').read_bytes());st.write('SISAE · grupos:',len(tables['PROG_CURSOS1.DBF']),'· inscripciones:',len(tables['INSCRIPCION.DBF']))
  except Exception as e:st.error(str(e))

elif nav=='Respaldos':
 st.write('El trabajo se guarda en la carpeta datos: SQLite, recursos, versiones y documentos. Cerrar el navegador no borra esos archivos de Cloud Shell.')
 if st.button('Preparar respaldo completo de datos'):st.session_state['backup']=C.backup()
 if 'backup' in st.session_state:st.download_button('Descargar respaldo',st.session_state['backup'],file_name='ATRIO_RESPALDO_DATOS.zip')
 st.warning('No reemplaces la carpeta datos al actualizar el código. Conserva una descarga de respaldo antes de cada actualización.')

# Asistente flotante global: una sola instancia, al final de la página.
FLOT.render()
