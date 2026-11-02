"""ATRIO 10.12.13 · Repositorio del ciclo vigente.
Adaptación documental a partir de Programación, usando EXACTAMENTE el motor fiel
pea_pdf_fiel_1012123; no escribe datos a Programación, Históricos ni MCE.
"""
from __future__ import annotations
import hashlib
import html
import io
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import streamlit as st
import centro as C
import especialidades_101211 as ESP
import pea_pdf_101212 as EXTRACT
import pea_pdf_fiel_1012123 as FIEL

OUT = C.OUT / 'pea_repositorio_actual'
MIME_WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
CSS = '''<style>
.r213 .eyebrow{font-size:10px;letter-spacing:.13em;font-weight:700;text-transform:uppercase;color:#aa8458}
.r213 h2{font-family:Georgia,serif!important;font-size:26px!important;color:#30232a;margin:2px 0 4px}
.r213 .sub{font-size:12px;color:#87737c;margin:0 0 10px}
.r213 .summary{display:flex;flex-wrap:wrap;gap:11px;padding:10px 13px;border:1px solid #eadcd5;
background:#fffbf8;border-radius:10px;font-size:12px;color:#503741;margin:8px 0 12px}
.r213 .summary strong{color:#66364a}
.r213 .tiny{font-size:11px;color:#89767a}
.r213 .steps{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin:9px 0 14px}
.r213 .step{border:1px solid #e8d6d4;border-radius:8px;background:#fffaf8;color:#6a5059;padding:7px 10px;font-size:11px}
.r213 .step.active{background:#35262c;color:#fff;border-color:#bd9472}
</style>'''


def _esc(t):
    return html.escape(str(t or ''))


def _db():
    db=C.connect()
    db.execute('''CREATE TABLE IF NOT EXISTS pea_repo_actual_101213 (
       id TEXT PRIMARY KEY, group_id TEXT NOT NULL, group_fingerprint TEXT NOT NULL,
       ciclo TEXT NOT NULL, docente TEXT NOT NULL, curso TEXT NOT NULL,
       horas_pdf REAL NOT NULL, participantes INTEGER NOT NULL,
       pdf_original TEXT NOT NULL, pdf_adaptado TEXT NOT NULL, word_controlado TEXT NOT NULL,
       reporte TEXT NOT NULL, creado TEXT NOT NULL, estado TEXT NOT NULL)''')
    return db


def _cycle():
    # Ciclo consultado al abrir; los registros guardan la etiqueta con que fueron creados.
    d=datetime.now(ZoneInfo("America/Mexico_City"))
    start=d.year if d.month>=7 else d.year-1
    return f'{start}–{start+1}'


def _days_from_program(text):
    raw=str(text or '')
    norm=C.motor.normal(raw)
    days='lunes martes miercoles jueves viernes sabado domingo'.split()
    # Solo deducir cuando hay días literales explícitos; nunca inventar.
    found=[day for day in days if re.search(r'\b'+day+r'\b',norm)]
    pair=re.search(r'\b('+'|'.join(days)+r')\s+a\s+('+'|'.join(days)+r')\b',norm)
    if pair:
        a,b=days.index(pair.group(1)),days.index(pair.group(2))
        if a<=b:found=days[a:b+1]
    accents={'miercoles':'miércoles','sabado':'sábado'}
    return ', '.join(accents.get(day,day).capitalize() for day in found)


def _hours_from_program(text):
    parts=re.findall(r'(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)',str(text or ''))
    if len(parts)<2:return ''
    return ' a '.join(parts[:2])


def _profiles(teacher):
    try:return C.profiles().get(C.motor.normal(teacher),{})
    except Exception:return {}


def _default_specialty(group):
    v=str(group.get('especialidad_programada') or '').strip()
    catalog=ESP.CATALOGO
    found=next((k for k in catalog if ESP._norm(k)==ESP._norm(v)),None)
    return found or ''


def _date(iso):
    try:return date.fromisoformat(str(iso)).strftime('%d/%m/%Y')
    except (TypeError,ValueError):return ''


def _fingerprint(pdf,data,group):
    info=[hashlib.sha256(pdf).hexdigest(),group['id'],group.get('fingerprint'),data]
    return hashlib.sha256(json.dumps(info,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def _safe_file(rel):
    path=(C.ROOT/rel).resolve()
    if OUT.resolve() not in path.parents or not path.is_file():
        raise ValueError('Archivo no disponible o fuera de la carpeta de Repositorio vigente.')
    return path


def _download(label,relative,key):
    try:
        path=_safe_file(relative)
        st.download_button(label,path.read_bytes(),file_name=path.name,
              mime='application/pdf' if path.suffix.lower()=='.pdf' else ('application/json' if path.suffix.lower()=='.json' else MIME_WORD),
              key=key,use_container_width=True)
    except (OSError,ValueError) as exc:st.error(str(exc))


def _save_new(group,pdf_source,preview,data,meta):
    """Separación física + DB por group_id: NO escribe pea_hist_101212."""
    uid=str(uuid.uuid4())
    folder=OUT/group['id']/uid
    folder.mkdir(parents=True,exist_ok=False)
    files={
        'pdf_original':'PEA_ORIGINAL.pdf',
        'pdf_adaptado':'PEA_ADAPTADO.pdf',
        'word_controlado':'PEA_CONTROLADO.docx',
        'reporte':'CONTROL_ADAPTACION.json'}
    payload={**data,'curso_pdf':meta['curso'],'duracion_pdf':meta['horas'],
             'grupo_id':group['id'],'grupo_fingerprint':group['fingerprint'],
             'origen':'Repositorio del ciclo vigente','revision':'PENDIENTE_REVISION_VISUAL',
             'reporte_motor':preview['report']}
    contents={
       'pdf_original':pdf_source,
       'pdf_adaptado':preview['pdf'],
       'word_controlado':preview['word'],
       'reporte':json.dumps(payload,ensure_ascii=False,indent=2,default=str).encode()}
    paths={k:str((folder/name).relative_to(C.ROOT)) for k,name in files.items()}
    try:
        for key,name in files.items():
            content=contents[key]
            if not content:raise ValueError('Falta archivo de salida: '+key)
            tmp=folder/(name+'.part')
            tmp.write_bytes(content)
            os.replace(tmp,folder/name)
        with _db() as db:
            db.execute('INSERT INTO pea_repo_actual_101213 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
                uid,group['id'],group['fingerprint'],_cycle(),group['hoja'],group['nombre'],
                float(meta['horas']),int(data['participantes']),paths['pdf_original'],
                paths['pdf_adaptado'],paths['word_controlado'],paths['reporte'],C.now(),
                'Borrador pendiente de revisión'))
    except Exception:
        import shutil
        shutil.rmtree(folder,ignore_errors=True)
        raise
    try:C.event(group['id'],'PEA Repositorio adaptado; pendiente de revisión',{'expediente':uid,'pdf_sha256':hashlib.sha256(pdf_source).hexdigest()})
    except Exception:pass
    return uid


def panel(g):
    """UI de Repositorio bajo Preparar PEA, sin tocar el asistente de Extensión."""
    if g.get('tipo')!='Repositorio':
        st.error('Este flujo solo está disponible para cursos tipo Repositorio.');return
    st.markdown(CSS,unsafe_allow_html=True)
    st.markdown('''<div class="r213"><div class="eyebrow">Jefatura de Capacitación · CECATI 31</div>
    <h2>Preparar PEA</h2><p class="sub">Repositorio · Adaptación del PDF oficial · Ciclo vigente</p>
    <div class="steps"><span class="step active">1 · Curso</span><span class="step">2 · Datos</span>
    <span class="step">3 · Vista previa</span><span class="step">4 · Guardar</span></div></div>''',unsafe_allow_html=True)
    st.markdown(f'''<div class="r213"><div class="summary"><span><strong>Docente:</strong> {_esc(g['hoja'])}</span>
    <span><strong>Curso:</strong> {_esc(g['nombre'])}</span><span><strong>{g['duracion']:g} h</strong></span>
    <span>{_esc(_date(g['inicio']))} – {_esc(_date(g['fin']))}</span>
    <span>Repositorio · Programación</span></div></div>''',unsafe_allow_html=True)
    if st.button('← Volver a cursos',key='r213_back'):
        st.session_state.pop('pea110_stage',None)
        st.session_state.pop('editor_group',None)
        st.session_state['jump']='Preparar PEA';st.rerun()
    source_file=st.file_uploader('PDF oficial del Repositorio',type=['pdf'],key='r213_source_'+g['id'])
    source=source_file.getvalue() if source_file else b''
    if not source:
        st.caption('Selecciona el PDF autorizado del curso; se conservará sin modificaciones.')
        return
    if len(source)>25*1024*1024:
        st.error('El PDF supera el máximo de 25 MB.');return
    try:meta=EXTRACT.inspeccionar(source)
    except Exception as exc:
        st.error('No se pudo leer el PDF: '+str(exc));return
    if not meta.get('curso') or not meta.get('horas') or meta.get('participantes') is None:
        st.error('No se reconocen nombre, duración o participantes del PDF. No se generará el PEA.');return
    st.caption(f"PDF original · {meta['curso']} · {meta['horas']:g} horas · {meta['participantes']} participante(s) · {meta['paginas']} páginas")
    # La coincidencia evita relacionar un expediente académico con un grupo distinto.
    matches=(C.motor.normal(str(meta['curso']))==C.motor.normal(str(g['nombre'])))
    hours_same=(abs(float(meta['horas'])-float(g['duracion']))<.01)
    if not matches or not hours_same:
        with st.expander('Diferencias entre PDF y Programación · revisar',expanded=True):
            st.write('PDF: **'+str(meta['curso'])+'** · '+f"{float(meta['horas']):g} h")
            st.write('Programación: **'+str(g['nombre'])+'** · '+f"{g['duracion']:g} h")
            st.warning('El contenido y las horas del PDF están protegidos. Para evitar vincular documentos incorrectos, selecciona un PDF correspondiente a este grupo. No se modifica Programación.')
        return
    if int(meta['paginas'])!=17:
        st.warning('Este adaptador está calibrado para la familia oficial de 17 páginas utilizada en la prueba. No puede editar de forma segura esta estructura diferente.');return
    profile=_profiles(g['hoja'])
    a,b,c=st.columns(3,gap='small')
    curp=a.text_input('16 · CURP',value=str(profile.get('curp') or ''),key='r213_curp_'+g['id'])
    tel=b.text_input('16 · Teléfono',value=str(profile.get('telefono') or ''),key='r213_tel_'+g['id'])
    mail=c.text_input('16 · Correo',value=str(profile.get('correo') or ''),key='r213_mail_'+g['id'])
    t0=str(profile.get('tipo') or '').strip().lower()
    typ=st.radio('17 · Tipo de docente',('Interno','Externo'),index=1 if 'extern' in t0 else 0,
                 horizontal=True,key='r213_typ_'+g['id'])
    choices=['Seleccionar especialidad']+[s for s in ESP.CATALOGO]
    selected_specialty=_default_specialty(g)
    sx=choices.index(selected_specialty) if selected_specialty in choices else 0
    special=st.selectbox('Especialidad del curso',choices,index=sx,key='r213_special_'+g['id'])
    c1,c2,c3=st.columns(3,gap='small')
    count_guess=g.get('poblacion')
    try:count_guess=int(float(count_guess))
    except (TypeError,ValueError):count_guess=0
    pdf_token=hashlib.sha256(source).hexdigest()[:10]
    participants=c1.number_input('10 · Participantes',min_value=1,max_value=9999,
              value=min(9999,count_guess) if count_guess>0 else max(1,min(9999,int(meta['participantes']))),step=1,
              key='r213_count_'+g['id']+'_'+pdf_token)
    days=c2.text_input('12 · Días de impartición',value=_days_from_program(g.get('horario','')),key='r213_days_'+g['id'])
    horario=c3.text_input('11 · Horario',value=_hours_from_program(g.get('horario','')),key='r213_hours_'+g['id'])
    a,b,c=st.columns([1,1,1.3],gap='small')
    start=a.text_input('14 · Fecha inicio',value=_date(g.get('inicio')),key='r213_ini_'+g['id'])
    end=b.text_input('14 · Fecha término',value=_date(g.get('fin')),key='r213_fin_'+g['id'])
    sede=c.text_input('Sede',value=str(g.get('aula') or 'CECATI N.º 31'),key='r213_sede_'+g['id'])
    col1,col2=st.columns([1,1.4],gap='small')
    modality=col1.radio('13 · Lugar de impartición',('CECATI','Acción móvil'),horizontal=True,key='r213_modality_'+g['id'])
    ubicacion=col2.text_input('Municipio y entidad',value='Coatzacoalcos, Veracruz',key='r213_location_'+g['id'])
    with st.expander('Datos adicionales del formulario · opciones administrativas',expanded=False):
        x,y=st.columns(2,gap='small')
        publico=x.text_input('4 · Con quién',value='Estudiantes',key='r213_public_'+g['id'])
        servicio=y.radio('3 · Tipo de servicio (en el PDF)',('CE','CAE'),horizontal=True,key='r213_service_'+g['id'])
        perfiles=['Estudiantes','Empleados','Autoempleado','Grupos en desventaja social y/o económica','Jubilados','Adultos mayores','Desempleados','Personas con discapacidad']
        perfil_usuario=st.multiselect('5 · Perfil de usuario',perfiles,default=['Estudiantes','Autoempleado','Desempleados'],key='r213_pusuarios_'+g['id'])
        st.caption('El formato original indica seleccionar solo una opción, pero el PDF de muestra trae varias. Comprueba la selección.')
        norma=st.radio('7 · Normalización asociada',('NO','SI'),horizontal=True,key='r213_norma_'+g['id'])
        x,y=st.columns([1,2],gap='small')
        norm_code=x.text_input('8 · Código EC o norma',key='r213_nc_'+g['id'])
        norm_name=y.text_input('8 · Nombre de norma',key='r213_nn_'+g['id'])
        code=st.text_input('Clave del curso, si existe',key='r213_code_'+g['id'])
    with st.expander('Validación académica · autoridades del ciclo vigente',expanded=False):
        a,b,c=st.columns(3,gap='small')
        valida=a.text_input('Valida',value=C.motor.AUTORIDAD_VALIDA,key='r213_valida_'+g['id'])
        visto=b.text_input('Vo. Bo.',value=C.motor.AUTORIDAD_VISTO,key='r213_visto_'+g['id'])
        autoriza=c.text_input('Autoriza',value=C.motor.AUTORIDAD_AUTORIZA,key='r213_autor_'+g['id'])
        aprueba=st.text_input('Aprueba (si corresponde)',key='r213_aprueba_'+g['id'])
        st.caption('No se insertarán imágenes de firma. Confirma nombres y cargos antes de emitir.')
    data={'docente':g['hoja'],'curso':g['nombre'],'especialidad':special,'duracion':float(meta['horas']),
          'participantes':int(participants),'ciclo':_cycle(),'curp':curp.strip(),
          'telefono':tel.strip(),'correo':mail.strip(),'tipo_docente':typ,
          'inicio':start.strip(),'fin':end.strip(),'dias':days.strip(),'horario':horario.strip(),
          'sede':sede.strip(),'ubicacion':ubicacion.strip(),'modalidad_sede':modality,
          'con_quien':publico.strip(),'servicio_pdf':servicio,'perfiles_usuario':perfil_usuario,
          'normalizacion':norma,'norma_codigo':norm_code.strip(),'norma_nombre':norm_name.strip(),
          'clave_curso':code.strip(),'valida':valida.strip(),'visto':visto.strip(),
          'autoriza':autoriza.strip(),'aprueba':aprueba.strip()}
    view_key=_fingerprint(source,data,g)
    prev_key='r213_preview_'+g['id']
    preview=st.session_state.get(prev_key)
    if st.button('1 · Preparar vista previa fiel',key='r213_preview_button_'+g['id'],type='primary'):
        try:
            mandatory=('curp','telefono','correo','especialidad','dias','horario','inicio','fin','sede','ubicacion','valida','visto','autoriza')
            missing=[x for x in mandatory if not str(data.get(x) or '').strip() or data.get(x)=='Seleccionar especialidad']
            if missing:raise ValueError('Faltan datos visibles: '+', '.join(missing))
            for field in ('inicio','fin'):
                datetime.strptime(data[field],'%d/%m/%Y')
            if data['normalizacion']=='SI' and (not data['norma_codigo'] or not data['norma_nombre']):
                raise ValueError('Completa el código y nombre de la norma cuando la normalización es Sí.')
            with st.spinner('Protegiendo hojas y tablas del documento oficial…'):
                pdf,word,report=FIEL.adaptar_pdf(source,data,crear_word=True)
            if not word or not pdf:raise ValueError('No fue posible producir ambos documentos.')
            st.session_state[prev_key]={'key':view_key,'pdf':pdf,'word':word,'report':report}
            preview=st.session_state[prev_key]
            st.success('Vista previa lista. Comprueba las páginas antes de guardar.')
        except (ValueError,OSError,RuntimeError,FIEL.ErrorAdaptacion) as exc:
            st.session_state.pop(prev_key,None);preview=None
            st.error(str(exc))
    if preview and preview.get('key')==view_key:
        with st.expander('Vista previa · páginas modificadas',expanded=True):
            pg=st.selectbox('Página',[2,3,4,5,17],format_func=lambda n:'Página '+str(n),key='r213_pag_'+g['id'])
            import fitz
            with fitz.open(stream=preview['pdf'],filetype='pdf') as document:
                pix=document[pg-1].get_pixmap(matrix=fitz.Matrix(1.05,1.05),alpha=False)
                st.image(pix.tobytes('png'),use_container_width=True)
            st.caption('PDF fiel al formato · Word híbrido con contenido académico no editable.')
        if st.button('2 · Confirmar y guardar en Mis PEA',type='primary',key='r213_save_'+g['id']):
            try:
                uid=_save_new(g,source,preview,data,meta)
                st.session_state['r213_last_'+g['id']]=uid
                st.success('PDF y Word guardados en Mis PEA → Generados · Repositorio actual. Pendientes de revisión, sin marcar MCE.')
            except (ValueError,OSError,sqlite3.Error) as exc:st.error('No se pudo guardar: '+str(exc))
    elif preview:
        st.caption('Cambió algún dato. Prepara una nueva vista previa antes de guardar.')
    if st.session_state.get('r213_last_'+g['id']):
        st.caption('Consulta los archivos del expediente en Mis PEA → Generados.')


def panel_mis_actuales():
    """Se inserta bajo Generados, sin crear pestañas nuevas ni mezclar Históricos."""
    try:
        with _db() as db: rows=[dict(x) for x in db.execute('SELECT * FROM pea_repo_actual_101213 ORDER BY creado DESC')]
    except sqlite3.Error as exc:
        st.error('No se pudo consultar Repositorios: '+str(exc));return
    st.markdown('**Repositorio · Documentos adaptados del ciclo actual**')
    if not rows:
        st.caption('Todavía no hay PDF de Repositorio adaptados para el ciclo vigente.');return
    current={g['id']:g for g in C.groups()}
    col1,col2=st.columns([1,2],gap='small')
    cycles=['Todos']+sorted({r['ciclo'] for r in rows},reverse=True)
    cy=col1.selectbox('Ciclo',cycles,key='r213_mis_cycle')
    q=col2.text_input('Buscar curso o docente',key='r213_mis_search').casefold().strip()
    visible=[r for r in rows if (cy=='Todos' or r['ciclo']==cy) and (not q or q in (r['curso']+' '+r['docente']).casefold())]
    for row in visible[:100]:
        with st.expander(row['curso']+' · '+row['docente']+' · '+row['creado'][:10],expanded=False):
            st.caption('Repositorio · '+row['ciclo']+' · '+row['estado'])
            if current.get(row['group_id'],{}).get('fingerprint')!=row['group_fingerprint']:
                st.warning('La programación de este grupo cambió desde que se elaboró este borrador. Comprueba los datos antes de utilizarlo.')
            cols=st.columns(4,gap='small')
            for col,(label,field) in zip(cols,[('↓ PDF adaptado','pdf_adaptado'),('↓ Word controlado','word_controlado'),('↓ PDF original','pdf_original'),('↓ Registro','reporte')]):
                with col:_download(label,row[field],'r213_dl_'+field+'_'+row['id'])
