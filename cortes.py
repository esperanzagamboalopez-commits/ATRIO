"""Historial SISAE y comparación de grupos e inscripciones entre dos respaldos."""
import fcntl,io,os,re,uuid,zipfile
from collections import Counter
from datetime import date
from pathlib import Path
import centro as C

KNOWN={'016026619ce2ee13479393412722d2cabd08d574da4cbf7de0eab8a29a94ca3b':'2026-10-17','6241c87feb027edd2217ed4bd07321de6d01563a2b65a455131a70840d4d99a0':'2026-10-29'}
G='PROG_CURSOS1.DBF'
I='INSCRIPCION.DBF'

def history():
    active=C.RES/'SISAE.zip'
    paths={}
    for p in [*sorted(C.ARCH.glob('*_SISAE.zip')),active]:
        if p.is_file():paths[C.sha(p.read_bytes())]=p
    return paths,C.sha(active.read_bytes()) if active.exists() else None

def records(rows,fields):
    result={}
    for row in rows:
        key=tuple(row[k].strip() for k in fields)
        if not all(key) or key in result:raise ValueError('Hay claves vacías o repetidas en este corte. Revisa las tablas antes de comparar.')
        result[key]=row
    return result

def validate(raw):
    if len(raw)>100*1024*1024:raise ValueError('El límite por respaldo es de 100 MB.')
    tables=C.sisae_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names={Path(n.strip()).name.upper():n for n in z.namelist()}
        for n,required in [(G,{'CLAVE_CURS','NOM_CURSO','DOC_NOM','CLV_AREA','CLV_ESP','F_INICIO','F_TERMINO','HRS_CURSO','LU_AM'}|{f'DIA{i}{end}' for i in range(1,4) for end in ('','A','_DE','_A')}|{'PERIODO'}),(I,{'CLV_CURSO','ID_ALUMNO','CURP','A_PATERNO','A_MATERNO','NOMBRE'}),('ESP.DBF',{'CLV_AREA','CLV_ESP','NOM_ESP'})]:
            if n not in names:raise ValueError('Falta '+n+' en el ZIP.')
            b=z.read(names[n]);head=int.from_bytes(b[8:10],'little');size=int.from_bytes(b[10:12],'little');count=int.from_bytes(b[4:8],'little')
            if head<33 or size<1 or len(b)<head+size*count:raise ValueError('Tabla incompleta: '+n)
            fields={b[i:i+11].split(b'\0')[0].decode() for i in range(32,head-1,32)}
            if required-fields:raise ValueError('Faltan columnas de '+n+': '+', '.join(sorted(required-fields)))
    records(tables[G],['CLAVE_CURS']);records(tables[I],['CLV_CURSO','ID_ALUMNO'])
    return tables

def save(raw,name,cut,activate):
    validate(raw);digest=C.sha(raw)
    with (C.DATA/'sisae.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        paths,active=history()
        if digest not in paths:
            target=C.ARCH/(digest+'_SISAE.zip')
            tmp=target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
            tmp.write_bytes(raw);os.replace(tmp,target)
        C.set_setting('corte_'+digest,{'date':cut.isoformat(),'name':Path(name).name})
        if activate and digest!=active:C.save_resource('SISAE.zip',raw)
    return digest

def compare(old,new):
    out={}
    for table,fields in [(G,['CLAVE_CURS']),(I,['CLV_CURSO','ID_ALUMNO'])]:
        a=records(old[table],fields);b=records(new[table],fields)
        changes=[]
        for k in sorted(a.keys()|b.keys()):
            ids=dict(zip(fields,k));row=b.get(k) or a[k]
            ids['Curso']=row.get('NOM_CURSO',row.get('NOM_CUR',''))
            if k not in a or k not in b:
                changes.append({**ids,'Movimiento':'Aparece' if k in b else 'Ya no aparece','Campos':''})
            else:
                diff=sorted(f for f in a[k].keys()|b[k].keys() if f not in ['DATE_CREAT','DATE_UPDAT','MAC_ADDRES','MAC_ADDRE2'] and a[k].get(f,'')!=b[k].get(f,''))
                if diff:changes.append({**ids,'Movimiento':'Cambió','Campos':', '.join(diff)})
        out[table]=changes
    return out

def panel():
    import streamlit as st
    paths,active=history()
    def meta(h):
        return C.setting('corte_'+h,{'date':KNOWN.get(h,''),'name':'Respaldo anterior'})
    def label(h):
        m=meta(h);d=m['date']
        return (date.fromisoformat(d).strftime('%d/%m/%Y') if d else 'Fecha sin identificar')+' · '+('Vigente · ' if h==active else '')+m['name']+' · '+h[:7]
    if active:st.info('Corte que usa ATRIO · '+label(active))
    st.subheader('Subir respaldo SISAE')
    st.caption('Selecciona el ZIP completo tal como lo exportaste de SISAE.')
    file=st.file_uploader('ZIP de tablas SISAE',type=['zip'],key='corte_zip')
    if file:
        raw=file.getvalue();h=C.sha(raw)
        try:
            t=validate(raw)
            st.write(f'{len(t[G])} grupos · {len(t[I])} inscripciones')
            m=re.search(r'(20\d\d)[._-](\d\d)[._-](\d\d)',file.name)
            guess=KNOWN.get(h) or ('-'.join(m.groups()) if m else '')
            cut=st.date_input('Fecha del corte',date.fromisoformat(guess) if guess else None,key='fecha_'+h)
            action=st.radio('Uso del respaldo',['Guardar solo en historial','Usar como corte actual'],key='uso_'+h)
            if st.button('Guardar corte',disabled=not cut):
                save(raw,file.name,cut,action=='Usar como corte actual')
                st.session_state['corte_aviso']='Corte guardado. '+('ATRIO ya consulta este respaldo.' if action=='Usar como corte actual' else 'Disponible para comparar.');st.rerun()
        except Exception as exc:st.error('No se pudo cargar el respaldo. '+str(exc))
    if st.session_state.get('corte_aviso'):st.success(st.session_state['corte_aviso'])
    st.subheader('Comparar dos cortes')
    if len(paths)<2:st.info('Guarda un segundo ZIP en el historial para habilitar la comparación.');return
    ordered=sorted(paths,key=lambda h:meta(h)['date'],reverse=True)
    current=st.selectbox('Corte a revisar',ordered,index=ordered.index(active) if active in ordered else 0,format_func=label)
    opts=[h for h in ordered if h!=current]
    old=st.selectbox('Comparar contra',opts,format_func=label)
    a=C.sisae_bytes(paths[old].read_bytes());b=C.sisae_bytes(paths[current].read_bytes())
    st.caption('Lectura de los cambios desde «Comparar contra» hacia «Corte a revisar». Una ausencia describe solo estos archivos.')
    for col,t,title in zip(st.columns(2),(G,I),('Grupos','Inscripciones')):
        col.metric(title,len(b[t]),len(b[t])-len(a[t]))
    try:result=compare(a,b)
    except ValueError as exc:st.error(str(exc));return
    for t,tab in zip((G,I),st.tabs(['Grupos','Inscripciones por grupo'])):
        with tab:
            rows=result[t];counts=Counter(x['Movimiento'] for x in rows)
            st.write(f"Aparecen: {counts['Aparece']} · Cambiaron: {counts['Cambió']} · Ya no aparecen: {counts['Ya no aparece']}")
            if rows:st.dataframe(rows,hide_index=True,width='stretch')
