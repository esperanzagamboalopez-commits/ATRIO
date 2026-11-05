"""ATRIO 10.11.2 — Preparar PEA exclusivo para generar documentos nuevos.
La revisión/reutilización de Word se hace solamente en Revisor, en otro módulo.
No cambia el motor, plantilla ni prompts del generador institucional.
"""
from __future__ import annotations
from datetime import date
import html, json, re, shutil, subprocess, tempfile, os
from pathlib import Path
import streamlit as st
import centro as C
import trabajos as J

STEPS=('Docente','Curso','Validación','Contenido','Salida')

CSS='''<style>
.p112 * {box-sizing:border-box}
.p112 .eyebrow{color:#987240;font-size:11px;letter-spacing:.12em;font-weight:700;text-transform:uppercase}
.p112 h2{color:#2b1c22;font-family:Georgia,serif;font-size:29px!important;font-weight:600;margin:4px 0 5px}
.p112 .sub{color:#756970;font-size:13px;margin:0 0 12px}
.p112 .rail{display:flex;gap:8px;align-items:center;background:#fffcf9;padding:11px 15px;border:1px solid #e8dad6;border-radius:13px;flex-wrap:wrap;margin:10px 0 15px;font-size:12px;color:#4c333b}
.p112 .rail b{color:#692d46}.p112 .rail .sep{color:#d6bdc3;padding:0 4px}
.p112 .ptitle{font-family:Georgia,serif;font-size:21px;color:#321f28;margin:0 0 5px}
.p112 .tiny{font-size:12px;color:#7c6b70}
.p112 .metric{border:1px solid #eadbd9;border-radius:11px;background:linear-gradient(120deg,#fffdfb,#fcf5f3);padding:13px 15px;min-height:85px}
.p112 .metric .k{font-size:11px;color:#78666c}.p112 .metric .v{font-family:Georgia,serif;font-size:26px;color:#57253b;margin-top:5px}
.p112 .item{display:flex;align-items:center;gap:10px;padding:11px 12px;border-bottom:1px solid #eee0dc;font-size:13px}
.p112 .item:last-child{border-bottom:0}.p112 .ok{color:#36815c;font-weight:700}.p112 .warn{color:#a36b29;font-weight:700}.p112 .softnote{border-left:2px solid #b58c50;padding:9px 12px;background:#faf6f1;border-radius:4px;color:#6c5660;font-size:12px;margin:10px 0}
.p112 .done{padding:24px 16px;text-align:center;background:#fffbf8;border:1px solid #eadcda;border-radius:15px}.p112 .done h2{font-size:25px!important}
.p112 .docrow{border:1px solid #ebd7db;border-radius:10px;background:#fcf7f5;padding:15px;margin:14px 0;word-break:break-all}
.p112 .minor{color:#8b767c;font-size:11px}
.p112 .miniunit{padding:10px 14px;border:1px solid #ebdfdd;border-radius:9px;margin:6px 0;color:#44333b;font-size:13px}
.p112 .section{border:1px solid #e7d9d5;border-radius:13px;background:#fffcfa;padding:18px;margin-top:7px}
.p112 .pass{color:#2a7654}.p112 .divider{height:1px;background:#e9dbd8;margin:12px 0}
/* ATRIO 10.12.1: acabado uniforme del asistente, solo zona de Preparar PEA */
</style>'''

CONTROL_CSS='''<style>
/* Estilos limitados a controles propios del asistente */
[class*="st-key-p112_step_"] button{height:44px!important;border:1px solid #dfc9c7!important;border-radius:10px!important;background:#fffbf8!important;box-shadow:none!important;color:#563742!important;font-size:13px!important;min-height:44px!important;}
[class*="st-key-p112_step_"] button[kind="primary"], [class*="st-key-p112_step_"] button[data-testid="stBaseButton-primary"] {background:var(--atrio-neon)!important;border-color:var(--atrio-neon)!important;color:var(--atrio-sobre-acento)!important;}
[class*="st-key-p112_step_"] button[kind="primary"] p,[class*="st-key-p112_step_"] button[data-testid="stBaseButton-primary"] p {color:var(--atrio-sobre-acento)!important;}
[class*="st-key-p112_step_"] button:disabled:not([kind="primary"]){opacity:.72!important;}
[class*="st-key-p112_back"] button,[class*="st-key-p112_reset"] button{border:1px solid #d9bcb5!important;border-radius:9px!important;background:#fffcfa!important;color:#492f3b!important;min-height:41px!important;}
[class*="st-key-p112_go_content"] button,[class*="st-key-p112_go_exit"] button,[class*="st-key-p112_ready_next"] button{border-radius:10px!important;background:var(--atrio-neon)!important;border:1px solid var(--atrio-neon)!important;color:var(--atrio-sobre-acento)!important;min-height:43px!important;}
[class*="st-key-p112_go_content"] button p,[class*="st-key-p112_go_exit"] button p,[class*="st-key-p112_ready_next"] button p{color:var(--atrio-sobre-acento)!important;}
</style>'''


def esc(s):return html.escape(str(s or ''))
def fecha(s):
    try:
        d=date.fromisoformat(str(s)[:10]);months=('enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre')
        return f'{d.day:02d} {months[d.month-1]} {d.year}'
    except Exception:return str(s)

def top(g,stage):
    st.markdown(CSS.removesuffix('</style>') + CONTROL_CSS.removeprefix('<style>'), unsafe_allow_html=True)
    st.markdown('<div class="p112"><div class="eyebrow">Jefatura de Capacitación · CECATI 31</div><h2>Preparar PEA</h2><p class="sub">De la programación al documento institucional, sin volver a capturar.</p></div>',unsafe_allow_html=True)
    active={'validacion':2,'contenido':3,'salida':4}[stage]
    cols=st.columns(5,gap='small')
    for i,name in enumerate(STEPS):
        label=('✓ ' if i<active else str(i+1)+' · ')+name
        if cols[i].button(label,key='p112_step_'+str(i),disabled=(i>active or i==active),type='primary' if i==active else 'secondary',use_container_width=True):
            if i<2:_back_to_selection()
            elif i==2:_go('validacion')
            elif i==3:_go('contenido')
    st.markdown(f'''<div class="p112"><div class="rail"><span>♙ <b>{esc(g['hoja'])}</b></span><span class="sep">│</span><span>{esc(g['nombre'])}</span><span class="sep">│</span><span>{esc(g['tipo'])}</span><span class="sep">│</span><span>{g['duracion']:g} h</span><span class="sep">│</span><span>{fecha(g['inicio'])} – {fecha(g['fin'])}</span><span class="sep">│</span><span>{esc(g['horario'])}</span></div></div>''',unsafe_allow_html=True)

def _go(step):st.session_state['pea110_stage']=step;st.rerun()

def _back_to_selection():
    for key in ('p112_jsondata','p112_show_json','p112_json_file','p112_job'):
        st.session_state.pop(key,None)
    st.session_state.pop('pea110_stage',None)
    st.session_state.pop('editor_group',None)
    st.session_state['jump']='Preparar PEA';st.rerun()

def bottom(stage):
    a,spacer,b=st.columns([1,2.2,1])
    with a:
        if st.button('← Atrás',key='p112_back',use_container_width=True):
            if stage=='validacion':_back_to_selection()
            else:_go('validacion' if stage=='contenido' else 'contenido')
    with b:
        if st.button('Empezar otra selección',key='p112_reset',use_container_width=True): _back_to_selection()

def parse_calendar(raw, official):
    """Lee formatos reales del motor: COINCIDE «11 sesiones × 4 h = 44 h»
    y DIFERENCIA «22 sesiones × 3 = 66 h; oficiales 60 h».
    No calcula ni modifica fechas oficiales.
    """
    txt=str(raw or '').strip()
    result={'raw':txt,'ok':False,'n':'—','h':'—','target':f'{float(official):g}'}
    match=re.search(r'(\d+)\s+sesiones?\s*[×xX*]\s*(\d+(?:[.,]\d+)?)\s*(?:h(?:oras?)?)?\s*=\s*(\d+(?:[.,]\d+)?)\s*h',txt,re.I)
    if match:
        result['n']=match.group(1)
        result['h']=f'{float(match.group(3).replace(",",".")):g}'
        result['ok']=txt.upper().startswith('COINCIDE:') and abs(float(result['h'])-float(official))<.01
    return result

def calc_calendar(g):
    try:
        raw=C.motor.revisar_calendario(g,C.RES)
        return parse_calendar(raw,g['duracion'])
    except Exception as exc:
        return {'error':'No se pudo calcular el calendario: '+str(exc),'raw':'','ok':False,'n':'—','h':'—'}

def validation(g):
    cal=calc_calendar(g)
    profile=C.profiles().get(C.motor.normal(g['hoja']))
    st.markdown('<div class="p112"><div class="ptitle">Validación del curso</div><p class="tiny">Comprobación de datos y calendario antes de solicitar el contenido.</p></div>',unsafe_allow_html=True)
    left,right=st.columns([1.55,1],gap='medium')
    with left:
        m=st.columns(3,gap='small');vals=[('Sesiones hábiles',cal.get('n','—')),('Horas calculadas',cal.get('h','—')+' h' if cal.get('h','—')!='—' else '—'),('Horas oficiales',f"{g['duracion']:g} h")]
        for col,(name,value) in zip(m,vals):col.markdown(f'<div class="p112"><div class="metric"><div class="k">{esc(name)}</div><div class="v">{esc(value)}</div></div></div>',unsafe_allow_html=True)
        checks=[('Registro en programación','Localizado',True),('Perfil del docente','Localizado' if profile else 'Requiere completar perfil',bool(profile)),('Calendario y carga horaria','Coincide' if cal.get('ok') else ('Diferencia de horas' if cal.get('n')!='—' else 'No verificable'),cal.get('ok',False)),('Datos oficiales del grupo',f"{g['duracion']:g} horas · {esc(g['tipo'])}",True)]
        markup='<div class="p112 section"><div class="ptitle">Comprobaciones</div>'
        for name,answer,ok in checks:markup+=f'<div class="item"><span class="{ "ok" if ok else "warn" }">{ "✓" if ok else "!" }</span><span style="flex:1">{esc(name)}</span><span class="{ "ok" if ok else "warn" }">{esc(answer)}</span></div>'
        markup+='</div>'
        st.markdown(markup,unsafe_allow_html=True)
    with right:
        st.markdown('<div class="p112 section"><div class="ptitle">Qué se comprobará</div><div class="item">1 · Curso, docente, fechas y duración oficial</div><div class="item">2 · Calendario y horas efectivas de impartición</div><div class="item">3 · Perfil docente y recursos académicos</div><div class="item">4 · Uso de la plantilla institucional sin modificaciones</div></div><div class="softnote">Los PEA entregados por docentes se revisan en la hoja <b>Revisor</b>; aquí solo se preparan PEA nuevos.</div></div>',unsafe_allow_html=True)
        if cal.get('raw') and not cal.get('ok'):
            st.markdown('<div class="p112"><div class="softnote"><b>Atención al calendario:</b> '+esc(cal['raw'])+'</div></div>',unsafe_allow_html=True)
    if g['tipo']=='Regular':st.caption('Curso regular: conserva su seguimiento; no genera PEA de Extensión.')
    elif g['tipo']=='Repositorio':st.caption('Curso de Repositorio: su revisión y adaptación se gestionan desde Revisor cuando existe un Word editable. No se reemplaza el tratamiento anterior de PDFs.')
    else:
        if st.button('Continuar a Contenido →',type='primary',key='p112_go_content'): _go('contenido')
    bottom('validacion')

def _artifact_and_content(g):
    arts=C.artifacts(g['id'])
    arts=[a for a in arts if a.get('fingerprint')==g.get('fingerprint')]
    for a in arts:
        path=(C.ROOT/a.get('content_path','')).resolve()
        if C.OUT.resolve() in path.parents and path.is_file():
            try:return a,json.loads(path.read_text(encoding='utf-8'))
            except (ValueError,OSError):pass
    return (arts[0] if arts else None),None

def _display_hora_summary(content, official):
    """Vista de lectura sobre el JSON validado, no cambia el método 20/80."""
    if not isinstance(content,dict):return
    units=content.get('unidades') or content.get('UNIDADES') or []
    if not isinstance(units,list) or not units:return
    try:
        med=sum(float(u.get('mediacion_horas',0)) for u in units)
        pra=sum(float(u.get('practica_horas',0)) for u in units)
        opening=2 if float(official)>=40 else 1
        total=med+pra+opening*2
    except (TypeError,ValueError,AttributeError):return
    cols=st.columns(3,gap='small')
    for col,label,value in zip(cols,('Horas computables','Duración oficial','Diferencia'),(f'{total:g} h',f'{float(official):g} h',f'{total-float(official):+g} h')):
        col.markdown(f'<div class="p112"><div class="metric"><div class="k">{esc(label)}</div><div class="v">{esc(value)}</div></div></div>',unsafe_allow_html=True)
    st.caption(f'Desglose del generador: {med+2*opening:g} h de mediación (incluye apertura y cierre), {pra:g} h de prácticas. El estudio independiente, si está registrado, es adicional y no se suma al total.')

def _show_content(content):
    if not content:
        st.caption('Todavía no hay contenido académico estructurado disponible. Genera un borrador para revisarlo aquí.')
        return
    if not isinstance(content,dict):st.json(content,expanded=False);return
    st.markdown('<div class="p112"><div class="ptitle">Borrador académico</div></div>',unsafe_allow_html=True)
    for label,keys in [('Objetivo general',('objetivo_general','OBJETIVO_GENERAL')),('Justificación',('justificacion','JUSTIFICACION')),('Competencias',('competencia','competencias','COMPETENCIA'))]:
        for k in keys:
            if k in content:
                with st.expander(label,expanded=False):st.write(content[k]);break
    items=[]
    for k in ('unidades','UNIDADES','planeacion','planeacion_didactica','temario','contenido_tematico','secuencias'):
        x=content.get(k)
        if isinstance(x,list):items=x;break
    if items:
        for i,item in enumerate(items,1):
            if not isinstance(item,dict):item={'contenido':item}
            label=str(item.get('titulo') or item.get('nombre') or item.get('unidad') or item.get('tema') or 'Unidad '+str(i))
            hour=item.get('horas') or item.get('duracion') or ''
            with st.expander(f'{i}. {label}'+(f' · {hour} h' if hour else ''),expanded=False):
                for k,v in item.items():
                    if k in ('titulo','nombre','unidad','tema'):continue
                    st.write('**'+k.replace('_',' ').capitalize()+'**',v)
    else:
        st.caption('Contenido estructurado disponible para consulta; despliega el JSON de control para ver las secciones exactas del motor.')
    with st.expander('Contenido completo para revisión',expanded=False):st.json(content,expanded=False)

def _jobs(g):
    with J.connection() as db:
        return [dict(r) for r in db.execute('SELECT * FROM pea_jobs WHERE group_id=? ORDER BY created DESC LIMIT 5',(g['id'],))]

def _job_auto_notice(g):
    """Actualiza solo esta pequeña sección cada 5 segundos, sin forzar una nueva generación."""
    jobs=_jobs(g)
    if not jobs:return
    latest=jobs[0]
    state=str(latest.get('status',''))
    detail=str(latest.get('detail',''))
    if state in J.ACTIVE:
        st.markdown('<div class="p112"><div class="softnote"><b>Preparando el PEA</b> · '+esc(detail)+'. El estado se actualiza automáticamente; puedes continuar trabajando en otra hoja.</div></div>',unsafe_allow_html=True)
    elif state=='Listo':
        a,_=_artifact_and_content(g)
        if a:
            st.markdown('<div class="p112"><div class="softnote" style="border-color:#417d63"><b>Word disponible para revisión.</b> Ya puedes consultar las unidades y descargar el documento en Salida.</div></div>',unsafe_allow_html=True)
            if st.button('Ver contenido académico →',key='p112_ready_next',type='primary'):
                st.rerun()
        else:
            st.caption('El trabajo terminó; vuelve a abrir el contenido para comprobar el archivo guardado.')
    elif state in ('Error','Tiempo agotado','Interrumpido'):
        st.markdown('<div class="p112"><div class="softnote"><b>Generación no completada:</b> '+esc(detail)+'</div></div>',unsafe_allow_html=True)

def _poll_job(g):
    @st.fragment(run_every=5)
    def _status():
        _job_auto_notice(g)
    _status()

def content(g):
    st.markdown('<div class="p112"><div class="ptitle">Contenido académico</div><p class="tiny">Elaboración según los prompts establecidos con Tema 1 y Tema 2. El revisor de documentos existentes se encuentra en otra hoja.</p></div>',unsafe_allow_html=True)
    art,acad=_artifact_and_content(g)
    left,right=st.columns([1.6,1],gap='medium')
    with left:
        with st.container(border=True):
            if acad:
                _display_hora_summary(acad,g['duracion'])
            _show_content(acad)
            if not acad:
                c=st.columns(2)
                if c[0].button('Generar contenido y Word',type='primary',key='p112_make'):
                    try:
                        job=J.start(g,10,st.session_state.get('p112_jsondata'))
                        st.session_state['p112_job']=job
                        st.rerun()
                    except Exception as exc:st.error('No se pudo iniciar la generación: '+str(exc))
                if c[1].button('Cargar JSON académico',key='p112_json_toggle'):
                    st.session_state['p112_show_json']=not st.session_state.get('p112_show_json',False)
                if st.session_state.get('p112_show_json'):
                    f=st.file_uploader('Contenido JSON para validar con el motor institucional',type=['json'],key='p112_json_file')
                    if f:
                        try:st.session_state['p112_jsondata']=json.loads(f.getvalue());st.caption('JSON recibido; será validado por el motor antes de generar Word.')
                        except Exception as exc:st.error('JSON inválido: '+str(exc))
            else:
                if st.button('Solicitar un nuevo borrador',key='p112_regenerate'):
                    try:st.session_state['p112_job']=J.start(g,10,None);st.rerun()
                    except Exception as exc:st.error(str(exc))
        _poll_job(g)
    with right:
        with st.container(border=True):
            st.markdown('**Control de calidad**')
            if acad:
                st.caption('El motor original ya validó el esquema académico y guardó la copia Word.')
                for name in ('Duración oficial','Validación académica del motor','Plantilla institucional'):
                    st.markdown('<div class="p112"><div class="item"><span class="ok">✓</span> '+esc(name)+'</div></div>',unsafe_allow_html=True)
                st.caption('El texto y las evidencias pueden revisarse antes de entregar el PEA; no constituye autorización.')
            else:
                st.caption('Se comprobarán horas, contenido didáctico y estructura antes de guardar el documento.')
        st.markdown('<div class="p112"><div class="softnote"><b>Plantilla congelada.</b> El motor conserva estructura, tablas y tipografía del Word institucional.</div></div>',unsafe_allow_html=True)
    if art:
        if st.button('Continuar a Salida →',type='primary',key='p112_go_exit'):_go('salida')
    bottom('contenido')

def pdf_converter():
    """Solo conversión fiel DOCX→PDF cuando LibreOffice existe en el servidor."""
    return shutil.which('libreoffice') or shutil.which('soffice')

def convert_pdf(docx):
    exe=pdf_converter()
    if not exe:raise RuntimeError('No se encontró LibreOffice en Cloud Shell. Descarga el Word y utiliza Guardar como PDF en Microsoft Word. No se realizará una conversión que altere la plantilla.')
    docx=Path(docx).resolve()
    if not docx.is_file() or docx.suffix.lower()!='.docx':raise ValueError('Archivo Word no disponible')
    with tempfile.TemporaryDirectory(prefix='atrio_pdf_') as temp:
        tmp=Path(temp)
        profile=(tmp/'lo_profile').as_uri()
        res=subprocess.run([exe,'-env:UserInstallation='+profile,'--headless','--convert-to','pdf:writer_pdf_Export','--outdir',str(tmp),str(docx)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=100,check=False)
        rendered=tmp/(docx.stem+'.pdf')
        if res.returncode or not rendered.is_file() or rendered.stat().st_size<400 or not rendered.read_bytes()[:5]==b'%PDF-':
            raise RuntimeError('La conversión no produjo un PDF válido; conserva el Word. '+(res.stderr or res.stdout)[-300:])
        dest=docx.with_suffix('.pdf');os.replace(rendered,dest)
        return dest

def exit_stage(g):
    art,acad=_artifact_and_content(g)
    if not art:
        st.caption('El Word todavía no está listo. Vuelve a Contenido y genera el borrador.')
        bottom('salida');return
    path=(C.ROOT/art['path']).resolve()
    if C.OUT.resolve() not in path.parents or not path.is_file():
        st.warning('El documento registrado aún no está disponible. Comprueba el proceso de generación.');bottom('salida');return
    st.markdown('<div class="p112"><div class="done"><div style="font-size:35px;color:#438663">✓</div><h2>Borrador listo para revisión</h2><p class="sub">Copia generada sobre el formato institucional, sin firma ni autorización automática.</p><div class="docrow">📄 '+esc(path.name)+' &nbsp; · &nbsp; '+str(int(g['duracion']))+' horas &nbsp; · &nbsp; DOCX</div></div></div>',unsafe_allow_html=True)
    # ATRIO 10.12.3: se retira solo la acción de PDF de Salida.
    # Permanecen el Word institucional, el JSON académico y el envío a Revisor.
    options=st.columns(3,gap='small')
    with options[0]:
        st.download_button('↓ Borrador Word',path.read_bytes(),file_name='PEA_'+g['nombre'].replace(' ','_')+'.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',use_container_width=True,key='p112_download')
    with options[1]:
        if acad:
            st.download_button('↓ Control JSON',json.dumps(acad,ensure_ascii=False,indent=2).encode('utf-8'),file_name='CONTROL_PEA_'+str(art['id'])[:8]+'.json',mime='application/json',use_container_width=True,key='p112_json_dl')
        else:
            st.button('Control JSON · no disponible',disabled=True,use_container_width=True,key='p112_json_none')
    with options[2]:
        if st.button('Enviar a Revisor →',use_container_width=True,type='primary',key='p112_send'):
            st.session_state['rv112_group']=g['id']
            st.session_state['rv112_artifact']=art['id']
            st.session_state['rv112_source']='Elegir de Mis PEA'
            st.session_state['_atrio_pagina_actual']='Revisor'
            st.session_state['jump']='Revisor';st.rerun()
    st.caption('Huella de control: '+str(art['id'])+' · Registro: PEA generado, pendiente de revisión.')
    bottom('salida')

def panel(g):
    # ATRIO 10.12.13: ruta independiente para Repositorio del ciclo vigente.
    # No cambia el asistente de Extensión, ni el generador institucional.
    if g.get('tipo')=='Repositorio':
        import pea_repositorio_actual_101213 as R213
        return R213.panel(g)
    stage=st.session_state.get('pea110_stage','validacion')
    if stage not in ('validacion','contenido','salida'):stage='validacion'
    top(g,stage)
    if stage=='validacion':validation(g)
    elif stage=='contenido':content(g)
    else:exit_stage(g)
