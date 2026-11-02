"""ATRIO 10.11.2 — Revisor independiente de PEA Word.
Análisis local orientativo, reportes al docente, cambios elegidos por la persona
responsable. No usa API de IA ni transmite documentos a terceros.
"""
from __future__ import annotations
import hashlib, html
from pathlib import Path
import streamlit as st
import centro as C
import pea_biblioteca_109 as P
import pea_adaptacion_1010 as A
import revision_pea_111 as R
from pea_wizard_112 import CSS,fecha,esc


def _header():
    st.markdown(CSS,unsafe_allow_html=True)
    st.markdown('''<div class="p112"><div class="eyebrow">Revisión académica · autorización humana</div><h2>Revisor de PEA</h2><p class="sub">Analiza documentos Word de docentes, elige los cambios y genera observaciones para revisión. Sin envío automático de documentos a IA.</p></div>''',unsafe_allow_html=True)

def _source(data):
    default=st.session_state.get('rv112_group')
    groups=[g for g in data if g['tipo']!='Regular']
    if not groups:
        st.caption('No hay grupos programados disponibles.');return None,None,None,None
    ids=[g['id'] for g in groups]
    g=st.selectbox('Grupo de la programación',groups,index=ids.index(default) if default in ids else 0,
         format_func=lambda x:f"{x['nombre']} · {x['hoja']} · {x['duracion']:g} h · {fecha(x['inicio'])}",key='rv112_group_selector')
    selected_mode=st.radio('Documento de origen',['Subir Word (.docx)','Elegir de Mis PEA'],horizontal=True,key='rv112_source')
    if selected_mode.startswith('Subir'):
        f=st.file_uploader('PEA entregado por docente · Word (.docx)',type=['docx'],key='rv112_file')
        return g,(f.getvalue() if f else None),(f.name if f else None),None
    rows=P.candidatos()
    if not rows:
        st.caption('No se encontraron PEA disponibles en Mis PEA; utiliza Subir Word.');return g,None,None,None
    def lab(x):return f"{x['origen']} · {x['curso']} · {x['docente']} · {str(x['creado'])[:10]}"
    prefer=st.session_state.get('rv112_artifact')
    rid=[x.get('id') for x in rows]
    pref='atrio:'+str(prefer)
    idx=rid.index(pref) if pref in rid else 0
    row=st.selectbox('Seleccionar Word guardado',rows,index=idx,format_func=lab,key='rv112_saved')
    try:return g,P._documento(row),row['nombre_original'],row['id'] if row['origen']!='ATRIO generado' else None
    except Exception as exc:
        st.error('No se pudo leer el documento guardado: '+str(exc));return g,None,None,None

def _kpi(label,value):
    st.markdown(f'<div class="p112"><div class="metric"><div class="k">{esc(label)}</div><div class="v">{esc(value)}</div></div></div>',unsafe_allow_html=True)

def _report_view(report,raw,name,g):
    found=report['hallazgos'];cnt=report['conteo']
    st.markdown(f'<div class="p112"><div class="ptitle">Hallazgos del documento</div><p class="tiny">{esc(name)} · Comparado con {esc(g["nombre"])}</p></div>',unsafe_allow_html=True)
    m=st.columns(3,gap='small')
    _kpi_in_cols(m,[("Diferencias",cnt.get('Diferencia comprobable',0)),('Por revisar',cnt.get('Requiere revisión',0)),('Sugerencias',cnt.get('Sugerencia pedagógica',0))])
    sel=[]
    for ix,h in enumerate(found):
        severity='Alta' if h['prioridad']=='Alta' else 'Media' if h['prioridad']=='Media' else 'Baja'
        with st.expander(f"{'●' if severity=='Alta' else '◦'} {h['asunto']}  ·  {severity} · {h['tipo']}",expanded=ix<2):
            st.caption(h['area']+' · '+h['ubicacion'])
            st.write(h['evidencia'])
            if st.checkbox('Incluir esta observación en el informe',value=True,key='rv112_obs_'+h['id']):
                text=st.text_area('Recomendación propuesta · editable',value=h['sugerencia'],height=85,key='rv112_txt_'+h['id'])
                sel.append(dict(h,sugerencia_editada=text))
    st.markdown('<div class="p112"><div class="softnote">Los hallazgos objetivos y las recomendaciones están separados. El análisis local no acredita por sí mismo una falta pedagógica ni sustituye la validación de la DGCFT.</div></div>',unsafe_allow_html=True)
    return sel

def _kpi_in_cols(cols,items):
    for col,(lab,val) in zip(cols,items):
        with col:_kpi(lab,val)

def _reports(report,selected):
    st.markdown('<div class="p112"><div class="ptitle">Informes de observaciones</div><p class="tiny">Incluyen exclusivamente los hallazgos seleccionados y tu redacción revisada.</p></div>',unsafe_allow_html=True)
    a,b=st.columns(2,gap='small')
    with a:
        st.download_button('↓ Diagnóstico interno · Word',R.informe_word(report,selected,False),file_name='DIAGNOSTICO_INTERNO_PEA.docx',use_container_width=True,key='rv112_int')
    with b:
        st.download_button('↓ Observaciones al docente · Word',R.informe_word(report,selected,True),file_name='OBSERVACIONES_PEA_DOCENTE.docx',use_container_width=True,key='rv112_doc')

def _corrections(report,raw,name,g,origin):
    st.markdown('<div class="p112"><div class="ptitle">Propuestas de corrección</div><p class="tiny">Solo se aplicarán a una copia los cambios administrativos que elijas. El PEA del docente permanecerá intacto.</p></div>',unsafe_allow_html=True)
    d,items=P.campos(raw,g)
    diffs=[x for x in items if x['diferente']]
    if not diffs:
        st.caption('No se detectaron diferencias en las fechas, duración ni horario comparados. Puedes emitir el informe sin alterar el Word.')
        return
    chosen=[]
    for i,x in enumerate(diffs):
        with st.container(border=True):
            a,b,c=st.columns([1.2,1.2,1],gap='small')
            with a:st.caption('Word del docente');st.write('**'+x['campo']+'**');st.write(x['anterior'] or 'No legible')
            with b:st.caption('Programación');st.write(x['nuevo'] or 'No indicado')
            with c:
                if st.checkbox('Aceptar cambio',key='rv112_choose_'+x['campo']):chosen.append(x['campo'])
    if 'Duración' in chosen:
        try:
            plan=A.proponer(raw,float(g['duracion']))
            st.markdown('<div class="p112"><div class="softnote"><b>Distribución numérica propuesta:</b> '+f"{plan['teoria']:g} h de mediación/teoría (20%), {plan['practicas']:g} h de prácticas (80%), estudio independiente {plan['estudio_independiente']:g} h adicional. No se suma al total oficial."+'</div></div>',unsafe_allow_html=True)
            with st.expander('Ver distribución por actividad',expanded=False):st.dataframe(plan['rows'],hide_index=True,use_container_width=True)
            st.caption('Las actividades y evaluaciones conservan su texto original. Antes de autorizar el documento, verifica que siguen siendo pedagógicamente viables.')
        except ValueError as exc:
            st.error('No es posible adaptar las horas automáticamente en este Word: '+str(exc));return
    if chosen:
        st.caption('Cambios aceptados: '+', '.join(chosen))
        check=st.checkbox('Revisé las diferencias y acepto generar un borrador, no un documento autorizado.',key='rv112_confirm')
        if st.button('Generar nueva versión Word',type='primary',disabled=not check,key='rv112_create'):
            try:
                oid=origin
                if not oid:oid,_=P.guardar_original(raw,name,g)
                ident,bdata,pending=P.generar_copia(raw,name,g,chosen,oid)
                status=C.status(g['id'])
                C.update_status(g['id'],'Generado',status['mce'],'Borrador del Revisor; requiere revisión académica.')
                st.session_state['rv112_latest']={'id':ident,'group':g['id'],'bytes':bdata,'pending':pending}
                st.rerun()
            except Exception as exc:st.error('No se pudo guardar la copia; se conserva el original. '+str(exc))
    last=st.session_state.get('rv112_latest')
    if last and last['group']==g['id']:
        st.markdown('<div class="p112"><div class="softnote"><b>Versión generada</b> · Guardada en Mis PEA → Generados. El original permanece en Subidos. Estado: Generado, pendiente de revisión.</div></div>',unsafe_allow_html=True)
        st.download_button('↓ Descargar Word actualizado',last['bytes'],file_name='PEA_ACTUALIZADO_'+last['id'][:8]+'.docx',use_container_width=True,key='rv112_download')
        if last['pending']:st.caption('Pendientes: '+', '.join(last['pending']))

def panel(data):
    _header()
    g,raw,name,oid=_source(data)
    if g is None:return
    if not raw:
        st.markdown('<div class="p112"><div class="softnote">Selecciona el grupo y sube el PEA Word que quieres revisar. Se analizará localmente; no se enviará automáticamente a un servicio externo.</div></div>',unsafe_allow_html=True)
        return
    try:R.validar_docx(raw)
    except Exception as exc:st.error('No es un DOCX válido para revisión: '+str(exc));return
    digest=hashlib.sha256(raw).hexdigest()
    identity=digest+':'+g['id']
    if st.session_state.get('rv112_identity')!=identity:
        st.session_state['rv112_identity']=identity
        st.session_state.pop('rv112_report',None)
        for k in list(st.session_state):
            if k.startswith(('rv112_choose_','rv112_obs_','rv112_txt_','rv112_confirm','rv112_latest','rv112_stored')):st.session_state.pop(k,None)
    a,b=st.columns([1.9,1],gap='medium')
    with a:
        st.markdown('<div class="p112"><div class="rail">📄 '+esc(name)+' &nbsp; · &nbsp; '+esc(g['nombre'])+' &nbsp; · &nbsp; '+fecha(g['inicio'])+' – '+fecha(g['fin'])+'</div></div>',unsafe_allow_html=True)
    with b:
        if st.button('Ejecutar análisis local',type='primary',use_container_width=True,key='rv112_analyze'):
            try:st.session_state['rv112_report']=R.analizar(raw,g)
            except Exception as exc:st.error('No se pudo analizar el documento: '+str(exc))
    rep=st.session_state.get('rv112_report')
    if not rep:
        st.caption('Al analizar se mostrará la matriz académica, las diferencias comprobables y las recomendaciones. No se modificará el Word.')
        return
    if oid is None:
        saved=st.session_state.get('rv112_stored')
        if saved and saved.get('identity')==identity:
            oid=saved['id']
            st.caption('Original archivado en Mis PEA → Subidos; permanece intacto.')
        elif st.button('Archivar original sin modificar en Mis PEA → Subidos',key='rv112_store'):
            try:
                oid,created=P.guardar_original(raw,name,g)
                st.session_state['rv112_stored']={'identity':identity,'id':oid}
                st.rerun()
            except Exception as exc:st.error('No se pudo guardar el original: '+str(exc))
    left,right=st.columns([1.6,1],gap='medium')
    with left:
        with st.container(border=True):sel=_report_view(rep,raw,name,g)
    with right:
        with st.container(border=True):
            st.markdown('<div class="p112"><div class="ptitle">Resumen del expediente</div></div>',unsafe_allow_html=True)
            st.write('**Curso:**',g['nombre']);st.write('**Docente:**',g['hoja']);st.write('**Duración programada:**',f"{g['duracion']:g} h")
            st.write('**Computables detectadas:**',f"{rep['computables']:g} h")
            st.write('**Estudio independiente:**',f"{rep['independiente']:g} h · adicional")
            st.write('**Hallazgos:**',len(rep['hallazgos']))
        with st.container(border=True):
            st.markdown('**Reglas del revisor**')
            st.caption('✓ Comprobar datos y fechas de la programación.\n\n✓ No sumar estudio independiente.\n\n✓ Analizar contenido y evidencias, sin atribuir una autorización automática.\n\n✓ Conservar Word y firmas únicamente en el original.')
    with st.expander('Matriz académica de ocho áreas',expanded=False):st.dataframe(rep['rubrica'],hide_index=True,use_container_width=True)
    _reports(rep,sel)
    st.divider()
    _corrections(rep,raw,name,g,oid)
