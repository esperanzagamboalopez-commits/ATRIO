# -*- coding: utf-8 -*-
"""Asistente Virtual ATRIO integrado con Mi Calendario. Conserva panel(data, C) y añade PDFs/Privacidad."""
import os, re, json, io, sqlite3, unicodedata, hashlib
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, date, time, timedelta
import streamlit as st
import acm_asistencia
import acm_oficios

try:
    from google import genai
    GEMINI_DISPONIBLE = True
except ImportError:
    genai = None
    GEMINI_DISPONIBLE = False

try:
    from docx import Document
    DOCX_DISPONIBLE = True
except ImportError:
    Document = None
    DOCX_DISPONIBLE = False

try:
    import fitz  # PyMuPDF para adaptación de PEA
    PYMUPDF_DISPONIBLE = True
except ImportError:
    fitz = None
    PYMUPDF_DISPONIBLE = False

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

DB_ATRIO = Path(os.environ.get(
    "ATRIO_DB_PATH",
    str(Path(__file__).resolve().parent / "datos" / "atrio.sqlite3")
))
CATEGORIAS_DEFAULT = [
    ("Constancias y documentos", "#d87a9e"),
    ("Cambios de horario", "#6b9ac9"),
    ("Visitas a talleres", "#84b59f"),
    ("Reuniones", "#9c89b8"),
    ("Seguimiento de trámites", "#e6c27a"),
    ("Control escolar", "#4db6ac"),
    ("Actividades institucionales", "#8b3a4a"),
    ("Notas personales", "#9e9e9e"),
    ("PEA y actividades académicas", "#b783a7"),
    ("Programación de cursos", "#7189b8"),
]
MODULOS_ATRIO = [
    "Ninguno", "Programación", "Control escolar", "Preparar PEA", "Revisor",
    "Seguimiento y MCE", "PEA históricos", "Mis PEA", "Excel para MCE",
    "Acciones Móviles", "Constancias y folios", "SISAE · Cortes",
    "Evaluación trimestral", "Auditoría SISAE", "Asistente Virtual"
]
PRIORIDADES = ["Alta", "Media", "Baja"]
TIPOS = ["Tarea", "Compromiso", "Reunión", "Evento", "Recordatorio"]
RECORDATORIOS = ["Ninguno", "Al momento", "15 minutos antes", "1 hora antes", "El mismo día", "1 día antes", "3 días antes", "1 semana antes"]
REPETICIONES = ["No se repite", "Diaria", "Semanal", "Mensual", "Anual"]

MESES_MAP = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
}

def _hoy():
    try:
        return datetime.now(ZoneInfo("America/Mexico_City")).date() if ZoneInfo else date.today()
    except Exception:
        return date.today()

def normalizar(texto):
    texto = str(texto or "").lower()
    texto = re.sub(r"[^\w\s]", "", texto)
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))

def _parsear_fecha_pregunta(q):
    hoy = _hoy()
    if "pasado mañana" in q: return (hoy + timedelta(days=2)).isoformat()
    if "mañana" in q: return (hoy + timedelta(days=1)).isoformat()
    
    m = re.search(r"(\d{1,2})\s*(?:de\s*)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)", q)
    if m:
        day = int(m.group(1))
        month_name = m.group(2)
        month_num = MESES_MAP.get(month_name)
        if month_num:
            year = hoy.year
            if int(month_num) < hoy.month - 1: year += 1
            return f"{year}-{int(month_num):02d}-{day:02d}"
    return None

def _DEF_MOSTRAR_tiempos(pregunta):
    """Responde cuántos días faltan para el cierre de periodo o ciclo."""
    q = normalizar(pregunta)
    
    if not any(k in q for k in ("cierre", "periodo", "ciclo", "trimestre")):
        return None
        
    if not any(k in q for k in ("cuando", "cuanto", "cuantos", "cuantas", "faltan", "dias", "fecha", "termina")):
        return None

    if "curso" in q or "simula" in q or "grupo" in q:
        return None
        
    hoy = _hoy()
    year = hoy.year
    month = hoy.month
    
    if month >= 7:
        cycle_end = date(year + 1, 6, 30)
    else:
        cycle_end = date(year, 6, 30)
        
    if 7 <= month <= 9:
        period_end = date(year, 9, 30)
        p_name = "1"
    elif 10 <= month <= 12:
        period_end = date(year, 12, 31)
        p_name = "2"
    elif 1 <= month <= 3:
        period_end = date(year, 3, 31)
        p_name = "3"
    else:
        period_end = date(year, 6, 30)
        p_name = "4"
        
    dias_periodo = (period_end - hoy).days
    dias_ciclo = (cycle_end - hoy).days
    
    if "ciclo" in q:
        return f"### Fechas límite\nEl ciclo escolar termina el **{cycle_end.strftime('%d/%m/%Y')}**. Faltan **{dias_ciclo} días**.\n\n*Fuente: Cálculo local basado en el calendario oficial.*"
    else:
        return f"### Fechas límite\nEl periodo {p_name} termina el **{period_end.strftime('%d/%m/%Y')}**. Faltan **{dias_periodo} días**.\n\n*Fuente: Cálculo local basado en el calendario oficial.*"

def _contexto_programacion(data):
    resultado = []
    try:
        for grupo in (data or [])[:150]:
            if isinstance(grupo, dict):
                resultado.append({
                    "curso": grupo.get("nombre", ""),
                    "docente": grupo.get("hoja", "")
                })
    except Exception:
        pass
    return resultado

def _score(evento):
    base = {"Alta": 40, "Media": 25, "Baja": 10}.get(evento.get("prioridad", "Media"), 25)
    ref = evento.get("fecha_limite") or evento.get("fecha_fin") or evento.get("fecha_inicio")
    try:
        dias = (datetime.strptime(str(ref)[:10], "%Y-%m-%d").date() - _hoy()).days
    except Exception:
        return base
    urgencia = 120 if dias < 0 else 105 if dias == 0 else 80 if dias <= 2 else 55 if dias <= 7 else 30 if dias <= 14 else 5
    return base + urgencia

def _motivo(evento):
    ref = evento.get("fecha_limite") or evento.get("fecha_fin") or evento.get("fecha_inicio")
    try:
        dias = (datetime.strptime(str(ref)[:10], "%Y-%m-%d").date() - _hoy()).days
    except Exception:
        return "No hay fecha de referencia; se conserva la prioridad manual."
    if dias < 0: return f"Vencido hace {abs(dias)} día(s)."
    if dias == 0: return "La fecha de referencia es hoy."
    if dias == 1: return "Vence mañana."
    if dias <= 3: return f"Vence en {dias} días."
    if dias <= 7: return "Tiene vencimiento cercano."
    return f"Fecha de referencia: {ref}."

def _categoria_id_en_conn(conn, nombre):
    nombre = str(nombre or "Notas personales").strip()
    fila = conn.execute("SELECT id FROM cal_categorias WHERE nombre=? LIMIT 1", (nombre,)).fetchone()
    if fila:
        return fila["id"]
    color = dict(CATEGORIAS_DEFAULT).get(nombre, "#9e9e9e")
    cur = conn.execute("INSERT INTO cal_categorias(nombre,color,activa) VALUES(?,?,1)", (nombre, color))
    return cur.lastrowid

def _guardar_propuesta(datos):
    guardadas, duplicadas = _guardar_propuestas_atomicas([datos])
    return "guardado" if guardadas else "duplicado" if duplicadas else "sin_cambios"

def _categoria_id(nombre):
    if not DB_ATRIO.exists():
        raise FileNotFoundError(f"No existe la base compartida: {DB_ATRIO.resolve()}")
    _asegurar_calendario()
    with _conexion() as conn:
        return _categoria_id_en_conn(conn, nombre)

def generar_word_membrete(texto, C):
    if not DOCX_DISPONIBLE:
        return None
    try:
        recurso = getattr(C, "RES", None)
        if not recurso:
            return None
        ruta = Path(recurso) / "MEMBRETE.docx"
        if not ruta.exists():
            return None
        doc = Document(str(ruta))
        for linea in str(texto).splitlines():
            if linea.strip():
                doc.add_paragraph(linea.strip())
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    except Exception:
        return None

def adaptar_pdf_pea_historico(ruta_origen, ruta_destino, nuevos_metadatos):
    if not PYMUPDF_DISPONIBLE: 
        return False, "PyMuPDF no está disponible (falta fitz)."
    try:
        doc = fitz.open(ruta_origen)
        doc.set_metadata(nuevos_metadatos)
        doc.save(ruta_destino)
        doc.close()
        return True, "Adaptación PDF completada con éxito."
    except Exception as e:
        return False, f"Error adaptando PDF: {str(e)}"

def _es_pregunta_capacidades(texto):
    q = normalizar(texto)
    patrones = (
        "que puedes hacer por mi", "que puedes hacer", "en que me puedes ayudar",
        "como me puedes ayudar", "que sabes hacer", "que funciones tienes",
        "para que sirves", "como puedes ayudarme",
    )
    return any(patron in q for patron in patrones)

def _es_saludo(texto):
    q = normalizar(texto).strip()
    saludos = {
        "hola", "holi", "hey", "buenas", "saludos", "que tal",
        "buen dia", "buenos dias", "buenas tardes", "buenas noches",
        "hola atrio", "buen dia atrio", "buenos dias atrio",
        "buenas tardes atrio", "buenas noches atrio",
    }
    return q in saludos

from collections import Counter, defaultdict
from pathlib import PurePosixPath
from zipfile import ZipFile, BadZipFile
import struct
import tempfile

ASISTENTE_VERSION = "UNIFICADO-PDF-FTS5-1.1.0"
ASSISTANT_VERSION = ASISTENTE_VERSION
ATRIO_VERSION = os.getenv("ATRIO_VERSION", "no_declarada")
HISTORIAL_PATH = None
CONFIG_IA_PATH = None

SYSTEM_PROMPT = """Eres el Asistente Virtual de la Jefatura de Capacitación del CECATI N.º 31.
Responde en español, con claridad y tono institucional.

Reglas obligatorias:
- Redacta documentos completos, formales y listos para revisión. Si piden oficio o convocatoria, entrega el cuerpo sin saludos de chatbot.
- Distingue hechos proporcionados, recomendaciones y datos faltantes.
- No inventes nombres, cargos, fechas, cifras, autorizaciones ni normas.
- No afirmes que enviaste, firmaste, guardaste o ejecutaste una acción.
- No alteres estados de SISAE, PEA, MCE o Control escolar.
- Los datos cuantitativos se resuelven con herramientas locales de solo lectura; no sustituyas una falla por una cifra estimada.
- No solicites ni incluyas CURP, expedientes, domicilios, teléfonos, correos ni información médica.
- Completar una actividad de calendario no significa concluir un trámite oficial.
- Las nuevas actividades son solo propuestas y requieren revisión y autorización explícita.

Si la usuaria pide generar una lista de asistencia para un curso de Acciones Móviles (ACM), extrae los datos y añade un bloque ATRIO_ASISTENCIA_JSON al final de tu DEF_MOSTRAR.
Formato:
<ATRIO_ASISTENCIA_JSON>
{"accion": "generar_asistencia", "docente": "nombre del docente", "curso": "nombre del curso", "institucion": "nombre de la institución"}
</ATRIO_ASISTENCIA_JSON>

Si la usuaria pide generar un oficio de Acciones Móviles (ACM) (Presentación, Vinculación o Asignación), extrae los datos y añade un bloque ATRIO_OFICIO_ACM_JSON al final de tu DEF_MOSTRAR. Si no especifica el tipo, usa "Los tres oficios". Si no hay folio, usa "S/N".
Formato:
<ATRIO_OFICIO_ACM_JSON>
{"accion": "generar_oficio_acm", "docente": "nombre", "curso": "nombre del curso", "tipo_oficio": "Presentación", "institucion": "nombre de la institución", "folio": "S/N"}
</ATRIO_OFICIO_ACM_JSON>
"""

def _ahora_iso():
    try:
        return datetime.now(ZoneInfo("America/Mexico_City")).isoformat(timespec="seconds") if ZoneInfo else datetime.now().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")

def _inyectar_estilos_asistente():
    st.markdown("""<style>
    [data-testid=\"stChatMessage\"]{border-radius:13px;padding:10px 12px;margin-bottom:10px}
    [data-testid=\"stChatMessage\"]:nth-child(even){background:#fffafd;border:1px solid #eadce3}
    [data-testid=\"stChatMessage\"]:nth-child(odd){background:#f7f2f4}
    div[data-testid=\"stMetric\"]{background:#fffafd;border:1px solid #eadce3;padding:12px 14px;border-radius:13px}
    </style>""",unsafe_allow_html=True)

def _raiz_proyecto(C=None):
    candidatos = []
    for attr in ("ROOT", "BASE_DIR", "PROJECT_ROOT"):
        valor = getattr(C, attr, None) if C is not None else None
        if valor:
            try: candidatos.append(Path(valor).expanduser().resolve())
            except Exception: pass
    recurso = getattr(C, "RES", None) if C is not None else None
    if recurso:
        try:
            recurso_path = Path(recurso).expanduser().resolve()
            candidatos.extend([recurso_path.parent.parent, recurso_path.parent])
        except Exception: pass
    candidatos.append(Path(__file__).resolve().parent)
    for p in candidatos:
        if (p / "datos").is_dir() or (p / "app.py").is_file() or (p / "centro.py").is_file():
            return p
    return candidatos[0]

def _ruta_db(C=None):
    env = os.getenv("ATRIO_DB_PATH", "").strip()
    candidatos = [Path(env).expanduser() if env else None]
    raiz = _raiz_proyecto(C)
    candidatos += [raiz / "datos" / "atrio.sqlite3", Path(__file__).resolve().parent / "datos" / "atrio.sqlite3"]
    for p in candidatos:
        if p is not None and p.is_file() and not p.is_symlink():
            return p.resolve()
    return next((p for p in candidatos if p is not None), raiz / "datos" / "atrio.sqlite3").resolve()

def _configurar_rutas(C=None):
    global DB_ATRIO, HISTORIAL_PATH, CONFIG_IA_PATH
    root = _raiz_proyecto(C)
    DB_ATRIO = _ruta_db(C)
    HISTORIAL_PATH = root / "datos" / "chat_history.json"
    CONFIG_IA_PATH = root / "datos" / "config_ia.json"
    return DB_ATRIO

def _pseudonimizar_nombres(texto):
    def reemplazar_nombre(match):
        nombre_real = match.group(0)
        hash_id = hashlib.md5(nombre_real.encode('utf-8')).hexdigest()[:6].upper()
        return f"DOCENTE_{hash_id}"
    patron_nombres = r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b"
    return re.sub(patron_nombres, reemplazar_nombre, str(texto))

def _minimizar_para_ia(obj, profundidad=0):
    if profundidad > 6:
        return "[contenido omitido por profundidad]"
    sensitive = {
        "curp", "id_alumno", "idalumno", "clave_alumno", "numero_control",
        "no_control", "telefono", "celular", "correo", "email", "domicilio",
        "direccion", "fecha_nacimiento", "discapacidad", "diagnostico", "foto",
        "nombre_alumno", "nombre_estudiante", "nombre_completo_alumno", "student_name",
        "firma", "password", "contrasena", "token", "api_key", "gemini_api_key"
    }
    if isinstance(obj, dict):
        return {
            str(k): ("[DATO PERSONAL OMITIDO]" if normalizar(k).replace(" ", "_") in sensitive
                     else _minimizar_para_ia(v, profundidad+1))
            for k,v in obj.items()
            if normalizar(k).replace(" ", "_") not in sensitive
        }
    if isinstance(obj, (list, tuple, set)):
        return [_minimizar_para_ia(v, profundidad+1) for v in list(obj)[:100]]
    if isinstance(obj, str):
        return obj[:1500]
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    return str(obj)[:500]

def _sanear_texto_para_ia(texto):
    value = str(texto or "")[:4000]
    value = re.sub(r"\b[A-ZÑ&]{4}\d{6}[A-Z0-9]{8}\b", "[CURP OMITIDA]", value, flags=re.I)
    value = re.sub(r"\b(?:no\.?|numero|num\.?)\s*(?:de\s*)?(?:control|alumno|expediente)\s*[:#-]?\s*[A-Z0-9-]{4,20}\b", "[IDENTIFICADOR OMITIDO]", value, flags=re.I)
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[CORREO OMITIDO]", value)
    value = re.sub(r"(?<!\d)(?:\+?52[\s-]?)?(?:\d[\s-]?){10}(?!\d)", "[TELÉFONO OMITIDO]", value)
    value = _pseudonimizar_nombres(value)
    return value

def obtener_credenciales():
    modelo_default = "gemini-3.8-flash"
    config = Path(CONFIG_IA_PATH) if CONFIG_IA_PATH else (_raiz_proyecto() / "datos" / "config_ia.json")
    def _modelo_vigente(value):
        model = str(value or modelo_default).strip() or modelo_default
        if model.lower() in ("gemini-1.5-flash", "models/gemini-1.5-flash"):
            return modelo_default
        return model
    try:
        if config.is_file() and not config.is_symlink():
            values = json.loads(config.read_text(encoding="utf-8"))
            key = str(values.get("GEMINI_API_KEY", "")).strip()
            model = _modelo_vigente(values.get("GEMINI_MODELO", modelo_default))
            if key:
                return key, model
    except Exception:
        pass
    try:
        key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        model = _modelo_vigente(st.secrets.get("GEMINI_MODELO", modelo_default))
        if key:
            return key, model
    except Exception:
        pass
    try:
        key = str(os.getenv("GEMINI_API_KEY", "") or st.session_state.get("GEMINI_API_KEY", "")).strip()
        model = _modelo_vigente(os.getenv("GEMINI_MODELO", "") or st.session_state.get("GEMINI_MODELO", modelo_default))
        return key, model
    except Exception:
        return "", modelo_default

def _fecha_iso(valor):
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime): return valor.date().isoformat()
    if isinstance(valor, date): return valor.isoformat()
    texto=str(valor).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            muestra=texto[:8] if fmt=="%Y%m%d" else texto[:10]
            return datetime.strptime(muestra,fmt).date().isoformat()
        except ValueError: pass
    return None

@contextmanager
def _conexion():
    ruta = Path(DB_ATRIO).expanduser().resolve()
    if not ruta.is_file() or ruta.is_symlink():
        raise FileNotFoundError(f"No existe la base ATRIO compartida: {ruta}")
    conn = sqlite3.connect(str(ruta), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _asegurar_calendario():
    with _conexion() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS cal_categorias(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
            color TEXT NOT NULL, activa INTEGER DEFAULT 1)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS cal_eventos(
            id INTEGER PRIMARY KEY AUTOINCREMENT, categoria_id INTEGER,
            titulo TEXT NOT NULL, tipo TEXT DEFAULT 'Tarea',
            fecha_inicio TEXT NOT NULL, fecha_fin TEXT, fecha_limite TEXT,
            hora_inicio TEXT, hora_fin TEXT, todo_el_dia INTEGER DEFAULT 0,
            lugar TEXT, responsable TEXT, descripcion TEXT,
            prioridad TEXT DEFAULT 'Media', recordatorio TEXT DEFAULT 'Ninguno',
            repeticion TEXT DEFAULT 'No se repite', modulo_vinculado TEXT DEFAULT 'Ninguno',
            registro_vinculado_id TEXT, estado TEXT DEFAULT 'Pendiente',
            creado_en TEXT, actualizado_en TEXT, eliminado_en TEXT)""")
        migrations = {
            "categoria_id":"INTEGER", "tipo":"TEXT DEFAULT 'Tarea'", "fecha_fin":"TEXT",
            "fecha_limite":"TEXT", "hora_inicio":"TEXT", "hora_fin":"TEXT",
            "todo_el_dia":"INTEGER DEFAULT 0", "lugar":"TEXT", "responsable":"TEXT",
            "descripcion":"TEXT", "prioridad":"TEXT DEFAULT 'Media'",
            "recordatorio":"TEXT DEFAULT 'Ninguno'", "repeticion":"TEXT DEFAULT 'No se repite'",
            "modulo_vinculado":"TEXT DEFAULT 'Ninguno'", "registro_vinculado_id":"TEXT",
            "estado":"TEXT DEFAULT 'Pendiente'", "creado_en":"TEXT", "actualizado_en":"TEXT",
            "eliminado_en":"TEXT"
        }
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(cal_eventos)")}
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE cal_eventos ADD COLUMN {name} {definition}")
        cat_columns = {r["name"] for r in conn.execute("PRAGMA table_info(cal_categorias)")}
        for name, definition in {"color":"TEXT DEFAULT '#9e9e9e'", "activa":"INTEGER DEFAULT 1"}.items():
            if name not in cat_columns:
                conn.execute(f"ALTER TABLE cal_categorias ADD COLUMN {name} {definition}")
        for name, color in CATEGORIAS_DEFAULT:
            exists = conn.execute("SELECT 1 FROM cal_categorias WHERE nombre=? LIMIT 1", (name,)).fetchone()
            if not exists:
                conn.execute("INSERT INTO cal_categorias(nombre,color,activa) VALUES(?,?,1)", (name, color))
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cal_inicio ON cal_eventos(fecha_inicio)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cal_limite ON cal_eventos(fecha_limite)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cal_estado ON cal_eventos(estado)")
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atrio_auditoria'").fetchone():
            conn.execute("""CREATE TABLE atrio_auditoria(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, usuario TEXT,
                accion TEXT NOT NULL, entidad TEXT, entidad_id TEXT, antes TEXT,
                despues TEXT, fuente TEXT, autorizado_por TEXT, resultado TEXT, detalle TEXT)""")

def diagnostico_calendario():
    result = {"ruta":str(Path(DB_ATRIO).resolve()), "existe":Path(DB_ATRIO).is_file(),
              "total":0,"activos":0,"atrasados":0,"proximos":0,"error":None}
    try:
        if not result["existe"]:
            raise FileNotFoundError("No existe la base compartida de Mi Calendario; no se creó otra base.")
        _asegurar_calendario()
        hoy = _hoy().isoformat()
        hasta = (_hoy() + timedelta(days=7)).isoformat()
        with _conexion() as conn:
            result["total"] = conn.execute("SELECT COUNT(*) FROM cal_eventos").fetchone()[0]
            active = "COALESCE(estado,'Pendiente') NOT IN ('Cancelado','Eliminado','Completada','Completado')"
            result["activos"] = conn.execute(f"SELECT COUNT(*) FROM cal_eventos WHERE {active}").fetchone()[0]
            due = "COALESCE(NULLIF(fecha_limite,''),NULLIF(fecha_fin,''),fecha_inicio)"
            result["atrasados"] = conn.execute(f"SELECT COUNT(*) FROM cal_eventos WHERE {active} AND {due} < ?",(hoy,)).fetchone()[0]
            result["proximos"] = conn.execute(f"SELECT COUNT(*) FROM cal_eventos WHERE {active} AND fecha_limite BETWEEN ? AND ?",(hoy,hasta)).fetchone()[0]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result

def consultar_calendario_registros(limite=120):
    diag = diagnostico_calendario()
    if diag.get("error"):
        raise RuntimeError(diag["error"])
    limite = max(1, min(int(limite), 500))
    with _conexion() as conn:
        rows = conn.execute("""SELECT e.id,e.categoria_id,e.fecha_inicio,e.fecha_fin,e.fecha_limite,
            e.titulo,e.tipo,e.prioridad,e.descripcion,e.modulo_vinculado,e.estado,e.hora_inicio,
            e.hora_fin,e.todo_el_dia,e.lugar,e.responsable,e.recordatorio,e.repeticion,
            e.creado_en,e.actualizado_en,c.nombre AS categoria,c.color AS color_categoria
            FROM cal_eventos e LEFT JOIN cal_categorias c ON e.categoria_id=c.id
            WHERE COALESCE(e.estado,'Pendiente') NOT IN ('Cancelado','Eliminado','Completada','Completado')
            ORDER BY CASE WHEN COALESCE(NULLIF(e.fecha_limite,''),NULLIF(e.fecha_fin,''),e.fecha_inicio) < ? THEN 0 ELSE 1 END,
            COALESCE(NULLIF(e.fecha_limite,''),NULLIF(e.fecha_fin,''),e.fecha_inicio),e.id LIMIT ?""",
            (_hoy().isoformat(),limite)).fetchall()
        return [dict(r) for r in rows]

def consultar_calendario_para_ia():
    diag = diagnostico_calendario()
    if diag.get("error"):
        return "NO FUE POSIBLE LEER EL CALENDARIO. No supongas que está vacío. " + diag["error"]
    rows = consultar_calendario_registros()
    out = [f"Fecha de consulta: {_hoy().isoformat()}; activas={diag['activos']}; atrasadas={diag['atrasados']}; vencen_7_dias={diag['proximos']}."]
    for e in rows[:80]:
        out.append(f"ID {e['id']} | {e.get('fecha_inicio')}→{e.get('fecha_fin') or ''} | límite={e.get('fecha_limite') or 'sin límite'} | {e.get('titulo')} | prioridad={e.get('prioridad')} | estado={e.get('estado')} | módulo={e.get('modulo_vinculado')} | notas={e.get('descripcion') or ''}")
    if not rows: out.append("No hay actividades activas registradas.")
    return "\n".join(out)

def _insertar_auditoria_conn(conn, accion, entidad, entidad_id, antes, despues,
                             fuente, autorizado_por, resultado="ok", detalle=None):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(atrio_auditoria)")}
    if not cols:
        raise RuntimeError("No está disponible la tabla de auditoría.")
    now = _ahora_iso()
    payload = {
        "ts":now,"fecha":now,"usuario":(st.session_state.get("usuario") or st.session_state.get("user") or "jefatura_capacitacion"),
        "accion":accion,"entidad":entidad,"entidad_id":str(entidad_id) if entidad_id is not None else None,
        "antes":json.dumps(antes,ensure_ascii=False,default=str) if antes is not None else None,
        "despues":json.dumps(despues,ensure_ascii=False,default=str) if despues is not None else None,
        "fuente":fuente,"autorizado_por":autorizado_por,"resultado":resultado,
        "detalle":detalle or ""
    }
    names = [k for k in payload if k in cols]
    conn.execute(f"INSERT INTO atrio_auditoria({','.join(names)}) VALUES({','.join('?' for _ in names)})",
                 tuple(payload[k] for k in names))

def _guardar_propuestas_atomicas(lista_datos):
    if not Path(DB_ATRIO).is_file():
        raise FileNotFoundError(f"No existe la base compartida: {DB_ATRIO}")
    _asegurar_calendario()
    now = _ahora_iso()
    results = {"guardadas":0,"duplicadas":0,"ids":[]}
    with _conexion() as conn:
        for item in lista_datos:
            title = str(item.get("titulo") or "").strip()
            start = _fecha_iso(item.get("fecha_inicio"))
            end = _fecha_iso(item.get("fecha_fin"))
            limit = _fecha_iso(item.get("fecha_limite"))
            if not title or not start:
                raise ValueError("Cada actividad necesita nombre y fecha de inicio confirmada.")
            if end and end < start:
                raise ValueError(f"La fecha de término de «{title}» es anterior al inicio.")
            if item.get("hora_inicio") and item.get("hora_fin") and str(item["hora_fin"]) <= str(item["hora_inicio"]):
                raise ValueError(f"La hora final de «{title}» debe ser posterior a la inicial.")
            duplicate = conn.execute("""SELECT id FROM cal_eventos WHERE lower(trim(titulo))=lower(trim(?))
                AND fecha_inicio=? AND COALESCE(estado,'Pendiente') NOT IN ('Cancelado','Eliminado') LIMIT 1""",
                (title,start)).fetchone()
            if duplicate:
                results["duplicadas"] += 1
                continue
            category = str(item.get("categoria") or "Notas personales").strip()
            cat = conn.execute("SELECT id FROM cal_categorias WHERE nombre=? LIMIT 1",(category,)).fetchone()
            cat_id = cat["id"] if cat else conn.execute("INSERT INTO cal_categorias(nombre,color,activa) VALUES(?,?,1)",
                (category,dict(CATEGORIAS_DEFAULT).get(category,"#9e9e9e"))).lastrowid
            all_day = bool(item.get("todo_el_dia",True))
            cur = conn.execute("""INSERT INTO cal_eventos(
                titulo,categoria_id,tipo,fecha_inicio,fecha_fin,fecha_limite,hora_inicio,hora_fin,
                todo_el_dia,lugar,responsable,descripcion,prioridad,recordatorio,repeticion,
                modulo_vinculado,estado,creado_en,actualizado_en)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                title,cat_id,item.get("tipo") if item.get("tipo") in TIPOS else "Tarea",
                start,end if end != start else None,limit,None if all_day else item.get("hora_inicio"),
                None if all_day else item.get("hora_fin"),1 if all_day else 0,
                str(item.get("lugar") or "").strip(),str(item.get("responsable") or "").strip(),
                str(item.get("descripcion") or "").strip(),item.get("prioridad") if item.get("prioridad") in PRIORIDADES else "Media",
                item.get("recordatorio") if item.get("recordatorio") in RECORDATORIOS else "Ninguno",
                item.get("repeticion") if item.get("repeticion") in REPETICIONES else "No se repite",
                item.get("modulo_vinculado") if item.get("modulo_vinculado") in MODULOS_ATRIO else "Ninguno",
                "Pendiente",now,now))
            new_id = cur.lastrowid
            results["ids"].append(new_id)
            results["guardadas"] += 1
            _insertar_auditoria_conn(conn,"crear_actividad","cal_eventos",new_id,None,
                {"titulo":title,"fecha_inicio":start,"fecha_fin":end,"fecha_limite":limit,
                 "prioridad":item.get("prioridad"),"modulo_vinculado":item.get("modulo_vinculado")},
                "ATRIO_ASISTENTE",st.session_state.get("usuario") or st.session_state.get("user") or "jefatura_capacitacion",
                "ok","Actividad guardada tras autorización expresa de la usuaria.")
        _insertar_auditoria_conn(conn,"autorizar_propuesta","propuesta_asistente",None,None,
            {"guardadas":results["guardadas"],"duplicadas":results["duplicadas"]},
            "ATRIO_ASISTENTE",st.session_state.get("usuario") or st.session_state.get("user") or "jefatura_capacitacion",
            "ok","La autorización y los registros individuales se confirmaron en una sola transacción.")
    return results

def _leer_tabla_dbf(z, table_name, required=(), optional=()):
    wanted = table_name.upper()
    matches = [i for i in z.infolist() if not i.is_dir() and PurePosixPath(i.filename.strip()).name.upper()==wanted]
    if len(matches) != 1:
        raise ValueError(f"La tabla {wanted} no es única o no está presente en el ZIP.")
    info = matches[0]
    if info.file_size > 90_000_000:
        raise ValueError(f"La tabla {wanted} excede el límite de lectura.")
    with z.open(info) as f:
        head = f.read(32)
        if len(head) != 32: raise ValueError(f"Encabezado DBF incompleto en {wanted}.")
        count = struct.unpack_from("<I",head,4)[0]
        hlen = struct.unpack_from("<H",head,8)[0]
        rlen = struct.unpack_from("<H",head,10)[0]
        if not 33 <= hlen <= 65535 or not 2 <= rlen <= 16384 or count > 1_000_000:
            raise ValueError(f"Estructura DBF fuera de límites en {wanted}.")
        desc = f.read(hlen-32)
        if len(desc) != hlen-32: raise ValueError(f"Descriptores DBF incompletos en {wanted}.")
        offsets, cursor = {}, 1
        for pos in range(0,len(desc),32):
            d = desc[pos:pos+32]
            if len(d) < 32 or d[0] == 13: break
            name = d[:11].split(b"\0",1)[0].decode("latin1").strip().upper()
            length = int(d[16])
            if not name or length <= 0 or name in offsets: raise ValueError(f"Campo DBF inválido en {wanted}.")
            offsets[name] = (cursor,length)
            cursor += length
        if cursor > rlen: raise ValueError(f"Los campos exceden el registro DBF de {wanted}.")
        absent = set(required)-set(offsets)
        if absent: raise ValueError(f"Faltan campos en {wanted}: {', '.join(sorted(absent))}.")
        selected = set(required) | (set(optional) & set(offsets))
        fields = {n:offsets[n] for n in selected}
        rows, deleted = [], 0
        f.seek(hlen)
        for _ in range(count):
            rec = f.read(rlen)
            if len(rec) != rlen: raise ValueError(f"Registro truncado en {wanted}.")
            if rec[:1] == b"*":
                deleted += 1
                continue
            if rec[:1] != b" ": raise ValueError(f"Marca de registro desconocida en {wanted}.")
            row = {}
            for name,(offset,length) in fields.items():
                row[name] = rec[offset:offset+length].decode("cp1252","replace").strip()
            rows.append(row)
        return rows, deleted, set(offsets)

def _clave_num(valor):
    s = str(valor or "").strip()
    if not s: return ""
    if re.fullmatch(r"\d+(?:\.0+)?",s):
        try: return str(int(float(s)))
        except Exception: return s
    return s.casefold()

def _esta_eliminado(valor):
    return normalizar(valor) in {"1", "t", "true", "s", "si", "y", "yes", "verdadero"}

def _fecha_dbf(valor):
    s = str(valor or "").strip()
    if len(s)==8 and s.isdigit():
        try: return datetime.strptime(s,"%Y%m%d").date().isoformat()
        except ValueError: return None
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
        try: return datetime.strptime(s,fmt).date().isoformat()
        except ValueError: pass
    return None

def _ciclo_periodo_pregunta(q):
    matches = re.findall(r"\b(20\d{2})\s*[-/]\s*(20\d{2})\b",q)
    if len(set(matches)) > 1: raise ValueError("Indica un solo ciclo escolar.")
    ciclo = f"{matches[0][0]}-{matches[0][1]}" if matches else os.getenv("ATRIO_CICLO_ACTUAL","2026-2027")
    patterns = {
        "1":(r"\bprimer(?:o)?\s+periodo\b",r"\b1(?:er|o)?\s+periodo\b",r"\bperiodo\s*1\b",r"\btrimestre\s*1\b",r"\bjulio\s+(?:a|hasta)\s+septiembre\b"),
        "2":(r"\bsegundo\s+periodo\b",r"\b2do\s+periodo\b",r"\bperiodo\s*2\b",r"\btrimestre\s*2\b",r"\boctubre\s+(?:a|hasta)\s+diciembre\b"),
        "3":(r"\btercer(?:o)?\s+periodo\b",r"\b3er\s+periodo\b",r"\bperiodo\s*3\b",r"\btrimestre\s*3\b",r"\benero\s+(?:a|hasta)\s+marzo\b"),
        "4":(r"\bcuarto\s+periodo\b",r"\b4to\s+periodo\b",r"\bperiodo\s*4\b",r"\btrimestre\s*4\b",r"\babril\s+(?:a|hasta)\s+junio\b")}
    found = [n for n,regs in patterns.items() if any(re.search(x,q) for x in regs)]
    if len(found)>1: raise ValueError("La pregunta menciona más de un periodo; indica uno solo.")
    return ciclo, (found[0] if found else None)

def _sisae_path(C=None):
    root = _raiz_proyecto(C)
    res = getattr(C,"RES",None) if C is not None else None
    candidates = []
    if res:
        try: candidates.append(Path(res).expanduser()/"SISAE.zip")
        except Exception: pass
    candidates += [root/"datos"/"recursos"/"SISAE.zip",root/"SISAE.zip",
                   Path(__file__).resolve().parent/"datos"/"recursos"/"SISAE.zip"]
    for p in candidates:
        if p.is_file() and not p.is_symlink(): return p.resolve()
    return candidates[0] if candidates else root/"datos"/"recursos"/"SISAE.zip"

def _leer_sisae_snapshot(ruta, ciclo, periodo):
    ruta = Path(ruta)
    if not ruta.is_file() or ruta.is_symlink() or ruta.suffix.lower() != ".zip":
        raise FileNotFoundError("No existe un ZIP SISAE local regular.")
    with ZipFile(ruta) as z:
        prog_req = ("CLAVE_CURS","CICLO","PERIODO","NOM_CURSO","ELIMINADO")
        prog_opt = ("CLV_PLA","CLV_AREA","CLV_ESP","DOC_NOM","F_INICIO","F_TERMINO",
                    "DIA1","DIA1_DE","DIA1_A","DIA2","DIA2_DE","DIA2_A","DIA3","DIA3_DE","DIA3_A")
        prog, del_prog, prog_cols = _leer_tabla_dbf(z,"PROG_CURSOS1.DBF",prog_req,prog_opt)
        ins_req = ("CLV_CURSO","ID_ALUMNO","CICLO","PERIODO","ELIMINADO")
        ins, del_ins, ins_cols = _leer_tabla_dbf(z,"INSCRIPCION.DBF",ins_req,("CLV_PLA","F_INSCRIP"))
        esp = []
        try:
            esp, _, _ = _leer_tabla_dbf(z,"ESP.DBF",("CLV_AREA","CLV_ESP","NOM_ESP"),())
        except ValueError:
            esp = []
        listas = None
        list_deleted = 0
        try:
            listas, list_deleted, list_cols = _leer_tabla_dbf(z,"LISTAS.DBF",("ID_ALUMNO","CLAVE_CURS","CICLO","PERIODO"),("CLV_PLA","CLV_ESP",))
        except ValueError:
            listas = None
    group_map = {}
    group_index = defaultdict(list)
    group_rows = []
    for g in prog:
        if _esta_eliminado(g.get("ELIMINADO","")): continue
        if g.get("CICLO") != ciclo: continue
        if periodo and g.get("PERIODO") != periodo: continue
        key = (g.get("CLV_PLA",""),g.get("CICLO",""),_clave_num(g.get("CLAVE_CURS")))
        if key in group_map: raise ValueError("Hay claves de grupo repetidas en PROG_CURSOS1.DBF; conteo detenido.")
        row = dict(g)
        group_map[key] = row
        group_index[(key[1], key[2])].append(key)
        group_rows.append(row)
    enrolled = []
    orphan = 0
    for r in ins:
        if _esta_eliminado(r.get("ELIMINADO","")) or r.get("CICLO") != ciclo: continue
        if periodo and r.get("PERIODO") != periodo: continue
        key = (r.get("CLV_PLA",""),r.get("CICLO",""),_clave_num(r.get("CLV_CURSO")))
        if key not in group_map:
            candidates = group_index.get((r.get("CICLO",""),_clave_num(r.get("CLV_CURSO"))), [])
            if not str(r.get("CLV_PLA","")).strip() and len(candidates) == 1:
                key = candidates[0]
            else:
                orphan += 1
                continue
        r["_GROUP_KEY"] = key
        enrolled.append(r)
    if orphan:
        raise ValueError(f"{orphan} registros de inscripción no enlazan con un grupo. No se emite conteo parcial.")
    unique_enroll = {}
    repeated_ins = 0
    no_id = 0
    for r in enrolled:
        person = _clave_num(r.get("ID_ALUMNO"))
        group_key = r.get("_GROUP_KEY") or (r.get("CLV_PLA",""),r.get("CICLO",""),_clave_num(r.get("CLV_CURSO")))
        key = (group_key[0],group_key[1],r.get("PERIODO",""),group_key[2],person)
        if not person:
            no_id += 1
            unique_enroll[("SIN_ID",len(unique_enroll),r.get("CLV_CURSO"))] = r
        elif key in unique_enroll:
            repeated_ins += 1
        else:
            unique_enroll[key] = r
    esp_catalog = {}
    for e in esp:
        esp_catalog[(e.get("CLV_AREA"),e.get("CLV_ESP"))] = e.get("NOM_ESP")
    by_group = Counter()
    people_by_group = defaultdict(set)
    people_all = set()
    people_by_specialty = defaultdict(set)
    people_by_teacher = defaultdict(set)
    for r in unique_enroll.values():
        key = r.get("_GROUP_KEY") or (r.get("CLV_PLA",""),r.get("CICLO",""),_clave_num(r.get("CLV_CURSO")))
        by_group[key] += 1
        person = _clave_num(r.get("ID_ALUMNO"))
        if person:
            person_key=(r.get("CLV_PLA",""),person)
            people_by_group[key].add(person_key)
            people_all.add(person_key)
            gref=group_map.get(key,{})
            spec=(gref.get("CLV_AREA",""),gref.get("CLV_ESP",""))
            spec_name=esp_catalog.get(spec,"Sin catálogo ESP") if 'esp_catalog' in locals() else "Sin catálogo ESP"
            if spec_name: people_by_specialty[spec_name].add(person_key)
            teacher_name=str(gref.get("DOC_NOM") or "Sin docente")
            people_by_teacher[teacher_name].add(person_key)
    list_state = "no_disponible"
    list_only_ins = list_only_list = repeated_list = 0
    if listas is not None:
        ins_keys = set()
        for r in enrolled:
            person = _clave_num(r.get("ID_ALUMNO"))
            if person:
                group_key = r.get("_GROUP_KEY") or (r.get("CLV_PLA",""),r.get("CICLO",""),_clave_num(r.get("CLV_CURSO")))
                ins_keys.add((group_key[0],group_key[1],r.get("PERIODO",""),group_key[2],person))
        list_counts = Counter()
        group_keys = set(group_map)
        for r in listas:
            if r.get("CICLO") != ciclo or (periodo and r.get("PERIODO") != periodo): continue
            key_group = (r.get("CLV_PLA",""),r.get("CICLO",""),_clave_num(r.get("CLAVE_CURS")))
            if key_group not in group_keys:
                candidates = group_index.get((r.get("CICLO",""),_clave_num(r.get("CLAVE_CURS"))), [])
                if not str(r.get("CLV_PLA","")).strip() and len(candidates) == 1:
                    key_group = candidates[0]
                else:
                    continue
            person = _clave_num(r.get("ID_ALUMNO"))
            if person:
                list_counts[(key_group[0],key_group[1],r.get("PERIODO",""),key_group[2],person)] += 1
        list_keys = set(list_counts)
        list_only_ins = len(ins_keys-list_keys)
        list_only_list = len(list_keys-ins_keys)
        repeated_list = sum(n-1 for n in list_counts.values() if n>1)
        list_state = "coincide" if list_only_ins == 0 and list_only_list == 0 and repeated_ins == 0 and no_id == 0 else "requiere_revision"
    
    out_groups = []
    for key,g in group_map.items():
        schedule = []
        for i in ("1","2","3"):
            day = g.get("DIA"+i,"")
            start,end = g.get("DIA"+i+"_DE", ""),g.get("DIA"+i+"_A", "")
            if day:
                schedule.append(f"{day} de {start} a {end}" if start and end else day)
        out_groups.append({
            "curso":g.get("NOM_CURSO",""),"docente":g.get("DOC_NOM",""),
            "inicio":_fecha_dbf(g.get("F_INICIO")),"fin":_fecha_dbf(g.get("F_TERMINO")),
            "horario":" | ".join(schedule) if schedule else "Sin horario legible",
            "especialidad":esp_catalog.get((g.get("CLV_AREA"),g.get("CLV_ESP")),"Sin catálogo ESP"),
            "clave_interna":_clave_num(g.get("CLAVE_CURS")),
            "inscripciones":by_group.get(key,0),"personas_unicas":len(people_by_group.get(key,set()))
        })
    by_group_enrolled = [x for x in out_groups if x["inscripciones"]>0]
    stamp = None
    m = re.search(r"(?<!\d)(20\d{2})[._-](\d{2})[._-](\d{2})(?!\d)",ruta.name)
    if m: stamp = f"{m[1]}-{m[2]}-{m[3]}"
    return {
        "ruta_nombre":ruta.name,"fecha_nominal":stamp,"ciclo":ciclo,"periodo":periodo or "todos",
        "grupos_programados":len(out_groups),"grupos_con_inscripciones":len(by_group_enrolled),
        "grupos_sin_inscripciones":len(out_groups)-len(by_group_enrolled),
        "grupos_1_9":sum(1 for x in by_group_enrolled if 1<=x["inscripciones"]<=9),
        "grupos_10_mas":sum(1 for x in by_group_enrolled if x["inscripciones"]>=10),
        "inscripciones":sum(x["inscripciones"] for x in out_groups),
        "personas_unicas":len(people_all),
        "personas_unicas_por_especialidad":{k:len(v) for k,v in people_by_specialty.items()},
        "personas_unicas_por_docente":{k:len(v) for k,v in people_by_teacher.items()},
        "inscripciones_repetidas":repeated_ins,
        "inscripciones_sin_id":no_id,"listas_estado":list_state,"solo_inscripcion":list_only_ins,
        "solo_listas":list_only_list,"listas_repetidas":repeated_list,
        "tablas_leidas":["PROG_CURSOS1.DBF","INSCRIPCION.DBF"]+( ["ESP.DBF"] if esp else [])+( ["LISTAS.DBF"] if listas is not None else []),
        "registros_dbf_eliminados_omitidos":{"programacion":del_prog,"inscripciones":del_ins,"listas":list_deleted},
        "grupos":out_groups,
        "advertencia":"Copia local SISAE; no es consulta en vivo. LISTAS01.DBF no se suma. Los IDs individuales se descartan antes de devolver resultados."
    }

def _leer_sisae_cache_key(path, mtime_ns, size, ciclo, periodo):
    return _leer_sisae_snapshot(path,ciclo,periodo)
try:
    _cache_sisae = st.cache_data(ttl=300, show_spinner=False)(_leer_sisae_cache_key)
except Exception:
    _cache_sisae = _leer_sisae_cache_key

def cargar_sisae_completo(ruta_zip_str, ciclo=None, periodo=None):
    p=Path(ruta_zip_str)
    if not p.is_file() or p.is_symlink(): raise FileNotFoundError("No se encontró el corte SISAE local.")
    cycle=ciclo or os.getenv("ATRIO_CICLO_ACTUAL","2026-2027")
    stat=p.stat()
    return _cache_sisae(str(p.resolve()),stat.st_mtime_ns,stat.st_size,cycle,periodo)

def extraer_datos_sisae(C):
    path = _sisae_path(C)
    snap = cargar_sisae_completo(path)
    safe = [{k:v for k,v in g.items() if k not in ("clave_interna",)} for g in snap["grupos"]]
    return json.dumps(safe,ensure_ascii=False)

def _grupos_data(data):
    if data is None: return []
    if hasattr(data,"to_dict"):
        try: data = data.to_dict(orient="records")
        except Exception: pass
    if isinstance(data,dict):
        for k in ("grupos","data","rows","registros"):
            if isinstance(data.get(k),(list,tuple)): data=data[k]; break
        else: data=[data]
    if not isinstance(data,(list,tuple)): return []
    aliases = {
        "nombre":("nombre","curso","nom_curso"),"hoja":("hoja","docente","profesor","nombre_docente"),
        "inicio":("inicio","fecha_inicio","f_inicio"),"fin":("fin","termino","fecha_fin","f_termino"),
        "horario":("horario","hora","horas"),"duracion":("duracion","horas_totales","duracion_horas"),
        "tipo":("tipo","modalidad"),"id":("id","group_id","id_grupo"),"especialidad":("especialidad","nombre_especialidad"),
        "fila":("fila","rowkey","fila_excel"),"aula":("aula","salon","taller")}
    out=[]
    for raw in data:
        if not isinstance(raw,dict): continue
        row={}
        normkeys={normalizar(k).replace(" ","_"):v for k,v in raw.items()}
        for dst,names in aliases.items():
            for name in names:
                if name in normkeys and normkeys[name] not in (None,""):
                    row[dst]=normkeys[name]; break
        for key in ("inicio","fin"):
            if row.get(key): row[key]=_fecha_iso(row[key]) or str(row[key])[:10]
        row["_original"]=raw
        out.append(row)
    return out

def _buscar_grupos(texto, grupos):
    q = set(normalizar(texto).split())
    ignorar = set("a al de del la el en y los las un una con para por que pasa si que curso cursos grupo grupos docente docentes maestro maestra profesor profesora imparte imparten tiene tienen busca buscar muestra dime cual cuales sobre cambia cambiara cambiar termina termina una semana fecha fin termino mismo ese este su sus simular simulacion cambio nueva nuevo propuesta propuesto actual actualmente horario inicio dias dia despues mas tarde semana semanas al analizar impacto fecha termina terminaras cierre".split())
    terms = {x for x in q-ignorar if len(x)>1}
    if not terms: return []
    found=[]
    for g in grupos:
        available = {
            token
            for field in (g.get("hoja"), g.get("nombre"), g.get("especialidad"))
            for token in normalizar(field).split()
            if token and token not in ignorar and len(token) > 1
        }
        if not available:
            continue
        matched = {
            t for t in terms
            if any(
                t == v or (len(t) >= 4 and len(v) >= 4 and (t in v or v in t))
                for v in available
            )
        }
        if matched and (matched==terms or len(matched)>=max(1,len(terms)-1)):
            found.append(g)
    return found

def _ficha_grupo(g):
    return " · ".join(str(v or "—") for v in (g.get("hoja"),g.get("nombre"),g.get("tipo"),g.get("inicio"),g.get("fin"),g.get("horario"),f"{g.get('duracion','?')} h",f"fila {g.get('fila','?')}"))

def _consulta_status(grupos, C):
    result=[]; unknown=0
    fn=getattr(C,"status",None) if C is not None else None
    if not callable(fn): return None
    for g in grupos:
        gid=g.get("id")
        if gid is None: unknown+=1; continue
        try:
            val=fn(gid)
            if not isinstance(val,dict): unknown+=1; continue
            result.append((g,val))
        except Exception:
            unknown+=1
    return result,unknown

def _pea_inventory(ids=None):
    if not Path(DB_ATRIO).is_file(): return {"estado":"base_no_disponible"}
    uri=Path(DB_ATRIO).resolve().as_uri()+"?mode=ro"
    conn=sqlite3.connect(uri,uri=True,timeout=10)
    conn.row_factory=sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        sources={"artifacts":"Extensión generada","biblioteca_pea":"Biblioteca PEA","pea_repo_actual_101213":"Repositorio adaptado"}
        rows=[]; missing=[]
        for table,label in sources.items():
            if table not in tables:
                missing.append(table); continue
            cols={r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            needed=[c for c in ("id","group_id","origen","ruta","estado","reviewed","path","pdf_original","pdf_adaptado","word_controlado") if c in cols]
            if not needed or "group_id" not in cols:
                missing.append(table); continue
            sql=f"SELECT {','.join(needed)} FROM {table}"
            args=[]
            if ids is not None and ids:
                sql += " WHERE group_id IN ("+",".join("?" for _ in ids)+")"; args=list(ids)
            elif ids == []:
                continue
            for r in conn.execute(sql,args):
                d=dict(r)
                if table=="biblioteca_pea":
                    d["tipo_doc"]="Original subido" if normalizar(d.get("origen"))=="subido" else "Copia Word actualizada"
                else: d["tipo_doc"]=label
                d["tabla"]=table
                rows.append(d)
        hist=None
        if ids is None and "pea_hist_101212" in tables:
            hist=conn.execute("SELECT COUNT(*) FROM pea_hist_101212").fetchone()[0]
        elif ids is None: missing.append("pea_hist_101212")
        counts=Counter(r["tipo_doc"] for r in rows)
        generated=[r for r in rows if r["tipo_doc"]!="Original subido"]
        ready_jobs=None
        if "pea_jobs" in tables and any(r["tabla"]=="artifacts" for r in generated):
            try: ready_jobs=conn.execute("SELECT COUNT(*) FROM pea_jobs WHERE status='Listo'").fetchone()[0]
            except sqlite3.Error: ready_jobs=None
        return {"estado":"consultado_con_fuentes_faltantes" if missing else "consultado",
            "versiones_generadas":len(generated),"grupos_con_version":len({r.get("group_id") for r in generated if r.get("group_id")}),
            "extension_generada":counts["Extensión generada"],"repositorio_adaptado":counts["Repositorio adaptado"],
            "copias_actualizadas":counts["Copia Word actualizada"],"originales_subidos":counts["Original subido"],
            "historicos":hist,"fuentes_no_disponibles":missing,"trabajos_listos_tabla_jobs":ready_jobs,
            "detalle":rows[:150]}
    finally: conn.close()

def _DEF_MOSTRAR_pea(pregunta, data, C):
    q=normalizar(pregunta)
    if not any(k in q for k in ("pea","mis pea","mce","revisor","historico","historicos")): return None
    wants_count=any(k in q for k in ("cuant","cuantos","cuantas","total","numero","cantidad","generad","elaborad","versiones","hay"))
    groups=_grupos_data(data)
    requested_reader = "revisor" if "revisor" in q else ("mce" if "mce" in q else ("pea_historico" if "historico" in q else None))
    readers=getattr(C,"ATRIO_ASISTENTE_LECTORES",{}) if C is not None else {}
    reader=readers.get(requested_reader) if requested_reader and isinstance(readers,dict) else None
    if callable(reader):
        try:
            external=reader()
            return f"### {requested_reader.replace('_',' ').title()} · lector local registrado\n"+json.dumps(_minimizar_para_ia(external),ensure_ascii=False,indent=2,default=str)[:9000]+f"\n\nFuente: lector `ATRIO_ASISTENTE_LECTORES['{requested_reader}']` · {_ahora_iso()}."
        except Exception as exc:
            return f"El lector real de {requested_reader} informó un error ({type(exc).__name__}). No se asume cero ni estado pendiente."
    if "historico" in q and wants_count and ("pea" in q or "document" in q):
        inv=_pea_inventory()
        if inv.get("estado")=="base_no_disponible": return "No pude consultar Mis PEA: no está disponible la base ATRIO. No reportaré cero históricos."
        if inv.get("historicos") is None: return "La tabla de PEA históricos `pea_hist_101212` no está disponible en esta base. No puedo confirmar un total."
        return f"### PEA históricos\nHay **{inv['historicos']} expedientes históricos** en la tabla `pea_hist_101212`. Se cuentan por separado de los PEA generados para el ciclo actual.\n\nFuente: SQLite ATRIO · consulta local de solo lectura · {_ahora_iso()}."
    if "mce" in q or "revisor" in q or ("pea" in q and any(x in q for x in ("pendiente","sin pea","faltan","faltante","no tienen"))):
        info=_consulta_status(groups,C)
        if info is None:
            return "No tengo acceso a los estados `C.status(id)` en esta sesión. No puedo confirmar pendientes de PEA o MCE; no interpretaré esto como cero."
        statuses,unknown=info
        pea_aplica=lambda g: normalizar(g.get("tipo"))!="regular"
        no_pea=[g for g,s in statuses if pea_aplica(g) and normalizar(s.get("doc"))=="sin pea"]
        no_ver=[g for g,s in statuses if pea_aplica(g) and normalizar(s.get("doc")) in ("sin verificar","")]
        mce_no=[g for g,s in statuses if normalizar(s.get("mce"))=="no subido"]
        mce_obs=[g for g,s in statuses if normalizar(s.get("mce"))=="observado"]
        mce_un=[g for g,s in statuses if normalizar(s.get("mce")) in ("sin verificar","")]
        lines=["### Estados registrados de seguimiento · solo grupos que `C.status(id)` permitió consultar"]
        if "revisor" in q:
            lines.append("El estado documental no sustituye el dictamen detallado del Revisor Académico.")
        if "mce" in q or "pendiente" in q:
            lines += [f"- MCE **No subido**: {len(mce_no)}.",f"- MCE **Observado**: {len(mce_obs)}.",f"- MCE **Sin verificar**: {len(mce_un)}."]
        if "pea" in q or "revisor" in q or "pendiente" in q:
            lines += [f"- PEA **Sin PEA**: {len(no_pea)}.",f"- PEA **Sin verificar**: {len(no_ver)}."]
        lines.append(f"- No se pudo consultar estado de {unknown} grupos.")
        lines.append("Sin verificar no se cuenta como pendiente confirmado. Un documento existente tampoco demuestra autorización.")
        if any(x in q for x in ("cuales","que grupos","que pea","lista","muestra","detalla","quienes")):
            for label, rows in (("PEA Sin PEA",no_pea),("MCE No subido",mce_no),("MCE Observado",mce_obs)):
                if rows: lines.append("\n**"+label+"**\n"+"\n".join("- "+_ficha_grupo(g) for g in rows[:30]))
        lines.append(f"Fuente: C.status(id) · consulta local · {_ahora_iso()}.")
        return "\n".join(lines)
    if "pea" in q and (wants_count or any(x in q for x in ("lista","cuales","muestra","detalla"))):
        inv=_pea_inventory()
        if inv.get("estado")=="base_no_disponible": return "No pude consultar Mis PEA porque no localicé el SQLite de ATRIO. No asumiré que no hay documentos."
        lines=["### Mis PEA · inventario documental"]
        if inv["estado"]=="consultado_con_fuentes_faltantes": lines.append("**Subtotal parcial:** hay fuentes documentales que no existen o no pudieron leerse en este esquema: "+", ".join(inv["fuentes_no_disponibles"])+".")
        lines += [f"- Versiones generadas/adaptadas (no originales subidos): **{inv['versiones_generadas']}**.",
                  f"- Extensión generada: {inv['extension_generada']}.",
                  f"- Repositorio adaptado: {inv['repositorio_adaptado']}.",
                  f"- Copias Word actualizadas: {inv['copias_actualizadas']}.",
                  f"- Originales subidos: **{inv['originales_subidos']}**."]
        if inv["historicos"] is not None: lines.append(f"- PEA históricos (tabla separada): **{inv['historicos']}**.")
        lines.append("Una versión generada no significa revisada, subida a MCE ni autorizada. Los originales subidos se separan del conteo de versiones.")
        if any(x in q for x in ("lista","cuales","muestra","detalla")):
            for row in inv.get("detalle",[])[:35]:
                lines.append(f"- {row.get('tipo_doc')} · registro {row.get('id')} · grupo {row.get('group_id')} · estado registrado: {row.get('estado') or 'no indicado'}.")
        lines.append(f"Fuente: SQLite ATRIO · artifacts, biblioteca_pea y pea_repo_actual_101213 · {_ahora_iso()}.")
        return "\n".join(lines)
    return "Identifiqué una consulta de PEA/MCE, pero necesito precisar si buscas versiones generadas, históricos, grupos sin PEA o estados de MCE."

def _DEF_MOSTRAR_programacion(pregunta, data):
    q = normalizar(pregunta)
    groups = _grupos_data(data)
    if not groups: return None

    asks_count = any(k in q for k in ("cuant", "total", "cantidad", "hay"))
    
    hoy = _hoy()
    target_date = _parsear_fecha_pregunta(q)
    
    if target_date:
        active = [g for g in groups if g.get('inicio') <= target_date <= g.get('fin')]
        title = f"Programación · Cursos en sesión el {target_date}"
        if not active: return f"### {title}\nNo hay cursos programados en sesión para esa fecha."
        lines=["### "+title]
        for g in active:
            lines.append(f"- {_ficha_grupo(g)}")
        return "\n".join(lines)

    mes_encontrado = None
    nombre_mes = ""
    for mes, num in MESES_MAP.items():
        if mes in q:
            mes_encontrado = num
            nombre_mes = mes
            break

    if mes_encontrado:
        es_busqueda_termino = any(k in q for k in ("termin", "finaliz", "conclu", "fin", "acaban"))
        campo_evaluar = "fin" if es_busqueda_termino else "inicio"
        verbo_accion = "terminan" if es_busqueda_termino else "inician"

        grupos_mes = []
        for g in groups:
            fecha_val = str(g.get(campo_evaluar) or "")
            if f"-{mes_encontrado}-" in fecha_val or (len(fecha_val) >= 7 and fecha_val[5:7] == mes_encontrado):
                grupos_mes.append(g)

        total_mes = len(grupos_mes)
        if total_mes == 0:
            return f"### Programación · Cursos que {verbo_accion} en {nombre_mes.capitalize()}\nNo se encontraron cursos programados para {verbo_accion} en **{nombre_mes}**."
        
        lineas = [f"### Programación · {total_mes} curso(s) que {verbo_accion} en {nombre_mes.capitalize()}"]
        for i, g in enumerate(grupos_mes[:25], 1):
            lineas.append(f"{i}. {_ficha_grupo(g)}")
        if total_mes > 25:
            lineas.append(f"\n*... y {total_mes - 25} grupos más.*")
        return "\n".join(lineas)

    if asks_count and any(k in q for k in ("docentes", "docente", "maestros")) and not _buscar_grupos(pregunta, groups):
        teachers = {normalizar(g.get("hoja")) for g in groups if normalizar(g.get("hoja"))}
        return f"En el contexto de Programación hay **{len(teachers)} docentes distintos** asociados a **{len(groups)} grupos**."

    hits = _buscar_grupos(pregunta, groups)
    if asks_count and hits:
        names = sorted({str(g.get("hoja")) for g in hits if g.get("hoja")})
        label = ", ".join(names) if names else "filtro solicitado"
        return f"### Programación · consulta por docente/curso\n{label}: **{len(hits)} grupos/cursos**.\n\n" + "\n".join(f"- {_ficha_grupo(g)}" for g in hits[:25])

    if asks_count:
        return f"Hay **{len(groups)} registros de grupos** en el contexto activo de Programación."

    if hits:
        return f"### Programación · {len(hits)} coincidencia(s)\n" + "\n".join(f"{i}. {_ficha_grupo(g)}" for i, g in enumerate(hits[:35], 1))

    return None

def _DEF_MOSTRAR_sisae(pregunta, C):
    q=normalizar(pregunta)
    keywords=("sisae","matricula","inscrito","inscritos","inscripcion","inscripciones","alumno","alumnos","alumna","alumnas","estudiante","estudiantes")
    if not any(k in q for k in keywords): return None
    if any(k in q for k in ("curp","discapacidad","domicilio","telefono","correo","nombre completo")):
        return "Por privacidad, el Asistente no consulta ni devuelve CURP, datos de contacto, información médica ni expedientes individuales. Usa el módulo institucional autorizado para ese tipo de consulta."
    if re.search(r"\balumno\s+[a-z]",q) or re.search(r"\bestudiante\s+[a-z]",q):
        return "La búsqueda individual de personas debe realizarse desde **Auditoría SISAE**, que es el módulo autorizado para esa consulta. El Asistente no buscará nombres de alumnos en el chat ni enviará identificadores personales a Gemini."
    if any(k in q for k in ("como subir","como cargar","como importar","actualizar corte")):
        return "Para actualizar la fuente, utiliza **SISAE · Cortes** y carga una copia autorizada del ZIP. Esta conversación solo consulta el corte local disponible; no escribe en SISAE."
    path=_sisae_path(C)
    if not path.is_file():
        return "**Matrícula SISAE no verificada.** No encontré un ZIP local en las rutas de recursos disponibles. No sustituiré la matrícula por el número de grupos de Programación."
    try:
        ciclo,periodo=_ciclo_periodo_pregunta(q)
        snap=cargar_sisae_completo(path,ciclo,periodo)
    except Exception as exc:
        return f"**No pude verificar esta consulta SISAE** ({type(exc).__name__}). No presentaré otra métrica como sustituto. Revisa el ZIP, sus tablas y el periodo solicitado."
    groups=snap["grupos"]
    specialty=None
    detected_specialties=sorted({g["especialidad"] for g in groups if g.get("especialidad") and g["especialidad"]!="Sin catálogo ESP" and normalizar(g["especialidad"]) in q})
    if "especialidad" in q or detected_specialties:
        found=detected_specialties
        if len(found)==1: specialty=found[0]
        elif len(found)>1: return "La pregunta coincide con más de una especialidad. Especifica el nombre exacto del catálogo SISAE."
        else: return "No pude identificar una especialidad exacta del catálogo ESP.DBF en la pregunta. Especifica su denominación."
        groups=[g for g in groups if g.get("especialidad")==specialty]
    stop_sisae={"cuantos","cuantas","alumnos","alumnas","inscritos","inscritas","inscripcion","inscripciones","sisae","docente","maestro","profesor","profesora","ciclo","periodo","especialidad","grupos","grupo","tiene","tienen","hay","total","matricula","de","del","la","el","en","para","con","por","un","una","que","los","las","curso","cursos","sobre","cuanto","cuanta","esta","este","durante","registrados","registradas"}
    teacher_terms=[t for t in set(q.split()) if len(t)>2 and t not in stop_sisae]
    if any(k in q for k in ("docente","profesor","maestro","imparte")):
        teacher_hits=[g for g in groups if g.get("docente") and all(any(t in normalizar(g["docente"]).split() for _ in [0]) for t in teacher_terms)] if teacher_terms else []
        if teacher_terms and teacher_hits: groups=teacher_hits
        elif teacher_terms: return "No encontré coincidencia inequívoca del docente en `DOC_NOM` de SISAE."
        else: return "Escribe el nombre o apellido del docente que deseas consultar."
    course_terms=[t for t in teacher_terms if t not in ("curso","cursos","imparte")]
    if any(k in q for k in ("menos de 10","menores de 10","de 1 a 9","entre 1 y 9")):
        subset=[g for g in groups if 1<=g["inscripciones"]<=9]
        metric=f"**{len(subset)} grupos** con entre 1 y 9 inscripciones"
    elif any(k in q for k in ("sin inscripcion","sin inscritos","sin matricula","cero inscritos","sin alumnos")):
        subset=[g for g in groups if g["inscripciones"]==0]
        metric=f"**{len(subset)} grupos** sin inscripciones en el corte"
    elif any(k in q for k in ("grupo","grupos","cursos con inscrip")) and not any(k in q for k in ("alumnos","alumnas","inscritos","matricula","inscripcion")):
        subset=[g for g in groups if g["inscripciones"]>0]
        metric=f"**{len(subset)} grupos** con inscripciones"
    elif any(k in q for k in ("curso","cursos de","imparte","grupo")) and teacher_terms:
        search_terms=[t for t in teacher_terms if t not in ("inscrito","inscritos","alumno","alumnos","matricula","sisae","periodo","ciclo","total","cuantos","cuantas")]
        subset=[g for g in groups if search_terms and all(t in normalizar(g["curso"]) or t in normalizar(g["docente"]) for t in search_terms)]
        if not subset:
            return "No encontré el curso/grupo solicitado en este corte SISAE. No sustituiré el resultado por el total general."
        metric=f"**{len(subset)} grupos/cursos** coincidentes"
    else:
        subset=groups
        total_ins=sum(g["inscripciones"] for g in subset)
        people=set()
        people_count=None
        if specialty and not any(k in q for k in ("docente","profesor","maestro","imparte")):
            people_count=snap.get("personas_unicas_por_especialidad",{}).get(specialty)
        elif len(subset)==len(groups):
            people_count=snap["personas_unicas"]
        elif any(k in q for k in ("docente","profesor","maestro","imparte")):
            teacher_names={g.get("docente") for g in subset if g.get("docente")}
            if len(teacher_names)==1:
                people_count=snap.get("personas_unicas_por_docente",{}).get(next(iter(teacher_names)))
        if people_count is None:
            metric=f"**{total_ins} inscripciones**. No calculé personas únicas para este filtro porque podría duplicar a una persona inscrita en varios grupos."
        else:
            metric=f"**{total_ins} inscripciones** y **{people_count} personas únicas**"
    lines=[f"### SISAE · ciclo {ciclo} · periodo de inscripción {periodo or 'todos los disponibles'}"]
    if specialty: lines.append(f"Especialidad: **{specialty}**.")
    lines.append(metric+".")
    if any(x in q for x in ("total","cuantos","cuantas","alumnos","matricula","inscripciones")):
        subset2=groups
        lines.append(f"Grupos con inscripciones: **{sum(1 for g in subset2 if g['inscripciones']>0)}**; sin inscripciones: **{sum(1 for g in subset2 if g['inscripciones']==0)}**.")
        lines.append(f"Grupos con 1–9 inscripciones: **{sum(1 for g in subset2 if 1<=g['inscripciones']<=9)}**; con 10 o más: **{sum(1 for g in subset2 if g['inscripciones']>=10)}**.")
    if any(x in q for x in ("lista","cuales","muestra","detalle","detalla","quienes")):
        for g in subset[:35]:
            lines.append(f"- {g['curso']} · {g.get('docente') or 'Docente no registrado'} · {g['inscripciones']} inscripciones · {g.get('horario')}")
    lines.append(f"Conciliación INSCRIPCION ↔ LISTAS: **{snap['listas_estado']}**. Solo se sumó INSCRIPCION.DBF; LISTAS se usa como comprobación y LISTAS01 se excluye.")
    if snap["inscripciones_repetidas"]: lines.append(f"Advertencia: {snap['inscripciones_repetidas']} filas repetidas en INSCRIPCION.DBF no se sumaron.")
    if snap["inscripciones_sin_id"]: lines.append(f"Advertencia: {snap['inscripciones_sin_id']} inscripciones sin ID interno; revisión requerida.")
    if snap["listas_repetidas"]: lines.append(f"LISTAS.DBF contiene {snap['listas_repetidas']} filas reiteradas; no se sumaron.")
    if snap["solo_inscripcion"] or snap["solo_listas"]: lines.append(f"Diferencias: {snap['solo_inscripcion']} solo en INSCRIPCION y {snap['solo_listas']} solo en LISTAS.")
    corte=f"nombre de archivo: {snap['fecha_nominal']} (no prueba fecha/hora de exportación)" if snap["fecha_nominal"] else "fecha de exportación no identificada en el nombre del ZIP"
    lines.append("\n**Corte:** "+corte+". Es una copia local, no una consulta en vivo.")
    lines.append(f"**Fuente:** {snap['ruta_nombre']} · {', '.join(snap['tablas_leidas'])} · {_ahora_iso()}.")
    return "\n".join(lines)

def _DEF_MOSTRAR_calendario(pregunta):
    q=normalizar(pregunta)
    keys=("agenda","calendario","pendientes","pendiente","atrasadas","atrasados","vencidos","vencidas","esta semana","hoy","mañana","prioridad","urgente","que sigue","tengo que hacer")
    if not any(k in q for k in keys): return None
    
    try: rows=consultar_calendario_registros()
    except Exception as exc: return f"No pude consultar Mi Calendario: {type(exc).__name__}: {exc}."
    
    hoy=_hoy(); today=hoy.isoformat()
    
    target_date = _parsear_fecha_pregunta(q)

    if target_date:
        rows = [r for r in rows if target_date in str(r.get("fecha_inicio")) or target_date in str(r.get("fecha_limite")) or target_date in str(r.get("fecha_fin"))]
        title = f"Actividades del {target_date}"
        if not rows: return f"### {title}\nNo tienes actividades registradas para esa fecha en tu agenda."
        lines=["### "+title]
        for r in rows:
            lines.append(f"- **{r.get('titulo')}** · prioridad {r.get('prioridad') or 'Media'}. {_motivo(r)}")
        return "\n".join(lines)

    end=(hoy+timedelta(days=7)).isoformat()
    if "atras" in q or "vencid" in q: rows=[r for r in rows if (r.get("fecha_limite") or r.get("fecha_fin") or r.get("fecha_inicio") or "9999")<today]; title="Actividades atrasadas"
    elif "hoy" in q: rows=[r for r in rows if r.get("fecha_inicio")==today or r.get("fecha_limite")==today]; title="Actividades de hoy"
    elif "semana" in q or "proxim" in q: rows=[r for r in rows if today<=(r.get("fecha_limite") or r.get("fecha_inicio") or "9999")<=end]; title="Próximos siete días"
    else: rows=sorted(rows,key=_score,reverse=True); title="Pendientes ordenados por atención recomendada"
    
    if not rows: return f"### {title}\nNo encontré actividades que coincidan con este criterio. La conexión con el calendario sí fue verificada."
    lines=["### "+title]
    for r in rows[:20]:
        ref=r.get("fecha_limite") or r.get("fecha_fin") or r.get("fecha_inicio") or "Sin fecha"
        lines.append(f"- **{r.get('titulo')}** · prioridad {r.get('prioridad') or 'Media'} · referencia {ref}. {_motivo(r)} Módulo: {r.get('modulo_vinculado') or 'Ninguno'}.")
    lines.append("\nFuente: Mi Calendario · SQLite compartido · consulta local. El orden es orientativo; no cambia fechas oficiales ni estados de los trámites.")
    return "\n".join(lines)

def _simular_cambio(pregunta, data, C):
    q=normalizar(pregunta)
    change=any(w in q for w in ("si cambia","si cambiara","cambiar","mover","aplazar","extender","reprogramar","terminara","fecha nueva","simular","que pasa si","que pasaria"))
    date_matches=re.findall(r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b",pregunta)
    relative_days=None
    if not date_matches:
        if any(x in q for x in ("una semana despues","una semana mas tarde","una semana adicional","7 dias despues","siete dias despues")): relative_days=7
        elif "dos semanas despues" in q or "14 dias despues" in q: relative_days=14
        else:
            m_days=re.search(r"\b(\d{1,2})\s+dias?\s+(?:despues|mas tarde|adicionales)\b",q)
            if m_days: relative_days=int(m_days.group(1))
    if not (change and (date_matches or relative_days is not None) and any(w in q for w in ("fecha","termino","fin","terminar","termina","cierre"))): return None
    if len(date_matches)>1: return "Para simular, indica solo la fecha nueva de término; no incluyas fechas adicionales."
    new=_fecha_iso(date_matches[0]) if date_matches else None
    if date_matches and not new: return "La fecha propuesta no es válida. Usa DD/MM/AAAA o AAAA-MM-DD."
    groups=_grupos_data(data)
    hits=_buscar_grupos(re.sub(r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b"," ",pregunta),groups)
    mem=st.session_state.get("atrio_contexto",{}) if st is not None else {}
    if not hits and mem.get("group_ids"):
        ids=set(map(str,mem["group_ids"]))
        hits=[g for g in groups if str(g.get("id")) in ids]
    if len(hits)!=1:
        if hits:
            st.session_state["atrio_contexto"]={"group_ids":[g.get("id") for g in hits if g.get("id") is not None]}
            return "Identifiqué varios grupos. Selecciona uno por número y repite la fecha:\n\n"+"\n".join(f"{i}. {_ficha_grupo(g)}" for i,g in enumerate(hits[:20],1))
        return "No pude identificar un grupo único en Programación. Indica docente y curso, o selecciona el grupo en ATRIO. No simularé sobre un registro ambiguo."
    g=hits[0]
    start=_fecha_iso(g.get("inicio")); old=_fecha_iso(g.get("fin"))
    if not start or not old: return "No puedo simular: el grupo no tiene fecha de inicio y término legibles en la fuente recibida."
    if relative_days is not None:
        new=(datetime.strptime(old,"%Y-%m-%d").date()+timedelta(days=relative_days)).isoformat()
    if not new: return "Indica una fecha concreta o un plazo inequívoco como «una semana después»."
    if new<start: return "La fecha propuesta es anterior al inicio del grupo. No es válida para esta simulación."
    new_date=datetime.strptime(new,"%Y-%m-%d").date(); old_date=datetime.strptime(old,"%Y-%m-%d").date()
    if new==old: return f"El grupo ya tiene término {old}. No hay variación que simular."
    from_period=((old_date.year if old_date.month>=7 else old_date.year-1),(old_date.month-7)%12//3+1)
    to_period=((new_date.year if new_date.month>=7 else new_date.year-1),(new_date.month-7)%12//3+1)
    lines=["### Simulación de reprogramación · solo lectura",_ficha_grupo(g),
           f"Término actual: **{old}** → propuesto: **{new}** ({(new_date-old_date).days:+d} días naturales)."]
    if from_period!=to_period: lines.append(f"La fecha propuesta cruza el periodo calendario P{from_period[1]} → P{to_period[1]}. La matrícula SISAE debe conservar el periodo de inscripción original del grupo; no se duplica automáticamente.")
    motor=getattr(C,"motor",None) if C is not None else None
    res=getattr(C,"RES",None) if C is not None else None
    if motor and res and (Path(res)/"DIAS_SIN_CLASE.json").is_file():
        try:
            report=motor.revisar_calendario(dict(g.get("_original",{}),fin=new),res)
            lines.append("Calendario/días sin clase: "+str(report))
        except Exception as exc: lines.append(f"Calendario: no se pudo validar con el motor ({type(exc).__name__}).")
    else: lines.append("Calendario y horas: pendientes de validar con el calendario de días sin clase y horario real del grupo. No calculé horas estimadas.")
    status=_consulta_status([g],C)
    if normalizar(g.get("tipo"))=="regular":
        lines.append("PEA: no aplicable para grupos Regular. MCE se revisa de forma independiente.")
    if status and status[0]:
        _g,s=status[0][0]
        lines.append(f"Estado confirmado por C.status: PEA={s.get('doc','Sin verificar')} · MCE={s.get('mce','Sin verificar')}.")
    else: lines.append("PEA/MCE: estado no consultado o no disponible para este grupo.")
    inv=_pea_inventory([g.get("id")]) if g.get("id") is not None else {"estado":"no_consultado"}
    if inv.get("estado") in ("consultado","consultado_con_fuentes_faltantes"):
        lines.append(f"Mis PEA: {inv['versiones_generadas']} versiones generadas/adaptadas vinculadas a este identificador de grupo; fuentes faltantes: {', '.join(inv['fuentes_no_disponibles']) or 'ninguna detectada'}.")
    else: lines.append("Mis PEA: no fue posible consultar el inventario documental vinculado.")
    try:
        s_path=_sisae_path(C)
        if s_path.is_file():
            ciclo=os.getenv("ATRIO_CICLO_ACTUAL","2026-2027")
            snap=cargar_sisae_completo(s_path,ciclo,None)
            cand=[x for x in snap["grupos"] if normalizar(x.get("curso"))==normalizar(g.get("nombre")) and normalizar(x.get("docente"))==normalizar(g.get("hoja")) and x.get("inicio")==start]
            if cand:
                lines.append(f"SISAE: {len(cand)} candidato(s) por curso, docente e inicio. Se debe contrastar el horario antes de vincular una clave.")
                for x in cand[:5]: lines.append(f"- {x['curso']} · {x['docente']} · {x['horario']} · {x['inscripciones']} inscripciones.")
            else: lines.append("SISAE: no se encontró coincidencia exacta de curso, docente e inicio en el corte. No demuestra por sí solo falta de captura.")
        else: lines.append("SISAE: no hay un corte local disponible para cotejar.")
    except Exception as exc: lines.append(f"SISAE: no se pudo cotejar esta simulación ({type(exc).__name__}).")
    lines.append("No se modificó Programación, SISAE, PEA, MCE, calendario ni documentos. Esto es una simulación; las constancias y listas emitidas deben revisarse por separado.")
    return "\n".join(lines)

def _DEF_MOSTRAR_capacidades(data, C):
    diag=diagnostico_calendario(); groups=_grupos_data(data)
    key,_model=obtener_credenciales(); gactive=bool(GEMINI_DISPONIBLE and key)
    word_ready=bool(DOCX_DISPONIBLE and getattr(C,"RES",None) and (Path(C.RES)/"MEMBRETE.docx").is_file())
    lines=[
      "## Asistente Virtual ATRIO · capacidades actuales",
      "Puedo consultar datos locales de ATRIO y ayudarte con organización y redacción. Las cifras se calculan desde las fuentes disponibles; si una fuente falta o falla, lo indicaré en lugar de inventar un resultado.",
      "",
      "### Consultas locales",
      "- **Mi Calendario:** consultar actividades activas, vencidas y próximas; ordenar pendientes por fecha límite y prioridad.",
      "- **Programación:** contar grupos del contexto recibido por el panel y buscar cursos por docente, modalidad, nombre y fechas.",
      "- **Mis PEA:** inventariar registros de las tablas locales disponibles, separando originales subidos, versiones generadas/adaptadas e históricos.",
      "- **Estados PEA/MCE:** leer `C.status(id)` cuando exista; ‘Sin verificar’ no se cuenta como pendiente confirmado.",
      "- **SISAE:** leer el ZIP local, filtrar por ciclo/periodo y separar inscripciones de personas únicas. No devuelve identificadores ni expedientes.",
      "- **Documentación Local:** búsqueda directa en el índice FTS5 de ATRIO sin utilizar bases de datos vectoriales en la nube.",
      "",
      "### Organización y documentos",
      "- **Listas de Asistencia (ACM):** generar el formato oficial de asistencia en Excel por quincenas para cursos de Acciones Móviles a partir de tu plantilla institucional.",
      "- **Oficios ACM:** generar los documentos de Presentación, Vinculación o Asignación para cursos ACM, a partir de las plantillas oficiales.",
      "- **Simulación:** analizar el impacto de cambiar la fecha de término de un grupo sin modificar Programación, SISAE, PEA ni calendario.",
      "- **Calendario:** preparar actividades nuevas para que las revises, edites o descartes. Solo se guardan cuando autorizas expresamente; se registra auditoría.",
      "- **Redacción:** preparar borradores institucionales y, si están disponibles las dependencias y la plantilla, generar Word con membrete.",
      "- **Adaptación PEA:** manipulación de PEA históricos a través de PyMuPDF (fitz) de forma local.",
      "",
      "### Conexiones detectadas en esta sesión",
      ("- **Calendario:** " + f"{diag['activos']} activas, {diag['atrasados']} atrasadas y {diag['proximos']} con vencimiento en siete días." if not diag.get("error") else "- **Calendario:** no se pudo verificar la base compartida: " + diag["error"]),
      f"- **Programación:** {len(groups)} registros recibidos por `panel(data, C)` en esta llamada; no equivale necesariamente a todo el padrón anual.",
      "- **Gemini:** " + ("biblioteca y clave detectadas; los datos personales y nombres se anonimizan." if gactive else "sin conexión completa detectada; las consultas locales siguen disponibles."),
      "- **Word:** " + ("plantilla y dependencia disponibles." if word_ready else "descarga con membrete no confirmada; requiere `python-docx` y `MEMBRETE.docx`."),
      "- **PyMuPDF:** " + ("disponible para adaptación de PDFs." if PYMUPDF_DISPONIBLE else "no disponible en este entorno."),
      "- **Revisor y Control escolar:** solo se consultan en detalle si hay un lector real registrado en `C.ATRIO_ASISTENTE_LECTORES`; no se inventan dictámenes ni estados.",
      "",
      "### Límites importantes",
      "- No modifico ni doy por concluidos trámites oficiales de SISAE, Programación, PEA, Revisor, MCE o Control escolar.",
      "- No edito, cancelo ni reprogramo eventos existentes desde el chat; el guardado autorizado crea actividades nuevas.",
      "- Los recordatorios y repeticiones se almacenan como opciones del evento; este módulo no envía notificaciones ni ejecuta repeticiones automáticas.",
      "- SISAE se consulta localmente; sus registros e identificadores no se envían a Gemini.",
      "",
      "Puedes empezar con: «¿Cuántos grupos hay en Programación?», «¿Cuántos docentes distintos aparecen?», «¿Qué cursos imparte…?», «¿Cuántas inscripciones hay en SISAE?», «¿Qué pendientes debo atender primero?», «Genera la asistencia de...», «Genera el oficio de...», «¿Cuándo cierra el periodo?» o «Simula que este grupo termina una semana después».",
      "",
      "**Tú conservas el control:** ninguna actividad nueva se guarda hasta que la revises y autorices expresamente."
    ]
    return "\n".join(lines)

def _DEF_MOSTRAR_procedimientos(pregunta):
    q=normalizar(pregunta)
    if any(k in q for k in ("respaldo", "backup", "respaldar", "copia de seguridad")):
        return "### Respaldos\nPara resguardar tu información, ve a la pestaña **Respaldos** en el menú lateral. Ahí puedes generar un archivo ZIP con la base de datos SQLite y todos los documentos generados. Te recomiendo hacerlo antes de cualquier actualización del sistema."
    if any(k in q for k in ("pea historico","pea historicos","ciclo anterior","ciclos anteriores")) and any(k in q for k in ("como","donde","hacer","preparar","adaptar","generar","usar")):
        return "Para un PEA de un ciclo anterior, entra en **PEA históricos**. Desde ahí se consulta el expediente del ciclo correspondiente y se prepara una nueva versión o adaptación. Los resultados se conservan en **Mis PEA → Históricos**. No se modifican Programación ni los PEA del ciclo vigente. Confirma siempre el ciclo y el documento de origen antes de generar una copia."
    if "repositorio" in q and any(k in q for k in ("pea","pdf","adaptar","preparar","como","curso")) and not any(k in q for k in ("cuantos","cuantas","total","matricula")):
        return "Para un curso de **Repositorio del ciclo actual**, entra en **Preparar PEA**, selecciona el docente y el curso correspondiente, adjunta el PDF original y revisa los datos administrativos y la adaptación antes de guardar. Conserva el PDF original y la copia adaptada en Mis PEA. La existencia de un documento no significa que haya sido revisado ni subido a MCE."
    if "programacion" in q and any(k in q for k in ("corregir","correccion","cambiar","actualizar excel","guardar cambio")):
        return "Las propuestas de corrección de **Programación** no sustituyen por sí solas el Excel fuente. Antes de cargar una copia corregida, revisa el cambio, conserva un respaldo y valida que el grupo siga vinculado a su registro correspondiente. Un cambio de nombre o fechas no debe crear un identificador nuevo ni perder la trazabilidad del grupo. Puedes actualizar el archivo en **Ajustes -> Recursos**."
    if "sisae" in q and any(k in q for k in ("como cargar","como subir","importar","actualizar corte","nuevo corte")):
        return "Para actualizar la fuente, utiliza **SISAE · Cortes** y registra una copia autorizada del ZIP con su ciclo, periodo, versión y fecha nominal. El Asistente solo lee el ZIP local y no escribe de regreso a SISAE. La ausencia de un grupo futuro en el corte no demuestra por sí sola una omisión de captura."
    if "mce" in q and any(k in q for k in ("como","excel","subir","enviar","formato")):
        return "El archivo de **Excel para MCE** se prepara desde el PEA correspondiente y se revisa antes de utilizarlo en el proceso institucional. La exportación del Excel no equivale a que el documento se haya subido, recibido, autorizado o validado en MCE. Esos estados solo deben mostrarse cuando exista confirmación registrada."
    if "constancia" in q and any(k in q for k in ("como","sacar","generar","imprimir","crear")):
        return "Para generar constancias, ve al módulo **Constancias y folios** en el menú lateral. Ahí podrás registrar los datos del participante y generar el documento oficial con su folio correspondiente."
    if "control escolar" in q and any(k in q for k in ("como","inscripcion","reingreso","numero de control","captura")):
        return "En **Control escolar**, verifica primero si se trata de nuevo ingreso o reingreso. Para un reingreso debe recuperarse el número de control ya asignado en SISAE; no se debe crear otro por falta de credencial. El Asistente no captura ni modifica SISAE: puede ayudarte a revisar información agregada y a organizar el seguimiento."
    return None

def _consultar_rag_local(pregunta):
    if not Path(DB_ATRIO).exists(): return None
    try:
        with sqlite3.connect(f"file:{DB_ATRIO}?mode=ro", uri=True) as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='docs_fts'")
            if not cur.fetchone(): return None
            
            terminos = " OR ".join([t for t in normalizar(pregunta).split() if len(t) > 2])
            if not terminos: return None
            
            res = conn.execute(
                "SELECT titulo, snippet(docs_fts, -1, '**', '**', '...', 10) as extracto "
                "FROM docs_fts WHERE docs_fts MATCH ? ORDER BY rank LIMIT 3", 
                (terminos,)
            ).fetchall()
            
            if res:
                return "### Documentación Operativa ATRIO (Búsqueda Local)\n" + "\n".join([f"- **{r[0]}**: {r[1]}" for r in res]) + "\n\nFuente: SQLite FTS5 Local (No requiere internet)."
    except Exception: pass
    return None

def responder_local(pregunta, data=None, C=None):
    q=normalizar(pregunta)
    writing = any(x in q for x in ("redacta", "redactar", "oficio", "convocatoria", "memorandum", "carta", "circular"))
    create_calendar = any(x in q for x in ("agendar", "agenda una actividad", "agenda esto", "crear actividad", "crea una actividad", "anota", "propone una actividad", "propon una actividad", "distribuye tareas", "organiza mis tareas"))
    if writing or create_calendar:
        return None
    if _es_saludo(pregunta):
        return "¡Hola! ¿Qué necesitas revisar hoy en ATRIO? Puedo ayudarte con Programación, Mis PEA, SISAE, seguimiento y Mi Calendario."
    if _es_pregunta_capacidades(q):
        return _DEF_MOSTRAR_capacidades(data,C)
    
    tiempos = _DEF_MOSTRAR_tiempos(pregunta)
    if tiempos is not None: return tiempos

    sim=_simular_cambio(pregunta,data,C)
    if sim is not None: return sim
    
    procedure=_DEF_MOSTRAR_procedimientos(pregunta)
    if procedure is not None: return procedure
    
    for func,args in ((_DEF_MOSTRAR_sisae,(pregunta,C)),(_DEF_MOSTRAR_pea,(pregunta,data,C)),(_DEF_MOSTRAR_calendario,(pregunta,)),(_DEF_MOSTRAR_programacion,(pregunta,data))):
        try:
            ans=func(*args)
            if ans is not None: return ans
        except Exception as exc:
            return f"No pude completar la consulta local ({type(exc).__name__}). No sustituiré el dato solicitado por otra métrica."
    
    qn=normalizar(pregunta)
    source=None
    if "revisor" in qn: source="revisor"
    elif "control escolar" in qn: source="control_escolar"
    elif "documento" in qn or "oficio" in qn or "constancia" in qn: source="documentos"
    elif "mce" in qn: source="mce"
    if source:
        readers=getattr(C,"ATRIO_ASISTENTE_LECTORES",{}) if C is not None else {}
        reader=readers.get(source) if isinstance(readers,dict) else None
        if callable(reader):
            try:
                val=reader()
                return f"### {source.replace('_',' ').title()}\n"+json.dumps(_minimizar_para_ia(val),ensure_ascii=False,indent=2,default=str)[:8000]
            except Exception as exc: return f"El lector de {source} devolvió un error ({type(exc).__name__}). No se considera un resultado vacío."
        return f"No hay un lector real configurado para **{source.replace('_',' ').title()}** en esta instalación. No puedo confirmar ese estado."
    
    rag_resp = _consultar_rag_local(pregunta)
    if rag_resp:
        return rag_resp
        
    return None

def responder_con_gemini(pregunta, data, C, historial):
    api_key,modelo=obtener_credenciales()
    if not GEMINI_DISPONIBLE or not api_key: return None,False
    try:
        fecha=_hoy().strftime("%d/%m/%Y")
        context=[]
        for m in (historial or [])[-3:]:
            role="Usuaria" if m.get("role")=="user" else "Asistente"
            content=_sanear_texto_para_ia(str(m.get("content", "")))[:900]
            context.append(f"{role}: {content}")
        agenda=""
        q=normalizar(pregunta)
        if any(w in q for w in ("agendar","agenda","calendario","organiza","distribuye","pendientes")):
            try: agenda=consultar_calendario_para_ia()[:9000]
            except Exception as exc: agenda="Calendario no consultable: "+type(exc).__name__+". No asumir que está vacío."
        prompt=f"""
{SYSTEM_PROMPT}
Fecha local: {fecha}; zona America/Mexico_City.

Si la usuaria solicita proponer actividades nuevas, incluye al final ATRIO_ACCIONES_JSON con una propuesta revisable. Usa null para cualquier fecha no confirmada. No incluyas acciones destructivas ni cambios de registros existentes.
Formato:
<ATRIO_ACCIONES_JSON>
{{"accion":"proponer_actividades","fuente":{{"origen":"RECOMENDACION_GEMINI","fecha_corte":"{_ahora_iso()}","confianza":"media"}},"requiere_autorizacion":true,"actividades":[{{"titulo":"","descripcion":"","tipo":"Tarea","fecha_inicio":null,"fecha_fin":null,"fecha_limite":null,"hora_inicio":null,"hora_fin":null,"todo_el_dia":true,"recordatorio":"Ninguno","repeticion":"No se repite","categoria":"Seguimiento de trámites","prioridad":"Media","modulo_vinculado":"Mi Calendario","lugar":"","responsable":""}}]}}
</ATRIO_ACCIONES_JSON>

Solo crea el bloque cuando se pida expresamente agendar/organizar. No inventes fechas ni dupliques actividades existentes.
Categorías válidas: {', '.join(n for n,_ in CATEGORIAS_DEFAULT)}.
Módulos válidos: {', '.join(MODULOS_ATRIO)}.

HISTORIAL RECIENTE:
{chr(10).join(context)}

AGENDA (solo si se consultó):
{agenda or 'No consultada para esta solicitud.'}

PETICIÓN:
{_sanear_texto_para_ia(pregunta)}
"""
        client=genai.Client(api_key=api_key)
        response=client.models.generate_content(model=modelo,contents=prompt)
        text=getattr(response,"text",None) or ""
        if not text.strip(): return "Gemini no devolvió contenido. No se realizó ningún cambio.",False
        
        text, proposal = _extraer_acciones(text)
        text, asistencia = _extraer_asistencia(text)
        text, oficio_acm = _extraer_oficio_acm(text)
        
        if proposal:
            st.session_state["atrio_propuesta_ia"]=proposal
        else:
            st.session_state.pop("atrio_propuesta_ia",None)
            
        if asistencia:
            st.session_state["atrio_asistencia_ia"] = asistencia
        else:
            st.session_state.pop("atrio_asistencia_ia", None)

        if oficio_acm:
            st.session_state["atrio_oficio_acm_ia"] = oficio_acm
        else:
            st.session_state.pop("atrio_oficio_acm_ia", None)

        return text,True
    except Exception as exc:
        return f"No se pudo completar la solicitud con Gemini ({type(exc).__name__}).",False

def _extraer_acciones(texto):
    patron=r"<ATRIO_ACCIONES_JSON>\s*(.*?)\s*</ATRIO_ACCIONES_JSON>"
    match=re.search(patron,texto or "",flags=re.I|re.S)
    if not match: return texto,None
    try: proposal=json.loads(match.group(1).strip())
    except Exception:
        clean=(texto[:match.start()]+texto[match.end():]).strip()
        return clean+"\n\nNo pude interpretar la propuesta estructurada; no se guardó ningún cambio.",None
    clean=(texto[:match.start()]+texto[match.end():]).strip()
    if not isinstance(proposal,dict) or proposal.get("accion")!="proponer_actividades": return clean,None
    activities=proposal.get("actividades",[])
    if not isinstance(activities,list): return clean,None
    source=proposal.get("fuente") if isinstance(proposal.get("fuente"),dict) else {}
    origin=str(source.get("origen") or "RECOMENDACION_GEMINI").upper()
    if origin not in ("ATRIO_DATOS","DOCUMENTO_INSTITUCIONAL","RECOMENDACION_GEMINI","MIXTO"): origin="RECOMENDACION_GEMINI"
    proposal["fuente"]={"origen":origin,"fecha_corte":str(source.get("fecha_corte") or _ahora_iso()),"confianza":str(source.get("confianza") or "media").lower()}
    proposal["requiere_autorizacion"]=True
    proposal["actividades"]=[x for x in activities if isinstance(x,dict)][:10]
    return clean,proposal if proposal["actividades"] else None

def _extraer_asistencia(texto):
    patron = r"<ATRIO_ASISTENCIA_JSON>\s*(.*?)\s*</ATRIO_ASISTENCIA_JSON>"
    match = re.search(patron, texto or "", flags=re.I|re.S)
    if not match: 
        return texto, None
    try: 
        req = json.loads(match.group(1).strip())
    except Exception:
        clean = (texto[:match.start()] + texto[match.end():]).strip()
        return clean, None
    clean = (texto[:match.start()] + texto[match.end():]).strip()
    if isinstance(req, dict) and req.get("accion") == "generar_asistencia":
        return clean, req
    return clean, None

def _extraer_oficio_acm(texto):
    patron = r"<ATRIO_OFICIO_ACM_JSON>\s*(.*?)\s*</ATRIO_OFICIO_ACM_JSON>"
    match = re.search(patron, texto or "", flags=re.I|re.S)
    if not match: 
        return texto, None
    try: 
        req = json.loads(match.group(1).strip())
    except Exception:
        clean = (texto[:match.start()] + texto[match.end():]).strip()
        return clean, None
    clean = (texto[:match.start()] + texto[match.end():]).strip()
    if isinstance(req, dict) and req.get("accion") == "generar_oficio_acm":
        return clean, req
    return clean, None

def cargar_historial():
    path=Path(HISTORIAL_PATH) if HISTORIAL_PATH else Path(__file__).resolve().parent/"datos"/"chat_history.json"
    try:
        if path.is_file() and not path.is_symlink():
            data=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data,list):
                valid=[x for x in data if isinstance(x,dict) and x.get("role") in ("user","assistant") and isinstance(x.get("content"),str)]
                return valid[-30:]
    except Exception: pass
    return [{"role":"assistant","content":"¡Hola! Soy el Asistente Virtual de ATRIO. Puedo consultar Programación, Mis PEA, SISAE y Mi Calendario, preparar simulaciones y redactar borradores para tu revisión."}]

def guardar_historial(historial):
    path=Path(HISTORIAL_PATH) if HISTORIAL_PATH else Path(__file__).resolve().parent/"datos"/"chat_history.json"
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        clean=[{"role":m.get("role"),"content":str(m.get("content",""))[:6000]} for m in historial[-30:] if m.get("role") in ("user","assistant")]
        temp=path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(clean,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(temp,path)
        return True
    except Exception: return False

def _diagnostico_gemini():
    key,model=obtener_credenciales()
    if not key: return "No hay clave Gemini configurada. Las consultas locales continúan disponibles.",[]
    try:
        import urllib.request, urllib.error
        req=urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=100",headers={"x-goog-api-key":key})
        with urllib.request.urlopen(req,timeout=12) as resp: payload=json.loads(resp.read(500000).decode("utf-8"))
        models=[x.get("name","").removeprefix("models/") for x in payload.get("models",[]) if "generateContent" in x.get("supportedGenerationMethods",[])]
        chosen=model.removeprefix("models/")
        if chosen not in models: return f"La clave responde, pero el modelo {chosen} no está habilitado. Selecciona uno de la lista.",models[:20]
        return f"Conexión y modelo configurado disponibles: {chosen}. Esto no garantiza cuota suficiente.",models[:20]
    except Exception as exc: return f"No se pudo comprobar Gemini ({type(exc).__name__}).",[]

def _mostrar_propuesta():
    propuesta=st.session_state.get("atrio_propuesta_ia")
    if not isinstance(propuesta,dict): return
    activities=propuesta.get("actividades",[])[:10]
    if not activities: return
    st.markdown("---\n### ✨ Propuesta del Asistente Virtual")
    source=propuesta.get("fuente") or {}
    if source:
        st.caption(f"Fuente: {source.get('origen','RECOMENDACION_GEMINI')} · al {source.get('fecha_corte','')} · confianza {source.get('confianza','media')}")
    st.caption("Revisa los datos. Nada se guardará hasta que autorices el botón final.")
    try:
        _asegurar_calendario()
        with _conexion() as conn:
            cats=[r["nombre"] for r in conn.execute("SELECT nombre FROM cal_categorias WHERE COALESCE(activa,1)=1 ORDER BY nombre").fetchall()]
        cats=cats or [n for n,_ in CATEGORIAS_DEFAULT]
    except Exception as exc:
        st.error(f"No pude leer las categorías del calendario: {type(exc).__name__}: {exc}")
        return
    signature=hashlib.sha256(json.dumps(propuesta,ensure_ascii=False,sort_keys=True).encode("utf-8")).hexdigest()[:12]
    values=[]
    with st.form(f"atrio_propuesta_form_{signature}"):
        for i,item in enumerate(activities):
            st.markdown(f"**Actividad {i+1}**")
            c1,c2=st.columns([2,1])
            with c1: title=st.text_input("Nombre de la actividad",value=str(item.get("titulo") or ""),key=f"av_t_{signature}_{i}")
            with c2:
                p0=item.get("prioridad") if item.get("prioridad") in PRIORIDADES else "Media"
                priority=st.selectbox("Prioridad",PRIORIDADES,index=PRIORIDADES.index(p0),key=f"av_p_{signature}_{i}")
            start_original=_fecha_iso(item.get("fecha_inicio"))
            start_default=datetime.strptime(start_original,"%Y-%m-%d").date() if start_original else _hoy()
            c1,c2=st.columns([2,1])
            with c1: start=st.date_input("Fecha de inicio *",value=start_default,key=f"av_start_{signature}_{i}")
            with c2: confirmed=st.checkbox("Confirmo la fecha",value=bool(start_original),key=f"av_confirm_{signature}_{i}")
            end_original=_fecha_iso(item.get("fecha_fin")); due_original=_fecha_iso(item.get("fecha_limite"))
            c1,c2=st.columns(2)
            with c1:
                has_end=st.checkbox("Actividad de varios días",value=bool(end_original),key=f"av_hasend_{signature}_{i}")
                end=st.date_input("Fecha de término",value=datetime.strptime(end_original,"%Y-%m-%d").date() if end_original else start_default,disabled=not has_end,key=f"av_end_{signature}_{i}")
            with c2:
                has_due=st.checkbox("Tiene fecha límite",value=bool(due_original),key=f"av_hasdue_{signature}_{i}")
                due=st.date_input("Fecha límite",value=datetime.strptime(due_original,"%Y-%m-%d").date() if due_original else start_default,disabled=not has_due,key=f"av_due_{signature}_{i}")
            all_day=st.checkbox("Todo el día",value=bool(item.get("todo_el_dia",True)),key=f"av_allday_{signature}_{i}")
            start_time=end_time=None
            if not all_day:
                try: default_start=time.fromisoformat(str(item.get("hora_inicio") or "09:00"))
                except Exception: default_start=time(9,0)
                try: default_end=time.fromisoformat(str(item.get("hora_fin") or "10:00"))
                except Exception: default_end=time(10,0)
                c1,c2=st.columns(2)
                with c1: start_time=st.time_input("Hora de inicio",value=default_start,key=f"av_st_{signature}_{i}")
                with c2: end_time=st.time_input("Hora de término",value=default_end,key=f"av_et_{signature}_{i}")
            c1,c2,c3=st.columns(3)
            with c1:
                cat0=item.get("categoria") if item.get("categoria") in cats else cats[0]
                category=st.selectbox("Categoría",cats,index=cats.index(cat0),key=f"av_cat_{signature}_{i}")
            with c2:
                type0=item.get("tipo") if item.get("tipo") in TIPOS else "Tarea"
                typ=st.selectbox("Tipo",TIPOS,index=TIPOS.index(type0),key=f"av_type_{signature}_{i}")
            with c3:
                mod0=item.get("modulo_vinculado") if item.get("modulo_vinculado") in MODULOS_ATRIO else "Ninguno"
                module=st.selectbox("Módulo relacionado",MODULOS_ATRIO,index=MODULOS_ATRIO.index(mod0),key=f"av_module_{signature}_{i}")
            c1,c2=st.columns(2)
            with c1: place=st.text_input("Lugar",value=str(item.get("lugar") or ""),key=f"av_place_{signature}_{i}")
            with c2: responsible=st.text_input("Responsable",value=str(item.get("responsable") or ""),key=f"av_resp_{signature}_{i}")
            c1,c2=st.columns(2)
            with c1:
                r0=item.get("recordatorio") if item.get("recordatorio") in RECORDATORIOS else "Ninguno"
                reminder=st.selectbox("Recordatorio",RECORDATORIOS,index=RECORDATORIOS.index(r0),key=f"av_rem_{signature}_{i}")
            with c2:
                rep0=item.get("repeticion") if item.get("repeticion") in REPETICIONES else "No se repite"
                repeat=st.selectbox("Repetición",REPETICIONES,index=REPETICIONES.index(rep0),key=f"av_rep_{signature}_{i}")
            description=st.text_area("Descripción",value=str(item.get("descripcion") or ""),key=f"av_desc_{signature}_{i}")
            values.append({"titulo":title,"fecha_inicio":start,"fecha_confirmada":confirmed,"fecha_fin":end if has_end else None,"fecha_limite":due if has_due else None,"hora_inicio":start_time.strftime("%H:%M") if start_time else None,"hora_fin":end_time.strftime("%H:%M") if end_time else None,"todo_el_dia":all_day,"prioridad":priority,"categoria":category,"tipo":typ,"modulo_vinculado":module,"lugar":place,"responsable":responsible,"recordatorio":reminder,"repeticion":repeat,"descripcion":description})
            if i<len(activities)-1: st.divider()
        confirm=st.form_submit_button("Autorizar y guardar actividades",type="primary",use_container_width=True)
    discard=st.button("Descartar propuesta",key=f"av_discard_{signature}")
    if discard:
        try:
            _asegurar_calendario()
            with _conexion() as conn:
                _insertar_auditoria_conn(conn,"descartar_propuesta","propuesta_asistente",signature,propuesta,None,(source.get("origen") or "RECOMENDACION_GEMINI"),st.session_state.get("usuario") or "jefatura_capacitacion","descartado","La usuaria descartó la propuesta.")
        except Exception: pass
        st.session_state.pop("atrio_propuesta_ia",None); st.rerun()
    if confirm:
        errors=[]
        for i,item in enumerate(values,1):
            if not item["titulo"].strip(): errors.append(f"Actividad {i}: falta el nombre.")
            if not item["fecha_confirmada"]: errors.append(f"Actividad {i}: confirma la fecha de inicio.")
            a=_fecha_iso(item["fecha_inicio"]); b=_fecha_iso(item["fecha_fin"])
            if b and a and b<a: errors.append(f"Actividad {i}: la fecha de término es anterior al inicio.")
            if item["hora_inicio"] and item["hora_fin"] and item["hora_fin"]<=item["hora_inicio"]: errors.append(f"Actividad {i}: la hora final debe ser posterior a la inicial.")
        if errors:
            for error in errors: st.error(error)
        else:
            try:
                result=_guardar_propuestas_atomicas(values)
                st.session_state.pop("atrio_propuesta_ia",None)
                st.success(f"Actividades guardadas: {result['guardadas']}. Posibles duplicados omitidos: {result['duplicadas']}. Auditoría confirmada en la misma transacción.")
                st.toast('✅ Actividades guardadas en el calendario', icon='📅')
                st.rerun()
            except Exception as exc:
                st.error(f"No se guardó ninguna actividad del lote. La transacción se revirtió: {type(exc).__name__}: {exc}")

def _mostrar_boton_limpiar_chat():
    col_vacia, col_boton = st.columns([0.8, 0.2])
    with col_boton:
        if st.button("🗑️ Limpiar chat", use_container_width=True, help="Reiniciar la conversación actual"):
            st.session_state.chat_history = [
                {"role": "assistant", "content": "¡Hola! Conversación reiniciada. ¿En qué te puedo ayudar hoy?"}
            ]
            st.rerun()

def _mostrar_boton_limpiar_chat():
    col_vacia, col_boton = st.columns([0.8, 0.2])
    with col_boton:
        if st.button("🗑️ Limpiar chat", use_container_width=True, help="Reiniciar la conversación actual"):
            st.session_state.chat_history = [
                {"role": "assistant", "content": "¡Hola! Conversación reiniciada. ¿En qué te puedo ayudar hoy?"}
            ]
            st.rerun()

def panel(data, C):
    _configurar_rutas(C)
    _inyectar_estilos_asistente()
    diag = diagnostico_calendario()
    
    st.markdown("""
    <div style="background:linear-gradient(109deg,#f5d8df 0%,#efafc9 45%,#ed78ab 100%);border-radius:16px;padding:24px 26px;color:#21191d;margin-bottom:18px;">
      <h1 style="margin:0;font-family:Georgia,serif;font-size:32px">Asistente Virtual ATRIO</h1>
      <p style="margin:5px 0 0 0;font-family:Georgia,serif;opacity:.85">Programación, PEA, SISAE, Calendario y Redacción institucional.</p>
    </div>""", unsafe_allow_html=True)

    _mostrar_boton_limpiar_chat()

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "¡Hola! Soy el Asistente Virtual. Tus datos personales y nombres se envían protegidos a la nube. ¿En qué te ayudo hoy?"}
        ]

    for msg in st.session_state.chat_history:
        avatar = "🤖" if msg.get("role") == "assistant" else "👩‍💼"
        with st.chat_message(msg.get("role"), avatar=avatar):
            st.markdown(msg.get("content"))
    # --- NUEVO: ENTRADA DE VOZ PARA CELULAR ---
    st.markdown("##### 🎤 O dicta tu mensaje (ideal para celular):")
    audio_val = st.audio_input("Graba un mensaje de voz", key="voice_input")
    
    # Si el usuario grabó un audio, lo transcribimos y lo usamos como pregunta
    if audio_val:
        with st.spinner("Escuchando tu mensaje..."):
            try:
                api_key, modelo = obtener_credenciales()
                if api_key:
                    client = genai.Client(api_key=api_key)
                    # Enviamos el audio a Gemini
                    response = client.models.generate_content(
                        model=modelo,
                        contents=[
                            "Transcribe este audio en español. No agregues ninguna otra palabra, solo devuelve la transcripción exacta.",
                            genai.types.Part.from_bytes(data=audio_val.read(), mime_type="audio/wav")
                        ]
                    )
                    # Asignamos la transcripción a la variable 'pregunta'
                    pregunta = response.text.strip()
                    st.success(f"🎤 Dijiste: *\"{pregunta}\"*")
                else:
                    st.warning("No hay clave de Gemini configurada para transcribir voz.")
            except Exception as e:
                st.error(f"No se pudo procesar el audio: {e}")

    pregunta = st.chat_input("Consulta Programación, SISAE, calendario, dudas operativas o redacta...")
    if pregunta:
        st.session_state.chat_history.append({"role": "user", "content": pregunta})
        with st.chat_message("user", avatar="👩‍💼"):
            st.markdown(pregunta)
        
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Procesando de forma segura..."):
                # Restauramos la variable 'DEF_MOSTRAR' en lugar de DEF_MOSTRAR
                DEF_MOSTRAR = responder_local(pregunta, data, C)
                fuente_local = DEF_MOSTRAR is not None
                
                if not fuente_local:
                    texto, ok = responder_con_gemini(pregunta, data, C, st.session_state.chat_history[:-1])
                    if ok: DEF_MOSTRAR = texto
                    else: DEF_MOSTRAR = "No pude resolver esa solicitud de forma local, y Gemini no respondió o no está disponible."
                
                st.markdown(DEF_MOSTRAR)
                if fuente_local: st.caption(f"Fuente: consulta local ATRIO · {_ahora_iso()}")
                
                req_asistencia = st.session_state.pop("atrio_asistencia_ia", None)
                if req_asistencia:
                    resultado = acm_asistencia.generar_asistencia_para_ia(
                        data, C, 
                        docente=req_asistencia.get("docente", ""), 
                        curso=req_asistencia.get("curso", ""), 
                        institucion=req_asistencia.get("institucion", "")
                    )
                    if resultado.get("status") == "ok":
                        st.success(resultado["mensaje"])
                        st.download_button(
                            "⬇️ Descargar Excel de Asistencia", 
                            data=resultado["bytes"], 
                            file_name=resultado["filename"], 
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                            key=f"dl_asist_{datetime.now().timestamp()}"
                        )
                    else:
                        st.error(resultado.get("mensaje"))

                req_oficio = st.session_state.pop("atrio_oficio_acm_ia", None)
                if req_oficio:
                    resultado = acm_oficios.generar_oficio_para_ia(
                        data, C,
                        docente=req_oficio.get("docente", ""),
                        curso=req_oficio.get("curso", ""),
                        institucion=req_oficio.get("institucion", ""),
                        tipo_oficio=req_oficio.get("tipo_oficio", "Los tres oficios"),
                        folio=req_oficio.get("folio", "S/N")
                    )
                    if resultado.get("status") == "ok":
                        st.success(resultado["mensaje"])
                        # AQUÍ ESTABA EL ERROR DE LA LÍNEA 1795: Faltaba cerrar la cadena del MIME
                        st.download_button(
                            "⬇️ Descargar Oficio", 
                            data=resultado["bytes"], 
                            file_name=resultado["filename"], 
                            mime=resultado.get("mime", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), 
                            key=f"dl_oficio_{datetime.now().timestamp()}"
                        )
                    else:
                        st.error(resultado.get("mensaje"))
                
                if any(w in normalizar(pregunta) for w in ("oficio","convocatoria","redacta")) and not DEF_MOSTRAR.startswith("No pude"):
                    buffer = generar_word_membrete(DEF_MOSTRAR, C)
                    if buffer:
                        st.download_button("📄 Descargar documento (Word)", data=buffer, file_name=f"Doc_{datetime.now().strftime('%H%M')}.docx")
                        
        st.session_state.chat_history.append({"role": "assistant", "content": DEF_MOSTRAR})
    
    _mostrar_propuesta()