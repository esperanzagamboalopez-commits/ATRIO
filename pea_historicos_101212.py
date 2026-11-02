"""ATRIO 10.12.12 · PEA históricos exclusivamente (NO ciclo vigente).
Dos acciones: nuevo PEA Extensión o adaptación supervisada de PDF existente.
No modifica Programación, SISAE, Agenda, estatus MCE ni plantilla institucional.
"""
from __future__ import annotations
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
from tempfile import TemporaryDirectory
import hashlib, io, json, re, uuid, html
import streamlit as st
from docx import Document
import centro as C
import pea_pdf_101212 as PDF
import pea_pdf_fiel_1012123 as FIEL
import especialidades_101211 as ESP

HIST=C.OUT/'pea_historicos'

CSS='''<style>
.h1212 .eyebrow{font-size:11px;letter-spacing:.1em;color:#a17b55;text-transform:uppercase;font-weight:700}
.h1212 h2{font:normal 26px Georgia,serif!important;color:#3d2630;margin:2px 0 4px}
.h1212 .sub{font-size:12px;color:#77696d;margin-bottom:11px}
.h1212 .micro{font-size:12px;color:#734b5c;background:#fffaf8;border-bottom:1px solid #e7d9d7;padding:9px 0}
</style>'''


def _db():
    con=C.connect()
    con.execute('''CREATE TABLE IF NOT EXISTS pea_hist_101212 (
        id TEXT PRIMARY KEY,ciclo TEXT NOT NULL,accion TEXT NOT NULL,tipo TEXT NOT NULL,
        docente TEXT NOT NULL,curso TEXT NOT NULL,especialidad TEXT NOT NULL,
        duracion REAL NOT NULL,inicio TEXT,fin TEXT,horario TEXT,sede TEXT,
        participantes INTEGER,notas TEXT,creado TEXT,estado TEXT NOT NULL,
        pdf_path TEXT,word_path TEXT,academico_path TEXT,sha_pdf TEXT)''')
    return con


def _save(uid,name,raw):
    folder=HIST/uid;folder.mkdir(parents=True,exist_ok=True)
    path=folder/name
    if path.exists():raise ValueError('Esta versión ya existe; no se sobrescribirá.')
    tmp=path.with_suffix(path.suffix+'.part')
    try:tmp.write_bytes(raw);tmp.replace(path)
    finally:tmp.unlink(missing_ok=True)
    return str(path.relative_to(C.ROOT))


def _get_file(relative):
    path=(C.ROOT/relative).resolve()
    if HIST.resolve() not in path.parents or not path.is_file():
        raise ValueError('El archivo histórico no se encuentra disponible.')
    return path


def _download(label,relative,key):
    if not relative:return
    try:
        file=_get_file(relative)
        st.download_button(label,data=file.read_bytes(),file_name=file.name,
            mime=('application/pdf' if file.suffix.lower()=='.pdf' else ('application/json' if file.suffix.lower()=='.json' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')),key=key)
    except (OSError,ValueError) as e:st.caption(str(e))


def _current_cycle():
    d=datetime.now(ZoneInfo('America/Mexico_City'))
    return d.year if d.month>=7 else d.year-1


def _teachers():
    profiles=C.profiles()
    names={str(x.get('nombre') or '') for x in profiles.values() if x.get('nombre')}
    names.update(g['hoja'] for g in C.groups() if g.get('hoja'))
    return sorted([n for n in names if n],key=C.motor.normal)


def _profile(name):return C.profiles().get(C.motor.normal(name),{})


def _especialidad_pdf(raw):
    """Consulta el punto 6 del PDF, sin inferir especialidades por nombre del curso.
    Si el documento tiene otro formato, la selección permanece manual.
    """
    if not raw:
        return ''
    try:
        with PDF._fitz().open(stream=raw, filetype='pdf') as doc:
            if len(doc) < 2:
                return ''
            text=doc[1].get_text(sort=True)
        area=re.search(r'(?is)(?:^|\n)\s*6\.\s*PRECISE\b(.+?)(?=(?:^|\n)\s*7\.\s*)',text,re.M)
        if not area:
            return ''
        catalogo={ESP._norm(item):item for item in ESP.CATALOGO}
        found={catalogo[ESP._norm(line)] for line in area.group(1).splitlines() if ESP._norm(line) in catalogo}
        return next(iter(found)) if len(found)==1 else ''
    except Exception:
        # No convertir un error de detección en una elección ficticia.
        return ''


def _opciones_especialidad(profile, teacher, source, action):
    """Prioridad: especialidad explícita en PDF; luego perfil o Programación.
    Un docente puede impartir distintas especialidades, por eso el resultado
    siempre es seleccionable y nunca reescribe el Padrón.
    """
    from_pdf=_especialidad_pdf(source) if action=='Adaptar PDF existente' else ''
    programadas,aviso=ESP.sugerencias_docente(C.RES/'PROGRAMACION DE CURSOS.xlsx',teacher)
    guardada=str(profile.get('especialidad') or '').strip()
    if guardada and (re.search(r'[\\/]|\.(?:png|jpe?g)\b',guardada,re.I) or
                     ESP._norm(guardada) not in {ESP._norm(x) for x in ESP.CATALOGO}):
        guardada=''
    suggested=from_pdf or (guardada if action=='Crear PEA nuevo' else '') or (programadas[0] if len(programadas)==1 and action=='Crear PEA nuevo' else '')
    prioritized=[x for x in [from_pdf,*programadas] if x]
    options=ESP.opciones(guardada,prioritized)
    if suggested and suggested not in options:options.insert(0,suggested)
    choices=['Seleccionar especialidad']+[x for x in options if x]
    return choices, (choices.index(suggested) if suggested in choices else 0), from_pdf,programadas,aviso


def _date_literal(s):
    s=str(s or '').strip()
    if not s:return ''
    if not re.fullmatch(r'\d{2}/\d{2}/\d{4}',s):
        raise ValueError('Escribe las fechas registradas como DD/MM/AAAA. No se calculan ni modifican.')
    try:datetime.strptime(s,'%d/%m/%Y')
    except ValueError:raise ValueError('La fecha '+s+' no es válida como DD/MM/AAAA.')
    return s


def _validate(vals):
    needed=('docente','curso','especialidad','horario','dias','sede','inicio','fin')
    missing=[x for x in needed if not str(vals.get(x) or '').strip()]
    if missing:raise ValueError('Faltan datos del expediente: '+', '.join(missing))
    vals=dict(vals,inicio=_date_literal(vals['inicio']),fin=_date_literal(vals['fin']))
    if vals.get('participantes') is None or int(vals['participantes'])<1:raise ValueError('Verifica los participantes originales.')
    if float(vals['duracion'])<=0:raise ValueError('Verifica las horas oficiales.')
    return vals


def _validate_authorities(a):
    keys=('valida','visto','autoriza')
    missing=[k for k in keys if not str(a.get(k) or '').strip()]
    if missing:raise ValueError('Captura las autoridades que correspondían al ciclo histórico: '+', '.join(missing))
    return a


def _store(ciclo,accion,tipo,vals,nota,original,word,record,pdf_adaptado=None):
    if ciclo==f'{_current_cycle()}–{_current_cycle()+1}':
        raise ValueError('El ciclo vigente no puede guardarse en Históricos.')
    uid=str(uuid.uuid4())
    folder=HIST/uid
    try:
        pdf_path=_save(uid,'PEA_PDF_ORIGINAL.pdf',original) if original else ''
        word_path=_save(uid,'PEA_BORRADOR_EDITABLE.docx',word)
        if pdf_adaptado is not None:
            _save(uid,'PEA_PDF_ADAPTADO.pdf',pdf_adaptado)
        record_path=_save(uid,'DATOS_DE_CONTROL.json',json.dumps(record,ensure_ascii=False,indent=2,default=str).encode())
        with _db() as con:
            con.execute('''INSERT INTO pea_hist_101212 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (uid,ciclo,accion,tipo,vals['docente'],vals['curso'],vals['especialidad'],float(vals['duracion']),
               vals['inicio'],vals['fin'],vals['horario']+' · '+vals['dias'],vals['sede'],int(vals['participantes']),nota,
               C.now(),'Borrador pendiente de revisión',pdf_path,word_path,record_path,
               hashlib.sha256(original).hexdigest() if original else ''))
    except Exception:
        # No dejar documentos huérfanos si falla el guardado de metadatos.
        import shutil
        if folder.is_dir():shutil.rmtree(folder)
        raise
    return uid


def _generate(vals,authorities,academic=None):
    """Usa el motor oficial, sin incluir el grupo histórico en Programación.
    La generación IA requiere conexión Gemini configurada; no se inventa contenido.
    """
    # Datos administrativos capturados para el expediente histórico, sin alterar Padrón.
    profile=dict(_profile(vals['docente']) or {})
    profile.update(nombre=vals['docente'],curp=vals.get('curp',''),
                   correo=vals.get('correo',''),telefono=vals.get('telefono',''),
                   tipo=vals.get('tipo_docente') or profile.get('tipo') or '')
    missing=[k for k in ('curp','correo','telefono','tipo') if not str(profile.get(k) or '').strip()]
    if missing:raise ValueError('Faltan datos del docente visibles en este expediente: '+', '.join(missing))
    course=dict(hoja=vals['docente'],fila=0,nombre=vals['curso'],tipo='Extensión',
                duracion=float(vals['duracion']),inicio=datetime.strptime(vals['inicio'],'%d/%m/%Y').date().isoformat(),
                fin=datetime.strptime(vals['fin'],'%d/%m/%Y').date().isoformat(),
                horario=(vals['dias']+' '+vals['horario']),aula=vals['sede'],
                poblacion=int(vals['participantes']),especialidad_programada=vals['especialidad'],docente=profile)
    C.motor.comprobar_plantilla(C.RES)
    # Jamás usar autoridades actuales implícitamente para un documento histórico.
    C.motor.AUTORIDAD_VALIDA=authorities['valida']
    C.motor.AUTORIDAD_VISTO=authorities['visto']
    C.motor.AUTORIDAD_AUTORIZA=authorities['autoriza']
    with TemporaryDirectory(prefix='atrio_hist1212_') as temp:
        content=academic if academic is not None else C.motor.contenido_ia(course,C.RES,'gemini')
        edge=2 if course['duracion']>=40 else 1
        C.motor.validator(content,{'apertura':edge,'cierre':edge},course['duracion'])
        C.motor.qa_v7.validar_o_rechazar(content,course,{'apertura':edge,'cierre':edge})
        target=Path(temp)/'HISTORICO.docx'
        C.motor.crear_docx(course,content,C.RES,target,False)
        if len(Document(target).tables)!=28:raise ValueError('Falló la estructura institucional del Word. No se guardó.')
        return target.read_bytes(),content


def _archive():
    with _db() as con:rows=[dict(r) for r in con.execute('SELECT * FROM pea_hist_101212 ORDER BY creado DESC')]
    if not rows:
        st.caption('No hay PEA históricos guardados todavía.');return
    cycles=['Todos']+sorted({r['ciclo'] for r in rows},reverse=True)
    a,b=st.columns([1,2],gap='small')
    cyc=a.selectbox('Ciclo',cycles,key='h1212_archive_ciclo')
    query=b.text_input('Buscar curso o docente',key='h1212_archive_query').casefold().strip()
    filtered=[r for r in rows if (cyc=='Todos' or cyc==r['ciclo']) and
              (not query or query in (r['curso']+' '+r['docente']).casefold())]
    st.caption(f'{len(filtered)} expediente(s) de ciclos anteriores')
    for row in filtered[:100]:
        with st.expander(row['curso']+' · '+row['ciclo']+' · '+row['docente'],expanded=False):
            st.caption(f"{row['accion']} · {row['duracion']:g} horas · {row['estado']}")
            if row['notas']:st.caption(row['notas'])
            adapted=Path(row['word_path']).parent/'PEA_PDF_ADAPTADO.pdf' if row['word_path'] else None
            if adapted is not None and (C.ROOT/adapted).is_file():
                x,y,z,w=st.columns(4,gap='small')
                with x:_download('↓ PDF adaptado',str(adapted),'h1212_pdfnew_'+row['id'])
                with y:_download('↓ Word controlado',row['word_path'],'h1212_word_'+row['id'])
                with z:_download('↓ Original',row['pdf_path'],'h1212_pdf_'+row['id'])
                with w:_download('↓ Registro',row['academico_path'],'h1212_record_'+row['id'])
            else:
                x,y,z=st.columns(3,gap='small')
                with x:_download('↓ Word',row['word_path'],'h1212_word_'+row['id'])
                with y:_download('↓ PDF original',row['pdf_path'],'h1212_pdf_'+row['id'])
                with z:_download('↓ Registro',row['academico_path'],'h1212_record_'+row['id'])


def panel_mis_historicos():
    st.caption('Solo documentos de ciclos anteriores · sin alterar los pendientes del ciclo vigente.')
    _archive()


def panel_historicos():
    st.markdown(CSS,unsafe_allow_html=True)
    st.markdown('<div class="h1212"><div class="eyebrow">Jefatura de Capacitación · CECATI 31</div><h2>PEA históricos</h2><div class="sub">Crear uno nuevo o adaptar un PDF · Solo ciclos escolares anteriores</div></div>',unsafe_allow_html=True)
    a,b=st.columns([1,1.8],gap='small')
    current=_current_cycle()
    years=[f'{y}–{y+1}' for y in range(current-1,current-20,-1)]
    ciclo=a.selectbox('Ciclo escolar anterior',years,key='h1212_ciclo')
    action=b.radio('¿Qué necesitas hacer?',('Crear PEA nuevo','Adaptar PDF existente'),horizontal=True,key='h1212_action')
    people=_teachers()
    if not people:st.error('No se encontraron docentes en Padrón ni Programación.');return
    a,b=st.columns([1.2,1],gap='small')
    teacher=a.selectbox('Docente · Padrón y Programación',people,key='h1212_teacher')
    typ=b.selectbox('Tipo de curso',('Extensión','Repositorio'),key='h1212_tipo') if action=='Adaptar PDF existente' else 'Extensión'
    if action=='Crear PEA nuevo':b.caption('PEA nuevo · Extensión')
    profile=_profile(teacher)
    if profile:
        completos=[k for k in ('curp','correo','telefono','tipo') if str(profile.get(k) or '').strip()]
        if len(completos)==4:
            st.caption('Ficha del Padrón localizada · CURP, teléfono, correo y tipo recuperados automáticamente. Puedes corregirlos para este PEA sin modificar el Padrón.')
        else:
            st.caption('Ficha del Padrón localizada · completa únicamente los datos que aún no estén registrados.')
    else:
        st.caption('Este docente figura en Programación, pero no tiene ficha en el Padrón. Programación no incluye necesariamente CURP, teléfono y correo. Puedes completarlos aquí o registrar su perfil una sola vez en Ajustes.')
    # Los docentes también pueden provenir de Programación sin ficha completa en Padrón.
    # Por eso siempre ofrecemos la corrección local de sus datos, sin escribir en el Excel.
    st.caption('16 · Datos del docente para este expediente · precargados del Padrón cuando existen')
    perfil_estado=json.dumps([teacher]+[str(profile.get(k) or '') for k in ('curp','telefono','correo','tipo')],ensure_ascii=False)
    pkey=hashlib.sha256(perfil_estado.encode('utf-8')).hexdigest()[:10]
    c1,c2,c3=st.columns([1.2,1,1.5],gap='small')
    curp_doc=c1.text_input('CURP del docente',value=str(profile.get('curp') or ''),
        key='h1212_curp_'+pkey,placeholder='No disponible en el Padrón')
    tel_doc=c2.text_input('Teléfono del docente',value=str(profile.get('telefono') or ''),
        key='h1212_tel_'+pkey,placeholder='No disponible en el Padrón')
    mail_doc=c3.text_input('Correo del docente',value=str(profile.get('correo') or ''),
        key='h1212_mail_'+pkey,placeholder='No disponible en el Padrón')
    # El punto 17 del PDF es editable en CADA expediente, incluso cuando
    # el Padrón contiene el tipo de docente. Nunca se escribe al Padrón.
    tipo_padron=str(profile.get('tipo') or '').strip()
    tipo_inicial=next((op for op in ('Interno','Externo')
                        if op.casefold()==tipo_padron.casefold()),'Interno')
    tipo_doc=st.radio('17 · Tipo de docente (página 4)',('Interno','Externo'),
        index=('Interno','Externo').index(tipo_inicial),horizontal=True,
        key='h1212_p17_tipo_doc_'+pkey,
        help='Marca exclusivamente Interno o Externo en el punto 17 del PEA. '
             'Solo aplica a este expediente histórico: no cambia el Padrón ni el perfil del punto 15.')
    st.caption('Punto 17: ATRIO colocará la X en una sola casilla del PDF y del Word. '
               'Los datos del docente se aplican solo a este PEA; no modifican el Padrón.')
    source=None;metadata=None
    if action=='Adaptar PDF existente':
        up=st.file_uploader('PDF original del curso',type=['pdf'],key='h1212_pdf')
        if up is not None:
            source=up.getvalue()
            try:
                metadata=PDF.inspeccionar(source)
                if metadata['curso'] and metadata['horas'] and metadata['participantes'] is not None:
                    st.markdown(f"<div class='h1212 micro'><b>Del PDF original:</b> {html.escape(metadata['curso'])} · {metadata['horas']:g} horas · {metadata['participantes']} participante(s) · {metadata['paginas']} páginas</div>",unsafe_allow_html=True)
                else:st.warning('No se identificaron todos los datos protegidos: curso, duración y participantes. Revisa el PDF.')
                # El punto 15 se conserva como aparece en el PDF, sin edición.
                if not metadata.get('perfil_docente'):
                    st.caption('No se pudo reconocer el punto 15 en este PDF. Verifica el original antes de emitir el Word.')
            except (ValueError,RuntimeError) as e:st.error(str(e))
        course=(metadata or {}).get('curso','')
        hours=(metadata or {}).get('horas',0) or 0
        # La duración y el nombre son académicos y permanecen intactos;
        # el punto 10 se considera dato administrativo, editable por expediente.
        if metadata and metadata.get('participantes') is not None:
            src_key=hashlib.sha256(source or b'').hexdigest()[:12]
            c_part,c_original=st.columns([1,2],gap='small')
            count=c_part.number_input('10 · Número de participantes',min_value=1,max_value=9999,
                value=max(1,int(metadata['participantes'])),step=1,key='h1212_participantes_'+src_key)
            c_original.caption('En el PDF original: '+str(metadata['participantes'])+' participante(s). Ajusta solo si el expediente lo requiere.')
        else:
            count=0
            st.caption('Al subir el PDF, ATRIO recuperará el curso, las horas y el número de participantes.')
    else:
        a,b,c=st.columns([2,1,1],gap='small')
        course=a.text_input('Nombre del curso',key='h1212_course')
        hours=b.number_input('Horas oficiales',min_value=1.,max_value=1000.,value=60.,step=1.,key='h1212_hours')
        count=c.number_input('Participantes',min_value=1,max_value=9999,value=10,key='h1212_count')
    # El curso del PDF tiene prioridad respecto a la especialidad principal del docente.
    options,index,from_pdf,programadas,specialty_note=_opciones_especialidad(profile,teacher,source,action)
    a,b=st.columns([1.6,1],gap='small')
    source_id=hashlib.sha256(source).hexdigest()[:10] if source else 'sinpdf'
    selected=a.selectbox('Especialidad del curso',options,index=index,
        key='h1212_specialty_'+hashlib.sha256((teacher+'|'+action+'|'+source_id).encode()).hexdigest()[:14])
    specialization='' if selected=='Seleccionar especialidad' else selected
    sede=b.text_input('Sede registrada',value='CECATI N.º 31',key='h1212_sede')
    if from_pdf:
        st.caption('Especialidad recuperada del punto 6 del PDF; puedes seleccionarla o corregirla para este expediente.')
    elif len(programadas)==1 and action=='Crear PEA nuevo':
        st.caption('Especialidad sugerida desde Programación; puedes elegir otra del catálogo.')
    elif len(programadas)>1:
        st.caption('Este docente aparece en más de una especialidad en Programación; selecciona la correspondiente al curso.')
    elif specialty_note:
        st.caption('No fue posible consultar las especialidades de Programación. Selecciona una del catálogo.')
    a,b,c,d=st.columns(4,gap='small')
    start=a.text_input('Fecha de inicio',placeholder='DD/MM/AAAA',key='h1212_ini')
    end=b.text_input('Fecha de término',placeholder='DD/MM/AAAA',key='h1212_end')
    days=c.text_input('Días registrados',placeholder='Lunes y miércoles',key='h1212_days')
    hours_text=d.text_input('Horario registrado',placeholder='08:00 a 11:00',key='h1212_schedule')
    data=dict(docente=teacher,curso=course,especialidad=specialization,duracion=hours,
              participantes=count,inicio=start,fin=end,dias=days,horario=hours_text,sede=sede,ciclo=ciclo,tipo=typ,
              curp=curp_doc.strip(),correo=mail_doc.strip(),telefono=tel_doc.strip(),
              tipo_docente=tipo_doc)
    with st.expander('Autoridades del ciclo histórico · obligatorio',expanded=False):
        st.caption('No se utilizarán automáticamente las autoridades del ciclo actual. No se insertan imágenes de firma.')
        a,b,c=st.columns(3,gap='small')
        valid=a.text_input('Valida · Jefatura Capacitación',key='h1212_valida')
        visto=b.text_input('Vo. Bo. · Dirección',key='h1212_visto')
        autor=c.text_input('Autoriza · Subdirección',key='h1212_autoriza')
        apr=st.text_input('Aprueba · si corresponde',key='h1212_aprueba')
    authorities=dict(valida=valid,visto=visto,autoriza=autor,aprueba=apr)
    with st.expander('Observaciones del expediente',expanded=False):
        note=st.text_area('Notas internas · no se imprimen en el PEA',height=75,key='h1212_note')
    academic=None
    if action=='Crear PEA nuevo':
        with st.expander('Contenido académico revisado · opcional',expanded=False):
            f=st.file_uploader('JSON académico validado',type=['json'],key='h1212_json')
            if f:
                try:academic=json.loads(f.getvalue().decode('utf-8-sig'))
                except (ValueError,UnicodeError):st.error('JSON académico inválido.')
            st.caption('Sin JSON, el motor institucional usa Gemini según la configuración existente; puede aplicar límites o costes del proveedor.')
    else:
        st.caption('PDF original intacto · PDF actualizado sin reconstruir tablas · Word de edición controlada (solo datos administrativos editables).')
        col_sede,col_info=st.columns([1.2,1],gap='small')
        modalidad=col_sede.radio('13 · Lugar de impartición',('CECATI','Acción móvil'),
            index=1,horizontal=True,key='h1212_modalidad_sede')
        ubicacion=col_info.text_input('Localidad del CECATI · página 5',value='Coatzacoalcos, Veracruz',key='h1212_ubicacion')
        data['ubicacion']=ubicacion
        data['modalidad_sede']=modalidad
        # Otros campos administrativos pertenecen al formulario original y
        # NO modifican la duración, objetivos, programa ni secuencias didácticas.
        with st.expander('Datos administrativos del formulario · páginas 2 a 5',expanded=False):
            x,y=st.columns([1.4,1],gap='small')
            con_quien=x.text_input('4 · Con quién se impartirá',value='Estudiantes',key='h1212_con_quien')
            servicio=y.radio('3 · Tipo de servicio del PDF',('CE','CAE'),index=0,horizontal=True,key='h1212_servicio_pdf',
                help='No confundir con la clasificación Repositorio / Extensión de ATRIO.')
            perfiles=['Estudiantes','Empleados','Autoempleado','Grupos en desventaja social y/o económica',
                      'Jubilados','Adultos mayores','Desempleados','Personas con discapacidad']
            audiencia=st.multiselect('5 · Perfil de usuario',perfiles,
                default=['Estudiantes','Autoempleado','Desempleados'],key='h1212_perfil_usuarios')
            st.caption('El PDF imprime «Seleccione sólo una opción» pero el original marca varias. Revisa tu selección antes de guardar.')
            z1,z2=st.columns([1,2],gap='small')
            norma=z1.radio('7 · Normalización asociada',('NO','SI'),horizontal=True,key='h1212_norma')
            codigo=z2.text_input('8 · Código EC o norma',key='h1212_norma_codigo')
            nombre_norma=st.text_input('8 · Nombre de la norma o estándar',key='h1212_norma_nombre')
            clave=st.text_input('21 · Clave del curso (si existe)',key='h1212_clave_curso')
            st.caption('El punto 17 respeta la selección Interno / Externo del formulario, aunque difiera del Padrón.')
        data.update(con_quien=con_quien,servicio_pdf=servicio,perfiles_usuario=audiencia,
                    normalizacion=norma,norma_codigo=codigo.strip(),norma_nombre=nombre_norma.strip(),clave_curso=clave.strip())
        if norma=='SI' and not all((codigo.strip(),nombre_norma.strip())):
            st.caption('Para marcar normalización «Sí», completa código y nombre de la norma antes de preparar la vista previa.')
        key_fiel=hashlib.sha256((hashlib.sha256(source or b'').hexdigest()+json.dumps([data,authorities],sort_keys=True,ensure_ascii=False,default=str)).encode()).hexdigest()
        previo=st.session_state.get('h1212_vista_fiel')
        if st.button('1 · Preparar vista previa fiel',key='h1212_preview_fiel'):
            try:
                clean_data=_validate(data);_validate_authorities(authorities)
                if not source:raise ValueError('Sube el PDF oficial original.')
                if not metadata or not all([metadata.get('curso'),metadata.get('horas'),metadata.get('participantes') is not None]):
                    raise ValueError('No se reconocen curso, horas o participantes del PDF original.')
                if data.get('normalizacion')=='SI' and not all((data.get('norma_codigo'),data.get('norma_nombre'))):
                    raise ValueError('Si el curso tiene normalización, indica código y nombre de la norma.')
                with st.spinner('Actualizando campos y casillas oficiales sin modificar el contenido académico...'):
                    pdf_final,word_final,report=FIEL.adaptar_pdf(source,dict(clean_data,**authorities),crear_word=True)
                st.session_state['h1212_vista_fiel']={'key':key_fiel,'pdf':pdf_final,'word':word_final,'reporte':report}
                previo=st.session_state['h1212_vista_fiel']
                st.success('Vista previa preparada: datos y casillas actualizados; contenido académico intacto. Revisa antes de guardar.')
            except (FIEL.ErrorAdaptacion,ValueError,RuntimeError,OSError) as ex:
                st.session_state.pop('h1212_vista_fiel',None);previo=None
                st.error(str(ex))
        if previo and previo.get('key')==key_fiel:
            with st.expander('Vista previa de las páginas modificadas',expanded=True):
                select_page=st.selectbox('Página a revisar',[2,3,4,5,17],format_func=lambda k:f'Página {k}',key='h1212_pagina_preview')
                import fitz
                with fitz.open(stream=previo['pdf'],filetype='pdf') as ver:
                    pix=ver[select_page-1].get_pixmap(matrix=fitz.Matrix(1.1,1.1),alpha=False)
                    st.image(pix.tobytes('png'),caption=f'Página {select_page} · Borrador pendiente de validación visual',use_container_width=True)
                st.caption('Word híbrido: cada hoja es una imagen fiel; solo los campos administrativos son editables. No permite editar tablas académicas.')
            if st.button('2 · Confirmar y guardar PDF + Word en Históricos',type='primary',key='h1212_save_pdf_fiel'):
                try:
                    clean_data=_validate(data);_validate_authorities(authorities)
                    rec={'accion':'Adaptar PDF conservando formato','datos':clean_data,'autoridades':authorities,
                         'reporte':previo['reporte'],'estado':'BORRADOR_REVISION_VISUAL'}
                    uid=_store(ciclo,'PDF adaptado',typ,clean_data,note,source,previo['word'],rec,pdf_adaptado=previo['pdf'])
                    st.session_state['h1212_last']=uid
                    st.success('PDF original, PDF adaptado y Word híbrido guardados en Mis PEA → Históricos. No autorizados ni subidos a MCE.')
                except (ValueError,RuntimeError,OSError) as ex:st.error(str(ex))
        elif previo:
            st.caption('Los datos cambiaron desde la vista previa. Vuelve a prepararla antes de guardar.')
    if action=='Crear PEA nuevo' and st.button('Generar borrador y guardar en Históricos',type='primary',key='h1212_save'):
        try:
            data=_validate(data);_validate_authorities(authorities)
            if action=='Crear PEA nuevo':
                faltantes=[k for k in ('curp','telefono','correo') if not str(data.get(k) or '').strip()]
                if faltantes:raise ValueError('Completa los datos visibles del docente: '+', '.join(faltantes))
                with st.spinner('Generando PEA nuevo con la plantilla institucional…'):
                    word,cont=_generate(data,authorities,academic)
                record={'accion':'Nuevo','contenido':cont,'autoridades':authorities,'datos':data,'estado':'BORRADOR_REVISION'}
                uid=_store(ciclo,'Nuevo',typ,data,note,None,word,record)
            st.session_state['h1212_last']=uid
            st.success('Borrador guardado en Mis PEA → Históricos. No se ha autorizado ni subido al MCE.')
        except (ValueError,RuntimeError,OSError,KeyError,TypeError) as e:st.error(str(e))
    last=st.session_state.get('h1212_last')
    if last:
        with _db() as con:row=con.execute('SELECT * FROM pea_hist_101212 WHERE id=?',(last,)).fetchone()
        if row:
            st.caption('Último borrador: '+row['curso']+' · '+row['ciclo'])
            _download('↓ Descargar Word',row['word_path'],'h1212_download_latest')
    with st.expander('Consultar expedientes históricos guardados',expanded=False):_archive()
