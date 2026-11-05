from pathlib import Path
from collections import Counter
from datetime import date,datetime
import hashlib, io, json, re, zipfile
import streamlit as st
import streamlit.components.v1 as components
from openpyxl import load_workbook
import centro as C

ROOT=Path(__file__).parent
widget=components.declare_component('atrio_hoja',path=str(ROOT/'puente'))
def safe(value):
    return json.dumps(value,ensure_ascii=False,default=str).replace('<','\\u003c')

class RecursoFaltante(Exception):
    pass

def leer_recurso(nombre):
    """Lee un recurso de datos/recursos; si falta, lanza RecursoFaltante con mensaje en español."""
    try:
        return (C.RES/nombre).read_bytes()
    except FileNotFoundError as exc:
        raise RecursoFaltante(f'Falta el archivo {nombre}. Por favor, súbelo en Ajustes.') from exc

def snapshot(groups):
    # El id del laboratorio es numérico. Usar una conversión estable del UUID.
    # Los primeros 13 dígitos hexadecimales caben exactamente en Number (JS).
    rows=[dict(id=int(g['id'].replace('-','')[:13],16),fingerprint=g['fingerprint'],docente=g['hoja'],curso=g['nombre'],tipo=g['tipo'].upper(),inicio=g['inicio'],fin=g['fin'],horas=g['duracion'],horario=g['horario'],sede=g['aula'],fila=g['fila']) for g in groups]
    ids={str(r['id']):g for r,g in zip(rows,groups)}
    if len(ids)!=len(rows):raise ValueError('Identificadores de grupo ambiguos.')
    raw=leer_recurso('SISAE.zip')
    tables=C.sisae_bytes(raw)
    counts=Counter(r['CLV_CURSO'] for r in tables['INSCRIPCION.DBF'])
    def dt(x):return f'{x[:4]}-{x[4:6]}-{x[6:]}' if len(x)==8 else ''
    sis=[]
    for r in tables['PROG_CURSOS1.DBF']:
        horarios=[]
        for i in ('1','2','3'):
            k='DIA'+i
            if r[k]:horarios.append(' '.join(v for v in [r[k],'a '+r[k+'A'] if r[k+'A'] else '',r[k+'_DE'],'a',r[k+'_A']] if v))
        sis.append(dict(key=r['CLAVE_CURS'],curso=r['NOM_CURSO'],docente=r['DOC_NOM'],inicio=dt(r['F_INICIO']),fin=dt(r['F_TERMINO']),horas=float(r['HRS_CURSO'] or 0),horario='; '.join(horarios),periodo=r['PERIODO'],alumnos=counts[r['CLAVE_CURS']]))
    def signature(g):
        norm=C.motor.normal;h=norm(g['horario'])
        return(norm(g['curso']),tuple(sorted(norm(g['docente']).split())),g['inicio'],g['fin'],g['horas'],tuple(re.findall(r'\d\d:\d\d',h)),tuple(re.findall('lunes|martes|miercoles|jueves|viernes|sabado|domingo',h)))
    sf=Counter(signature(g) for g in sis);xf=Counter(signature(g) for g in rows)
    by={signature(g):g for g in sis}
    links={str(g['id']):by[signature(g)] for g in rows if sf[signature(g)]==xf[signature(g)]==1}
    digest=hashlib.sha256(raw).hexdigest()
    lookup={g['key']:g for g in sis}
    saved=C.setting('hojas03_links',{})
    for r in rows:
        ident=str(r['id'])
        record=saved.get(ident,{})
        key=record.get('key')
        r['automatic']=ident in links
        if record.get('cut')==digest and record.get('fingerprint')==r['fingerprint'] and (key in lookup or key==''):
            if key:
                links[ident]=lookup[key]
            else:
                links.pop(ident,None)  # Desvinculación explícita: no restaurar sugerencia automática
            r['automatic']=False
        r['linked']=links.get(ident,{}).get('key','')
        r['cut']=digest
    students={k:[dict(id=r['ID_ALUMNO'],nombre=' '.join(r[n] for n in ('NOMBRE','A_PATERNO','A_MATERNO'))) for r in tables['INSCRIPCION.DBF'] if r['CLV_CURSO']==v['key']] for k,v in links.items()}
    return rows,ids,sis,links,students,hashlib.sha256(raw).hexdigest()

def working_copy(ids,proposals):
    wb=load_workbook(C.RES/'PROGRAMACION DE CURSOS.xlsx')
    for k,p in proposals.items():
        g=ids.get(k)
        if not g or p.get('fingerprint')!=g['fingerprint']:raise ValueError('Una propuesta corresponde a una programación anterior. Revisa esa ficha y guarda la propuesta nuevamente.')
        sheet=wb[g['hoja']]
        for key,col in [('curso',2),('inicio',5),('fin',6),('horas',7),('horario',9)]:
            v=p[key]
            if key in ('inicio','fin'):v=date.fromisoformat(v)
            elif key=='horas':v=float(v)
            cell=sheet.cell(g['fila'],col);cell.value=v
            if isinstance(v,str):cell.data_type='s'
    out=io.BytesIO();wb.save(out);return out.getvalue()

def show(number,groups,today,tracking=False):
    try:
        rows,ids,sis,links,students,digest=snapshot(groups)
    except RecursoFaltante as e:
        st.error(str(e))
        return
    except (zipfile.BadZipFile,KeyError,ValueError) as e:
        st.error(f'El archivo SISAE.zip no se pudo leer ({e}). Por favor, vuelve a subirlo en Ajustes.')
        return
    keys=['links','proposals','pea','school','bags','records']
    state={k:C.setting('hojas03_'+k,{}) for k in keys}
    for k,g in ids.items():
        status=C.status(g['id'])
        if k in state['pea'] or status['doc']!='Sin verificar' or status['mce']!='Sin verificar':
            state['pea'][k]=dict(state['pea'].get(k,{}),doc=status['doc'],mce=status['mce'],note=status['note'])
    template=(ROOT/f'hoja{number}.html').read_text()
    import tema
    template='<style>'+tema.root_css()+'</style>'+template
    if number==3:
        # ATRIO 10.9: elegir tarjeta en paso 2 avanza al paso 3, sin tocar
        # el HTML ni la lógica de los pasos 3, 4 y 5.
        antes='course=picked}draw()'
        despues='course=picked;if(course){window.openCourse(course.id);return}}draw()'
        if template.count(antes)!=1:
            st.error('Asistente PEA diferente al revisado: no se modifica el avance automático.')
        else:
            template=template.replace(antes,despues,1)
    if number==3:
        # ATRIO 10.12.1: SOLO apariencia del selector inicial Docente/Curso.
        # Igualar botones del indicador de cinco pasos al resto de Preparar PEA.
        template += """<style>
        #atrio-preparacion .steps{display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;gap:9px!important;width:100%!important}
        #atrio-preparacion .wizard-step{border:1px solid #dec9c4!important;border-radius:10px!important;background:#fffbf8!important;color:#563742!important;min-height:44px!important;padding:10px 7px!important;font-size:12px!important;font-weight:600!important}
        #atrio-preparacion .wizard-step.current{background:var(--atrio-neon)!important;border-color:var(--atrio-neon)!important;color:var(--atrio-sobre-acento)!important;opacity:1!important}
        #atrio-preparacion .wizard-step:disabled:not(.current){opacity:.7!important}
        #atrio-preparacion .button.primary{border-radius:10px!important;background:#6d2e49!important;border-color:#a36b84!important}
        @media(max-width:650px){#atrio-preparacion .steps{gap:3px!important}#atrio-preparacion .wizard-step{padding:8px 2px!important;font-size:10px!important}}
        </style>"""
    if number==3 and st.session_state.pop('pea110_return',False):
        # Al volver, restaurar selección y regresar al paso Validación (3),
        # sin cambiar el HTML original del asistente.
        selected=st.session_state.get('editor_group')
        wid=next((str(k) for k,g in ids.items() if g['id']==selected),None)
        if wid is not None:
            teacher=ids[wid]['hoja']
            restore=json.dumps({'id':wid,'docente':teacher})
            template+='''<script>window.addEventListener('load',()=>{
               const chosen='''+restore+''';
               const b=[...document.querySelectorAll('[data-wteacher]')].find(x=>x.textContent.includes(chosen.docente));
               if(b)b.click();
               const course=document.querySelector('[data-wcourse="'+chosen.id+'"]');
               if(course)course.click();
            });</script>'''
    template=re.sub(r'<aside>.*?</aside>','',template,flags=re.S)
    template+='<style>body{margin:0}div.shell{display:block!important;grid-template-columns:1fr!important}main{min-width:0}</style>'
    values={'program-data':rows,'ce-data':rows,'close-data':rows,'sis-reference':sis,'sisae-data':sis,'ce-links':links,'ce-students':students}
    for k,v in values.items():template=template.replace('@@'+k+'@@',safe(v))
    template=template.replace('@@ngrupos@@',str(len(rows))).replace('@@fecha@@','corte cargado').replace('@@hoy@@',today.isoformat()).replace('@@corte@@',f'{len(sis)} grupos y {sum(x["alumnos"] for x in sis)} inscripciones')
    bridge='''<script>window.store=STATE;let before=JSON.parse(JSON.stringify(window.store));window.openCourse=id=>parent.postMessage({atrio:'open',id},'*');
    function flush(){let delta=[];for(let k of Object.keys(window.store)){for(let id of new Set([...Object.keys(window.store[k]),...Object.keys(before[k])])){let value=window.store[k][id],old=before[k][id];if(JSON.stringify(old)!==JSON.stringify(value))delta.push({k,id,old:old??null,value:value??null})}}
    if(delta.length){before=JSON.parse(JSON.stringify(window.store));parent.postMessage({atrio:'save',delta},'*')}}
    document.addEventListener('click',()=>setTimeout(flush,60));window.addEventListener('load',()=>new ResizeObserver(()=>parent.postMessage({atrio:'height',height:document.body.offsetHeight+4},'*')).observe(document.body));</script>'''.replace('STATE',safe(state))
    if tracking:template+='<script>document.querySelector("#show-tracking").click()</script>'
    rev=st.session_state.get('html_refresh',0)
    token=hashlib.sha256((digest+str(number)+str(tracking)+str(rev)+''.join(g['fingerprint'] for g in groups)).encode()).hexdigest()
    download=st.empty()
    event=widget(page=bridge+template,signature=token,notice=st.session_state.get('hojas_notice',''),key='hoja03_'+str(number),default=None)
    if event and event.get('nonce')!=st.session_state.get('handled'+str(number)):
        st.session_state['handled'+str(number)]=event['nonce']
        if event.get('atrio')=='credenciales' and number==4:
            import credenciales
            key=links.get(str(event.get('id')),{}).get('key')
            st.session_state.pop('cred_output',None)
            try:
                if not key or key!=event.get('group') or digest!=event.get('cut'):raise ValueError('Cambió el corte o el grupo. Vuelve a seleccionar los alumnos.')
                selected=credenciales.datos((C.RES/'SISAE.zip').read_bytes(),key,event['students'])
                st.session_state['cred_output']=(key,digest,len(selected),credenciales.powerpoint(selected))
                st.session_state['hojas_notice']='PowerPoint listo. Descárgalo arriba de la ficha.'
            except ValueError as exc:st.session_state['hojas_notice']=str(exc)
            st.rerun()
        if event.get('atrio')=='open' and str(event.get('id')) in ids:
            g=ids[str(event['id'])];st.session_state.update(selected=g['id'],teacher=g['hoja'],editor_group=g['id'],jump='Preparar PEA',pea110_stage='validacion');st.rerun()
        if event.get('atrio')=='save':
            try:
                save_changes(event['delta'],ids,number)
            except ValueError as exc:
                st.session_state['html_refresh']=rev+1
                st.session_state['hojas_notice']=str(exc)
                st.rerun()
            st.session_state['hojas_notice']='Cambios guardados en ATRIO.';st.rerun()
    result=st.session_state.get('cred_output')
    if number==4 and result and result[1]==digest:
        download.download_button(f'Descargar {result[2]} credencial(es) · grupo {result[0]}',result[3],file_name=f'CREDENCIALES_{result[0]}.pptx')
    if number==2 and state['proposals']:
        try:st.download_button('Descargar copia de Excel con propuestas',working_copy(ids,state['proposals']),'PROGRAMACION_PROPUESTA.xlsx')
        except ValueError as exc:st.error(str(exc))

def save_changes(delta,ids,number):
    allowed={2:{'proposals','links'},3:{'pea'},4:{'school'},5:{'pea','records','bags'}}[number]
    with C.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for item in delta:
            k=item['k']
            ident=str(item['id'])
            if k not in allowed:raise ValueError('El cambio no corresponde a esta hoja.')
            row=db.execute('SELECT value FROM settings WHERE key=?',('hojas03_'+k,)).fetchone()
            current=json.loads(row[0]) if row else {}
            old=current.get(ident)
            val=item['value']
            if k=='links':
                rows,_,sis,_,_,cut=snapshot(list(ids.values()))
                if (ident not in ids or not isinstance(val,dict) or
                    val.get('fingerprint')!=ids[ident]['fingerprint'] or val.get('cut')!=cut or
                    (val.get('key') and not any(g['key']==val['key'] for g in sis))):
                    raise ValueError('Cambió la referencia. Vuelve a revisar la ficha.')
                if val.get('key') and any(str(x['id'])!=ident and x['linked']==val['key'] for x in rows):
                    raise ValueError('Ese grupo SISAE ya corresponde a otra ficha.')
            if k=='pea':
                if ident not in ids:raise ValueError('El grupo cambió en la programación.')
                uid=ids[ident]['id']
                row=db.execute('SELECT doc,mce,note FROM status WHERE group_id=?',(uid,)).fetchone()
                if row:old=dict(old or {},**dict(row))
            if old==val:continue
            expected=item.get('old')
            if k=='pea' and isinstance(expected,dict):
                expected={'note':'',**expected}
            if old!=expected:
                raise ValueError('El registro cambió en otra pantalla. Se cargó su versión más reciente. Revisa el cambio antes de guardar.')
            if k=='pea':
                db.execute('INSERT OR REPLACE INTO status(group_id,doc,mce,note) VALUES(?,?,?,?)',(uid,val['doc'],val['mce'],val.get('note','')))
            if val is None:current.pop(ident,None)
            else:current[ident]=val
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('hojas03_'+k,json.dumps(current,ensure_ascii=False)))
            db.execute('INSERT INTO events(at,action,payload) VALUES(?,?,?)',(C.now(),'Cambio en hoja '+str(number),json.dumps({'apartado':k,'id':ident,'antes':old,'despues':val},ensure_ascii=False)))
