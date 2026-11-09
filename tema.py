"""ATRIO · Temas visuales.

Cuatro presets. El preset activo se fija con fijar() al inicio de cada ejecución
(lo lee app.py desde C.setting('tema_visual')). root_css() devuelve las variables
CSS :root que consumen la app Streamlit, Inicio y las hojas en iframe.
Solo afecta presentación; no toca datos ni lógica de negocio.
"""
import re

GLASS_EXECUTIVE = 'Glass Executive'
JAPANDI = 'Japandi Minimalista'
CYBER = 'Cyber-Neon'
EDITORIAL = 'Editorial Premium'
EDITORIAL_ROSA = 'Editorial Rosa'
ORBITA = 'ATRIO Órbita'

# Valores base de cada identidad. El resto de la aplicación consume estos tokens.
PALETA_ORBITA = {
    'fondo': '#F1F0E8',
    'acento': '#087E83',
    'secundario': '#D4E36A',
    'calendario': '#F5E8C8',
}

PRESETS = {
    EDITORIAL_ROSA: dict(dark=False, bg='#FBF7F2', surface='#FFFFFF', accent='#FF1493', gold='#D4AF37',
                         text='#2A2326', titulo='#2A2326', muted='#6B6063', border='#2A2326', sidebar='#F4EDE4',
                         sobre='#2A2326', calendar='#F7E8EF', header='#292326',
                         hero='linear-gradient(115deg,#F8E9EE 0%,#FBF7F2 58%,#F1DCE5 100%)'),
    GLASS_EXECUTIVE: dict(dark=True, bg='#09090B', surface='#18181B', accent='#FF1493', gold='#D4AF37',
                          text='#F5F1EA', titulo='#FFFFFF', muted='#A1A1AA', border='#FFFFFF', sidebar='#09090B',
                          calendar='#F2E9ED', header='#09090B',
                          hero='linear-gradient(115deg,#242027 0%,#18181B 58%,#34242E 100%)'),
    JAPANDI: dict(dark=False, bg='#FAFAF9', surface='#FFFFFF', accent='#5F7A5E', gold='#8A7F5B',
                  text='#1C1917', titulo='#1C1917', muted='#57534E', border='#1C1917', sidebar='#F1F1EC',
                  calendar='#E8EEE7', header='#263326',
                  hero='linear-gradient(115deg,#E7EDE5 0%,#FAFAF9 58%,#E2E7D9 100%)'),
    CYBER: dict(dark=True, bg='#0F172A', surface='#1E293B', accent='#22D3EE', gold='#38BDF8',
                text='#F8FAFC', titulo='#FFFFFF', muted='#94A3B8', border='#FFFFFF', sidebar='#0B1222',
                calendar='#E3F3F5', header='#0B1222',
                hero='linear-gradient(115deg,#182A3F 0%,#1E293B 58%,#173748 100%)'),
    EDITORIAL: dict(dark=False, bg='#FBF7F2', surface='#FFFFFF', accent='#6D1F2F', gold='#9A7A45',
                    text='#2A2326', titulo='#2A2326', muted='#6B6063', border='#2A2326', sidebar='#F4EDE4',
                    calendar='#F1E9E4', header='#2A2326',
                    hero='linear-gradient(115deg,#F1E6DF 0%,#FBF7F2 58%,#E9DCD1 100%)'),
    ORBITA: dict(dark=False, bg=PALETA_ORBITA['fondo'], surface='#FBFAF4',
                 accent=PALETA_ORBITA['acento'], gold=PALETA_ORBITA['secundario'],
                 text='#172F3B', titulo='#172F3B', muted='#526C70', border='#C5D4CF',
                 sidebar='#E1E9E3', calendar=PALETA_ORBITA['calendario'],
                 header='#172F3B', sobre='#FFFFFF',
                 hero='linear-gradient(115deg,#CFE4DD 0%,#F1F0E8 58%,#DCE8B4 100%)'),
}

# Órbita se incorpora como opción; el tema predeterminado anterior se conserva.
OPCIONES = [EDITORIAL_ROSA, ORBITA, EDITORIAL, JAPANDI]
DEFECTO = EDITORIAL_ROSA

_activo = DEFECTO
_personalizacion = {}


def validar_paleta(paleta):
    """Devuelve únicamente los cuatro colores admitidos y en formato hexadecimal seguro."""
    if not isinstance(paleta, dict):
        return {}
    return {
        key: value.upper()
        for key, value in paleta.items()
        if key in PALETA_ORBITA and isinstance(value, str)
        and re.fullmatch(r'#[0-9a-fA-F]{6}', value)
    }


def paleta_predeterminada():
    """Copia independiente de la paleta base de ATRIO Órbita."""
    return dict(PALETA_ORBITA)


def fijar(nombre, personalizacion=None):
    """Fija el preset activo y, para Órbita, una paleta personalizada validada."""
    global _activo, _personalizacion
    _activo = nombre if nombre in PRESETS else DEFECTO
    _personalizacion = validar_paleta(personalizacion) if _activo == ORBITA else {}
    return _activo


def activo():
    return _activo


def _rgb(hex_):
    h = hex_.lstrip('#')
    return ','.join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def variables(nombre=None):
    objetivo = nombre or _activo
    p = dict(PRESETS[objetivo])
    if objetivo == ORBITA and objetivo == _activo:
        campos = {'fondo': 'bg', 'acento': 'accent', 'secundario': 'gold', 'calendario': 'calendar'}
        for clave, campo in campos.items():
            if clave in _personalizacion:
                p[campo] = _personalizacion[clave]
    calendario = p.get('calendar', p['surface'])
    encabezado = p.get('header', p['titulo'])
    return {
        '--atrio-bg': p['bg'], '--atrio-bg-rgb': _rgb(p['bg']),
        '--atrio-surface': p['surface'], '--atrio-cristal-rgb': _rgb(p['surface']),
        '--atrio-borde-rgb': _rgb(p['border']),
        '--atrio-neon': p['accent'], '--atrio-neon-rgb': _rgb(p['accent']),
        '--atrio-oro': p['gold'], '--atrio-oro-rgb': _rgb(p['gold']),
        '--atrio-tinta': p['text'], '--atrio-titulo': p['titulo'], '--atrio-tenue': p['muted'],
        '--atrio-sidebar': p['sidebar'], '--atrio-cristal': f"rgba({_rgb(p['surface'])},0.6)",
        '--atrio-borde': f"rgba({_rgb(p['border'])},0.18)",
        '--atrio-acento-suave': f"rgba({_rgb(p['accent'])},0.14)",
        '--atrio-sobre-acento': p.get('sobre') or ('#09090B' if p['accent'] in ('#22D3EE', '#D4AF37') else '#FFFFFF'),
        '--atrio-calendario': calendario, '--atrio-calendario-rgb': _rgb(calendario),
        '--atrio-encabezado': encabezado, '--atrio-encabezado-rgb': _rgb(encabezado),
        '--atrio-encabezado-texto': p.get('header_text', '#FFFFFF'),
        '--atrio-encabezado-acento': p.get('header_accent', p['gold']),
        '--atrio-hero-gradient': p.get('hero', 'linear-gradient(115deg,var(--atrio-surface),var(--atrio-bg))'),
        '--atrio-sombra': '0 6px 24px rgba(42,35,38,.08)' if not p['dark'] else '0 0 20px rgba(255,20,147,.25)',
        '--atrio-scheme': 'dark' if p['dark'] else 'light',
        # Estados (verde, rojo, ámbar) legibles en tema claro y oscuro.
        '--atrio-ok': '#4ADE80' if p['dark'] else '#15803D',
        '--atrio-ok-bg': 'rgba(74,222,128,.14)' if p['dark'] else 'rgba(21,128,61,.10)',
        '--atrio-error': '#F87171' if p['dark'] else '#B91C1C',
        '--atrio-error-bg': 'rgba(248,113,113,.14)' if p['dark'] else 'rgba(185,28,28,.08)',
        '--atrio-alerta': '#FBBF24' if p['dark'] else '#A16207',
        '--atrio-alerta-bg': 'rgba(251,191,36,.14)' if p['dark'] else 'rgba(161,98,7,.10)',
    }


def root_css(nombre=None):
    vars_ = variables(nombre)
    decl = ';'.join(f'{k}:{v}' for k, v in vars_.items())
    return (f':root{{{decl}}}'
            'html,body{background:transparent!important;color:var(--atrio-tinta)}'
            ':root{color-scheme:' + vars_['--atrio-scheme'] + '}')


# Literales de la hoja Glass base -> variables del tema activo.
_LITERALES = [
    (r'rgba\(\s*24\s*,\s*24\s*,\s*27\s*,', 'rgba(var(--atrio-cristal-rgb),'),
    (r'rgba\(\s*9\s*,\s*9\s*,\s*11\s*,', 'rgba(var(--atrio-bg-rgb),'),
    (r'rgba\(\s*255\s*,\s*20\s*,\s*147\s*,', 'rgba(var(--atrio-neon-rgb),'),
    (r'rgba\(\s*212\s*,\s*175\s*,\s*55\s*,', 'rgba(var(--atrio-oro-rgb),'),
    (r'rgba\(\s*255\s*,\s*255\s*,\s*255\s*,', 'rgba(var(--atrio-borde-rgb),'),
    (r'#F5F1EA', 'var(--atrio-tinta)'),
    (r'#FF1493', 'var(--atrio-neon)'),
    (r'#D4AF37', 'var(--atrio-oro)'),
    (r'#A1A1AA', 'var(--atrio-tenue)'),
    (r'#18181B', 'var(--atrio-surface)'),
    (r'#09090B', 'var(--atrio-bg)'),
]


def tematizar(css):
    """Convierte literales Glass de un bloque CSS en variables del tema activo.
    No debe recibir un bloque :root con valores literales (eso lo define root_css)."""
    for patron, reemplazo in _LITERALES:
        css = re.sub(patron, reemplazo, css, flags=re.I)
    return css
