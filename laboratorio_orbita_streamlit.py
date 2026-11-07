"""Vista previa aislada de ATRIO Órbita en Streamlit.

No importa app.py ni centro.py. No abre SQLite, Excel, SISAE ni documentos del plantel.
El calendario usa una base temporal por sesión y solo recibe cursos/actividades ficticios.
"""
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import tema
import interfaz as UI
import calendario as CAL


st.set_page_config(
    page_title="ATRIO · Vista previa",
    page_icon="◈",
    layout="wide",
)

PALETA_BASE = tema.paleta_predeterminada()
st.sidebar.markdown("### Laboratorio visual")
st.sidebar.caption("Vista aislada · solo datos ficticios")

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
tokens = tema.variables()

# Aislamiento: el calendario de esta vista nunca apunta al SQLite institucional.
if "_lab_calendar_db_path" not in st.session_state:
    ruta_temporal = Path(tempfile.gettempdir()) / f"atrio_calendario_demo_{uuid4().hex}.sqlite3"
    st.session_state["_lab_calendar_db_path"] = str(ruta_temporal)
CAL.DB_PATH = Path(st.session_state["_lab_calendar_db_path"])
CAL.init_db()

ahora = datetime.now(ZoneInfo("America/Mexico_City"))
hoy = ahora.date()
cursos = [
    {
        "id": "LAB-001",
        "docente": "DOCENTE DE PRUEBA",
        "curso": "INFORMÁTICA BÁSICA · MUESTRA",
        "tipo": "EXTENSIÓN",
        "inicio": "2026-11-10",
        "fin": "2026-12-10",
        "horas": 60,
        "horario": "MARTES A SÁBADO · 09:00–12:00",
        "alerta": "Registro demostrativo para revisión visual",
    },
    {
        "id": "LAB-002",
        "docente": "DOCENTE DE PRUEBA",
        "curso": "HERRAMIENTAS DIGITALES · MUESTRA",
        "tipo": "REPOSITORIO",
        "inicio": "2026-11-17",
        "fin": "2026-12-17",
        "horas": 40,
        "horario": "MARTES A SÁBADO · 15:00–17:00",
        "alerta": "",
    },
    {
        "id": "LAB-003",
        "docente": "DOCENTE DE PRUEBA",
        "curso": "HOJA DE CÁLCULO · MUESTRA",
        "tipo": "REGULAR",
        "inicio": "2026-10-01",
        "fin": "2026-10-30",
        "horas": 30,
        "horario": "MARTES A SÁBADO · 10:00–12:00",
        "alerta": "",
    },
]


def _sembrar_agenda_demostrativa():
    """Crea actividades inventadas una sola vez dentro del SQLite temporal."""
    if st.session_state.get("_lab_calendar_seeded"):
        return
    categorias = {c["nombre"]: c["id"] for c in CAL.obtener_categorias()}
    muestras = [
        {
            "titulo": "Revisión de agenda · demostración",
            "descripcion": "Actividad ficticia para probar la agenda diaria.",
            "categoria_id": categorias.get("Notas personales"),
            "tipo": "Tarea",
            "prioridad": "Media",
            "fecha_inicio": hoy,
            "todo_el_dia": True,
            "modulo_vinculado": "Ninguno",
            "recordatorio": "Ninguno",
            "repeticion": "No se repite",
            "lugar": "CECATI 31 · muestra",
        },
        {
            "titulo": "Visita a talleres · demostración",
            "descripcion": "Ejemplo de actividad institucional en el calendario.",
            "categoria_id": categorias.get("Visitas a talleres"),
            "tipo": "Evento",
            "prioridad": "Alta",
            "fecha_inicio": hoy + timedelta(days=4),
            "todo_el_dia": False,
            "hora_inicio": "10:00",
            "hora_fin": "12:00",
            "modulo_vinculado": "Ninguno",
            "recordatorio": "Ninguno",
            "repeticion": "No se repite",
            "lugar": "Taller de muestra",
        },
        {
            "titulo": "Seguimiento de trámite · demostración",
            "descripcion": "Fecha límite ficticia para revisar cómo se identifica un vencimiento.",
            "categoria_id": categorias.get("Seguimiento de trámites"),
            "tipo": "Compromiso",
            "prioridad": "Alta",
            "fecha_inicio": hoy + timedelta(days=2),
            "fecha_limite": hoy + timedelta(days=2),
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

# El calendario funcional aparece primero; los cursos solo aportan sus fechas de inicio/término.
CAL.render_inicio_calendario(cursos)

# Se conserva la composición aprobada de Inicio debajo del calendario funcional.
inicio = (Path(__file__).parent / "inicio.html").read_text(encoding="utf-8")
inicio = '<style>' + tema.root_css() + '</style>' + inicio
reemplazos = {
    "__COURSES__": json.dumps(cursos, ensure_ascii=False).replace("<", "\\u003c"),
    "__COUNT__": str(len(cursos)),
    "__TODAY__": hoy.isoformat(),
    "__GREETING__": (
        "Buenos días" if ahora.hour < 12
        else "Buenas tardes" if ahora.hour < 20
        else "Buenas noches"
    ),
    "__SISAE_SUMMARY__": (
        '<div class="sisae-data"><div><strong>Corte SISAE de demostración</strong>'
        '<div class="subtle">Sin corte de muestra.</div></div>'
        '<span class="sisae-number">—</span></div>'
    ),
    "__DARK_CSS__": "",
    "__TEMA_CSS__": tema.root_css(),
    "__SOFT__": tokens["--atrio-calendario"],
    "__STRONG__": tokens["--atrio-neon"],
}
for clave, valor in reemplazos.items():
    inicio = inicio.replace(clave, valor)

components.html(inicio, height=1320, scrolling=True)

# Resumen técnico del laboratorio, deliberadamente al final y con jerarquía discreta.
with st.container(border=True):
    st.subheader("ATRIO · Vista previa de integración")
    st.caption(
        "Esta vista no utiliza datos del plantel. La composición superior corresponde "
        "al archivo inicio.html real y contiene únicamente registros de demostración."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Grupos de muestra", "3", "Ficticios")
    c2.metric("PEA por revisar", "1", "Demostración")
    with c3:
        st.markdown("**SISAE**")
        st.caption("Sin corte de muestra.")
    st.info(
        "Vista aislada: la agenda guarda únicamente en el SQLite temporal de esta sesión; "
        "no ejecuta procesos ni modifica datos institucionales."
    )

st.caption(
    "El calendario conserva las actividades únicamente en un SQLite temporal de esta sesión. "
    "No se conecta a la base institucional ni a recursos reales."
)
