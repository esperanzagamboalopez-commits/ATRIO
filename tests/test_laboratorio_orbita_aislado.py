import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tema


def test_vista_streamlit_aislada_no_importa_aplicacion_ni_conecta_recursos():
    source = (Path(__file__).resolve().parents[1] / "laboratorio_orbita_streamlit.py").read_text(
        encoding="utf-8"
    )

    assert "import centro" not in source
    assert "import app" not in source
    assert "from centro" not in source
    assert "C.RES" not in source
    assert "sqlite3.connect" not in source
    assert "SISAE.zip" not in source
    assert "PROGRAMACION DE CURSOS.xlsx" not in source
    assert "tema.fijar(seleccion, paleta)" in source
    assert "TINI.render(" in source


def test_vista_previa_usa_grupos_y_tareas_ficticias():
    source = (Path(__file__).resolve().parents[1] / "laboratorio_orbita_streamlit.py").read_text(
        encoding="utf-8"
    )

    assert "LAB-001" in source
    assert "LAB-002" in source
    assert "LAB-003" in source
    assert "DOCENTE DE PRUEBA" in source
    assert "metricas_demo" in source
    assert "tareas_demo" in source
    assert "alumnos_unicos" in source
    assert "inscripciones" in source
    assert tema.ORBITA in tema.OPCIONES


def test_vista_previa_no_renderiza_la_plantilla_html_heredada_ni_panel_tecnico():
    source = (Path(__file__).resolve().parents[1] / "laboratorio_orbita_streamlit.py").read_text(
        encoding="utf-8"
    )

    assert "inicio.html" not in source
    assert "components.html" not in source
    assert "ATRIO · Vista previa de integración" not in source
    assert "Componentes de interfaz" not in source
    assert "No conectado" not in source


def test_inicio_operativo_usa_el_tablero_compartido():
    root = Path(__file__).resolve().parents[1]
    interface = (root / "interfaz.py").read_text(encoding="utf-8")
    pending = (root / "pendientes.py").read_text(encoding="utf-8")
    dashboard = (root / "tablero_inicio.py").read_text(encoding="utf-8")

    assert "import tablero_inicio as TI" in interface
    assert "TI.render(data, today)" in interface
    assert "from tablero_inicio import cargar_tareas" in pending
    assert "tareas = tareas if tareas is not None else cargar_tareas(grupos, hoy)" in dashboard
    assert "Prioridades de hoy" in dashboard
    assert "Panorama de capacitación" in dashboard


def test_vista_previa_usa_sqlite_temporal_para_mi_calendario():
    source = (Path(__file__).resolve().parents[1] / "laboratorio_orbita_streamlit.py").read_text(
        encoding="utf-8"
    )

    assert "tempfile.gettempdir()" in source
    assert 'CAL.DB_PATH = Path(st.session_state["_lab_calendar_db_path"])' in source
    assert "CAL.init_db()" in source
    assert "TINI.render(" in source
    assert "incluir_calendario=True" in source
    assert "sqlite temporal" in source.lower()


def test_laboratorio_no_usa_datos_operativos_ni_estado_simulado_persistente():
    source = (Path(__file__).resolve().parents[1] / "laboratorio_orbita_streamlit.py").read_text(
        encoding="utf-8"
    )

    assert "C.set_setting" not in source
    assert "C.status" not in source
    assert "PROGRAMACION DE CURSOS.xlsx" not in source
    assert "SISAE.zip" not in source
    assert "datos/atrio.sqlite3" not in source
