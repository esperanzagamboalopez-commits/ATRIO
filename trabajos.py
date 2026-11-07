"""Trabajos PEA en procesos independientes del navegador; un generador activo."""
import contextlib,fcntl,json,os,re,sqlite3,subprocess,sys,time,uuid
from pathlib import Path
import centro as C

LIMIT=600
ACTIVE=('En cola','En proceso')
def connection():
    c=C.connect()
    c.execute('CREATE TABLE IF NOT EXISTS pea_jobs(id TEXT PRIMARY KEY, group_id TEXT, title TEXT, created REAL, started REAL, finished REAL, status TEXT, detail TEXT, payload TEXT)')
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS pea_active ON pea_jobs(group_id) WHERE status IN ('En cola','En proceso')")
    return c

def lockpath(jid):
    return C.DATA/('job-'+jid+'.lock')

def change(jid,status,detail):
    with connection() as c:
        c.execute('UPDATE pea_jobs SET status=?,detail=?,finished=? WHERE id=?',(status,detail,time.time() if status not in ACTIVE else None,jid))

def recover():
    with connection() as c:
        rows=c.execute("SELECT id FROM pea_jobs WHERE status IN ('En cola','En proceso')").fetchall()
    for row in rows:
        jid=row['id']
        with lockpath(jid).open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:continue
            with connection() as c:
                ok=c.execute('SELECT path FROM artifacts WHERE id=?',(jid,)).fetchone()
                c.execute("UPDATE pea_jobs SET status=?,detail=?,finished=? WHERE id=? AND status IN ('En cola','En proceso')",('Listo' if ok else 'Interrumpido','Word guardado' if ok else 'El proceso se detuvo. Puedes volver a solicitar el borrador.',time.time(),jid))

def start(group,participants,academic):
    C.validate_group_current(group)
    recover()
    jid=str(uuid.uuid4())
    with lockpath(jid).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with connection() as c:
            existing=c.execute("SELECT id FROM pea_jobs WHERE group_id=? AND status IN ('En cola','En proceso')",(group['id'],)).fetchone()
            if existing:return existing['id']
            payload=json.dumps([group,participants,academic],ensure_ascii=False)
            try:c.execute('INSERT INTO pea_jobs VALUES(?,?,?,?,?,?,?,?,?)',(jid,group['id'],group['nombre'],time.time(),None,None,'En cola','Esperando turno',payload))
            except sqlite3.IntegrityError:return
        try:subprocess.Popen([sys.executable,__file__,'supervise',jid],cwd=C.ROOT,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,pass_fds=(lock.fileno(),))
        except OSError:
            change(jid,'Error','No pudo iniciarse el proceso. Reintenta desde Preparar documento.');raise
    return jid

class Progress:
    def __init__(self,jid):self.jid=jid
    def stage(self,text):change(self.jid,'En proceso',text)
    def flush(self):pass
    def write(self,line):
        attempt=re.search(r'Consultando Gemini \(intento (\d+/\d+)',line)
        wait=re.search(r'Esperaré (\d+) segundos',line)
        if attempt:self.stage('Consultando Gemini · intento '+attempt[1])
        elif wait:self.stage('Gemini ocupado · reintento en '+wait[1]+' segundos')
        elif 'válido encontrado en caché' in line:self.stage('Contenido recuperado')
        return len(line)

def work(jid):
    with connection() as c:
        payload=c.execute('SELECT payload FROM pea_jobs WHERE id=?',(jid,)).fetchone()[0]
    g,n,academic=json.loads(payload)
    C.generate(g,n,'gemini',academic,Progress(jid),jid)
    change(jid,'Listo','Word guardado · pendiente de revisión')

def supervise(jid):
    with (C.DATA/'generador.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with connection() as c:c.execute('UPDATE pea_jobs SET started=?,status=?,detail=? WHERE id=?',(time.time(),'En proceso','Comprobando perfil, calendario y plantilla',jid))
        try:
            result=subprocess.run([sys.executable,__file__,'work',jid],timeout=LIMIT)
            if result.returncode:raise RuntimeError('El proceso de generación se detuvo.')
        except subprocess.TimeoutExpired:
            with connection() as c:done=c.execute('SELECT path FROM artifacts WHERE id=?',(jid,)).fetchone()
            change(jid,'Listo' if done else 'Tiempo agotado','Word guardado' if done else 'Se alcanzaron 10 minutos de generación. Revisa el servicio de contenido y vuelve a intentar.')
        except Exception as exc:change(jid,'Error',str(exc))

def panel():
    import streamlit as st
    @st.fragment(run_every=5)
    def progress_panel():
        recover()
        with connection() as c:jobs=c.execute('SELECT * FROM pea_jobs ORDER BY created DESC LIMIT 60').fetchall()
        st.caption('Actualización cada 5 segundos. Puedes cambiar de hoja o cerrar esta pestaña mientras Cloud Shell siga activo.')
        if not jobs:st.info('Aquí aparecerán los PEA que solicites desde Preparar documento.')
        for j in jobs:
            with st.container(border=True):
                st.write(j['title']);st.write(j['status']+' · '+j['detail'])
                start=j['started'] or j['created'];elapsed=int((j['finished'] or time.time())-start)
                st.caption(('Tiempo en cola' if j['status']=='En cola' else 'Tiempo transcurrido')+f' · {elapsed//60} min {elapsed%60:02} s')
                if j['status']=='Listo':
                    with connection() as c:a=c.execute('SELECT path FROM artifacts WHERE id=?',(j['id'],)).fetchone()
                    if a and (C.ROOT/a[0]).is_file():st.download_button('Descargar borrador Word',(C.ROOT/a[0]).read_bytes(),file_name='PEA_'+j['id'][:8]+'.docx',key='job_'+j['id'])
    progress_panel()

if __name__=='__main__':
    action,jid=sys.argv[1:]
    try:(supervise if action=='supervise' else work)(jid)
    except Exception as exc:
        msg=str(exc)
        key=os.environ.get('GEMINI_API_KEY')
        if key:msg=msg.replace(key,'[clave oculta]')
        change(jid,'Error',msg[:700] or type(exc).__name__)
