"""Datos persistentes, recursos versionados y generación aislada de ATRIO."""
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
import contextlib, hashlib, io, json, os, re, shutil, sqlite3, struct, sys, uuid, zipfile, threading, time, tempfile
from openpyxl import load_workbook, Workbook
from docx import Document
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'datos'; RES=DATA/'recursos'; OUT=DATA/'salidas'; ARCH=DATA/'versiones'
for p in (RES,OUT,ARCH):p.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'motor'))
import generador_pea_extension_v6_4 as motor
from identidad_programacion import planificar_conciliacion, grupos_operativos as filtrar_grupos_operativos, grupo_incluido_en_actualizacion

def ruta_dias_sin_clase():
    """Primera ruta existente de DIAS_SIN_CLASE.json (datos/recursos y luego raíz). None si no existe."""
    for candidata in (RES/'DIAS_SIN_CLASE.json', ROOT/'DIAS_SIN_CLASE.json'):
        if candidata.exists():return candidata
    return None
def now():return datetime.now(ZoneInfo('America/Mexico_City')).isoformat(timespec='seconds')
def connect():
 c=sqlite3.connect(DATA/'atrio.sqlite3');c.row_factory=sqlite3.Row
 c.executescript('''CREATE TABLE IF NOT EXISTS groups(id TEXT PRIMARY KEY, rowkey TEXT, fingerprint TEXT, payload TEXT, active INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at TEXT, group_id TEXT, action TEXT, payload TEXT);
 CREATE TABLE IF NOT EXISTS status(group_id TEXT PRIMARY KEY, doc TEXT DEFAULT 'Sin verificar', mce TEXT DEFAULT 'Sin verificar', note TEXT DEFAULT '');
 CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, group_id TEXT, created TEXT, path TEXT, content_path TEXT, fingerprint TEXT, reviewed INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);''');return c

_PROGRAM_LOCK_LOCAL=threading.local()

@contextlib.contextmanager
def programacion_lock(timeout=60):
    """Bloqueo interproceso de la programación; flock se libera si el proceso termina."""
    ARCH.mkdir(parents=True,exist_ok=True)
    depth=getattr(_PROGRAM_LOCK_LOCAL,'depth',0)
    if depth:
        _PROGRAM_LOCK_LOCAL.depth=depth+1
        try: yield
        finally: _PROGRAM_LOCK_LOCAL.depth-=1
        return
    lock_key=hashlib.sha256(str(DATA.resolve()).encode('utf-8')).hexdigest()[:20]
    lock_path=Path(tempfile.gettempdir())/f'atrio_programacion_{lock_key}.lock'
    handle=open(lock_path,'a+b')
    try:
        try:
            import fcntl
        except ImportError as exc:
            raise RuntimeError('El bloqueo seguro de programación requiere soporte fcntl en este entorno.') from exc
        deadline=time.monotonic()+timeout
        while True:
            try:
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic()>=deadline:
                    raise TimeoutError('La programación está siendo utilizada por otro proceso. Intenta nuevamente.')
                time.sleep(.1)
        _PROGRAM_LOCK_LOCAL.depth=1
        try: yield
        finally:
            _PROGRAM_LOCK_LOCAL.depth=0
            fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
    finally:
        handle.close()

def _ruta_journal_programacion():
    return ARCH/'PROGRAMACION_PENDING.json'

def _es_ruta_segura_programacion(path):
    candidate=Path(path).resolve()
    allowed=(RES.resolve(),ARCH.resolve())
    return any(candidate==base or base in candidate.parents for base in allowed)

def _escribir_journal_programacion(data):
    journal=_ruta_journal_programacion()
    tmp=journal.with_suffix('.json.tmp')
    raw=json.dumps(data,ensure_ascii=False).encode('utf-8')
    with open(tmp,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(tmp,journal)

def recuperar_programacion():
    """Resuelve una operación interrumpida según el evento de confirmación en SQLite."""
    with programacion_lock():
        journal=_ruta_journal_programacion()
        if not journal.exists(): return False
        try:
            data=json.loads(journal.read_text(encoding='utf-8'))
            operation_id=str(data['operation_id'])
            commit_action=str(data.get('commit_action','Reprogramación aplicada'))
            excel=Path(data['excel']).resolve()
            backup=Path(data['backup']).resolve()
            if not _es_ruta_segura_programacion(excel) or not _es_ruta_segura_programacion(backup):
                raise ValueError('El journal contiene rutas fuera de los directorios permitidos.')
            if not backup.is_file():
                raise FileNotFoundError('No se encuentra el respaldo necesario para recuperar la programación.')
            with connect() as conn:
                row=conn.execute("SELECT 1 FROM events WHERE action=? AND payload LIKE ?",(commit_action,'%'+operation_id+'%')).fetchone()
            if row:
                # SQLite confirmó: conservar el Excel nuevo y retirar solo el journal.
                journal.unlink()
                return True
            # SQLite no confirmó: restaurar el Excel anterior antes de permitir otra operación.
            fd,name=tempfile.mkstemp(prefix='RECUPERACION_',suffix='.xlsx',dir=str(excel.parent))
            os.close(fd)
            temp=Path(name)
            try:
                shutil.copy2(backup,temp)
                os.replace(temp,excel)
            finally:
                temp.unlink(missing_ok=True)
            journal.unlink()
            return True
        except Exception as exc:
            raise RuntimeError(f'ATRIO detectó una reprogramación interrumpida y no pudo completar su recuperación: {exc}') from exc


def setting(k,default=None):
 with connect() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone()
 return json.loads(r[0]) if r else default

def set_setting(k,v):
 with connect() as c:c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(k,json.dumps(v,ensure_ascii=False)))

def event(g,action,payload):
 with connect() as c:c.execute('INSERT INTO events(at,group_id,action,payload) VALUES (?,?,?,?)',(now(),g,action,json.dumps(payload,ensure_ascii=False,default=str)))

def sha(b):return hashlib.sha256(b).hexdigest()
def iso(v):
 d=motor.fecha(v)
 return d.isoformat() if d else None

def parse_program(path):
 w=load_workbook(path,read_only=True,data_only=True);out=[]
 for sheet in w:
  esp=''
  for n,row in enumerate(sheet.iter_rows(values_only=True),1):
   if row and motor._nombre_hoja_especialidad(row[0]) and len(row)>1 and row[1]:esp=str(row[1]).strip()
   if n<15 or len(row)<9:continue
   t=motor.normal(row[0]); typ={'extension':'Extensión','regular':'Regular','repositorio':'Repositorio'}.get(t)
   if not typ:continue
   if not row[1]:raise ValueError(f'{sheet.title}, fila {n}: curso sin nombre')
   try:hours=float(row[6])
   except (ValueError,TypeError):raise ValueError(f'{sheet.title}, fila {n}: duración inválida')
   start,end=iso(row[4]),iso(row[5])
   if not start or not end or end<start or hours<=0:raise ValueError(f'{sheet.title}, fila {n}: revisar fechas/duración')
   out.append(dict(hoja=sheet.title,fila=n,tipo=typ,nombre=str(row[1]).strip(),poblacion=row[3],inicio=start,fin=end,duracion=hours,horario=str(row[8] or '').strip(),aula=str(row[9] or '').strip() if len(row)>9 else '',especialidad_programada=esp,observaciones=str(row[11] or '') if len(row)>11 else ''))
 w.close()
 if not out:raise ValueError('No se identificaron grupos; se espera programación por docente desde fila 15.')
 return out

def fingerprint(g):return sha(json.dumps({k:g.get(k) for k in ['hoja','nombre','tipo','inicio','fin','duracion','horario','poblacion','aula','especialidad_programada']},sort_keys=True,default=str).encode())
def _import_program_impl(path, operation_id=None):
 rows=parse_program(path)
 previous=[]
 with connect() as c:
  previous=[dict(x) for x in c.execute('SELECT * FROM groups WHERE active=1')]
 prepared=[]
 for g in rows:
  item=dict(g);item['fingerprint']=fingerprint(g);prepared.append(item)
 plan=planificar_conciliacion(previous,prepared)
 warnings=list(plan['avisos'])
 possible_replacements={}
 for item in plan['nuevos']:
  old_id=item.get('posible_grupo_anterior')
  if old_id:
   possible_replacements[old_id]=item
 new_ids={}
 with connect() as c:
  c.execute('BEGIN IMMEDIATE')
  for match in plan['vinculados']:
   g=dict(match['actual']);g.pop('fingerprint',None)
   meta={
    'estado_programacion':'Vigente',
    'incluido_en_ultima_actualizacion':True,
    'ultima_conciliacion':now(),
    'motivo_conciliacion':match['motivo_vinculo'],
    'accion_pea_sugerida':match['accion_pea'],
    'requiere_revision_horas':bool(match['horas_cambiaron']),
    'requiere_revision_docente':bool(match['docente_cambio']),
    'requiere_pea_nuevo':False,
   }
   g['_atrio']=meta
   key=f"{g['hoja']}|{g['fila']}"
   c.execute('INSERT OR REPLACE INTO groups VALUES(?,?,?,?,1)',(
    match['id'],key,fingerprint(g),json.dumps(g,ensure_ascii=False,default=str)))
   if match['cambios']:
    c.execute('INSERT INTO events(at,group_id,action,payload) VALUES(?,?,?,?)',(
     now(),match['id'],'Programación actualizada',
     json.dumps({'antes':match['anterior'],'despues':g,
                 'campos_modificados':match['cambios'],
                 'accion_pea_sugerida':match['accion_pea']},
                ensure_ascii=False,default=str)))
  for item in plan['nuevos']:
   g=dict(item['actual']);g.pop('fingerprint',None)
   uid=str(uuid.uuid4());new_ids[uid]=item
   pea_required=bool(item['requiere_pea_nuevo'] and g.get('tipo')=='Extensión')
   g['_atrio']={
    'estado_programacion':'Revisar identidad' if item['requiere_revision_manual'] else 'Vigente',
    'incluido_en_ultima_actualizacion':True,
    'ultima_conciliacion':now(),
    'motivo_conciliacion':item['motivo'],
    'accion_pea_sugerida':item['accion_pea'],
    'requiere_pea_nuevo':pea_required,
    'posible_grupo_anterior':item.get('posible_grupo_anterior'),
   }
   key=f"{g['hoja']}|{g['fila']}"
   c.execute('INSERT INTO groups(id,rowkey,fingerprint,payload,active) VALUES(?,?,?,?,1)',(
    uid,key,fingerprint(g),json.dumps(g,ensure_ascii=False,default=str)))
   if pea_required:
    c.execute('INSERT OR IGNORE INTO status(group_id,doc,mce,note) VALUES(?,?,?,?)',(
     uid,'Sin PEA','Sin verificar',
     'Curso nuevo o nombre cambiado. Se requiere un PEA nuevo; no reutilizar el PEA del nombre anterior.'))
   action=('Identidad pendiente de revisión' if item['requiere_revision_manual']
           else 'PEA nuevo requerido por cambio de nombre' if item['motivo']=='nombre_cambiado'
           else 'Curso nuevo incorporado')
   c.execute('INSERT INTO events(at,group_id,action,payload) VALUES(?,?,?,?)',(
    now(),uid,action,json.dumps({
     'grupo':g,'posible_grupo_anterior':item.get('posible_grupo_anterior'),
     'requiere_pea_nuevo':pea_required,
     'requiere_revision_manual':item['requiere_revision_manual']},
     ensure_ascii=False,default=str)))
  no_included=0
  for item in plan['no_incluidos']:
   uid=item['id'];g=dict(item['grupo']);old_meta=dict(g.get('_atrio') or {})
   prior_replacement=possible_replacements.get(uid)
   if prior_replacement:
    new_uid=next((new_id for new_id,new_item in new_ids.items()
                  if new_item is prior_replacement),None)
    state='Sustituido por cambio de nombre · antecedente conservado'
    meta=dict(old_meta,estado_programacion=state,
              incluido_en_ultima_actualizacion=False,
              sustituido_por_grupo=new_uid,ultima_conciliacion=now())
    active=0
   else:
    state='Pendiente de reprogramación · no incluido en esta actualización'
    meta=dict(old_meta,estado_programacion=state,
              incluido_en_ultima_actualizacion=False,
              ultima_conciliacion=now())
    active=1
    no_included+=1
   g['_atrio']=meta
   c.execute('UPDATE groups SET payload=?,active=? WHERE id=?',(
    json.dumps(g,ensure_ascii=False,default=str),active,uid))
   if old_meta.get('estado_programacion')!=state:
    c.execute('INSERT INTO events(at,group_id,action,payload) VALUES(?,?,?,?)',(
     now(),uid,'Grupo conservado fuera de la actualización',
     json.dumps({'estado':state,'sustituido_por_grupo':meta.get('sustituido_por_grupo'),
                 'datos_anteriores_conservados':True},
                ensure_ascii=False,default=str)))
  summary=dict(plan['resumen'])
  summary['pendientes_conservados']=no_included
  summary['nombres_cambiados']=sum(1 for x in plan['nuevos'] if x['motivo']=='nombre_cambiado')
  c.execute('INSERT INTO events(at,action,payload) VALUES(?,?,?)',(
   now(),'Importación programación',json.dumps({'grupos_recibidos':len(rows),
    'resumen':summary,'avisos':warnings,
    'operation_id':operation_id,
    'regla':'Los grupos no incluidos se conservan; no se interpretan como cancelados.'},
    ensure_ascii=False,default=str)))
 if no_included:
  warnings.append(f"{no_included} grupo(s) no incluidos en esta actualización quedaron conservados como pendientes de reprogramación; no se eliminaron.")
 return len(rows),warnings

def import_program(path, operation_id=None):
 with programacion_lock():
  recuperar_programacion()
  return _import_program_impl(path, operation_id=operation_id)

def groups():
 """Devuelve todos los grupos activos, incluidos los pendientes para consulta y reprogramación."""
 with programacion_lock():
  recuperar_programacion()
  with connect() as c:rows=c.execute('SELECT * FROM groups WHERE active=1').fetchall()
 return [dict(json.loads(x['payload']),id=x['id'],fingerprint=x['fingerprint']) for x in rows]

def operational_groups(groups=None):
 """Grupos incluidos en la actualización actual; excluye pendientes conservados."""
 return filtrar_grupos_operativos(groups if groups is not None else globals()['groups']())

def validate_group_current(group, conn=None):
 """Rechaza generación basada en un grupo que cambió o dejó de estar incluido."""
 def check(db):
  row=db.execute('SELECT fingerprint,payload,active FROM groups WHERE id=?',
                 (group.get('id'),)).fetchone()
  if not row or not row['active']:
   raise ValueError('El curso ya no está vigente en la programación. Actualiza la selección antes de generar el PEA.')
  if not group.get('fingerprint') or row['fingerprint'] != group.get('fingerprint'):
   raise ValueError('La programación de este curso cambió mientras el PEA estaba seleccionado. Vuelve a abrir el curso y revisa sus datos antes de generar.')
  current=json.loads(row['payload'])
  if not grupo_incluido_en_actualizacion(current):
   raise ValueError('Este curso quedó pendiente de reprogramación y no participa en la jornada actual. Consérvalo y selecciónalo cuando se incluya en una nueva actualización.')
  return True
 if conn is not None:return check(conn)
 with connect() as db:return check(db)


def profiles():
 w=load_workbook(RES/'Plantilla_Datos_Docentes_PEA_CECATI31.xlsx',read_only=True,data_only=True)
 if 'DOCENTES' not in w:raise ValueError('El padrón requiere hoja DOCENTES')
 sheet=w['DOCENTES'];headers=[str(c.value or '').strip() for c in sheet[1]]
 expected=('ID DOCENTE','NOMBRE COMPLETO','CURP','CORREO INSTITUCIONAL','TELÉFONO','TIPO DOCENTE','RUTA FIRMA (PNG/JPG)','USO DE FIRMA AUTORIZADO','OBSERVACIONES')
 if tuple(motor.normal(h) for h in headers[:9])!=tuple(motor.normal(h) for h in expected):
  w.close();raise ValueError('Estructura del Padrón no reconocida: se esperan las columnas A-I originales. No se mezclan firma y especialidad.')
 if len(headers)>9 and headers[9] and motor.normal(headers[9])!=motor.normal('ESPECIALIDAD DOCENTE'):
  w.close();raise ValueError('La columna J ya contiene otro dato. No se sobrescribirá.')
 out={}
 for row in sheet.iter_rows(min_row=2,values_only=True):
  if len(row)>=9 and row[1]:
   vals=list(row)+[None]*max(0,10-len(row))
   out[motor.normal(row[1])]=dict(id=vals[0],nombre=vals[1],curp=vals[2],correo=vals[3],telefono=vals[4],tipo=vals[5],firma=vals[6],autorizada=vals[7],observaciones=vals[8],especialidad=vals[9])
 w.close();return out
def status(uid):
 with connect() as c:r=c.execute('SELECT * FROM status WHERE group_id=?',(uid,)).fetchone()
 return dict(r) if r else dict(doc='Sin verificar',mce='Sin verificar',note='')

def update_status(uid,doc,mce,note):
 before=status(uid)
 with connect() as c:c.execute('INSERT OR REPLACE INTO status VALUES(?,?,?,?)',(uid,doc,mce,note))
 event(uid,'Estado actualizado',{'antes':before,'doc':doc,'mce':mce,'nota':note})

def artifacts(uid):
 with connect() as c:return [dict(x) for x in c.execute('SELECT * FROM artifacts WHERE group_id=? ORDER BY created DESC',(uid,))]

def _save_resource_impl(name,raw):
 allowed={'PROGRAMACION DE CURSOS.xlsx','Plantilla_Datos_Docentes_PEA_CECATI31.xlsx','PEA_final en blanco.docx','DIAS_SIN_CLASE.json','SISAE.zip','MEMBRETE.docx','REPOSITORIO.pdf','CALENDARIO.pdf'}
 if name not in allowed:raise ValueError('Recurso no permitido')
 if len(raw)>100*1024*1024:raise ValueError('Máximo 100 MB')
 if name.endswith('.xlsx'):
  w=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
  if name.startswith('Plantilla') and 'DOCENTES' not in w:raise ValueError('Falta hoja DOCENTES')
  w.close()
 if name=='PROGRAMACION DE CURSOS.xlsx':
  tmp=RES/'programacion.validando.xlsx';tmp.write_bytes(raw)
  try:parse_program(tmp)
  finally:tmp.unlink(missing_ok=True)
 if name.endswith('.docx'):
  doc=Document(io.BytesIO(raw))
  if name.startswith('PEA'):motor.assert_plantilla(doc)
 if name=='DIAS_SIN_CLASE.json':
  dates=json.loads(raw.decode('utf-8-sig'))
  if not isinstance(dates,list):raise ValueError('Usa una lista JSON de fechas AAAA-MM-DD')
  for x in dates:date.fromisoformat(x)
 if name=='SISAE.zip':sisae_bytes(raw)
 if name.endswith('.pdf') and not raw.startswith(b'%PDF'):raise ValueError('PDF inválido')
 path=RES/name
 backup=None
 if path.exists():
  backup=ARCH/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+name)
  shutil.copy2(path,backup)
 operation_id=None
 if name=='PROGRAMACION DE CURSOS.xlsx':
  if backup is None:
   raise FileNotFoundError('No existe una programación anterior para respaldar; no se sustituirá el archivo.')
  operation_id=str(uuid.uuid4())
  _escribir_journal_programacion({
   'operation_id':operation_id,'commit_action':'Importación programación',
   'excel':str(path.resolve()),'backup':str(backup.resolve()),'created':now(),
  })
 tmp=path.with_suffix(path.suffix+'.tmp')
 try:
  tmp.write_bytes(raw);os.replace(tmp,path)
  if name=='PROGRAMACION DE CURSOS.xlsx':
   # La importación y su evento de confirmación comparten la transacción SQLite.
   result=_import_program_impl(path,operation_id=operation_id)
   _ruta_journal_programacion().unlink(missing_ok=True)
  else:
   result=None
  event(None,'Recurso actualizado',{'nombre':name,'sha256':sha(raw)})
  if name=='DIAS_SIN_CLASE.json':set_setting('calendario_confirmado',False)
  return result
 finally:
  tmp.unlink(missing_ok=True)

def save_resource(name,raw):
 if name=='PROGRAMACION DE CURSOS.xlsx':
  with programacion_lock():
   recuperar_programacion()
   try:
    return _save_resource_impl(name,raw)
   except Exception:
    # Si el proceso sigue vivo, intenta revertir ahora; ante cierre abrupto
    # el journal se resolverá en la siguiente operación de programación.
    recuperar_programacion()
    raise
 return _save_resource_impl(name,raw)

def dbf(raw):
 count=struct.unpack_from('<I',raw,4)[0];head,length=struct.unpack_from('<HH',raw,8);fields=[];p=32
 while p<head and raw[p]!=13:
  d=raw[p:p+32];fields.append((d[:11].split(b'\0')[0].decode(),chr(d[11]),d[16]));p+=32
 rows=[]
 for i in range(count):
  line=raw[head+i*length:head+(i+1)*length]
  if not line or line[0]==42:continue
  row={};off=1
  for name,typ,n in fields:
   value=line[off:off+n];off+=n;row[name]=value.decode('cp1252',errors='replace').strip() if typ in 'CNDLFM' else ''
  rows.append(row)
 return rows

def sisae_bytes(raw):
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if sum(i.file_size for i in z.infolist())>300*1024*1024:raise ValueError('ZIP demasiado grande al descomprimir')
  names={Path(n.strip()).name.upper():n for n in z.namelist()}
  for n in ['PROG_CURSOS1.DBF','INSCRIPCION.DBF']:
   if n not in names:raise ValueError(f'Falta {n}')
  return {n:dbf(z.read(names[n])) for n in ['PROG_CURSOS1.DBF','INSCRIPCION.DBF']}

def generate(g,participants,mode='cache',academic=None,progress=None,job_id=None):
 validate_group_current(g)
 if g['tipo']!='Extensión':raise ValueError('Generación Word disponible solo para extensión. Regular no requiere PEA; repositorio necesita su original y adaptación.')
 if participants<1:raise ValueError('Confirma participantes previstos')
 if not setting('calendario_confirmado',False):raise ValueError('Revisa y confirma el calendario en Ajustes')
 prof=profiles().get(motor.normal(g['hoja']))
 if not prof:raise ValueError('No hay perfil docente coincidente en el padrón')
 missing=[k for k in ['curp','correo','telefono','tipo','especialidad'] if not str(prof.get(k) or '').strip()]
 if missing:raise ValueError('Completa el perfil docente en Ajustes: '+', '.join(missing))
 if not g['especialidad_programada']:raise ValueError('Revisa la especialidad en la programación')
 course=dict(g,docente=prof,poblacion=participants)
 motor.comprobar_plantilla(RES)
 motor.AUTORIDAD_VALIDA=setting('valida','Lila Inurreta Fernández');motor.AUTORIDAD_VISTO=setting('visto','Lila Inurreta Fernández');motor.AUTORIDAD_AUTORIZA=setting('autoriza','Sergio López Hernández')
 report=motor.revisar_calendario(course,RES)
 if report.startswith('ERROR:'):raise ValueError(report)
 with contextlib.redirect_stdout(progress or io.StringIO()):
  content=academic if academic is not None else motor.contenido_ia(course,RES,mode)
  if progress:progress.stage('Validando el contenido académico')
  opening=2 if course['duracion']>=40 else 1
  motor.validator(content,{'apertura':opening,'cierre':opening},course['duracion'])
  motor.qa_v7.validar_o_rechazar(content,course,{'apertura':opening,'cierre':opening})
  if progress:progress.stage('Preparando y verificando el Word')
  aid=job_id or str(uuid.uuid4());folder=OUT/g['id']/aid;folder.mkdir(parents=True)
  # Record exact input resources for reproducibility, without credentials.
  metadata=dict(curso={k:v for k,v in course.items() if k!='docente'},autoridades={k:setting(k,d) for k,d in [('valida','Lila Inurreta Fernández'),('visto','Lila Inurreta Fernández'),('autoriza','Sergio López Hernández')]},calendario=report,recursos={p.name:sha(p.read_bytes()) for p in RES.iterdir() if p.is_file() and p.suffix in ['.json','.docx','.xlsx']})
  content_path=folder/'contenido.json';content_path.write_text(json.dumps(content,ensure_ascii=False,indent=2))
  out=folder/'PEA_PARA_REVISION.docx';motor.crear_docx(course,content,RES,out,False)
  result=Document(out)
  if len(result.tables)!=28:raise ValueError('El documento generado no conserva las 28 tablas institucionales')
  (folder/'datos_generacion.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,default=str))
 try:
  with connect() as c:
   c.execute('BEGIN IMMEDIATE')
   validate_group_current(g,c)
   c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,0)',(aid,g['id'],now(),str(out.relative_to(ROOT)),str(content_path.relative_to(ROOT)),g['fingerprint']))
   st=c.execute('SELECT mce FROM status WHERE group_id=?',(g['id'],)).fetchone()
   mce=st['mce'] if st else 'Sin verificar'
   c.execute('INSERT OR REPLACE INTO status VALUES(?,?,?,?)',(g['id'],'Generado',mce,'Archivo generado; pendiente de revisión'))
   c.execute('INSERT INTO events(at,group_id,action,payload) VALUES(?,?,?,?)',
             (now(),g['id'],'PEA generado',json.dumps({'archivo':str(out.relative_to(ROOT)),'id':aid,'calendario':report},ensure_ascii=False,default=str)))
 except Exception:
  shutil.rmtree(folder,ignore_errors=True)
  raise
 return out

def mark_reviewed(aid):
 with connect() as c:
  a=c.execute('SELECT * FROM artifacts WHERE id=?',(aid,)).fetchone()
  if not a or not (ROOT/a['path']).is_file():raise ValueError('No se encuentra el archivo')
  c.execute('UPDATE artifacts SET reviewed=1 WHERE id=?',(aid,))
 st=status(a['group_id']);update_status(a['group_id'],'Revisado',st['mce'],'Revisión confirmada por usuaria')
 event(a['group_id'],'Versión revisada',{'id':aid})

HEADERS=['Nombre del curso','Especialidad','Asociado a normativa','Código','Norma','Duración','Número de participantes','Horario','Días de impartición','Lugar de impartición','Fecha de inicio','Fecha de término','Tipo de docente','CURP','Teléfono','Correo','Objetivo general','Justificación','Temática','Menciona CERESO']
def mce_excel(g,values):
 # User-reviewed values only; no defaults silently assert facts.
 w=Workbook();s=w.active;s.title='DATOS_MCE';s.append(HEADERS)
 s.append([str(values.get(k,'') or '') for k in HEADERS]);s.freeze_panes='A2';s.auto_filter.ref=s.dimensions
 for col in s.columns:s.column_dimensions[col[0].column_letter].width=min(55,max(22,len(str(col[0].value))+2))
 for cell in s[2]:
  if isinstance(cell.value,str) and cell.value.startswith(('=','+','-','@')):cell.value="'"+cell.value
 out=io.BytesIO();w.save(out);event(g['id'],'Excel MCE preparado',{'curso':g['nombre']});return out.getvalue()

def backup():
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  con=connect();dest=sqlite3.connect(':memory:');con.backup(dest);con.close()
  # Copy consistent SQLite backup using a unique temporary name.
  tmp=DATA/(str(uuid.uuid4())+'.sqlite3');disk=sqlite3.connect(tmp);dest.backup(disk);disk.close();dest.close();z.write(tmp,'datos/atrio.sqlite3');tmp.unlink()
  for directory in [RES,OUT,ARCH]:
   for p in directory.rglob('*'):
    if p.is_file():z.write(p,str(p.relative_to(ROOT)))
 return out.getvalue()

def save_profile(name,values,signature_bytes=None,signature_ext=None):
 path=RES/'Plantilla_Datos_Docentes_PEA_CECATI31.xlsx'
 w=load_workbook(path);sheet=w['DOCENTES']
 expected=('ID DOCENTE','NOMBRE COMPLETO','CURP','CORREO INSTITUCIONAL','TELÉFONO','TIPO DOCENTE','RUTA FIRMA (PNG/JPG)','USO DE FIRMA AUTORIZADO','OBSERVACIONES')
 headers=[str(sheet.cell(1,c).value or '').strip() for c in range(1,11)]
 if tuple(motor.normal(h) for h in headers[:9])!=tuple(motor.normal(h) for h in expected):
  w.close();raise ValueError('El Padrón tiene encabezados distintos. No se modificó ningún dato.')
 if headers[9] and motor.normal(headers[9])!=motor.normal('ESPECIALIDAD DOCENTE'):
  w.close();raise ValueError('La columna J está ocupada; no se puede agregar Especialidad sin revisar.')
 rownum=None
 for n in range(2,sheet.max_row+1):
  if motor.normal(sheet.cell(n,2).value)==motor.normal(name):rownum=n;break
 rownum=rownum or sheet.max_row+1
 sheet.cell(rownum,1).value=sheet.cell(rownum,1).value or str(uuid.uuid4())[:8]
 for col,key in [(2,'nombre'),(3,'curp'),(4,'correo'),(5,'telefono'),(6,'tipo')]:
  sheet.cell(rownum,col).value=name if key=='nombre' else (values.get(key) or '')
 sheet.cell(1,10).value='ESPECIALIDAD DOCENTE'
 sheet.cell(rownum,10).value=(values.get('especialidad') or '').strip()
 # G es ruta de firma; H, autorización; I, observaciones. Nunca se sobrescriben inadvertidamente.
 signature_path=None
 if signature_bytes is not None:
  raw=bytes(signature_bytes)
  ext=str(signature_ext or '').lower().strip()
  if ext not in ('.png','.jpg','.jpeg') or len(raw)>3*1024*1024 or len(raw)<30:
   w.close();raise ValueError('La imagen de firma debe ser PNG/JPG y pesar menos de 3 MB.')
  valid=raw.startswith(b'\x89PNG\r\n\x1a\n') if ext=='.png' else raw.startswith(b'\xff\xd8\xff')
  if not valid:
   w.close();raise ValueError('El archivo no contiene una imagen PNG/JPG válida.')
  import hashlib
  folder=RES/'firmas_docentes';folder.mkdir(parents=True,exist_ok=True)
  file_name=hashlib.sha256(motor.normal(name).encode()).hexdigest()[:14]+'_'+hashlib.sha256(raw).hexdigest()[:14]+ext
  signature_path=folder/file_name
  if not signature_path.exists():signature_path.write_bytes(raw)
  sheet.cell(rownum,7).value='firmas_docentes/'+file_name
 out=io.BytesIO();w.save(out);w.close()
 try:save_resource(path.name,out.getvalue())
 except Exception:
  # Si falla el Excel, se conserva el archivo de firma en lugar de borrar potencialmente una imagen ya utilizada.
  raise
 event(None,'Perfil docente actualizado',{'docente':name,'firma_actualizada':signature_bytes is not None})