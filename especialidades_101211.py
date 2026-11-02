"""Especialidades de Programación para Ajustes > perfil docente.
No edita Excel ni reasigna grupos; devuelve sugerencias verificadas.
"""
from __future__ import annotations
import re
import unicodedata
from pathlib import Path
from openpyxl import load_workbook

CATALOGO = (
    'Administración',
    'Artes Gráficas',
    'Asistencia Educativa',
    'Asistencia Ejecutiva',
    'Contabilidad',
    'Electricidad',
    'Elaboración de Dibujos Arquitectónicos e Industriales',
    'Informática',
    'Inglés',
    'Máquinas-Herramienta',
    'Prótesis Dental',
    'Refrigeración y Aire Acondicionado',
    'Soldadura y Pailería',
)


def _norm(value):
    s = unicodedata.normalize('NFKD', str(value or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\s*[-–—]\s*', '-', s.upper())
    return ' '.join(s.split())


def _es_especialidad(antecedente, trayectoria, clave):
    """No confundir sector, trayectoria ocupacional y especialidad.
    Regla prioritaria: reconocimiento exacto en el catálogo; los dos códigos
    de trayectorias que usan título largo se apoyan en área/código oficial.
    """
    a, b, c = _norm(antecedente), _norm(trayectoria), _norm(clave)
    known = {_norm(x): x for x in CATALOGO}
    if b in known:
        return known[b]
    if a in known:
        return known[a]
    if c.startswith('04-SIEME-') and 'ELECTRIC' in b:
        return 'Electricidad'
    if c.startswith('22-ULIDC-') and 'LENGUA INGLESA' in b:
        return 'Inglés'
    return None  # No inferir especialidad a partir del nombre del curso.


def _por_docente(programacion):
    file = Path(programacion)
    if not file.is_file():
        return {}, 'No se encontró el Excel de Programación en los recursos de ATRIO.'
    book = None
    try:
        book = load_workbook(file, read_only=True, data_only=True)
        out = {}
        for sheet in book:
            actual_area = ''
            found = set()
            for cells in sheet.iter_rows(min_row=1, max_col=2, values_only=True):
                first = str(cells[0] or '').strip()
                second = str(cells[1] or '').strip()
                if not first:
                    continue
                if re.match(r'^\d{2}-[A-Z0-9]+-20\d{2}[A-Z]?$', _norm(first)):
                    esp = _es_especialidad(actual_area, second, first)
                    if esp:
                        found.add(esp)
                    actual_area = ''
                elif not second and first and _norm(first) not in {
                    'CLAVE', 'EXTENSION', 'REGULAR', 'REPOSITORIO',
                } and not first.upper().startswith(('SUBSECRETAR', 'DIRECCION', 'PROGRAMACION', 'CICLO ESCOLAR', 'NOMBRE DEL DOCENTE', 'CLAVE DEL CENTRO')):
                    actual_area = first
            if found:
                out[_norm(sheet.title)] = tuple(sorted(found, key=_norm))
        return out, None
    except Exception as exc:
        # No invalidar el resto de Ajustes si el recurso no se puede leer.
        return {}, 'No fue posible interpretar las especialidades en Programación (' + type(exc).__name__ + ').'
    finally:
        if book is not None:
            book.close()


def sugerencias_docente(programacion, docente):
    por_docente, error = _por_docente(programacion)
    return list(por_docente.get(_norm(docente), ())), error


def opciones(guardada, propuestas):
    """Primero coincidencias de ese docente; después el catálogo completo."""
    ordered = []
    for val in [*propuestas, *CATALOGO]:
        if _norm(val) not in {_norm(x) for x in ordered}:
            ordered.append(val)
    guardada = str(guardada or '').strip()
    if guardada and not re.search(r'[\\/]|\.(?:png|jpg|jpeg)\b', guardada, re.I):
        if _norm(guardada) not in {_norm(x) for x in ordered}:
            ordered.insert(0, guardada)
    return ordered
