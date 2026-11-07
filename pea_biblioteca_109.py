"""ATRIO 10.9: biblioteca original/derivado y revisión selectiva de PEA Word.

No autoriza ni modifica el documento del docente. Toda modificación produce un borrador.
Conserva el esquema de registros de 10.8 para leer archivos subidos antes de su reversión.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, date
from zipfile import ZipFile
from lxml import etree
from docx import Document
import hashlib, io, os, re, uuid, json
import streamlit as st
import centro as C
import pea_adaptacion_1010 as AUTO

BASE = C.OUT / 'biblioteca_pea'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
MAX_BYTES = 20 * 1024 * 1024
F = '%d/%m/%Y'


def _db():
    db=C.connect()
    db.execute('''CREATE TABLE IF NOT EXISTS biblioteca_pea (
        id TEXT PRIMARY KEY, origen TEXT NOT NULL, parent_id TEXT,
        group_id TEXT, curso TEXT, docente TEXT, tipo TEXT, duracion REAL,
        nombre_original TEXT, ruta TEXT NOT NULL, sha256 TEXT NOT NULL,
        creado TEXT NOT NULL, estado TEXT NOT NULL, nota TEXT DEFAULT ''
    )''')
    return db


def listar(origen=None):
    with _db() as db:
        sql='SELECT * FROM biblioteca_pea WHERE 1=1'; args=[]
        if origen:
            sql+=' AND origen=?';args=[origen]
        sql+=' ORDER BY creado DESC'
        return [dict(x) for x in db.execute(sql,args)]


def _ruta(r):
    path=(C.ROOT/r['ruta']).resolve()
    if BASE.resolve() not in path.parents or not path.is_file():
        raise ValueError('El documento no existe o su ruta no está permitida.')
    return path


def _documento(r):
    if r.get('origen')!='ATRIO generado':return _ruta(r).read_bytes()
    path=(C.ROOT/r['ruta']).resolve()
    if C.OUT.resolve() not in path.parents or not path.is_file():
        raise ValueError('Documento generado fuera del área de salidas de ATRIO.')
    return path.read_bytes()


def candidatos():
    """Word guardados en Subidos, copias generadas y originales generados por ATRIO."""
    rows=listar()
    try:
        # Los documentos de grupos sustituidos también deben conservar su contexto.
        # Se consulta groups completo, sin reactivar ni modificar antecedentes.
        with C.connect() as db:
            stored_groups=db.execute('SELECT id,fingerprint,payload FROM groups').fetchall()
            artifacts=[dict(x) for x in db.execute('SELECT * FROM artifacts ORDER BY created DESC LIMIT 250')]
        groups={}
        for stored in stored_groups:
            try:
                groups[stored['id']] = {
                    'payload': json.loads(stored['payload'] or '{}'),
                    'fingerprint': stored['fingerprint'],
                }
            except (TypeError, ValueError):
                continue
        for a in artifacts:
            stored=groups.get(a['group_id'],{})
            g=stored.get('payload',{})
            old_version=bool(
                a.get('fingerprint') and stored.get('fingerprint')
                and a['fingerprint'] != stored['fingerprint']
            )
            path=(C.ROOT/a['path']).resolve()
            if C.OUT.resolve() not in path.parents or path.suffix.lower()!='.docx' or not path.is_file():
                continue
            meta=g.get('_atrio') or {}
            rows.append({'id':'atrio:'+a['id'],'origen':'ATRIO generado','group_id':a['group_id'],
                        'curso':g.get('nombre','PEA generado por ATRIO'),'docente':g.get('hoja','Docente histórico'),
                        'duracion':g.get('duracion','?'),'creado':a['created'],
                        'estado_programacion':meta.get('estado_programacion',''),
                        'es_version_anterior':old_version,
                        'ruta':str(path.relative_to(C.ROOT)),'nombre_original':path.name})
    except Exception:
        # Los originales de biblioteca siguen accesibles si no hay artefactos nativos.
        pass
    return rows


def _root(raw):
    if len(raw)>MAX_BYTES:raise ValueError('El Word supera 20 MB.')
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            if not {'word/document.xml','[Content_Types].xml'}.issubset(z.namelist()):
                raise ValueError('Archivo DOCX inválido.')
            if sum(i.file_size for i in z.infolist())>100*1024*1024:
                raise ValueError('DOCX con tamaño descomprimido excesivo.')
            if any(i.filename.lower().endswith('vbaproject.bin') for i in z.infolist()):
                raise ValueError('No se admiten archivos con macros.')
            return etree.fromstring(z.read('word/document.xml'))
    except (OSError, ValueError, etree.XMLSyntaxError) as exc:
        raise ValueError('No se puede interpretar este DOCX: '+str(exc)) from exc


def _norm(s):
    return C.motor.normal(str(s or ''))


def diagnostico(raw):
    root=_root(raw); doc=Document(io.BytesIO(raw))
    dur=None; start=''; end=''; horario='';dias='';curso='';participantes=None
    for t in doc.tables:
        cells=[c.text.strip() for r in t.rows[:1] for c in r.cells]
        flat=' '.join(cells).upper()
        if 'NOMBRE DEL CURSO' in flat:
            pos=next((i for i,c in enumerate(cells) if 'NOMBRE DEL CURSO' in c.upper()),-1)
            if pos>=0 and pos+1<len(cells):curso=cells[pos+1]
        if 'DURACIÓN TOTAL' in flat and 'HORARIO DEL CURSO' in flat:
            for i,c in enumerate(cells):
                if 'DURACIÓN TOTAL' in c and i+1<len(cells):
                    x=re.search(r'\d+(?:[.,]\d+)?',cells[i+1]);dur=float(x.group().replace(',','.')) if x else None
                if 'HORARIO DEL CURSO' in c and i+1<len(cells):horario=cells[i+1]
        if 'NÚMERO DE PARTICIPANTES' in flat:
            for v in cells:
                if re.fullmatch(r'\d+',v):participantes=int(v)
        if 'DÍAS Y HORARIO' in flat and 'INICIO' in flat:
            for c in cells:
                dates=re.findall(r'\b\d{2}/\d{2}/\d{4}\b',c)
                for dt in dates:
                    if not start:start=dt
                    elif not end:end=dt
                if len(c)>25 and any(d in c.lower() for d in ('lunes','martes','miércoles','viernes')):dias=c
    # Las fechas del PEA de muestra están en controles de contenido Word.
    for tbl in root.xpath('.//w:tbl',namespaces=NS):
        texts=tbl.xpath('.//w:t/text()',namespaces=NS)
        joined=' '.join(texts)
        if 'DÍAS Y HORARIO' in joined and 'INICIO' in joined and 'TÉRMINO' in joined:
            dates=re.findall(r'\b\d{2}/\d{2}/\d{4}\b',joined)
            if len(dates)>=2:start,end=dates[:2]
            break
    if dur is None:
        joined=' '.join(root.xpath('.//w:t/text()',namespaces=NS))
        m=re.search(r'DURACI[ÓO]N\s+TOTAL\s+(\d+(?:[.,]\d+)?)\s+horas',joined,re.I)
        if m:dur=float(m.group(1).replace(',','.'))
    if not curso:
        joined=' '.join(root.xpath('.//w:t/text()',namespaces=NS))
        m=re.search(r'NOMBRE DEL CURSO\s+(.+?)\s+CECATI\s+Y ENTIDAD FEDERATIVA',joined,re.I)
        if m and len(m.group(1).strip())<90:curso=m.group(1).strip()
    graphics=0
    for tbl in root.xpath('.//w:tbl',namespaces=NS):
        labels=' '.join(tbl.xpath('.//w:t/text()',namespaces=NS)).lower()
        if 'elabora' in labels and 'valida' in labels:
            graphics+=len(tbl.xpath('.//w:drawing|.//w:pict|.//w:object',namespaces=NS))
    return {'duracion':dur,'inicio':start,'termino':end,'horario':horario,'dias':dias,'curso':curso,
            'participantes':participantes,'tablas':len(doc.tables),'secciones':len(doc.sections),'firmas_graficas':graphics}


def _programado_fecha(iso):return date.fromisoformat(iso).strftime(F)


DAYS=('lunes','martes','miercoles','jueves','viernes','sabado','domingo')

def _timeblocks(s):
    return [(int(h),int(m)) for h,m in re.findall(r'(?<!\d)(\d{1,2}):(\d{2})(?!\d)',str(s))]

def _time_text(s):
    times=_timeblocks(s)
    if len(times)<2:return str(s)
    (a,b),(c,d)=times[:2]
    return f'{a}:{b:02d} a {c}:{d:02d}'

def _weekdays(s):
    import unicodedata
    v=''.join(c for c in unicodedata.normalize('NFD',str(s).lower()) if unicodedata.category(c)!='Mn')
    days={i for i,n in enumerate(DAYS) if re.search(r'\b'+n+r'\b',v)}
    for i,n in enumerate(DAYS):
        for j,n2 in enumerate(DAYS):
            if i<j and re.search(r'\b'+n+r'\s+a\s+'+n2+r'\b',v):days.update(range(i,j+1))
    return days

def campos(original,grupo):
    """Distingue diferencias de información y meras variantes ortográficas del horario."""
    d=diagnostico(original)
    newtime=_time_text(grupo['horario'])
    oldtime=_time_text(d['horario'])
    same_time=bool(_timeblocks(grupo['horario'])) and _timeblocks(grupo['horario'])[:2]==_timeblocks(d['horario'])[:2]
    dayset1=_weekdays(grupo['horario']);dayset2=_weekdays(d['dias'])
    same_days=bool(dayset1 and dayset2 and dayset1==dayset2)
    days_new=d['dias'] if same_days and same_time else grupo['horario']
    items=[('Fecha de inicio',d['inicio'],_programado_fecha(grupo['inicio']),'administrativo',None),
           ('Fecha de término',d['termino'],_programado_fecha(grupo['fin']),'administrativo',None),
           ('Duración',f"{d['duracion']:g} horas" if d['duracion'] is not None else '',f"{grupo['duracion']:g} horas",'academico',None),
           ('Horario',d['horario'],newtime,'administrativo',same_time),
           ('Días y horario',d['dias'],days_new,'administrativo',same_days and same_time)]
    return d,[{'campo':name,'anterior':old,'nuevo':new,'clase':kind,
               'diferente':(not forced if forced is not None else _norm(old)!=_norm(new))}
              for name,old,new,kind,forced in items]


def auditoria_didactica(raw):
    """Lee distribuciones explícitas, sin asumir si estudio independiente computa en la duración."""
    doc=Document(io.BytesIO(raw))
    blocks=[]; seen=[]
    names=('mediación docente','estudio independiente','prácticas')
    regex=re.compile(r'(\d+(?:[.,]\d+)?)\s*(?:de\s+)?horas?\s+de\s+(mediación docente|estudio independiente|prácticas)',re.I)
    for table in doc.tables:
        if not table.rows or 'SECUENCIA DIDÁCTICA' not in table.rows[0].cells[0].text:continue
        for row in table.rows:
            last=row.cells[-1]
            if any(last._tc is previous for previous in seen):continue
            seen.append(last._tc)
            matches=regex.findall(last.text)
            if not matches:continue
            label=' '.join(row.cells[0].text.split())[:95]
            if not label:label='Contenido sin título identificable'
            values={name:0.0 for name in names}
            for n,kind in matches:
                key=next((x for x in names if x.lower()==kind.lower()),None)
                if key:values[key]+=float(n.replace(',','.'))
            blocks.append({'actividad':label,**values})
    totals={name:round(sum(b[name] for b in blocks),2) for name in names}
    return blocks,totals


def guardar_original(raw,nombre,grupo):
    if not nombre.lower().endswith('.docx'):raise ValueError('Se requiere Word .docx.')
    d=diagnostico(raw)
    digest=hashlib.sha256(raw).hexdigest()
    for r in listar(origen='Subido'):
        if r['sha256']==digest:
            return r['id'],False
    ident=str(uuid.uuid4());folder=BASE/ident;folder.mkdir(parents=True,exist_ok=False)
    target=folder/'ORIGINAL_DOCENTE.docx'
    try:
        with target.open('xb') as h:h.write(raw)
        with _db() as db:
            db.execute('''INSERT INTO biblioteca_pea
                (id,origen,parent_id,group_id,curso,docente,tipo,duracion,nombre_original,ruta,sha256,creado,estado,nota)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (ident,'Subido',None,grupo['id'],grupo['nombre'],grupo['hoja'],grupo['tipo'],d['duracion'],Path(nombre).name,
                 str(target.relative_to(C.ROOT)),digest,C.now(),'Original · pendiente de revisión','Original del docente conservado sin cambios.'))
        C.event(grupo['id'],'Original Word recibido',{'id':ident,'sha256':digest})
    except Exception:
        target.unlink(missing_ok=True)
        try:folder.rmdir()
        except OSError:pass
        raise
    return ident,True


def _tables(root):
    for tbl in root.xpath('.//w:tbl',namespaces=NS):
        flat=' '.join(tbl.xpath('.//w:t/text()',namespaces=NS))
        yield tbl,flat


def _replace_in_table(root,condition,old,new):
    if not old or old==new:return 0
    found=0
    for tbl,flat in _tables(root):
        if condition(flat):
            for node in tbl.xpath('.//w:t',namespaces=NS):
                txt=node.text or ''
                if old in txt:
                    found+=txt.count(old)
                    node.text=txt.replace(old,new)
    return found


def _modificar_word(raw,edits):
    root=_root(raw); before=diagnostico(raw)
    if not edits:raise ValueError('No seleccionaste cambios.')
    totals={}
    for name,old,new in edits:
        if name in ('Fecha de inicio','Fecha de término','Días y horario'):
            fn=lambda s:'DÍAS Y HORARIO' in s and 'INICIO' in s
        elif name=='Horario':
            fn=lambda s:'HORARIO DEL CURSO' in s and 'DURACIÓN TOTAL' in s
        else:raise ValueError('Campo no permitido para modificación automática: '+name)
        hits=_replace_in_table(root,fn,old,new)
        if hits==0:raise ValueError('No se localizó sin ambigüedad el valor original de '+name+' en su tabla. No se creó Word.')
        totals[name]=hits
    # Solo se eliminan gráficos de la TABLA DE VALIDACIÓN, no logotipos del archivo.
    removed=0
    for tbl,labels in _tables(root):
        if 'elabora' in labels.lower() and 'valida' in labels.lower():
            for graphic in list(tbl.xpath('.//w:drawing|.//w:pict|.//w:object',namespaces=NS)):
                graphic.getparent().remove(graphic);removed+=1
    buffer=io.BytesIO()
    with ZipFile(io.BytesIO(raw)) as src,ZipFile(buffer,'w') as dest:
        for info in src.infolist():
            data=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True) if info.filename=='word/document.xml' else src.read(info.filename)
            dest.writestr(info,data)
    output=buffer.getvalue(); after=diagnostico(output)
    if (before['tablas'],before['secciones'])!=(after['tablas'],after['secciones']):
        raise ValueError('Cambió la estructura del Word. Se descartó la copia.')
    if after['firmas_graficas']:
        raise ValueError('Hay firmas gráficas en la sección de validación. La copia no se generó.')
    return output,removed,totals


def generar_copia(raw,nombre,grupo,seleccion,original_id=None):
    d,items=campos(raw,grupo)
    if grupo['tipo']=='Regular':raise ValueError('Regular: no corresponde generar PEA de Extensión.')
    if d['curso'] and _norm(d['curso'])!=_norm(grupo['nombre']):
        raise ValueError('El nombre del curso del Word no coincide con la programación. Selecciona el PEA correcto.')
    if d['duracion'] is None:raise ValueError('Duración del Word ilegible: no se puede verificar compatibilidad.')
    changes=[]
    for item in items:
        name=item['campo']
        if name in seleccion and item['diferente'] and item['clase']=='administrativo':
            if not item['anterior']:raise ValueError('No se leyó el dato original '+name+'. Revisión manual necesaria.')
            if name=='Días y horario' and not item['nuevo']:raise ValueError('Sin días de clase en programación.')
            changes.append((name,item['anterior'],item['nuevo']))
    if not changes and 'Duración' not in seleccion:raise ValueError('No seleccionaste cambios.')
    if 'Duración' in seleccion:
        plan=AUTO.proponer(raw,float(grupo['duracion']))
        result,removed=AUTO.aplicar(raw,plan,changes)
        counts={'Duración y planeación numérica':len(plan['rows']),'Cambios administrativos':len(changes)}
    else:
        result,removed,counts=_modificar_word(raw,changes)
    # Un borrador sigue pendiente de revisión académica; los originales no se alteran.
    remaining=[i['campo'] for i in items if i['diferente'] and i['campo'] not in seleccion]
    if 'Duración' in seleccion:remaining.append('Revisión pedagógica de actividades y evaluaciones')
    if abs(float(d['duracion'])-float(grupo['duracion']))>.001 and 'Duración' not in seleccion and 'Duración' not in remaining:
        remaining.append('Duración')
    ident=str(uuid.uuid4());folder=BASE/ident;folder.mkdir(parents=True,exist_ok=False)
    target=folder/'BORRADOR_ACTUALIZADO.docx'
    try:
        with target.open('xb') as f:f.write(result)
        with _db() as db:
            db.execute('''INSERT INTO biblioteca_pea
                (id,origen,parent_id,group_id,curso,docente,tipo,duracion,nombre_original,ruta,sha256,creado,estado,nota)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (ident,'Copia actualizada',original_id,grupo['id'],grupo['nombre'],grupo['hoja'],grupo['tipo'],float(grupo['duracion']) if 'Duración' in seleccion else d['duracion'],
                 Path(nombre).name,str(target.relative_to(C.ROOT)),hashlib.sha256(result).hexdigest(),C.now(),
                 'Borrador · requiere revisión','Cambios: '+', '.join(c[0] for c in changes)+(' y adaptación numérica 20/80' if 'Duración' in seleccion else '')+'. Pendientes: '+(', '.join(remaining) or 'validación académica')+'.'))
        C.event(grupo['id'],'PEA actualizado parcialmente',{'id':ident,'base':original_id,'cambios':[c[0] for c in changes],
            'pendientes':remaining,'firmas_retiradas':removed,'ubicaciones':counts})
    except Exception:
        target.unlink(missing_ok=True)
        try:folder.rmdir()
        except OSError:pass
        raise
    return ident,result,remaining


def _dl(r,label='Descargar Word'):
    try:
        path=_ruta(r)
        st.download_button(label,path.read_bytes(),file_name='PEA_'+('ORIGINAL_' if r['origen']=='Subido' else 'ACTUALIZADO_')+
            r['id'][:8]+'.docx',key='pea109_dl_'+r['id'])
    except Exception as exc:st.error(str(exc))


def _label(r):
    label=f"{r['curso']} · {r['docente']} · {r['duracion'] or '?'} h · {r['creado'][:10]}"
    if r.get('es_version_anterior'):
        label+=" · Versión anterior de programación"
    else:
        state=str(r.get('estado_programacion') or '').strip()
        if state and state!='Vigente':
            label+=f" · {state}"
    return label


def panel_contenido(grupo):
    st.caption('Elige un Word y decide qué diferencias modificar. No se cambia el original ni se reutilizan firmas anteriores.')
    source=st.radio('Seleccionar PEA',('Elegir de Mis PEA','Subir Word del docente'),horizontal=True,key='pea109_source')
    originals=candidatos();row=None;raw=None;nombre=''
    if source=='Elegir de Mis PEA':
        if not originals:st.info('Aún no hay Word en Mis PEA. Usa «Subir Word del docente».');return
        row=st.selectbox('PEA disponible · Generados y Subidos',originals,format_func=lambda r:r['origen']+' · '+_label(r),key='pea109_original')
        try:raw=_documento(row)
        except ValueError as exc:st.error(str(exc));return
        nombre=row['nombre_original']
    else:
        file=st.file_uploader('PEA original (.docx)',type=['docx'],key='pea109_upload')
        if file is None:return
        raw=file.getvalue();nombre=file.name
        try:_root(raw)
        except ValueError as exc:st.error(str(exc));return
        if st.button('Guardar original en Mis PEA → Subidos',key='pea109_save_original'):
            try:
                rid,created=guardar_original(raw,nombre,grupo)
                st.success('Original guardado intacto.' if created else 'Este Word ya estaba guardado. No se duplicó.')
            except Exception as exc:st.error(str(exc))
    try:d,items=campos(raw,grupo)
    except Exception as exc:st.error('No se pudo analizar el Word: '+str(exc));return
    st.markdown('**Comparación con Programación**')
    if d['firmas_graficas']:st.info('El original contiene una firma gráfica. Solo se conservará en el original; una copia nueva quedará sin esa firma.')
    if d['curso'] and _norm(d['curso'])!=_norm(grupo['nombre']):
        st.warning('El nombre leído del Word no coincide con el curso elegido. Verifica el documento antes de reutilizarlo.')
    checks=[]
    for idx,item in enumerate(items):
        name=item['campo'];before=item['anterior'] or 'No legible';after=item['nuevo'] or 'No indicado'
        c1,c2,c3=st.columns([2.1,2.1,1.3])
        with c1:st.caption(name+' · Word');st.write(before)
        with c2:st.caption('Programación');st.write(after)
        with c3:
            if item['diferente']:
                checked=st.checkbox('Modificar',key=f'pea109_change_{idx}_'+hashlib.sha256(raw).hexdigest()[:10])
                if checked:checks.append(name)
            else:st.caption('✓ Coincide')
        st.divider()
    mismatch=d['duracion'] is None or abs(float(d['duracion'])-float(grupo['duracion']))>.001
    if mismatch:
        st.warning('El PEA declara una duración distinta de Programación. El estudio independiente es adicional y NUNCA se suma a la duración oficial.')
    plan=None
    if 'Duración' in checks:
        st.markdown('**Propuesta automática de distribución de horas**')
        try:
            plan=AUTO.proponer(raw,float(grupo['duracion']))
            st.info(f"Duración de Programación: {plan['objetivo']:g} h · Mediación/teoría: {plan['teoria']:g} h (20%) · Prácticas: {plan['practicas']:g} h (80%).")
            st.caption(f"Estudio independiente: {plan['estudio_independiente']:g} h ADICIONALES, fuera del total y del 20/80.")
            st.dataframe(plan['rows'],hide_index=True,use_container_width=True)
            st.warning('ATRIO propone y aplica automáticamente las horas en las mismas celdas del Word. No reescribe ni valida por sí mismo las actividades o evaluaciones: debes revisar que sean viables con esta distribución antes de autorizar el documento.')
        except ValueError as exc:
            st.error('No se pudo preparar una propuesta segura: '+str(exc))
    elif mismatch:
        st.caption('Si omites modificar Duración, la copia administrativa conservará las horas anteriores y quedará pendiente de adaptación académica.')
    if not checks:st.caption('Selecciona los campos que quieres modificar para habilitar la copia.')
    st.markdown('**Vista previa de la selección**')
    chosen=[i for i in items if i['campo'] in checks]
    if chosen:
        for i in chosen:st.write(f"• {i['campo']}: {i['anterior'] or 'Sin lectura'} → {i['nuevo'] or 'Sin dato'}")
    else:st.caption('Ninguna modificación seleccionada.')
    if mismatch and 'Duración' not in checks:
        st.caption('Si solo actualizas fechas u horario, el Word seguirá con su duración original. El resultado será un borrador con diferencias académicas pendientes, NO un PEA validado.')
    validated=st.checkbox('Revisé las diferencias. Entiendo que el documento resultante será un borrador sin validación ni firmas nuevas.',key='pea109_confirm')
    academic_ok = st.checkbox('Revisé la propuesta automática de horas y comprobaré actividades y evaluaciones antes de cualquier validación académica.',key='pea110_revisar_horas') if 'Duración' in checks and plan else True
    can_create=bool(checks) and validated and (plan is not None if 'Duración' in checks else True) and academic_ok
    if st.button('Crear copia Word con los cambios seleccionados',type='primary',disabled=not can_create,key='pea109_create'):
        try:
            if not row:
                id_orig,_=guardar_original(raw,nombre,grupo)
            else:id_orig=row['id']
            ident,out,remaining=generar_copia(raw,nombre,grupo,checks,id_orig)
            st.session_state['pea109_ultimo_borrador']={'grupo':grupo['id'],'sha':hashlib.sha256(raw).hexdigest(),'id':ident,'word':out,'pendientes':remaining}
            st.success('Copia guardada en Mis PEA → Generados. Original intacto. Borrador pendiente de revisión.')
        except Exception as exc:st.error('No se generó la copia: '+str(exc))
    latest=st.session_state.get('pea109_ultimo_borrador')
    if latest and latest['grupo']==grupo['id'] and latest['sha']==hashlib.sha256(raw).hexdigest():
        st.success('Último borrador actualizado disponible en Mis PEA → Generados.')
        if latest['pendientes']:st.warning('Diferencias que todavía requieren revisión: '+', '.join(latest['pendientes']))
        st.download_button('Descargar última copia actualizada',latest['word'],
            file_name='PEA_ACTUALIZADO_'+latest['id'][:8]+'.docx',key='pea109_download_latest')


def panel_mis_pea(trabajos,grupos):
    tab_generated,tab_uploaded,tab_historicos=st.tabs(('Generados','Subidos','Históricos'))
    with tab_generated:
        # Repositorio del ciclo vigente: archivos independientes de Históricos.
        import pea_repositorio_actual_101213 as R213
        R213.panel_mis_actuales()
        trabajos.panel()
        derived=[r for r in listar() if r['origen']!='Subido']
        if derived:
            st.markdown('**Versiones actualizadas de Word subidos**')
            for r in derived:
                with st.expander(_label(r)):
                    st.caption('Versión actualizada · '+r['estado'])
                    st.write(r['nota']);_dl(r)
    with tab_uploaded:
        st.caption('Originales que entregaron los docentes. Ninguno se sobrescribe.')
        if grupos:
            g=st.selectbox('Grupo al que corresponde el original',grupos,format_func=lambda x:x['hoja']+' · '+x['nombre'],key='pea109_mis_grupo')
            file=st.file_uploader('Subir Word original',type=['docx'],key='pea109_mis_file')
            if file is not None and st.button('Guardar Word original',key='pea109_mis_guardar'):
                try:
                    _,created=guardar_original(file.getvalue(),file.name,g)
                    st.success('Original guardado.' if created else 'Ya existe este documento; no se duplicó.')
                except Exception as exc:st.error(str(exc))
        originals=listar(origen='Subido')
        if not originals:st.info('Aún no hay Word originales subidos.')
        for r in originals:
            with st.expander(_label(r)):
                st.caption(r['estado']+' · archivo '+r['nombre_original'])
                _dl(r)
                if r['id']:
                    children=[v for v in listar() if v.get('parent_id')==r['id']]
                    if children:st.caption(f'{len(children)} versiones actualizadas relacionadas con este original; disponibles en Generados.')

    with tab_historicos:
        from pea_historicos_101212 import panel_mis_historicos
        panel_mis_historicos()
