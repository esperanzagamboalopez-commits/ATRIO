import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tema


def test_vista_streamlit_aislada_no_importa_motores_ni_conecta_recursos():
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


def test_vista_streamlit_usa_inicio_real_y_registros_ficticios():
    root = Path(__file__).resolve().parents[1]
    source = (root / "laboratorio_orbita_streamlit.py").read_text(encoding="utf-8")
    template = (root / "inicio.html").read_text(encoding="utf-8")

    assert "inicio.html" in source
    assert "LAB-001" in source
    assert "DOCENTE DE PRUEBA" in source
    assert "__COURSES__" in template
    assert "__SISAE_SUMMARY__" in template
    assert tema.ORBITA in tema.OPCIONES


def test_inicio_no_muestra_panel_informativo_ni_accion_simulada():
    root = Path(__file__).resolve().parents[1]
    template = (root / "inicio.html").read_text(encoding="utf-8")
    preview = (root / "laboratorio_orbita_streamlit.py").read_text(encoding="utf-8")
    interface = (root / "interfaz.py").read_text(encoding="utf-8")

    assert "Lo que requiere tu atención" not in template
    assert "__ALERT_TEXT__" not in template
    assert 'id="check"' not in template
    assert "q('#check')" not in template
    assert "Ver cursos para revisar" not in template
    assert "PEA y trámites en MCE" not in template
    assert "pea-mce-band" not in template
    assert "__ALERT_TEXT__" not in preview
    assert "__ALERT_TEXT__" not in interface


def test_inicio_va_primero_y_el_resumen_del_laboratorio_queda_al_pie():
    source = (Path(__file__).resolve().parents[1] / "laboratorio_orbita_streamlit.py").read_text(
        encoding="utf-8"
    )

    assert source.index("components.html(inicio") < source.index(
        'st.subheader("ATRIO · Vista previa de integración")'
    )
    assert 'c1.metric("Grupos de muestra"' in source
    assert 'c2.metric("PEA por revisar"' in source
    assert 'c3.metric("Corte SISAE"' in source
    assert 'st.info("Vista aislada:' in source


def test_no_se_muestran_componentes_genericos_sin_contexto():
    source = (Path(__file__).resolve().parents[1] / "laboratorio_orbita_streamlit.py").read_text(
        encoding="utf-8"
    )

    assert "Componentes de interfaz" not in source
    assert "Acción de muestra" not in source
    assert "Campo de ejemplo" not in source
    assert "Selector de muestra" not in source
