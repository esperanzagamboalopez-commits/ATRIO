"""ATRIO 10.11 — Paso 3, 4 y 5 de Preparar PEA.
No sustituye generador institucional, ni modifica otras hojas.
"""
from __future__ import annotations
import hashlib, json, io
from pathlib import Path
import streamlit as st
import centro as C
import trabajos as J
import pea_biblioteca_109 as P
import pea_adaptacion_1010 as A
import revision_pea_111 as R

OPTIONS=['Gemini · generar o recuperar caché válida',
         'JSON académico propio · cargar y validar',
         'Reutilizar PEA existente · Word']


def _go(stage):
    st.session_state['pea110_stage']=stage
    st.rerun()


def _reset():
    for key in list(st.session_state):
        if key.startswith('pea111_') or key.startswith('p111_'):
            st.session_state.pop(key,None)
    st.session_state.pop('pea110_stage',None)
    st.session_state.pop('editor_group',None)
    st.session_state['jump']='Preparar PEA'
    st.rerun()


def _doc():
    return st.session_state.get('pea111_doc') or None


def _selected(g):
    return (st.session_state.get('pea111_doc_group')==g['id'] and _doc() is not None)


def _pick_doc(g):
    source=st.radio('Origen del Word',('Mis PEA · Generados y Subidos','Subir Word del docente'),
                    horizontal=True,key='pea111_source')
    if source.startswith('Mis PEA'):
        rows=P.candidatos()
        if not rows:
            st.info('No hay Word disponibles. Selecciona «Subir Word del docente».')
            return
        candidate=st.selectbox('Seleccionar PEA existente',rows,format_func=lambda row:f"{row['origen']} · {row['curso']} · {row['docente']} · {row['duracion'] or '?'} h",key='pea111_pick')
        try:
            raw=P._documento(candidate)
        except Exception as exc:
            st.error(str(exc));return
        name=candidate['nombre_original'];origin_id=candidate['id'] if not str(candidate['id']).startswith('atrio:') else None
    else:
        file=st.file_uploader('Word original del docente (.docx)',type=['docx'],key='pea111_upload')
        if file is None:
            if _selected(g) and st.session_state.get('pea111_source')==source:return
            return
        raw=file.getvalue();name=file.name;origin_id=None
    try:
        R.validar_docx(raw)
    except Exception as exc:
        st.error('Word no válido: '+str(exc));return
    sha=hashlib.sha256(raw).hexdigest()
    prev=_doc()
    if not prev or prev.get('sha')!=sha or st.session_state.get('pea111_doc_group')!=g['id']:
        st.session_state['pea111_doc']={'raw':raw,'name':name,'id':origin_id,'sha':sha}
        st.session_state['pea111_doc_group']=g['id']
        for x in ['pea111_checks','pea111_accepted','pea111_created','pea111_observations']:
            st.session_state.pop(x,None)
    if source=='Subir Word del docente':
        if st.button('Guardar original sin modificar en Mis PEA → Subidos',key='p111_archive'):
            try:
                ident,created=P.guardar_original(raw,name,g)
                st.session_state['pea111_doc']['id']=ident
                st.success('Original archivado sin modificaciones.' if created else 'El original ya existía; no se duplicó.')
            except Exception as exc:st.error('No fue posible archivar el original: '+str(exc))
    if st.session_state.get('pea111_doc',{}).get('id'):
        st.caption('Documento original vinculado a Mis PEA; no se sobrescribirá.')


def _report(g):
    doc=_doc()
    if not _selected(g):return None
    try:return R.analizar(doc['raw'],g)
    except Exception as exc:
        st.error('No se pudo analizar el PEA: '+str(exc));return None


def _administrative(g,report):
    doc=_doc()
    _,items=P.campos(doc['raw'],g)
    choices=[]
    for x in items:
        with st.container(border=True):
            a,b,c=st.columns([1.7,1.7,1.1]);a.caption('Campo · PEA original');a.write('**'+x['campo']+'**');a.write(x['anterior'] or 'No legible')
            b.caption('Valor en Programación');b.write(x['nuevo'] or 'Sin dato')
            if x['diferente']:
                if c.checkbox('Modificar',value=False,key='p111_field_'+x['campo'].replace(' ','_')):choices.append(x['campo'])
            else:c.success('Coincide')
    st.session_state['pea111_checks']=choices
    return choices


def _horas(g,report):
    h=report['horas'];prog=float(g['duracion'])
    x,y,z=st.columns(3)
    x.metric('Horas programadas',f'{prog:g} h')
    y.metric('Horas computables del Word',f"{report['computables']:g} h")
    z.metric('Estudio independiente · adicional',f"{report['independiente']:g} h")
    st.caption('El estudio independiente NO se suma al total oficial y no forma parte del 20/80.')
    return h


def panel(g):
    # Evitar heredar selecciones y archivos de otro grupo.
    if st.session_state.get('pea111_group') not in (None,g['id']):
        for key in list(st.session_state):
            if key.startswith('pea111_') or key.startswith('p111_'):st.session_state.pop(key,None)
    st.session_state['pea111_group']=g['id']
    stage=st.session_state.get('pea110_stage','validacion')
    if stage not in ('validacion','contenido','salida'):stage='validacion'
    labels={'validacion':'3. Validación','contenido':'4. Contenido','salida':'5. Salida'}
    st.caption('De la programación al PEA · 1. Docente ✓  ·  2. Curso ✓  ·  '+labels[stage])
    left,right=st.columns([1,1])
    with left:
        if st.button('← Volver a '+('Curso' if stage=='validacion' else 'Validación' if stage=='contenido' else 'Contenido'),key='pea111_back'):
            if stage=='validacion':_reset()
            else:_go('validacion' if stage=='contenido' else 'contenido')
    with right:
        if st.button('Empezar otra selección',key='pea111_new'): _reset()
    st.subheader(g['nombre'])
    st.caption(f"{g['hoja']} · {g['tipo']} · {g['duracion']:g} horas · {g['inicio']} al {g['fin']}")
    mode=st.session_state.get('pea111_mode',OPTIONS[0])
    if stage=='validacion':
        st.markdown('### Validación · datos y calendario')
        x,y,z=st.columns(3)
        with x:st.metric('Duración oficial',f"{g['duracion']:g} h")
        with y:st.metric('Periodo',str(g['inicio']))
        with z:st.metric('Término',str(g['fin']))
        try:
            calendar=C.motor.revisar_calendario(g,C.RES)
            (st.error if str(calendar).startswith('ERROR:') else st.info)(str(calendar))
        except Exception as exc:st.warning('Calendario aún no verificable: '+str(exc))
        try:
            prof=C.profiles().get(C.motor.normal(g['hoja']))
            st.caption('Perfil docente: '+('localizado' if prof else 'no localizado; revisar en Ajustes'))
        except Exception:st.caption('Perfil docente: pendiente de comprobar')
        if g['tipo']=='Regular':
            st.info('Curso Regular: no se genera PEA de Extensión. Conserva su seguimiento académico.');return
        if g['tipo']=='Repositorio':
            st.warning('Repositorio: la adaptación automática del PDF sigue pendiente. Puedes conservar el original del grupo, igual que en la versión anterior.')
            source=st.file_uploader('Original de Repositorio · PDF',type=['pdf'],key='pea111_repo_pdf')
            if source and st.button('Guardar original PDF del grupo',key='pea111_repo_save'):
                raw=source.getvalue()
                if not raw.startswith(b'%PDF'):st.error('PDF inválido; no se guardó el archivo.')
                else:
                    dest=C.OUT/g['id']/'repositorio_original.pdf'
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_bytes(raw)
                    C.event(g['id'],'Original repositorio asociado',{'path':str(dest.relative_to(C.ROOT))})
                    st.success('Original guardado. No se ha adaptado ni marcado como generado.')
            return
        mode=st.radio('Origen del contenido',OPTIONS,index=OPTIONS.index(mode) if mode in OPTIONS else 0,key='pea111_mode',horizontal=False)
        if mode.startswith('Reutilizar'):
            _pick_doc(g)
            report=_report(g)
            if report:
                st.markdown('**Diferencias administrativas y académicas**')
                _horas(g,report)
                _administrative(g,report)
                n=report['conteo']
                st.caption(f"Diagnóstico local: {n.get('Diferencia comprobable',0)} diferencias objetivas · {n.get('Requiere revisión',0)} asuntos por revisar · {n.get('Sugerencia pedagógica',0)} recomendaciones.")
        else:
            st.info('Se utilizarán los prompts y las validaciones institucionales existentes. No se modificarán los criterios de elaboración.')
            if mode.startswith('JSON'):
                uploaded=st.file_uploader('Contenido académico JSON',type=['json'],key='pea111_json')
                if uploaded:
                    try:st.session_state['pea111_jsondata']=json.loads(uploaded.getvalue())
                    except Exception as exc:st.error('JSON inválido: '+str(exc))
        ready=not mode.startswith('Reutilizar') or bool(_report(g))
        if st.button('Continuar a Contenido →',type='primary',disabled=not ready,key='pea111_to_contento'):_go('contenido')
    elif stage=='contenido':
        st.markdown('### Contenido · evaluación pedagógica')
        if mode.startswith('Reutilizar'):
            report=_report(g)
            if not report:
                st.warning('Regresa a Validación y selecciona un Word.');return
            st.info('Revisión automática LOCAL de un Word recibido. Las recomendaciones pedagógicas requieren tu valoración; no constituyen un dictamen de la DGCFT.')
            checks=st.session_state.get('pea111_checks',[])
            if 'Duración' in checks:
                try:
                    plan=A.proponer(_doc()['raw'],float(g['duracion']))
                    st.markdown('**Propuesta automática 20% / 80% · sin estudio independiente en el total**')
                    st.write(f"Mediación/teoría operativa: **{plan['teoria']:g} h** · Prácticas: **{plan['practicas']:g} h** · Estudio independiente adicional: **{plan['estudio_independiente']:g} h**.")
                    st.dataframe(plan['rows'],hide_index=True,use_container_width=True)
                    st.warning('Las actividades, competencias y evaluaciones conservan su texto original. Deben revisarse para comprobar su viabilidad pedagógica; la redistribución automática de números no las valida.')
                except Exception as exc:st.error('No es segura la adaptación numérica: '+str(exc))
            st.markdown('**Matriz de ocho áreas de revisión CECATI**')
            st.dataframe(report.get('rubrica',[]),hide_index=True,use_container_width=True)
            st.markdown('**Hallazgos y observaciones para tu informe**')
            selected=[]
            for i,h in enumerate(report['hallazgos']):
                with st.expander(f"{h['tipo']} · {h['asunto']} · {h['prioridad']}",expanded=i<3):
                    st.caption('Área: '+h['area']+' · Sección: '+h['ubicacion'])
                    st.write('**Hallazgo:** '+h['evidencia'])
                    if st.checkbox('Incluir en informe',value=True,key='p111_incluir_'+h['id']):
                        edited=st.text_area('Recomendación editable',value=h['sugerencia'],key='p111_sugerir_'+h['id'],height=85)
                        selected.append(dict(h,sugerencia_editada=edited))
                    else:st.caption('No se incluirá en el informe.')
            st.session_state['pea111_observations']=selected
            st.caption('Los errores comprobados se distinguen de aspectos por revisar y sugerencias; el reporte incluirá únicamente lo que selecciones.')
        else:
            st.info('Para un PEA nuevo, ATRIO conservará el generador académico y sus prompts ya establecidos con Tema 1 y Tema 2. No se modifica la plantilla ni se crea una segunda metodología de elaboración.')
            st.write('**Curso:** '+g['nombre'])
            st.write(f"**Duración oficial:** {g['duracion']:g} horas")
            st.write('**Contenido académico:** se generará o recuperará desde la caché existente cuando confirmes en Salida. La validación original del motor seguirá siendo obligatoria.')
            st.caption('No se simula contenido pedagógico antes de su generación.')
        if st.button('Continuar a Salida →',type='primary',key='pea111_to_salida'):_go('salida')
    else:
        st.markdown('### Salida · documentos e informes')
        if mode.startswith('Reutilizar'):
            report=_report(g)
            if not report:
                st.warning('Vuelve a Validación y selecciona un Word.');return
            docs=st.session_state.get('pea111_observations',[])
            st.write(f'**Informe académico:** {len(docs)} observaciones seleccionadas.')
            if st.checkbox('Revisé los hallazgos y las recomendaciones que se incluirán.',key='p111_report_confirm'):
                internal=R.informe_word(report,docs,False)
                teacher=R.informe_word(report,docs,True)
                st.download_button('Descargar diagnóstico interno · Word',internal,file_name='DIAGNOSTICO_INTERNO_PEA.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',key='pea111_internal')
                st.download_button('Descargar observaciones al docente · Word',teacher,file_name='OBSERVACIONES_DOCENTE_PEA.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',key='pea111_teacher')
            st.divider()
            checked=st.session_state.get('pea111_checks',[])
            st.markdown('**Copia Word del PEA con los cambios seleccionados**')
            if checked:
                st.write('Cambios: '+', '.join(checked))
                st.caption('La copia conserva el formato del original. No incorpora firmas anteriores; siempre requiere revisión académica.')
                confirm=st.checkbox('Confirmo la creación de un borrador y que revisaré las actividades y evaluaciones si cambiaron las horas.',key='p111_word_confirm')
                if st.button('Crear y guardar borrador Word',type='primary',disabled=not confirm,key='p111_save_word'):
                    try:
                        r=_doc();oid=r.get('id')
                        if oid is None:oid,_=P.guardar_original(r['raw'],r['name'],g)
                        ident,out,remaining=P.generar_copia(r['raw'],r['name'],g,checked,oid)
                        previous=C.status(g['id']);C.update_status(g['id'],'Generado',previous['mce'],
                            'Borrador Word actualizado; requiere revisión académica. Pendientes: '+(', '.join(remaining) if remaining else 'revisión de documento'))
                        st.session_state['pea111_created']={'id':ident,'bytes':out,'group':g['id'],'pending':remaining}
                        st.success('Borrador guardado en Mis PEA → Generados. Seguimiento: PEA generado, pendiente de revisión. MCE no se modificó.')
                    except Exception as exc:st.error('No se pudo generar el Word: '+str(exc))
            else:st.info('No seleccionaste cambios. Puedes descargar los informes sin modificar el PEA original.')
            last=st.session_state.get('pea111_created')
            if last and last['group']==g['id']:
                st.download_button('Descargar Word actualizado',last['bytes'],file_name='PEA_ACTUALIZADO_'+last['id'][:8]+'.docx',key='p111_download')
                if last['pending']:st.warning('Pendientes de revisión: '+', '.join(last['pending']))
        else:
            st.caption('Se utilizará el generador original de ATRIO. Se conservan los prompts y la plantilla vigente.')
            qty=int(g['poblacion']) if isinstance(g['poblacion'],(int,float)) and g['poblacion']>0 else 10
            participants=st.number_input('Participantes previstos',min_value=1,value=qty,key='p111_participants')
            st.caption('Esta cantidad no equivale automáticamente a inscripciones SISAE.')
            confirm=st.checkbox('Revisé datos del curso, autoridades, perfil docente y calendario.',key='p111_new_confirm')
            if st.button('Generar y guardar borrador Word',type='primary',disabled=not confirm,key='p111_create_new'):
                try:
                    academic=st.session_state.get('pea111_jsondata') if mode.startswith('JSON') else None
                    if mode.startswith('JSON') and academic is None:raise ValueError('No se ha cargado JSON académico válido.')
                    J.start(g,participants,academic)
                    st.success('PEA generado con el motor institucional; revisa su versión en Mis PEA → Generados.')
                except Exception as exc:st.error('Generación no completada: '+str(exc))
        arts=C.artifacts(g['id'])
        if arts:
            with st.expander('PEA generados previamente para este grupo'):
                for a in arts[:5]:
                    st.write('Versión '+str(a['created']))
                    path=C.ROOT/a['path']
                    if path.is_file():st.download_button('Descargar Word · '+a['id'][:8],path.read_bytes(),file_name='PEA_'+a['id'][:8]+'.docx',key='p111_art_'+a['id'])
        st.info('Excel para MCE conserva exclusivamente su propia hoja; no se duplica aquí.')
