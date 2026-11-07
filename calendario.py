# -*- coding: utf-8 -*-
"""Mi Calendario ATRIO - Panel visual, agenda, pendientes e historial.

Reemplazo del módulo de calendario. Conserva las tablas cal_eventos y
cal_categorias existentes; las migraciones agregan columnas faltantes sin
eliminar registros. La interfaz mantiene render_calendario() como entrada.

Nota funcional: recordatorios y repeticiones se conservan como metadatos,
pero esta versión no envía notificaciones ni genera ocurrencias recurrentes.
"""

import os
import html
import re
import sqlite3
import calendar
from pathlib import Path
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

import streamlit as st

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None


DB_PATH = Path(
    os.environ.get(
        "ATRIO_DB_PATH",
        str(Path(__file__).resolve().parent / "datos" / "atrio.sqlite3"),
    )
)

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

CATEGORIAS_DEFAULT = [
    ("Constancias y documentos", "#FF1493"),
    ("Cambios de horario", "#60A5FA"),
    ("Visitas a talleres", "#34D399"),
    ("Reuniones", "#A78BFA"),
    ("Seguimiento de trámites", "#D4AF37"),
    ("Control escolar", "#2DD4BF"),
    ("Actividades institucionales", "#BE185D"),
    ("Notas personales", "#9E9E9E"),
    ("PEA y actividades académicas", "#F472B6"),
    ("Programación de cursos", "#818CF8"),
]

MODULOS_ATRIO = [
    "Ninguno", "Programación", "Control escolar", "Preparar PEA", "Revisor",
    "Seguimiento y MCE", "PEA históricos", "Mis PEA", "Excel para MCE",
    "Acciones Móviles", "Constancias y folios", "SISAE · Cortes",
    "Evaluación trimestral", "Auditoría SISAE", "Asistente Virtual",
]
TIPOS = ["Tarea", "Compromiso", "Reunión", "Evento", "Recordatorio"]
PRIORIDADES = ["Alta", "Media", "Baja"]
RECORDATORIOS = [
    "Ninguno", "Al momento", "15 minutos antes", "1 hora antes",
    "El mismo día", "1 día antes", "3 días antes", "1 semana antes",
]
REPETICIONES = ["No se repite", "Diaria", "Semanal", "Mensual", "Anual"]
ESTADOS_CERRADOS = ("Completada", "Completado", "Cancelado", "Eliminado")


# -----------------------------------------------------------------------------
# FECHA, FORMATO Y SEGURIDAD DE PRESENTACIÓN
# -----------------------------------------------------------------------------

def fecha_hoy():
    try:
        if ZoneInfo:
            return datetime.now(ZoneInfo("America/Mexico_City")).date()
    except Exception:
        pass
    return date.today()


def ahora_local():
    try:
        if ZoneInfo:
            return datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None)
    except Exception:
        pass
    return datetime.now()


def _iso(valor):
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Fecha no válida: {valor}")


def _fecha(valor, fallback=None):
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date() if valor else fallback
    except (TypeError, ValueError):
        return fallback


def _hora(valor, fallback):
    try:
        return time.fromisoformat(str(valor)) if valor else fallback
    except (TypeError, ValueError):
        return fallback


def _fecha_texto(valor, incluir_dia=False):
    fecha = _fecha(valor)
    if not fecha:
        return "Sin fecha"
    if incluir_dia:
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        return f"{dias[fecha.weekday()].capitalize()} {fecha.day:02d}/{fecha.month:02d}/{fecha.year}"
    return fecha.strftime("%d/%m/%Y")


def _color_seguro(valor, fallback="#9E9E9E"):
    texto = str(valor or "").strip()
    return texto if re.fullmatch(r"#[0-9a-fA-F]{6}", texto) else fallback


def _esc(valor):
    return html.escape(str(valor or ""), quote=True)


def _prioridad_color(prioridad):
    return {"Alta": "#FF1493", "Media": "#D4AF37", "Baja": "#34D399"}.get(
        prioridad, "var(--atrio-tenue)"
    )


def _fecha_referencia(ev):
    """Fecha que determina vencimiento/orden: límite, término o inicio."""
    return _fecha(ev.get("fecha_limite") or ev.get("fecha_fin") or ev.get("fecha_inicio"))


def _es_pendiente(ev):
    return (ev.get("estado") or "Pendiente") not in ESTADOS_CERRADOS


# -----------------------------------------------------------------------------
# BASE DE DATOS Y MIGRACIONES NO DESTRUCTIVAS
# -----------------------------------------------------------------------------

@contextmanager
def _conexion():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
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


def _agregar_columna_si_falta(conn, tabla, nombre, definicion):
    # tabla/nombre/definicion proceden exclusivamente de constantes del módulo.
    columnas = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    if nombre not in columnas:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}")


def init_db():
    with _conexion() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS cal_categorias(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                color TEXT NOT NULL,
                activa INTEGER DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS cal_eventos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria_id INTEGER,
                titulo TEXT NOT NULL,
                tipo TEXT DEFAULT 'Tarea',
                fecha_inicio TEXT NOT NULL,
                fecha_fin TEXT,
                fecha_limite TEXT,
                hora_inicio TEXT,
                hora_fin TEXT,
                todo_el_dia INTEGER DEFAULT 0,
                lugar TEXT,
                responsable TEXT,
                descripcion TEXT,
                prioridad TEXT DEFAULT 'Media',
                recordatorio TEXT DEFAULT 'Ninguno',
                repeticion TEXT DEFAULT 'No se repite',
                modulo_vinculado TEXT DEFAULT 'Ninguno',
                registro_vinculado_id TEXT,
                estado TEXT DEFAULT 'Pendiente',
                creado_en TEXT,
                actualizado_en TEXT,
                eliminado_en TEXT,
                FOREIGN KEY(categoria_id) REFERENCES cal_categorias(id)
            )"""
        )

        columnas_cat = {
            "nombre": "TEXT",
            "color": "TEXT DEFAULT '#9E9E9E'",
            "activa": "INTEGER DEFAULT 1",
        }
        for columna, definicion in columnas_cat.items():
            _agregar_columna_si_falta(conn, "cal_categorias", columna, definicion)

        columnas_evento = {
            "categoria_id": "INTEGER",
            "titulo": "TEXT",
            "tipo": "TEXT DEFAULT 'Tarea'",
            "fecha_inicio": "TEXT",
            "fecha_fin": "TEXT",
            "fecha_limite": "TEXT",
            "hora_inicio": "TEXT",
            "hora_fin": "TEXT",
            "todo_el_dia": "INTEGER DEFAULT 0",
            "lugar": "TEXT",
            "responsable": "TEXT",
            "descripcion": "TEXT",
            "prioridad": "TEXT DEFAULT 'Media'",
            "recordatorio": "TEXT DEFAULT 'Ninguno'",
            "repeticion": "TEXT DEFAULT 'No se repite'",
            "modulo_vinculado": "TEXT DEFAULT 'Ninguno'",
            "registro_vinculado_id": "TEXT",
            "estado": "TEXT DEFAULT 'Pendiente'",
            "creado_en": "TEXT",
            "actualizado_en": "TEXT",
            "eliminado_en": "TEXT",
        }
        for columna, definicion in columnas_evento.items():
            _agregar_columna_si_falta(conn, "cal_eventos", columna, definicion)

        for nombre, color in CATEGORIAS_DEFAULT:
            existe = conn.execute(
                "SELECT id FROM cal_categorias WHERE nombre=? LIMIT 1", (nombre,)
            ).fetchone()
            if not existe:
                conn.execute(
                    "INSERT INTO cal_categorias(nombre,color,activa) VALUES(?,?,1)",
                    (nombre, color),
                )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_cal_inicio ON cal_eventos(fecha_inicio)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cal_limite ON cal_eventos(fecha_limite)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cal_estado ON cal_eventos(estado)")


def obtener_categorias(incluir_inactivas=False):
    init_db()
    where = "" if incluir_inactivas else "WHERE COALESCE(activa,1)=1"
    with _conexion() as conn:
        return [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM cal_categorias {where} ORDER BY nombre"
            ).fetchall()
        ]


def obtener_eventos(anio, mes):
    """Eventos que ocupan el mes o cuya fecha límite cae dentro del mes."""
    init_db()
    ultimo = calendar.monthrange(int(anio), int(mes))[1]
    inicio = date(int(anio), int(mes), 1)
    fin = date(int(anio), int(mes), ultimo)
    with _conexion() as conn:
        filas = conn.execute(
            """SELECT e.*, c.nombre AS cat_nombre, c.color AS cat_color
               FROM cal_eventos e
               LEFT JOIN cal_categorias c ON e.categoria_id=c.id
               WHERE COALESCE(e.estado,'Pendiente') NOT IN ('Eliminado','Cancelado')
                 AND (
                    (e.fecha_inicio <= ? AND COALESCE(NULLIF(e.fecha_fin,''),e.fecha_inicio) >= ?)
                    OR e.fecha_limite BETWEEN ? AND ?
                 )
               ORDER BY COALESCE(e.fecha_inicio,e.fecha_limite), e.id""",
            (_iso(fin), _iso(inicio), _iso(inicio), _iso(fin)),
        ).fetchall()
        return [dict(r) for r in filas]


def obtener_pendientes(limite=500, categoria_filtro=None):
    init_db()
    consulta = """SELECT e.*, c.nombre AS cat_nombre, c.color AS cat_color
                  FROM cal_eventos e
                  LEFT JOIN cal_categorias c ON e.categoria_id=c.id
                  WHERE COALESCE(e.estado,'Pendiente') NOT IN
                        ('Completada','Completado','Cancelado','Eliminado')"""
    parametros = []
    if categoria_filtro and categoria_filtro != "Todas":
        consulta += " AND c.nombre=?"
        parametros.append(categoria_filtro)
    consulta += " ORDER BY COALESCE(NULLIF(e.fecha_limite,''),NULLIF(e.fecha_fin,''),e.fecha_inicio), e.id LIMIT ?"
    parametros.append(int(limite))
    with _conexion() as conn:
        return [dict(r) for r in conn.execute(consulta, tuple(parametros)).fetchall()]


def obtener_historial(limite=200):
    init_db()
    with _conexion() as conn:
        filas = conn.execute(
            """SELECT e.*, c.nombre AS cat_nombre, c.color AS cat_color
               FROM cal_eventos e
               LEFT JOIN cal_categorias c ON e.categoria_id=c.id
               WHERE COALESCE(e.estado,'Pendiente') IN ('Completada','Completado','Cancelado','Eliminado')
               ORDER BY COALESCE(e.actualizado_en,e.creado_en) DESC, e.id DESC
               LIMIT ?""",
            (int(limite),),
        ).fetchall()
        return [dict(r) for r in filas]


def guardar_evento(data):
    init_db()
    titulo = str(data.get("titulo", "")).strip()
    inicio = _iso(data.get("fecha_inicio"))
    fin = _iso(data.get("fecha_fin"))
    if not titulo or not inicio:
        raise ValueError("El título y la fecha de inicio son obligatorios.")
    if fin and fin < inicio:
        raise ValueError("La fecha de término no puede ser anterior al inicio.")
    if data.get("hora_inicio") and data.get("hora_fin"):
        if str(data["hora_fin"]) <= str(data["hora_inicio"]):
            raise ValueError("La hora de término debe ser posterior a la hora de inicio.")

    ahora = ahora_local().isoformat(timespec="seconds")
    with _conexion() as conn:
        conn.execute(
            """INSERT INTO cal_eventos(
                titulo,categoria_id,tipo,fecha_inicio,fecha_fin,fecha_limite,
                hora_inicio,hora_fin,todo_el_dia,lugar,responsable,descripcion,
                prioridad,recordatorio,repeticion,modulo_vinculado,
                registro_vinculado_id,estado,creado_en,actualizado_en
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                titulo, data.get("categoria_id"), data.get("tipo", "Tarea"), inicio,
                fin if fin != inicio else None, _iso(data.get("fecha_limite")),
                data.get("hora_inicio"), data.get("hora_fin"),
                1 if data.get("todo_el_dia") else 0, data.get("lugar") or "",
                data.get("responsable") or "", data.get("descripcion") or "",
                data.get("prioridad", "Media"), data.get("recordatorio", "Ninguno"),
                data.get("repeticion", "No se repite"),
                data.get("modulo_vinculado", "Ninguno"),
                data.get("registro_vinculado_id"), "Pendiente", ahora, ahora,
            ),
        )


def actualizar_evento(evento_id, data):
    titulo = str(data.get("titulo", "")).strip()
    inicio = _iso(data.get("fecha_inicio"))
    fin = _iso(data.get("fecha_fin"))
    if not titulo or not inicio:
        raise ValueError("El título y la fecha de inicio son obligatorios.")
    if fin and fin < inicio:
        raise ValueError("La fecha de término no puede ser anterior al inicio.")
    if data.get("hora_inicio") and data.get("hora_fin"):
        if str(data["hora_fin"]) <= str(data["hora_inicio"]):
            raise ValueError("La hora de término debe ser posterior a la hora de inicio.")

    ahora = ahora_local().isoformat(timespec="seconds")
    with _conexion() as conn:
        conn.execute(
            """UPDATE cal_eventos SET
                titulo=?, categoria_id=?, tipo=?, fecha_inicio=?, fecha_fin=?, fecha_limite=?,
                hora_inicio=?, hora_fin=?, todo_el_dia=?, lugar=?, responsable=?, descripcion=?,
                prioridad=?, recordatorio=?, repeticion=?, modulo_vinculado=?, actualizado_en=?
               WHERE id=?""",
            (
                titulo, data.get("categoria_id"), data.get("tipo"), inicio,
                fin if fin != inicio else None, _iso(data.get("fecha_limite")),
                data.get("hora_inicio"), data.get("hora_fin"),
                1 if data.get("todo_el_dia") else 0, data.get("lugar") or "",
                data.get("responsable") or "", data.get("descripcion") or "",
                data.get("prioridad"), data.get("recordatorio"), data.get("repeticion"),
                data.get("modulo_vinculado"), ahora, int(evento_id),
            ),
        )


def cambiar_estado(evento_id, estado):
    ahora = ahora_local().isoformat(timespec="seconds")
    eliminado = ahora if estado == "Eliminado" else None
    with _conexion() as conn:
        conn.execute(
            "UPDATE cal_eventos SET estado=?, eliminado_en=?, actualizado_en=? WHERE id=?",
            (estado, eliminado, ahora, int(evento_id)),
        )


def calcular_score(ev):
    prioridad = ev.get("prioridad") or "Media"
    base = {"Alta": 40, "Media": 25, "Baja": 10}.get(prioridad, 25)
    referencia = _fecha_referencia(ev)
    if not referencia:
        return base
    dias = (referencia - fecha_hoy()).days
    urgencia = (
        120 if dias < 0 else 105 if dias == 0 else 80 if dias <= 2
        else 55 if dias <= 7 else 30 if dias <= 14 else 5
    )
    return base + urgencia


def _abrir_modulo(modulo):
    if modulo in MODULOS_ATRIO:
        # app.py consume jump antes de construir el menú y conserva su ruta original.
        st.session_state["jump"] = modulo
        st.rerun()
        return
    rutas = st.session_state.get("ATRIO_RUTAS", {})
    if isinstance(rutas, dict) and rutas.get(modulo) and hasattr(st, "switch_page"):
        st.switch_page(rutas[modulo])
    else:
        st.session_state["atrio_modulo_destino"] = modulo
        st.info(f"Destino solicitado: **{_esc(modulo)}**.")


# -----------------------------------------------------------------------------
# ESTILOS Y PIEZAS VISUALES
# -----------------------------------------------------------------------------

def _inyectar_estilos():
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.35rem; padding-bottom: 2.5rem; max-width: 1600px;}
        .atrio-hero {
          background: linear-gradient(112deg, rgba(255,20,147,.10) 0%, var(--atrio-surface) 55%, rgba(212,175,55,.12) 100%);
          border:1px solid var(--atrio-borde); border-left:6px solid var(--atrio-neon); border-radius:22px; padding:25px 28px;
          margin:0 0 18px 0; box-shadow:var(--atrio-sombra);
          backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
        }
        .atrio-eyebrow {font-family:'Inter',sans-serif;font-size:10px;letter-spacing:2px;text-transform:uppercase;
          font-weight:800;color:var(--atrio-oro);margin-bottom:7px;}
        .atrio-hero h1 {font-family:'Playfair Display',Georgia,serif;font-size:clamp(27px,3vw,39px);
          font-weight:700;color:var(--atrio-titulo);line-height:1.08;margin:0;}
        .atrio-hero p {font-family:'Inter',sans-serif;font-size:13px;color:var(--atrio-tenue);margin:8px 0 0 0;}
        .atrio-metric {background:var(--atrio-surface);border:1px solid var(--atrio-borde);border-radius:16px;
          padding:15px 16px;min-height:112px;box-shadow:var(--atrio-sombra);
          backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);}
        .atrio-metric-top {display:flex;align-items:center;justify-content:space-between;gap:8px;}
        .atrio-metric-label {font-size:11px;color:var(--atrio-tenue);font-weight:700;}
        .atrio-metric-icon {font-size:17px;}
        .atrio-metric-value {font-family:'Playfair Display',Georgia,serif;font-size:29px;line-height:1.1;font-weight:700;color:var(--atrio-titulo);margin-top:11px;}
        .atrio-metric-note {font-size:10px;color:var(--atrio-tenue);margin-top:4px;}
        .atrio-section-title {font-family:'Playfair Display',Georgia,serif;font-size:22px;font-weight:700;color:var(--atrio-titulo);margin:0;}
        .atrio-section-sub {font-size:11px;color:var(--atrio-tenue);margin-top:3px;}
        .atrio-month-label {font-family:'Playfair Display',Georgia,serif;color:var(--atrio-titulo);font-weight:700;font-size:25px;text-align:center;padding:5px 0 8px;}
        .atrio-weekday {text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:1px;
          color:var(--atrio-oro);font-weight:800;padding:7px 0;}
        .atrio-day {background:var(--atrio-surface);border:1px solid var(--atrio-borde);border-radius:12px;
          min-height:133px;padding:8px 7px;}
        .atrio-day.today {background:var(--atrio-acento-suave);border:2px solid var(--atrio-neon);padding:7px 6px;}
        .atrio-day.selected {background:rgba(212,175,55,.10);border-color:var(--atrio-oro);}
        .atrio-day.muted {background:var(--atrio-bg);opacity:.55;}
        .atrio-day-head {display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;}
        .atrio-day-number {font-weight:800;font-size:12px;color:var(--atrio-tinta);}
        .atrio-day.today .atrio-day-number {background:var(--atrio-neon);color:var(--atrio-sobre-acento);border-radius:50%;
          width:23px;height:23px;display:inline-flex;align-items:center;justify-content:center;}
        .atrio-chip {font-size:9px;line-height:1.25;font-weight:700;padding:4px 5px;border-radius:6px;
          color:#2A2326;margin:3px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
        .atrio-chip.deadline {background:var(--atrio-oro);color:#2A2326;border:1px solid var(--atrio-oro);}
        .atrio-chip.done {opacity:.5;text-decoration:line-through;}
        .atrio-more {font-size:9px;color:var(--atrio-tenue);text-align:center;margin-top:3px;}
        .atrio-event-card {background:var(--atrio-surface);box-shadow:var(--atrio-sombra);border:1px solid var(--atrio-borde);border-radius:14px;
          padding:13px 15px;margin:0 0 9px 0;backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);}
        .atrio-event-title {font-size:14px;line-height:1.3;font-weight:800;color:var(--atrio-titulo);}
        .atrio-event-meta {font-size:10px;color:var(--atrio-tenue);margin-top:5px;line-height:1.5;}
        .atrio-pill {display:inline-block;border-radius:20px;padding:3px 8px;font-size:9px;font-weight:800;
          background:var(--atrio-acento-suave);color:var(--atrio-neon);border:1px solid var(--atrio-neon);margin-right:4px;}
        .atrio-empty {background:var(--atrio-surface);border:1px dashed var(--atrio-oro);border-radius:14px;
          padding:20px;text-align:center;color:var(--atrio-tenue);font-size:12px;}
        div[data-testid="stTabs"] button {font-weight:700;}
        div[data-testid="stButton"] button {border-radius:10px;}
        @media (max-width: 900px) {
          .atrio-day {min-height:105px;padding:5px 4px;}
          .atrio-chip {font-size:8px;padding:3px 4px;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _metric_card(etiqueta, valor, nota, icono, color="#FF1493"):
    st.markdown(
        f"""<div class="atrio-metric">
          <div class="atrio-metric-top">
            <span class="atrio-metric-label">{_esc(etiqueta)}</span>
            <span class="atrio-metric-icon" style="color:{_color_seguro(color)}">{_esc(icono)}</span>
          </div>
          <div class="atrio-metric-value">{int(valor)}</div>
          <div class="atrio-metric-note">{_esc(nota)}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _tarjeta_evento(ev, mostrar_categoria=True, mostrar_detalle=True):
    prioridad = ev.get("prioridad") or "Media"
    color = _prioridad_color(prioridad)
    titulo = _esc(ev.get("titulo") or "Actividad sin título")
    categoria = _esc(ev.get("cat_nombre") or "General")
    fecha_inicio = _fecha_texto(ev.get("fecha_inicio"), incluir_dia=True)
    fecha_fin = _fecha(ev.get("fecha_fin"))
    fecha_limite = _fecha(ev.get("fecha_limite"))
    horario = "Todo el día" if ev.get("todo_el_dia") else " · ".join(
        x for x in (ev.get("hora_inicio"), ev.get("hora_fin")) if x
    )
    if not horario:
        horario = "Horario no especificado"
    tipo = _esc(ev.get("tipo") or "Actividad")
    extra = []
    if mostrar_categoria:
        extra.append(categoria)
    extra.append(tipo)
    extra.append(horario)
    if fecha_fin and fecha_fin != _fecha(ev.get("fecha_inicio")):
        extra.append(f"Hasta {_fecha_texto(fecha_fin)}")
    if ev.get("lugar"):
        extra.append(f"Lugar: {_esc(ev.get('lugar'))}")
    if ev.get("responsable"):
        extra.append(f"Responsable: {_esc(ev.get('responsable'))}")

    estado = ev.get("estado") or "Pendiente"
    estado_txt = _esc(estado)
    descripcion = _esc(ev.get("descripcion") or "")
    limite_html = (
        f'<span class="atrio-pill" style="background:rgba(212,175,55,.14);color:#8A6D12;border:1px solid rgba(212,175,55,.45)">'
        f'🚩 Límite {_fecha_texto(fecha_limite)}</span>'
        if fecha_limite else ""
    )
    descripcion_html = (
        f'<div class="atrio-event-meta" style="margin-top:7px">{descripcion}</div>'
        if mostrar_detalle and descripcion else ""
    )
    st.markdown(
        f"""<div class="atrio-event-card">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
            <div class="atrio-event-title">{titulo}</div>
            <span class="atrio-pill" style="background:{color}18;color:{color}">{_esc(prioridad)}</span>
          </div>
          <div class="atrio-event-meta">{_esc(fecha_inicio)} · {' · '.join(extra)}</div>
          <div style="margin-top:7px">{limite_html}<span class="atrio-pill">{estado_txt}</span></div>
          {descripcion_html}
        </div>""",
        unsafe_allow_html=True,
    )


def _tarjeta_prioridad(ev, compacta=False):
    prioridad = ev.get("prioridad") or "Media"
    color = _prioridad_color(prioridad)
    titulo = _esc(ev.get("titulo") or "Actividad")
    fecha_ref = _fecha_referencia(ev)
    fecha_lbl = _fecha_texto(fecha_ref)
    categoria = _esc(ev.get("cat_nombre") or "General")
    limite = "Vence" if ev.get("fecha_limite") else "Fecha programada"
    st.markdown(
        f"""<div class="atrio-event-card" style="padding:11px 12px;border-left:4px solid {color}">
          <div class="atrio-event-meta" style="margin-top:0">{_esc(limite)} · {fecha_lbl}</div>
          <div class="atrio-event-title" style="font-size:13px;margin-top:4px">{titulo}</div>
          <div class="atrio-event-meta">{categoria} · <span style="color:{color};font-weight:800">{_esc(prioridad)}</span></div>
        </div>""",
        unsafe_allow_html=True,
    )
    if not compacta:
        a, b = st.columns(2)
        with a:
            modulo = ev.get("modulo_vinculado")
            if modulo and modulo != "Ninguno":
                if st.button("↗ Abrir módulo", key=f"modulo_prio_{ev['id']}", use_container_width=True):
                    _abrir_modulo(modulo)
        with b:
            if st.button("✓ Completar", key=f"completar_prio_{ev['id']}", use_container_width=True):
                cambiar_estado(ev["id"], "Completada")
                st.rerun()


# -----------------------------------------------------------------------------
# FORMULARIOS DE ALTA Y EDICIÓN
# -----------------------------------------------------------------------------

def _form_nuevo():
    categorias = obtener_categorias()
    mapa = {c["nombre"]: c["id"] for c in categorias}
    nombres = list(mapa) or ["Notas personales"]
    fecha_default = st.session_state.get("cal_fecha_form", fecha_hoy())

    with st.container():
        st.markdown("#### Nueva actividad")
        with st.form("form_nuevo_evento_atrio", clear_on_submit=False):
            titulo = st.text_input("Actividad o pendiente *", placeholder="Ej. Revisar PEA de Soldadura")
            descripcion = st.text_area("Descripción y detalles", height=80)
            a, b, c = st.columns(3)
            with a:
                categoria = st.selectbox("Categoría", nombres)
            with b:
                tipo = st.selectbox("Tipo", TIPOS)
            with c:
                prioridad = st.selectbox("Prioridad", PRIORIDADES, index=1)

            st.markdown("**Fechas y horarios**")
            a, b, c = st.columns(3)
            with a:
                f_ini = st.date_input("Fecha de inicio *", value=fecha_default)
            with b:
                es_varios_dias = st.checkbox("Dura varios días", value=False)
                f_fin = st.date_input("Fecha de término", value=fecha_default, disabled=not es_varios_dias)
            with c:
                tiene_limite = st.checkbox("Tiene fecha límite", value=False)
                f_lim = st.date_input("Fecha límite", value=fecha_default, disabled=not tiene_limite)

            a, b, c = st.columns(3)
            with a:
                todo = st.checkbox("Todo el día", value=True)
            with b:
                h_ini = st.time_input("Hora de inicio", value=time(9, 0), disabled=todo)
            with c:
                h_fin = st.time_input("Hora de término", value=time(10, 0), disabled=todo)

            st.markdown("**Organización y seguimiento**")
            a, b, c = st.columns(3)
            with a:
                modulo = st.selectbox("Módulo relacionado", MODULOS_ATRIO)
            with b:
                responsable = st.text_input("Responsable", placeholder="Nombre o área")
            with c:
                lugar = st.text_input("Lugar", placeholder="Ej. CECATI 31")
            a, b = st.columns(2)
            with a:
                recordatorio = st.selectbox("Recordatorio", RECORDATORIOS)
            with b:
                repeticion = st.selectbox("Repetición", REPETICIONES)

            guardar = st.form_submit_button("Guardar actividad", type="primary", use_container_width=True)

        if guardar:
            if not titulo.strip():
                st.error("El título es obligatorio.")
            elif es_varios_dias and f_fin < f_ini:
                st.error("La fecha de término no puede ser anterior al inicio.")
            elif not todo and h_fin <= h_ini:
                st.error("La hora de término debe ser posterior a la hora de inicio.")
            else:
                try:
                    guardar_evento(
                        {
                            "titulo": titulo,
                            "descripcion": descripcion,
                            "categoria_id": mapa.get(categoria),
                            "tipo": tipo,
                            "prioridad": prioridad,
                            "fecha_inicio": f_ini,
                            "fecha_fin": f_fin if es_varios_dias else None,
                            "fecha_limite": f_lim if tiene_limite else None,
                            "todo_el_dia": todo,
                            "hora_inicio": None if todo else h_ini.strftime("%H:%M"),
                            "hora_fin": None if todo else h_fin.strftime("%H:%M"),
                            "modulo_vinculado": modulo,
                            "responsable": responsable,
                            "lugar": lugar,
                            "recordatorio": recordatorio,
                            "repeticion": repeticion,
                        }
                    )
                    st.session_state["mostrar_form_cal"] = False
                    st.success("Actividad guardada correctamente.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar: {exc}")

        if st.button("Cancelar captura", key="cal_cancelar_captura", use_container_width=False):
            st.session_state["mostrar_form_cal"] = False
            st.rerun()


def _form_editar(ev):
    categorias = obtener_categorias(incluir_inactivas=True)
    mapa = {c["nombre"]: c["id"] for c in categorias}
    nombres = list(mapa) or ["Notas personales"]
    cat_actual = ev.get("cat_nombre")
    if cat_actual and cat_actual not in mapa:
        nombres.append(cat_actual)
        mapa[cat_actual] = ev.get("categoria_id")
    idx_cat = nombres.index(cat_actual) if cat_actual in nombres else 0

    f_ini0 = _fecha(ev.get("fecha_inicio"), fecha_hoy())
    f_fin0 = _fecha(ev.get("fecha_fin"), f_ini0)
    f_lim0 = _fecha(ev.get("fecha_limite"), f_ini0)
    tipo0 = ev.get("tipo") if ev.get("tipo") in TIPOS else "Tarea"
    prio0 = ev.get("prioridad") if ev.get("prioridad") in PRIORIDADES else "Media"
    mod0 = ev.get("modulo_vinculado") if ev.get("modulo_vinculado") in MODULOS_ATRIO else "Ninguno"

    with st.form(f"form_editar_atrio_{ev['id']}"):
        tab1, tab2, tab3 = st.tabs(["Básico", "Fechas", "Gestión"])
        with tab1:
            titulo = st.text_input("Actividad *", value=ev.get("titulo") or "")
            descripcion = st.text_area("Descripción", value=ev.get("descripcion") or "", height=95)
            a, b, c = st.columns(3)
            with a:
                categoria = st.selectbox("Categoría", nombres, index=idx_cat)
            with b:
                tipo = st.selectbox("Tipo", TIPOS, index=TIPOS.index(tipo0))
            with c:
                prioridad = st.selectbox("Prioridad", PRIORIDADES, index=PRIORIDADES.index(prio0))
        with tab2:
            a, b = st.columns(2)
            with a:
                f_ini = st.date_input("Fecha de inicio *", value=f_ini0)
            with b:
                es_varios_dias = st.checkbox("Dura varios días", value=bool(ev.get("fecha_fin")))
                f_fin = st.date_input("Fecha de término", value=f_fin0, disabled=not es_varios_dias)
            tiene_limite = st.checkbox("Tiene fecha límite", value=bool(ev.get("fecha_limite")))
            f_lim = st.date_input("Fecha límite", value=f_lim0, disabled=not tiene_limite)
            a, b, c = st.columns(3)
            with a:
                todo = st.checkbox("Todo el día", value=bool(ev.get("todo_el_dia")))
            with b:
                h_ini = st.time_input("Hora de inicio", value=_hora(ev.get("hora_inicio"), time(9, 0)), disabled=todo)
            with c:
                h_fin = st.time_input("Hora de término", value=_hora(ev.get("hora_fin"), time(10, 0)), disabled=todo)
        with tab3:
            a, b = st.columns(2)
            with a:
                modulo = st.selectbox("Módulo relacionado", MODULOS_ATRIO, index=MODULOS_ATRIO.index(mod0))
            with b:
                responsable = st.text_input("Responsable", value=ev.get("responsable") or "")
            lugar = st.text_input("Lugar", value=ev.get("lugar") or "")
            a, b = st.columns(2)
            with a:
                recordatorio = st.selectbox(
                    "Recordatorio", RECORDATORIOS,
                    index=RECORDATORIOS.index(ev.get("recordatorio")) if ev.get("recordatorio") in RECORDATORIOS else 0,
                )
            with b:
                repeticion = st.selectbox(
                    "Repetición", REPETICIONES,
                    index=REPETICIONES.index(ev.get("repeticion")) if ev.get("repeticion") in REPETICIONES else 0,
                )
        guardar = st.form_submit_button("Guardar cambios", type="primary", use_container_width=True)

    if guardar:
        if not titulo.strip():
            st.error("El título es obligatorio.")
        elif es_varios_dias and f_fin < f_ini:
            st.error("La fecha de término no puede ser anterior al inicio.")
        elif not todo and h_fin <= h_ini:
            st.error("La hora de término debe ser posterior a la hora de inicio.")
        else:
            try:
                actualizar_evento(
                    ev["id"],
                    {
                        "titulo": titulo,
                        "descripcion": descripcion,
                        "categoria_id": mapa.get(categoria),
                        "tipo": tipo,
                        "prioridad": prioridad,
                        "fecha_inicio": f_ini,
                        "fecha_fin": f_fin if es_varios_dias else None,
                        "fecha_limite": f_lim if tiene_limite else None,
                        "todo_el_dia": todo,
                        "hora_inicio": None if todo else h_ini.strftime("%H:%M"),
                        "hora_fin": None if todo else h_fin.strftime("%H:%M"),
                        "modulo_vinculado": modulo,
                        "responsable": responsable,
                        "lugar": lugar,
                        "recordatorio": recordatorio,
                        "repeticion": repeticion,
                    },
                )
                st.success("Cambios guardados.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudieron guardar los cambios: {exc}")


# -----------------------------------------------------------------------------
# CÁLCULO DE MÉTRICAS
# -----------------------------------------------------------------------------

def obtener_metricas(anio, mes):
    hoy = fecha_hoy()
    inicio_mes = date(int(anio), int(mes), 1)
    fin_mes = date(int(anio), int(mes), calendar.monthrange(int(anio), int(mes))[1])
    fin_ventana = hoy + timedelta(days=7)
    with _conexion() as conn:
        actividades_mes = conn.execute(
            """SELECT COUNT(DISTINCT id) AS n FROM cal_eventos
               WHERE COALESCE(estado,'Pendiente') NOT IN ('Cancelado','Eliminado')
                 AND ((fecha_inicio <= ? AND COALESCE(NULLIF(fecha_fin,''),fecha_inicio) >= ?)
                      OR fecha_limite BETWEEN ? AND ?)""",
            (_iso(fin_mes), _iso(inicio_mes), _iso(inicio_mes), _iso(fin_mes)),
        ).fetchone()["n"]
        vencimientos = conn.execute(
            """SELECT COUNT(*) AS n FROM cal_eventos
               WHERE COALESCE(estado,'Pendiente') NOT IN ('Completada','Completado','Cancelado','Eliminado')
                 AND fecha_limite BETWEEN ? AND ?""",
            (_iso(hoy), _iso(fin_ventana)),
        ).fetchone()["n"]
        atrasados = conn.execute(
            """SELECT COUNT(*) AS n FROM cal_eventos
               WHERE COALESCE(estado,'Pendiente') NOT IN ('Completada','Completado','Cancelado','Eliminado')
                 AND COALESCE(NULLIF(fecha_limite,''),NULLIF(fecha_fin,''),fecha_inicio) < ?""",
            (_iso(hoy),),
        ).fetchone()["n"]
        concluidas = conn.execute(
            """SELECT COUNT(*) AS n FROM cal_eventos
               WHERE COALESCE(estado,'') IN ('Completada','Completado')
                 AND substr(COALESCE(actualizado_en,creado_en,''),1,10) BETWEEN ? AND ?""",
            (_iso(inicio_mes), _iso(fin_mes)),
        ).fetchone()["n"]
    return {
        "mes": int(actividades_mes or 0),
        "vencimientos": int(vencimientos or 0),
        "atrasados": int(atrasados or 0),
        "concluidas": int(concluidas or 0),
    }


# -----------------------------------------------------------------------------
# VISTAS: CALENDARIO, AGENDA, PENDIENTES E HISTORIAL
# -----------------------------------------------------------------------------

def _construir_items_mes(anio, mes, eventos):
    """Distribuye por separado la duración de la actividad y su fecha límite."""
    inicio_mes = date(anio, mes, 1)
    fin_mes = date(anio, mes, calendar.monthrange(anio, mes)[1])
    por_dia = {}

    for ev in eventos:
        fi = _fecha(ev.get("fecha_inicio"))
        ff = _fecha(ev.get("fecha_fin"), fi)
        if fi and ff:
            cursor = max(fi, inicio_mes)
            final = min(ff, fin_mes)
            while cursor <= final:
                por_dia.setdefault(cursor.day, []).append({"tipo": "evento", "data": ev})
                cursor += timedelta(days=1)

        fecha_limite = _fecha(ev.get("fecha_limite"))
        if fecha_limite and inicio_mes <= fecha_limite <= fin_mes:
            por_dia.setdefault(fecha_limite.day, []).append({"tipo": "limite", "data": ev})

    for dia in por_dia:
        por_dia[dia].sort(
            key=lambda item: (0 if item["tipo"] == "limite" else 1, item["data"].get("id", 0))
        )
    return por_dia


def _vista_mensual(anio, mes, eventos):
    por_dia = _construir_items_mes(anio, mes, eventos)
    hoy = fecha_hoy()
    st.markdown(
        f'<div class="atrio-month-label">{MESES[mes - 1]} {anio}</div>',
        unsafe_allow_html=True,
    )
    encabezados = st.columns(7, gap="small")
    for col, nombre in zip(encabezados, DIAS_CORTOS):
        col.markdown(f'<div class="atrio-weekday">{nombre}</div>', unsafe_allow_html=True)

    semanas = calendar.Calendar(firstweekday=0).monthdayscalendar(anio, mes)
    for num_semana, semana in enumerate(semanas):
        columnas = st.columns(7, gap="small")
        for indice, dia in enumerate(semana):
            with columnas[indice]:
                if dia == 0:
                    st.markdown('<div class="atrio-day muted"></div>', unsafe_allow_html=True)
                    continue
                fecha_dia = date(anio, mes, dia)
                clases = ["atrio-day"]
                if fecha_dia == hoy:
                    clases.append("today")
                items = por_dia.get(dia, [])
                html_items = []
                for item in items[:2]:
                    ev = item["data"]
                    titulo = _esc(ev.get("titulo") or "Actividad")
                    if item["tipo"] == "limite":
                        html_items.append(
                            f'<div class="atrio-chip deadline" title="Fecha límite: {titulo}">'
                            f'🚩 {titulo}</div>'
                        )
                    else:
                        color = _color_seguro(ev.get("cat_color"))
                        estado = ev.get("estado") or "Pendiente"
                        clase_extra = " done" if estado in ("Completada", "Completado") else ""
                        hora = ""
                        if not ev.get("todo_el_dia") and ev.get("hora_inicio"):
                            hora = f' · {_esc(ev.get("hora_inicio"))}'
                        html_items.append(
                            f'<div class="atrio-chip{clase_extra}" style="background:{color}" '
                            f'title="{titulo}">{titulo}{hora}</div>'
                        )
                mas = (
                    f'<div class="atrio-more">+{len(items) - 2} más</div>'
                    if len(items) > 2 else ""
                )
                st.markdown(
                    f'<div class="{" ".join(clases)}">'
                    f'<div class="atrio-day-head"><span class="atrio-day-number">{dia}</span></div>'
                    f'{"".join(html_items)}{mas}</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "＋", key=f"cal_add_{anio}_{mes}_{dia}",
                    help=f"Crear actividad para el {_fecha_texto(fecha_dia)}",
                    use_container_width=True,
                ):
                    st.session_state["cal_fecha_form"] = fecha_dia
                    st.session_state["mostrar_form_cal"] = True
                    st.rerun()


def _vista_agenda():
    hoy = fecha_hoy()
    fecha_agenda = st.session_state.get("cal_fecha_agenda", hoy)
    fecha_agenda = _fecha(_iso(fecha_agenda), hoy)
    st.markdown('<div class="atrio-section-title">Agenda por fecha</div>', unsafe_allow_html=True)
    st.markdown('<div class="atrio-section-sub">Consulta las actividades de un día y lo que viene después.</div>', unsafe_allow_html=True)
    fecha_agenda = st.date_input("Selecciona un día", value=fecha_agenda, key="cal_fecha_agenda_widget")
    st.session_state["cal_fecha_agenda"] = fecha_agenda

    inicio_rango = fecha_agenda
    fin_rango = fecha_agenda + timedelta(days=1)
    mes_eventos = obtener_eventos(fecha_agenda.year, fecha_agenda.month)
    dia_items = []
    for ev in mes_eventos:
        fi = _fecha(ev.get("fecha_inicio"))
        ff = _fecha(ev.get("fecha_fin"), fi)
        limite = _fecha(ev.get("fecha_limite"))
        if fi and ff and fi <= fecha_agenda <= ff:
            dia_items.append(("Actividad", ev))
        if limite == fecha_agenda:
            dia_items.append(("Fecha límite", ev))

    st.markdown(f"#### {_fecha_texto(fecha_agenda, incluir_dia=True)}")
    if not dia_items:
        st.markdown('<div class="atrio-empty">No hay actividades ni fechas límite registradas para este día.</div>', unsafe_allow_html=True)
    else:
        vistos = set()
        for clase, ev in dia_items:
            clave = (clase, ev["id"])
            if clave in vistos:
                continue
            vistos.add(clave)
            if clase == "Fecha límite":
                st.warning(f"Fecha límite: **{ev.get('titulo')}**")
            _tarjeta_evento(ev)

    st.markdown("---")
    st.markdown("#### Lo que viene en los próximos 7 días")
    fin_proximos = fecha_agenda + timedelta(days=7)
    proximos = obtener_pendientes(limite=500)
    proximos = [
        ev for ev in proximos
        if (_fecha(ev.get("fecha_inicio")) and fecha_agenda <= _fecha(ev.get("fecha_inicio")) <= fin_proximos)
        or (_fecha(ev.get("fecha_limite")) and fecha_agenda <= _fecha(ev.get("fecha_limite")) <= fin_proximos)
    ]
    proximos.sort(key=lambda ev: (_fecha_referencia(ev) or date.max, ev.get("id", 0)))
    if not proximos:
        st.caption("No hay compromisos pendientes en ese periodo.")
    else:
        for ev in proximos:
            _tarjeta_evento(ev, mostrar_detalle=False)



# -----------------------------------------------------------------------------
# VISTA COMPACTA PARA INICIO · CALENDARIO + AGENDA
# -----------------------------------------------------------------------------

def _eventos_de_fecha(fecha, eventos):
    """Devuelve actividades y fechas límite que corresponden a un día."""
    salida = []
    for ev in eventos or []:
        fi = _fecha(ev.get("fecha_inicio"))
        ff = _fecha(ev.get("fecha_fin"), fi)
        limite = _fecha(ev.get("fecha_limite"))
        es_actividad = bool(fi and ff and fi <= fecha <= ff)
        es_limite = limite == fecha
        if es_actividad and es_limite:
            salida.append(("Actividad · fecha límite", ev))
        elif es_actividad:
            salida.append(("Actividad", ev))
        elif es_limite:
            salida.append(("Fecha límite", ev))
    return salida


def _cursos_de_fecha(cursos, fecha):
    """Fechas de inicio y término de cursos; son referencias, nunca eventos editables."""
    salida = []
    for grupo in cursos or []:
        inicio = _fecha(grupo.get("inicio"))
        termino = _fecha(grupo.get("fin"))
        nombre = grupo.get("nombre") or grupo.get("curso") or "Curso sin nombre"
        docente = grupo.get("hoja") or grupo.get("docente") or "Docente sin dato"
        if inicio == fecha:
            salida.append({
                "tipo": "Inicio de curso", "nombre": nombre, "docente": docente,
                "grupo_id": grupo.get("id"),
            })
        if termino == fecha:
            salida.append({
                "tipo": "Término de curso", "nombre": nombre, "docente": docente,
                "grupo_id": grupo.get("id"),
            })
    return salida


def _tareas_de_fecha(tareas, fecha):
    """Seguimientos derivados de ATRIO; no duplica actividades de Mi Calendario."""
    salida = []
    for tarea in tareas or []:
        if tarea.get("proceso") == "Mi Calendario" or tarea.get("fuente") == "Mi Calendario":
            continue
        if _fecha(tarea.get("fecha")) == fecha:
            salida.append(tarea)
    orden = {"Bloqueado": 0, "Vencido": 1, "Pendiente": 2, "Aviso": 3, "En espera": 4, "Por verificar": 5}
    salida.sort(key=lambda x: (
        orden.get(x.get("estado"), 6),
        x.get("fecha") or "9999-12-31",
        x.get("proceso", ""),
        x.get("curso", ""),
    ))
    return salida


def _marcas_inicio_mes(anio, mes, eventos, cursos, tareas=None):
    """Marcas compactas: actividades, límites, tareas ATRIO e hitos de cursos."""
    marcas = {}
    for dia, items in _construir_items_mes(anio, mes, eventos).items():
        for item in items:
            marcas.setdefault(dia, []).append(
                "L" if item["tipo"] == "limite" else "A"
            )
    inicio_mes = date(int(anio), int(mes), 1)
    fin_mes = date(int(anio), int(mes), calendar.monthrange(int(anio), int(mes))[1])
    for grupo in cursos or []:
        for campo, marca in (("inicio", "C"), ("fin", "T")):
            fecha = _fecha(grupo.get(campo))
            if fecha and inicio_mes <= fecha <= fin_mes:
                marcas.setdefault(fecha.day, []).append(marca)
    for tarea in tareas or []:
        fecha = _fecha(tarea.get("fecha"))
        if (
            fecha and inicio_mes <= fecha <= fin_mes
            and tarea.get("proceso") != "Mi Calendario"
            and tarea.get("fuente") != "Mi Calendario"
        ):
            marcas.setdefault(fecha.day, []).append("L")
    return marcas


def render_inicio_calendario(cursos=None, tareas=None):
    """Panel funcional de calendario y agenda para Inicio.

    Las actividades usan las tablas normales de Mi Calendario. Los cursos solo
    aportan marcas de inicio/término y no se duplican como eventos editables.
    """
    try:
        init_db()
    except Exception as exc:
        st.error(f"No se pudo preparar el calendario de Inicio: {exc}")
        return

    _inyectar_estilos()
    hoy = fecha_hoy()
    st.session_state.setdefault("inicio_cal_anio", hoy.year)
    st.session_state.setdefault("inicio_cal_mes", hoy.month)
    st.session_state.setdefault("inicio_cal_fecha", hoy)

    seleccionado = _fecha(st.session_state.get("inicio_cal_fecha"), hoy)
    anio = int(st.session_state["inicio_cal_anio"])
    mes = int(st.session_state["inicio_cal_mes"])
    if (seleccionado.year, seleccionado.month) != (anio, mes):
        anio, mes = seleccionado.year, seleccionado.month
        st.session_state["inicio_cal_anio"] = anio
        st.session_state["inicio_cal_mes"] = mes

    st.markdown(
        '<div class="atrio-section-title">Calendario y agenda</div>'
        '<div class="atrio-section-sub">Tus actividades y las fechas de los cursos, en un mismo lugar.</div>',
        unsafe_allow_html=True,
    )
    controles = st.columns([0.85, 0.85, 1.15, 0.85, 1.25])
    if controles[0].button("Hoy", key="inicio_cal_hoy", use_container_width=True):
        st.session_state.update({
            "inicio_cal_anio": hoy.year, "inicio_cal_mes": hoy.month,
            "inicio_cal_fecha": hoy,
        })
        st.rerun()
    if controles[1].button("‹", key="inicio_cal_anterior", help="Mes anterior", use_container_width=True):
        mes -= 1
        if mes < 1:
            mes, anio = 12, anio - 1
        st.session_state.update({
            "inicio_cal_anio": anio, "inicio_cal_mes": mes,
            "inicio_cal_fecha": date(anio, mes, 1),
        })
        st.rerun()
    controles[2].markdown(
        f'<div class="atrio-month-label" style="font-size:19px;padding:5px 0">'
        f'{MESES[mes - 1]} {anio}</div>',
        unsafe_allow_html=True,
    )
    if controles[3].button("›", key="inicio_cal_siguiente", help="Mes siguiente", use_container_width=True):
        mes += 1
        if mes > 12:
            mes, anio = 1, anio + 1
        st.session_state.update({
            "inicio_cal_anio": anio, "inicio_cal_mes": mes,
            "inicio_cal_fecha": date(anio, mes, 1),
        })
        st.rerun()
    if controles[4].button("＋ Nueva actividad", key="inicio_cal_nueva", type="primary", use_container_width=True):
        st.session_state["cal_fecha_form"] = seleccionado
        st.session_state["mostrar_form_cal"] = True
        st.rerun()

    eventos_mes = obtener_eventos(anio, mes)
    marcas = _marcas_inicio_mes(anio, mes, eventos_mes, cursos or [], tareas or [])
    semanas = calendar.Calendar(firstweekday=0).monthdayscalendar(anio, mes)
    lado_cal, lado_agenda = st.columns([1.45, 1], gap="large")

    with lado_cal:
        encabezados = st.columns(7, gap="small")
        for col, nombre in zip(encabezados, DIAS_CORTOS):
            col.markdown(
                f'<div class="atrio-weekday">{_esc(nombre)}</div>',
                unsafe_allow_html=True,
            )
        for numero_semana, semana in enumerate(semanas):
            columnas = st.columns(7, gap="small")
            for indice, dia in enumerate(semana):
                with columnas[indice]:
                    if not dia:
                        st.markdown('<div style="height:34px"></div>', unsafe_allow_html=True)
                        continue
                    fecha_dia = date(anio, mes, dia)
                    claves = marcas.get(dia, [])
                    etiqueta = str(dia) + (" ·" if claves else "")
                    if st.button(
                        etiqueta,
                        key=f"inicio_cal_dia_{anio}_{mes}_{dia}",
                        type="primary" if fecha_dia == seleccionado else "secondary",
                        help="Marcas: " + ", ".join({
                            "A": "actividad", "L": "fecha límite",
                            "C": "inicio de curso", "T": "término de curso",
                        }[x] for x in claves) if claves else f"Seleccionar {_fecha_texto(fecha_dia)}",
                        use_container_width=True,
                    ):
                        st.session_state["inicio_cal_fecha"] = fecha_dia
                        st.rerun()
                    if claves:
                        leyenda = " · ".join(dict.fromkeys(claves))
                        st.caption(leyenda)

        st.caption("A · Actividad   L · Fecha límite   C · Inicio de curso   T · Término de curso")

    seleccionado = _fecha(st.session_state.get("inicio_cal_fecha"), hoy)
    with lado_agenda:
        st.markdown(
            f'<div class="atrio-section-title" style="font-size:19px">Agenda del día</div>'
            f'<div class="atrio-section-sub">{_esc(_fecha_texto(seleccionado, incluir_dia=True))}</div>',
            unsafe_allow_html=True,
        )
        actividades_dia = _eventos_de_fecha(
            seleccionado, obtener_eventos(seleccionado.year, seleccionado.month)
        )
        cursos_dia = _cursos_de_fecha(cursos, seleccionado)
        tareas_dia = _tareas_de_fecha(tareas, seleccionado)
        if not actividades_dia and not cursos_dia and not tareas_dia:
            st.markdown(
                '<div class="atrio-empty">No hay actividades ni inicios o términos de cursos para este día.</div>',
                unsafe_allow_html=True,
            )

        for tipo, ev in actividades_dia:
            if "límite" in tipo.casefold():
                st.warning(f"Fecha límite: **{ev.get('titulo') or 'Actividad'}**")
            _tarjeta_evento(ev, mostrar_detalle=True)
            acciones = st.columns(2)
            if acciones[0].button("Editar", key=f"inicio_cal_editar_{ev['id']}", use_container_width=True):
                st.session_state["inicio_cal_editar_id"] = ev["id"]
                st.rerun()
            estado = ev.get("estado") or "Pendiente"
            if estado not in ESTADOS_CERRADOS:
                if acciones[1].button("Completar", key=f"inicio_cal_completar_{ev['id']}", use_container_width=True):
                    cambiar_estado(ev["id"], "Completada")
                    st.rerun()
            elif estado in ("Completada", "Completado"):
                acciones[1].caption("Actividad completada")

        for item in cursos_dia:
            st.markdown(
                f'<div class="atrio-event-card">'
                f'<span class="atrio-pill">{_esc(item["tipo"])}</span>'
                f'<div class="atrio-event-title">{_esc(item["nombre"])}</div>'
                f'<div class="atrio-event-meta">{_esc(item["docente"])} · Fecha tomada de Programación</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        for indice, tarea in enumerate(tareas_dia):
            estado = str(tarea.get("estado") or "Pendiente")
            st.markdown(
                f'<div class="atrio-event-card">'
                f'<span class="atrio-pill">Fecha límite · {_esc(tarea.get("proceso", "Seguimiento"))}</span>'
                f'<div class="atrio-event-title">{_esc(tarea.get("curso", "Actividad"))}</div>'
                f'<div class="atrio-event-meta">{_esc(estado)} · {_esc(tarea.get("docente", ""))}</div>'
                f'<div class="atrio-event-meta">{_esc(tarea.get("motivo", ""))}</div>'
                f'<div class="atrio-event-meta">Siguiente acción: {_esc(tarea.get("accion", ""))}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            modulo = tarea.get("modulo")
            if modulo in MODULOS_ATRIO:
                if st.button(
                    f"Ir a {modulo} →",
                    key=f"inicio_cal_tarea_{indice}_{abs(hash(str(tarea.get('id', ''))))}",
                ):
                    _abrir_modulo(modulo)

        with st.expander("Próximos 7 días", expanded=False):
            fin_ventana = seleccionado + timedelta(days=7)
            proximos = [
                ev for ev in obtener_pendientes(limite=1000)
                if (
                    _fecha(ev.get("fecha_inicio")) and
                    seleccionado <= _fecha(ev.get("fecha_inicio")) <= fin_ventana
                ) or (
                    _fecha(ev.get("fecha_limite")) and
                    seleccionado <= _fecha(ev.get("fecha_limite")) <= fin_ventana
                )
            ]
            proximos.sort(key=lambda ev: (_fecha_referencia(ev) or date.max, ev.get("id", 0)))
            if not proximos:
                st.caption("No hay actividades pendientes registradas en los próximos siete días.")
            else:
                for ev in proximos[:5]:
                    _tarjeta_prioridad(ev, compacta=True)

            tareas_proximas = [
                tarea for tarea in (tareas or [])
                if (
                    tarea.get("proceso") != "Mi Calendario"
                    and tarea.get("fuente") != "Mi Calendario"
                    and _fecha(tarea.get("fecha"))
                    and seleccionado < _fecha(tarea.get("fecha")) <= fin_ventana
                )
            ]
            if tareas_proximas:
                st.markdown("**Fechas límite y seguimientos ATRIO**")
                for tarea in tareas_proximas[:8]:
                    st.caption(
                        f"{_fecha_texto(tarea.get('fecha'))} · "
                        f"{tarea.get('proceso')} · {tarea.get('curso')} · "
                        f"{tarea.get('estado')}"
                    )

            cursos_proximos = []
            for desplazamiento in range(8):
                fecha_proxima = seleccionado + timedelta(days=desplazamiento)
                for item in _cursos_de_fecha(cursos, fecha_proxima):
                    cursos_proximos.append((fecha_proxima, item))
            if cursos_proximos:
                st.markdown("**Fechas de cursos**")
                for fecha_proxima, item in cursos_proximos:
                    st.caption(
                        f"{_fecha_texto(fecha_proxima)} · {item['tipo']} · "
                        f"{item['nombre']} · {item['docente']}"
                    )

    editar_id = st.session_state.get("inicio_cal_editar_id")
    if editar_id:
        evento_editar = next((ev for ev in obtener_eventos(anio, mes) if ev.get("id") == editar_id), None)
        if evento_editar:
            with st.expander("Editar actividad seleccionada", expanded=True):
                _form_editar(evento_editar)
                if st.button("Cerrar edición", key="inicio_cal_cerrar_edicion"):
                    st.session_state.pop("inicio_cal_editar_id", None)
                    st.rerun()
        else:
            st.session_state.pop("inicio_cal_editar_id", None)

    if st.session_state.get("mostrar_form_cal"):
        st.session_state.setdefault("cal_fecha_form", seleccionado)
        with st.container(border=True):
            _form_nuevo()



def _vista_pendientes():
    st.markdown('<div class="atrio-section-title">Pendientes por atender</div>', unsafe_allow_html=True)
    st.markdown('<div class="atrio-section-sub">Filtra por área, prioridad o situación para decidir qué atender primero.</div>', unsafe_allow_html=True)
    categorias = [c["nombre"] for c in obtener_categorias()]
    a, b, c = st.columns([1.3, 1, 1.4])
    with a:
        categoria = st.selectbox("Área", ["Todas"] + categorias, key="cal_pend_area")
    with b:
        prioridad = st.selectbox("Prioridad", ["Todas"] + PRIORIDADES, key="cal_pend_prioridad")
    with c:
        periodo = st.selectbox(
            "Fecha", ["Todos", "Atrasados", "Próximos 7 días", "Próximos 30 días", "Sin vencimiento próximo"],
            key="cal_pend_periodo",
        )
    busqueda = st.text_input("Buscar actividad", placeholder="Escribe parte del título o descripción", key="cal_pend_busqueda")

    pendientes = obtener_pendientes(limite=1000, categoria_filtro=categoria)
    hoy = fecha_hoy()
    if prioridad != "Todas":
        pendientes = [ev for ev in pendientes if (ev.get("prioridad") or "Media") == prioridad]
    if busqueda.strip():
        q = busqueda.casefold().strip()
        pendientes = [
            ev for ev in pendientes
            if q in str(ev.get("titulo") or "").casefold()
            or q in str(ev.get("descripcion") or "").casefold()
        ]
    if periodo == "Atrasados":
        pendientes = [ev for ev in pendientes if _fecha_referencia(ev) and _fecha_referencia(ev) < hoy]
    elif periodo == "Próximos 7 días":
        limite = hoy + timedelta(days=7)
        pendientes = [ev for ev in pendientes if _fecha_referencia(ev) and hoy <= _fecha_referencia(ev) <= limite]
    elif periodo == "Próximos 30 días":
        limite = hoy + timedelta(days=30)
        pendientes = [ev for ev in pendientes if _fecha_referencia(ev) and hoy <= _fecha_referencia(ev) <= limite]
    elif periodo == "Sin vencimiento próximo":
        limite = hoy + timedelta(days=30)
        pendientes = [ev for ev in pendientes if not _fecha_referencia(ev) or _fecha_referencia(ev) > limite]

    pendientes.sort(key=lambda ev: (calcular_score(ev), -int(ev.get("id", 0))), reverse=True)
    st.caption(f"{len(pendientes)} actividad(es) coinciden con los filtros.")
    if not pendientes:
        st.markdown('<div class="atrio-empty">No hay pendientes que coincidan con estos filtros.</div>', unsafe_allow_html=True)
        return

    for ev in pendientes:
        _tarjeta_evento(ev)
        a, b, c = st.columns([1, 1, 2])
        with a:
            if st.button("✓ Completar", key=f"pend_done_{ev['id']}", use_container_width=True):
                cambiar_estado(ev["id"], "Completada")
                st.rerun()
        with b:
            if st.button("Editar", key=f"pend_edit_{ev['id']}", use_container_width=True):
                st.session_state["cal_evento_editar_id"] = ev["id"]
                st.rerun()
        with c:
            modulo = ev.get("modulo_vinculado")
            if modulo and modulo != "Ninguno":
                if st.button(f"↗ {modulo}", key=f"pend_mod_{ev['id']}", use_container_width=True):
                    _abrir_modulo(modulo)

    editar_id = st.session_state.get("cal_evento_editar_id")
    if editar_id:
        seleccionado = next((ev for ev in pendientes if ev["id"] == editar_id), None)
        if seleccionado:
            with st.expander("Editar actividad seleccionada", expanded=True):
                _form_editar(seleccionado)
        else:
            st.session_state.pop("cal_evento_editar_id", None)


def _vista_historial():
    st.markdown('<div class="atrio-section-title">Historial y papelera</div>', unsafe_allow_html=True)
    st.markdown('<div class="atrio-section-sub">Consulta actividades concluidas, canceladas o enviadas a la papelera.</div>', unsafe_allow_html=True)
    historial = obtener_historial()
    if not historial:
        st.markdown('<div class="atrio-empty">Todavía no hay actividades en el historial.</div>', unsafe_allow_html=True)
        return
    for ev in historial:
        estado = ev.get("estado") or "Pendiente"
        icono = "✓" if estado in ("Completada", "Completado") else ("×" if estado == "Cancelado" else "⌫")
        with st.expander(f"{icono}  {ev.get('titulo')} · {estado}"):
            _tarjeta_evento(ev)
            a, b = st.columns(2)
            with a:
                if st.button("Restaurar a Pendiente", key=f"restore_{ev['id']}", use_container_width=True):
                    cambiar_estado(ev["id"], "Pendiente")
                    st.rerun()
            with b:
                if estado == "Eliminado":
                    st.caption("Registro conservado en papelera; al restaurarlo volverá a Pendientes.")


def _administrar():
    with st.expander("⚙️ Administración y edición de actividades", expanded=False):
        eventos = obtener_pendientes(limite=1000)
        if not eventos:
            st.info("No hay actividades pendientes para administrar.")
            return
        seleccion = st.selectbox(
            "Selecciona una actividad",
            eventos,
            format_func=lambda ev: f"#{ev['id']} · {ev.get('titulo')} · {ev.get('fecha_inicio')}",
            key="cal_admin_seleccion",
        )
        _form_editar(seleccion)
        st.markdown("---")
        st.caption("Acciones de estado")
        a, b = st.columns(2)
        with a:
            if st.button("Cancelar actividad", key=f"admin_cancel_{seleccion['id']}", use_container_width=True):
                cambiar_estado(seleccion["id"], "Cancelado")
                st.rerun()
        with b:
            if st.button("Mover a la papelera", key=f"admin_delete_{seleccion['id']}", use_container_width=True):
                cambiar_estado(seleccion["id"], "Eliminado")
                st.rerun()


# -----------------------------------------------------------------------------
# PUNTO DE ENTRADA DEL MÓDULO
# -----------------------------------------------------------------------------

def render_calendario():
    try:
        init_db()
    except Exception as exc:
        st.error(f"No se pudo preparar la base de datos del calendario: {exc}")
        return

    hoy = fecha_hoy()
    valores_iniciales = {
        "cal_anio": hoy.year,
        "cal_mes": hoy.month,
        "cal_mes_widget": hoy.month,
        "cal_anio_widget": hoy.year,
        "cal_fecha_agenda": hoy,
    }
    for clave, valor in valores_iniciales.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor

    _inyectar_estilos()

    st.markdown(
        """<div class="atrio-hero">
          <div class="atrio-eyebrow">ATRIO · Gestión académica</div>
          <h1>Mi espacio de trabajo</h1>
          <p>Organiza tus actividades, revisa tus compromisos y mantén el seguimiento de tus pendientes.</p>
        </div>""",
        unsafe_allow_html=True,
    )

    anio = int(st.session_state["cal_anio"])
    mes = int(st.session_state["cal_mes"])
    metricas = obtener_metricas(anio, mes)
    tarjetas = st.columns(4, gap="medium")
    with tarjetas[0]:
        _metric_card("Actividades del mes", metricas["mes"], f"{MESES[mes - 1]} {anio}", "▦", "#FF1493")
    with tarjetas[1]:
        _metric_card("Vencimientos próximos", metricas["vencimientos"], "En los próximos 7 días", "◷", "#D4AF37")
    with tarjetas[2]:
        _metric_card("Pendientes atrasados", metricas["atrasados"], "Requieren revisión", "!", "#FF1493")
    with tarjetas[3]:
        _metric_card("Actividades concluidas", metricas["concluidas"], "Concluidas en el mes", "✓", "#34D399")

    st.markdown(" ")
    botones = st.columns([1, 1.2, 2.2, 1.5])
    with botones[0]:
        if st.button("Hoy", key="cal_ir_hoy", use_container_width=True):
            st.session_state.update(
                {
                    "cal_anio": hoy.year,
                    "cal_mes": hoy.month,
                    "cal_mes_widget": hoy.month,
                    "cal_anio_widget": hoy.year,
                    "cal_fecha_agenda": hoy,
                }
            )
            st.rerun()
    with botones[1]:
        if st.button("◀ Anterior", key="cal_mes_anterior", use_container_width=True):
            nuevo_mes = mes - 1
            nuevo_anio = anio
            if nuevo_mes < 1:
                nuevo_mes, nuevo_anio = 12, anio - 1
            st.session_state.update(
                {"cal_mes": nuevo_mes, "cal_anio": nuevo_anio,
                 "cal_mes_widget": nuevo_mes, "cal_anio_widget": nuevo_anio}
            )
            st.rerun()
    with botones[2]:
        c_mes, c_anio = st.columns([1.35, 1])
        with c_mes:
            mes_widget = st.selectbox(
                "Mes", range(1, 13), key="cal_mes_widget",
                format_func=lambda n: MESES[n - 1], label_visibility="collapsed",
            )
        with c_anio:
            anio_widget = st.number_input(
                "Año", min_value=2000, max_value=2100, step=1,
                key="cal_anio_widget", label_visibility="collapsed",
            )
        if int(mes_widget) != mes or int(anio_widget) != anio:
            st.session_state["cal_mes"] = int(mes_widget)
            st.session_state["cal_anio"] = int(anio_widget)
            st.rerun()
    with botones[3]:
        if st.button("＋ Nueva actividad", type="primary", key="cal_nueva_global", use_container_width=True):
            st.session_state["cal_fecha_form"] = date(anio, mes, 1)
            st.session_state["mostrar_form_cal"] = True
            st.rerun()

    if st.session_state.get("mostrar_form_cal"):
        with st.container():
            _form_nuevo()

    tab_cal, tab_agenda, tab_pend, tab_hist = st.tabs(
        ["▦  Calendario", "☷  Agenda", "◷  Pendientes", "↺  Historial"]
    )

    with tab_cal:
        cabecera = st.columns([2.2, 1])
        with cabecera[0]:
            st.markdown('<div class="atrio-section-title">Tu calendario</div>', unsafe_allow_html=True)
            st.markdown('<div class="atrio-section-sub">Selecciona el símbolo + de un día para programar una actividad.</div>', unsafe_allow_html=True)
        with cabecera[1]:
            st.markdown(
                '<div style="text-align:right;font-size:10px;color:var(--atrio-tenue);padding-top:8px">'
                '<span style="color:#FF1493">●</span> Actividad &nbsp; '
                '<span style="color:#D4AF37">●</span> Fecha límite</div>',
                unsafe_allow_html=True,
            )
        eventos_mes = obtener_eventos(anio, mes)
        _vista_mensual(anio, mes, eventos_mes)

        st.markdown("---")
        lado_a, lado_b = st.columns([1.5, 1])
        with lado_a:
            st.markdown("#### Prioridades")
            categorias = [c["nombre"] for c in obtener_categorias()]
            filtro_cat = st.selectbox("Filtrar por área", ["Todas"] + categorias, key="cal_prioridad_filtro")
            prioridades = sorted(
                obtener_pendientes(categoria_filtro=filtro_cat),
                key=calcular_score,
                reverse=True,
            )[:5]
            if not prioridades:
                st.markdown('<div class="atrio-empty">No hay pendientes por atender.</div>', unsafe_allow_html=True)
            else:
                for ev in prioridades:
                    _tarjeta_prioridad(ev, compacta=True)
        with lado_b:
            st.markdown("#### Próximo vencimiento")
            proximos_vencimientos = [
                ev for ev in obtener_pendientes(limite=1000)
                if _fecha(ev.get("fecha_limite")) and _fecha(ev.get("fecha_limite")) >= hoy
            ]
            proximos_vencimientos.sort(key=lambda ev: (_fecha(ev.get("fecha_limite")), ev.get("id", 0)))
            if proximos_vencimientos:
                ev = proximos_vencimientos[0]
                _tarjeta_prioridad(ev, compacta=True)
            else:
                st.markdown('<div class="atrio-empty">No hay fechas límite próximas registradas.</div>', unsafe_allow_html=True)

    with tab_agenda:
        _vista_agenda()

    with tab_pend:
        _vista_pendientes()

    with tab_hist:
        _vista_historial()

    st.markdown("---")
    _administrar()
    st.caption(
        "Nota: los recordatorios y las repeticiones se guardan en cada actividad; "
        "la activación de notificaciones y la generación automática de recurrencias "
        "requieren una integración adicional."
    )
