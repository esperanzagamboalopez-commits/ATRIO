import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tema


@pytest.fixture(autouse=True)
def restaurar_tema():
    yield
    tema.fijar(tema.DEFECTO)


def test_orbita_es_opcion_sin_reemplazar_los_temas_existentes():
    assert tema.ORBITA in tema.OPCIONES
    assert tema.EDITORIAL_ROSA in tema.OPCIONES
    assert tema.EDITORIAL in tema.OPCIONES
    assert tema.JAPANDI in tema.OPCIONES
    assert tema.DEFECTO == tema.EDITORIAL_ROSA


def test_orbita_publica_tokens_de_identidad_y_calendario():
    tema.fijar(tema.ORBITA)
    tokens = tema.variables()

    assert tokens["--atrio-bg"] == "#F1F0E8"
    assert tokens["--atrio-neon"] == "#087E83"
    assert tokens["--atrio-oro"] == "#D4E36A"
    assert tokens["--atrio-calendario"] == "#F5E8C8"
    assert tokens["--atrio-encabezado"] == "#172F3B"
    assert "linear-gradient" in tokens["--atrio-hero-gradient"]
    assert "backdrop-filter" not in tema.root_css().lower()


def test_paleta_personalizada_solo_sobrescribe_los_cuatro_colores_autorizados():
    tema.fijar(tema.ORBITA, {
        "fondo": "#123456",
        "acento": "#ABCDEF",
        "secundario": "#FFEEDD",
        "calendario": "#112233",
        "texto": "#000000",
        "extra": "#FFFFFF",
    })
    tokens = tema.variables()

    assert tokens["--atrio-bg"] == "#123456"
    assert tokens["--atrio-neon"] == "#ABCDEF"
    assert tokens["--atrio-oro"] == "#FFEEDD"
    assert tokens["--atrio-calendario"] == "#112233"
    assert tokens["--atrio-tinta"] == "#172F3B"


def test_colores_invalidos_se_descartan_y_se_conserva_la_paleta_base():
    tema.fijar(tema.ORBITA, {
        "fondo": "rojo",
        "acento": "#12GG45",
        "secundario": None,
        "calendario": "#aabbcc",
    })
    tokens = tema.variables()

    assert tokens["--atrio-bg"] == "#F1F0E8"
    assert tokens["--atrio-neon"] == "#087E83"
    assert tokens["--atrio-oro"] == "#D4E36A"
    assert tokens["--atrio-calendario"] == "#AABBCC"


def test_paleta_de_orbita_no_modifica_los_demas_temas():
    tema.fijar(tema.ORBITA, {"fondo": "#123456"})
    orbita_fondo = tema.variables()["--atrio-bg"]

    tema.fijar(tema.EDITORIAL_ROSA)
    rosa = tema.variables()

    assert orbita_fondo == "#123456"
    assert rosa["--atrio-bg"] == tema.PRESETS[tema.EDITORIAL_ROSA]["bg"]
    assert rosa["--atrio-bg"] != orbita_fondo


def test_validador_acepta_hexadecimal_de_seis_digitos_y_normaliza_mayusculas():
    assert tema.validar_paleta({
        "fondo": "#a1b2c3",
        "acento": "#AABBCC",
        "calendario": "#000000",
    }) == {
        "fondo": "#A1B2C3",
        "acento": "#AABBCC",
        "calendario": "#000000",
    }
