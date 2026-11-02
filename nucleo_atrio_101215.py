"""Consultas locales para la Jefatura. La única conexión SQLite es de lectura."""
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import json
import re
import sqlite3
import unicodedata
import zipfile
import struct

def normal(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in text if not unicodedata.combining(c))))

def conectar(root):
    db = sqlite3.connect((Path(root)/"datos"/"atrio.sqlite3").resolve().as_uri()+"?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db

def grupos(db):
    return [dict(json.loads(r["payload"]), id=r["id"], fingerprint=r["fingerprint"])
            for r in db.execute("SELECT id,fingerprint,payload FROM groups WHERE active=1 ORDER BY rowkey,id")]

# Tabla, columnas utilizadas, rol del documento. Las tareas de generación no son documentos.
FUENTES = {
    "artifacts": "id,group_id,path,content_path,fingerprint,reviewed",
    "biblioteca_pea": "id,group_id,origen,ruta,estado",
    "pea_repo_actual_101213": "id,group_id,group_fingerprint,pdf_original,pdf_adaptado,word_controlado,reporte,estado",
}
def inventario(db, ids=None):
    rows, missing = [], []
    for table, fields in FUENTES.items():
        try:
            sql = f"SELECT {fields} FROM {table}"
            if ids is not None:
                sql += " WHERE group_id IN (" + ",".join("?" for _ in ids) + ")"
            for row in db.execute(sql, tuple(ids or ())):
                r = dict(row)
                kind = {"artifacts":"Extensión generada","pea_repo_actual_101213":"Repositorio adaptado"}.get(table)
                kind = kind or ("Original subido" if r["origen"]=="Subido" else "Copia Word actualizada")
                rows.append(dict(r, tipo_doc=kind, tabla=table))
        except sqlite3.OperationalError as exc:
            if not str(exc).startswith(("no such table:", "no such column:")): raise
            missing.append(table)
    return rows, missing

def conteo(db, ids=None, detalle=False, root=None):
    from collections import Counter
    rows, missing = inventario(db, ids)
    counts = Counter(r["tipo_doc"] for r in rows)
    generated = [r for r in rows if r["tipo_doc"]!="Original subido"]
    n = len(generated)
    ng = len({r["group_id"] for r in generated if r["group_id"]})
    parts = [f"**{'Subtotal verificable' if missing else 'Mis PEA · Generados'}: {n} versiones** vinculadas a {ng} grupos identificados.",
             f"Extensión generada: {counts['Extensión generada']} · Repositorio adaptado: {counts['Repositorio adaptado']} · Copias Word actualizadas: {counts['Copia Word actualizada']}.",
             f"Subidos: {counts['Original subido']} originales."]
    if missing:
        # Presentar solo categorías cuya fuente sí fue consultada.
        parts[1] = "Desglose disponible: " + (", ".join(f"{k}: {v}" for k,v in counts.items() if k!="Original subido") or "sin versiones en las fuentes legibles") + "."
        if "biblioteca_pea" in missing: parts[2] = "Subidos: fuente no disponible."
        parts.append("Fuentes no verificadas: "+", ".join(missing)+".")
    if ids is None:
        try:
            hist = db.execute("SELECT count(*) FROM pea_hist_101212").fetchone()[0]
            parts.append(f"Históricos: {hist} expedientes, contabilizados por separado.")
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc): raise
            parts.append("Históricos: fuente no disponible.")
    if root is not None and "artifacts" not in missing:
        try:
            jobs = {r["id"] for r in db.execute("SELECT id,status FROM pea_jobs ORDER BY created DESC LIMIT 60") if r["status"]=="Listo"}
            ext = [r for r in generated if r["tabla"]=="artifacts"]
            available = 0
            for r in ext:
                path = (Path(root)/(r["path"] or "")).resolve()
                if r["id"] in jobs and path.is_relative_to(Path(root).resolve()) and path.is_file():
                    available += 1
            parts.append(f"Contraste de Extensión · {available} de {len(ext)} versiones tienen descarga en la lista de los últimos 60 trabajos: estado Listo, identificador coincidente y Word presente.")
        except sqlite3.OperationalError as exc:
            if "no such" not in str(exc): raise
            parts.append("Descargas de Extensión: no se pudo verificar la lista de trabajos.")
    if detalle:
        names = {g["id"]:g for g in grupos(db)}
        for r in generated:
            g = names.get(r["group_id"], {})
            parts.append(f"• {r['tipo_doc']} · {g.get('nombre','Grupo fuera de la programación activa')} · {g.get('hoja','')} · registro {r['id']}.")
    parts.append("Para cotejar, abre Mis PEA con los filtros en Todos. Cada adaptación de repositorio cuenta una vez aunque incluya PDF y Word.")
    return "\n\n".join(parts)

def ficha(g):
    return " · ".join(str(v or "—") for v in (g.get("hoja"),g.get("nombre"),g.get("tipo"),g.get("inicio"),g.get("fin"),g.get("horario"),f"{g.get('duracion','?')} h",f"fila {g.get('fila','?')}"))

def buscar(text, rows):
    """Cruza términos de nombres de docente y curso. Los empates mantienen todos los grupos."""
    words = set(normal(text).split())
    ignore = set("a al de del la el en y los las un una con para por que curso cursos grupo grupos docente docentes maestro maestra basico cambio fecha termino dia me da".split())
    teacher_vocab = {w for g in rows for w in normal(g.get("hoja")).split()} - ignore
    course_vocab = {w for g in rows for w in normal(g.get("nombre")).split()} - (ignore-{"basico"})
    teachers, courses = words & teacher_vocab, words & course_vocab
    if not (teachers or courses): return []
    return [g for g in rows if teachers <= set(normal(g.get("hoja")).split())
            and courses-teachers <= set(normal(g.get("nombre")).split())
            ]

def periodo(d):
    return (d.year if d.month>=7 else d.year-1, (d.month-7)%12//3+1)

def fecha(text):
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%Y%m%d"):
        try: return datetime.strptime(str(text), fmt).date()
        except ValueError: pass
    return None

def cotejo_sisae(C,g):
    path = C.RES/"SISAE.zip"
    if not path.is_file(): return "SISAE · Sin corte disponible."
    try:
        with zipfile.ZipFile(path) as z:
            records = [i for i in z.infolist() if Path(i.filename.strip()).name.upper()=="PROG_CURSOS1.DBF"]
            if len(records)!=1 or records[0].file_size>32*1024*1024:
                return "SISAE · No se pudo identificar una tabla de grupos legible."
            rows = C.dbf(z.read(records[0]))
        teacher = sorted(normal(g.get("hoja")).split())
        candidates = [r for r in rows if r.get("ELIMINADO","").upper() not in ("1","T","S")
                      and sorted(normal(r.get("DOC_NOM")).split())==teacher
                      and normal(r.get("NOM_CURSO"))==normal(g.get("nombre"))
                      and fecha(r.get("F_INICIO"))==fecha(g.get("inicio"))]
        if not candidates: return "SISAE · Sin coincidencia exacta de docente, curso e inicio en el corte. Revisa la conciliación antes de concluir que falta captura."
        lines = [f"SISAE · {len(candidates)} candidato(s) por docente, curso e inicio. Contrasta el horario con Programación."]
        for r in candidates:
            slots = [" ".join(r.get("DIA"+str(i)+s,"") for s in ("","A","_DE","_A")).strip() for i in (1,2,3)]
            lines.append(f"• {r.get('CLAVE_CURS') or 'Sin clave'} · término {fecha(r.get('F_TERMINO')) or 'sin fecha legible'} · {' / '.join(filter(None,slots)) or 'sin horario legible'}")
        return "\n\n".join(lines)
    except (ValueError, OSError, KeyError, IndexError, struct.error, zipfile.BadZipFile, RuntimeError):
        return "SISAE · No fue posible leer los grupos del corte."

def simulation(db,C,g,new):
    start, old = fecha(g.get("inicio")), fecha(g.get("fin"))
    if not start or not old: return "Revisa las fechas vigentes de Programación antes de simular."
    if not new: return "Indica la nueva fecha de término en formato DD/MM/AAAA."
    if new < start: return f"La fecha propuesta es anterior al inicio ({start}). Elige una fecha desde el inicio del grupo."
    if new == old: return f"El grupo ya tiene como término {old}. Las fechas coinciden."
    rows, missing = inventario(db,[g["id"]])
    lines = ["**Simulación de término · solo lectura**", ficha(g),
             f"Programación · {old:%d/%m/%Y} → {new:%d/%m/%Y} ({(new-old).days:+d} días naturales)."]
    original, proposed = periodo(old), periodo(new)
    if original != proposed:
        lines.append(f"El cierre pasaría de P{original[1]} ({original[0]}–{original[0]+1}) a P{proposed[1]} ({proposed[0]}–{proposed[0]+1}). Conserva el periodo de inscripción al evaluar matrícula.")
    if (C.RES/"DIAS_SIN_CLASE.json").is_file():
        try:
            report = C.motor.revisar_calendario(dict(g,fin=new.isoformat()),C.RES)
            lines.append("Calendario propuesto · "+report)
        except (KeyError, OSError, ValueError,TypeError): lines.append("Calendario · Requiere revisar días inhábiles, horario y duración.")
    else: lines.append("Calendario · Faltan los días sin clase para verificar las horas.")
    lines.append("**Mis PEA · Registros vinculados al grupo**")
    if normal(g.get("tipo"))=="regular": lines.append("Este grupo es Regular. Su trámite no requiere generar PEA.")
    if not rows: lines.append("Sin documentos vinculados en las fuentes consultadas.")
    for r in rows:
        fields = [("path","Word generado"),("content_path","contenido"),("ruta","Word"),("pdf_original","PDF original"),("pdf_adaptado","PDF adaptado"),("word_controlado","Word controlado"),("reporte","reporte")]
        files = []
        for field,label in fields:
            if r.get(field):
                p = (C.ROOT/r[field]).resolve()
                ok = p.is_relative_to(C.ROOT.resolve()) and p.is_file()
                files.append(f"{label} {p.name} ({'localizado' if ok else 'no comprobado'})")
        lines.append(f"• {r['tipo_doc']} · registro {r['id']} · "+(", ".join(files) or "sin ruta registrada"))
    if missing: lines.append("Fuentes documentales no verificadas: "+", ".join(missing))
    if rows: lines.append("Contrasta las fechas de estos documentos. Si procede una actualización, conserva el original y prepara una versión para revisión.")
    try:
        state = db.execute("SELECT doc,mce FROM status WHERE group_id=?", (g["id"],)).fetchone()
        lines.append("Seguimiento · "+(f"PEA: {state['doc'] or 'Sin verificar'} · MCE: {state['mce'] or 'Sin verificar'}." if state else "Sin estado confirmado para este grupo."))
    except sqlite3.OperationalError as exc:
        if "no such" not in str(exc): raise
        lines.append("Seguimiento y MCE · Fuente no disponible.")
    lines += [cotejo_sisae(C,g),"Excel para MCE y constancias · Comprueba la fecha en cualquier exportación o constancia ya emitida. Aquí no se verificó su emisión."]
    return "\n\n".join(lines)
