"""Vista previa aislada del tablero ejecutivo ATRIO Órbita.

Usa exclusivamente grupos, indicadores y tareas ficticias. El calendario
escribe únicamente en un SQLite temporal único por sesión; no importa app.py
ni centro.py y no abre SISAE, Excel ni recursos institucionales.
"""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

import tema
import interfaz as UI
import calendario as CAL
import tablero_inicio as TINI


st.set_page_config(
    page_title="ATRIO · Laboratorio Órbita",
    page_icon="◈",
    layout="wide",
)

PALETA_BASE = tema.paleta_predeterminada()
st.sidebar.markdown("### Laboratorio ATRIO Órbita")
st.sidebar.caption("Vista aislada · exclusivamente datos ficticios")

opciones = tema.OPCIONES
seleccion = st.sidebar.selectbox(
    "Tema visual",
    opciones,
    index=opciones.index(tema.ORBITA),
    key="lab_orbita_tema",
)

paleta = {}
if seleccion == tema.ORBITA:
    st.sidebar.markdown("#### Personalizar · Mi paleta")
    etiquetas = {
        "fondo": "Fondo general",
        "acento": "Color principal",
        "secundario": "Color secundario",
        "calendario": "Calendario",
    }
    for campo, etiqueta in etiquetas.items():
        paleta[campo] = st.sidebar.color_picker(
            etiqueta,
            value=st.session_state.get("lab_orbita_" + campo, PALETA_BASE[campo]),
            key="lab_orbita_" + campo,
        )
    if st.sidebar.button("Restablecer paleta", key="lab_orbita_reset"):
        for campo, valor in PALETA_BASE.items():
            st.session_state["lab_orbita_" + campo] = valor
        st.rerun()

tema.fijar(seleccion, paleta)
UI.theme(False)

# La vista de laboratorio jamás apunta al SQLite institucional.
if "_lab_calendar_db_path" not in st.session_state:
    ruta_temporal = (
        Path(tempfile.gettempdir())
        / f"atrio_calendario_demo_{uuid4().hex}.sqlite3"
    )
    st.session_state["_lab_calendar_db_path"] = str(ruta_temporal)
CAL.DB_PATH = Path(st.session_state["_lab_calendar_db_path"])
CAL.init_db()

ahora = datetime.now(ZoneInfo("America/Mexico_City"))
hoy = ahora.date()
cursos = [
    {
        "id": "LAB-001",
        "docente": "DOCENTE DE PRUEBA",
        "nombre": "INFORMÁTICA BÁSICA · MUESTRA",
        "curso": "INFORMÁTICA BÁSICA · MUESTRA",
        "tipo": "Extensión",
        "inicio": "2026-11-10",
        "fin": "2026-12-10",
        "duracion": 60,
        "horas": 60,
        "horario": "MARTES A SÁBADO · 09:00–12:00",
        "aula": "Taller de muestra",
    },
    {
        "id": "LAB-002",
        "docente": "DOCENTE DE PRUEBA",
        "nombre": "HERRAMIENTAS DIGITALES · MUESTRA",
        "curso": "HERRAMIENTAS DIGITALES · MUESTRA",
        "tipo": "Repositorio",
        "inicio": "2026-11-17",
        "fin": "2026-12-17",
        "duracion": 40,
        "horas": 40,
        "horario": "MARTES A SÁBADO · 15:00–17:00",
        "aula": "Taller de muestra",
    },
    {
        "id": "LAB-003",
        "docente": "DOCENTE DE PRUEBA",
        "nombre": "HOJA DE CÁLCULO · MUESTRA",
        "curso": "HOJA DE CÁLCULO · MUESTRA",
        "tipo": "Regular",
        "inicio": "2026-10-01",
        "fin": "2026-10-30",
        "duracion": 30,
        "horas": 30,
        "horario": "MARTES A SÁBADO · 10:00–12:00",
        "aula": "Aula de muestra",
    },
]


def _sembrar_agenda_demostrativa():
    """Crea actividades inventadas una sola vez en la base temporal."""
    if st.session_state.get("_lab_calendar_seeded"):
        return
    categorias = {c["nombre"]: c["id"] for c in CAL.obtener_categorias()}
    muestras = [
        {
            "titulo": "Reunión de coordinación · demostración",
            "descripcion": "Compromiso ficticio del Área de Capacitación.",
            "categoria_id": categorias.get("Reuniones"),
            "tipo": "Reunión",
            "prioridad": "Alta",
            "fecha_inicio": hoy + timedelta(days=2),
            "hora_inicio": "10:00",
            "hora_fin": "11:00",
            "todo_el_dia": False,
            "modulo_vinculado": "Ninguno",
            "recordatorio": "Ninguno",
            "repeticion": "No se repite",
            "lugar": "CECATI 31 · muestra",
        },
        {
            "titulo": "Entrega de informe · demostración",
            "descripcion": "Entrega ficticia ajena a MCE y PEA, registrada en Mi Calendario.",
            "categoria_id": categorias.get("Constancias y documentos"),
            "tipo": "Compromiso",
            "prioridad": "Media",
            "fecha_inicio": hoy + timedelta(days=4),
            "fecha_limite": hoy + timedelta(days=4),
            "todo_el_dia": True,
            "modulo_vinculado": "Ninguno",
            "recordatorio": "Ninguno",
            "repeticion": "No se repite",
        },
    ]
    for evento in muestras:
        CAL.guardar_evento(evento)
    st.session_state["_lab_calendar_seeded"] = True


_sembrar_agenda_demostrativa()

# Estos indicadores y tareas son deliberadamente ficticios; el tablero no lee
# el SISAE ni la SQLite institucional durante esta vista de prueba.
metricas_demo = {
    "disponible": True,
    "alumnos_unicos": 24,
    "inscripciones": 31,
    "corte": "Corte ficticio de demostración",
}
tareas_demo = [
    {
        "id": "LAB-TAREA-PEA",
        "proceso": "Elaboración de PEAs",
        "curso": "INFORMÁTICA BÁSICA · MUESTRA",
        "docente": "DOCENTE DE PRUEBA",
        "tipo_curso": "Extensión",
        "fecha": (hoy + timedelta(days=1)).isoformat(),
        "motivo": "Ejemplo ficticio: el curso se aproxima y el PEA debe estar listo con cinco días de anticipación.",
        "accion": "Revisar y elaborar el PEA del curso de muestra.",
        "modulo": "Preparar PEA",
        "estado": "Pendiente",
        "prioridad": "Alta",
        "responsable": "Me corresponde",
        "fuente": "Demostración",
        "certeza": "Confirmado",
    },
    {
        "id": "LAB-TAREA-ACM",
        "proceso": "Cursos ACM",
        "curso": "ACM · TALLER DE MUESTRA",
        "docente": "DOCENTE DE PRUEBA",
        "tipo_curso": "Acción móvil",
        "fecha": (hoy + timedelta(days=5)).isoformat(),
        "motivo": "Ejemplo ficticio: el grupo ACM se aproxima a su fecha de inicio.",
        "accion": "Revisar oficio, sede y preparación del curso.",
        "modulo": "Acciones Móviles",
        "estado": "Aviso",
        "prioridad": "Media",
        "responsable": "Me corresponde",
        "fuente": "Demostración",
        "certeza": "Aviso",
    },
]

TINI.render(
    cursos,
    hoy,
    metricas_sisae=metricas_demo,
    tareas=tareas_demo,
    incluir_calendario=True,
)
st.sidebar.caption(
    "Los cambios de agenda se guardan solo en el SQLite temporal de esta sesión."
)
