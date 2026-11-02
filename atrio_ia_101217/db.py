"""No se aceptan sentencias SQL redactadas por la persona o por Gemini."""
import sqlite3
from pathlib import Path

_QUERIES = {
    'grupos_activos': 'SELECT COUNT(*) FROM groups WHERE active=1',
    'expedientes_historicos': 'SELECT COUNT(*) FROM pea_hist_101212',
}


def ejecutar_lectura(root: Path, consulta: str) -> int:
    if consulta not in _QUERIES:
        raise ValueError('Consulta fuera del catálogo de consultas autorizadas.')
    path = (Path(root).resolve()/'datos'/'atrio.sqlite3')
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError('No se encontró la base esperada.')
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('PRAGMA busy_timeout=2500')
        return int(conn.execute(_QUERIES[consulta]).fetchone()[0])
    finally:
        conn.close()
