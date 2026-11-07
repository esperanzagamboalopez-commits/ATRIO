"""Vista previa aislada de ATRIO Órbita en Streamlit.

No importa app.py ni centro.py. No abre SQLite, Excel, SISAE ni documentos.
Usa los estilos reales de tema.py/interfaz.py e inicio.html con datos ficticios.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import tema
import interfaz as UI


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

# La composición real de Inicio es el contenido principal y aparece primero.
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
        '<div class="sisae-data"><div><strong>Resumen de muestra</strong>'
        '<div class="subtle">SISAE no está conectado en este laboratorio.</div></div>'
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

# Este bloque informativo queda al pie, en el espacio reservado para la antigua franja.
with st.container(border=True):
    st.subheader("ATRIO · Vista previa de integración")
    st.caption(
        "Esta vista no utiliza datos del plantel. La composición superior corresponde "
        "al archivo inicio.html real y contiene únicamente registros de demostración."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Grupos de muestra", "3", "Ficticios")
    c2.metric("PEA por revisar", "1", "Demostración")
    c3.metric("Corte SISAE", "No conectado", "Sin consulta")
    st.info("Vista aislada: ningún botón ejecuta procesos ni guarda cambios.")

st.caption(
    "Laboratorio de presentación solamente. Para ejecutar la aplicación real "
    "y conectar recursos institucionales se requiere una autorización separada."
)
