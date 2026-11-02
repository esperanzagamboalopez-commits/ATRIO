"""ATRIO 10.12.8 — edición conservadora de párrafos narrativos de oficios ACM.

Trabaja EXCLUSIVAMENTE sobre bytes DOCX provisionalmente generados. Conserva los
runs, estilos, tablas, membretes, firmas, imágenes y la plantilla original.
No utiliza IA ni solicitudes externas.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from io import BytesIO
from docx import Document

MAX_PARAGRAPHS = 12
MAX_LENGTH = 3200


def extraer_parrafos_editables(data: bytes):
    """Párrafos narrativos entre PRESENTE y ATENTAMENTE (excluye datos de grupos)."""
    doc = Document(BytesIO(data))
    active = False
    rows = []
    for index, p in enumerate(doc.paragraphs):
        content = p.text.strip()
        if content.upper() == 'PRESENTE':
            active = True
            continue
        if content.upper() == 'ATENTAMENTE':
            break
        if not active or not content:
            continue
        # El grupo único se inserta en un párrafo. No debe editarse como prosa;
        # sus datos están protegidos y provienen de Programación.
        if content.startswith('Grupo 1\n') and 'Inicio:' in content:
            continue
        if content.startswith('Grupo 1') and 'Término:' in content:
            continue
        if content.startswith('No. de Oficio'):
            continue
        rows.append({'indice': index, 'texto': p.text})
        if len(rows) >= MAX_PARAGRAPHS:
            break
    return rows


def _editar_preservando_runs(parrafo, texto_nuevo: str):
    """Repartir caracteres conservados a su run original y los nuevos al run cercano.

    El algoritmo evita hacer parrafo.text=..., que borraría estilos mixtos, y
    conserva las mismas cantidades/atributos de runs del documento.
    """
    runs = parrafo.runs
    if not runs:
        raise ValueError('El párrafo no tiene fragmentos de texto editables.')
    original = ''.join(run.text for run in runs)
    if original == texto_nuevo:
        return
    if not texto_nuevo.strip():
        raise ValueError('No se puede vaciar completamente un párrafo del oficio.')
    if len(texto_nuevo) > MAX_LENGTH:
        raise ValueError(f'El texto excede el máximo de {MAX_LENGTH} caracteres.')
    # Cada posición original se vincula con su run y su estilo.
    owners = [i for i, run in enumerate(runs) for _ in run.text]
    pieces = ['' for _ in runs]
    def owner_at(pos):
        if not owners: return 0
        return owners[min(max(pos, 0), len(owners)-1)]
    matcher = SequenceMatcher(None, original, texto_nuevo, autojunk=False)
    for op, a, b, c, d in matcher.get_opcodes():
        if op == 'equal':
            for j in range(a, b):
                pieces[owner_at(j)] += original[j]
        elif op in ('insert', 'replace'):
            pieces[owner_at(a)] += texto_nuevo[c:d]
    for run, value in zip(runs, pieces):
        run.text = value
    if parrafo.text != texto_nuevo:
        raise ValueError('No se pudo conservar el párrafo después de editarlo.')


def aplicar_ediciones(base: bytes, cambios: dict[int, str]):
    """Genera un NUEVO Word a partir de la copia previa. No guarda en disco."""
    elegibles = {p['indice']: p['texto'] for p in extraer_parrafos_editables(base)}
    if any(k not in elegibles for k in cambios):
        raise ValueError('Intento de editar un apartado protegido del Word.')
    # Sin modificaciones, reutilizar EXACTAMENTE los bytes de la vista previa.
    if not cambios:
        return base, []
    doc = Document(BytesIO(base))
    diferencias = []
    for idx in sorted(cambios):
        text = str(cambios[idx]).replace('\r\n', '\n').replace('\r', '\n')
        if text != elegibles[idx]:
            _editar_preservando_runs(doc.paragraphs[idx], text)
            diferencias.append({'parrafo': idx, 'antes': elegibles[idx], 'despues': text})
    dest = BytesIO()
    doc.save(dest)
    data = dest.getvalue()
    check = Document(BytesIO(data))
    if len(check.tables) != len(Document(BytesIO(base)).tables):
        raise ValueError('Cambió la estructura de las tablas: se canceló la edición.')
    return data, diferencias


def validar_integridad(data: bytes, *, docente: str, institucion: str, grupos: list[dict], folio: str):
    """Verifica que los datos mínimos oficiales permanezcan visibles tras editar."""
    doc = Document(BytesIO(data))
    all_text = '\n'.join(p.text for p in doc.paragraphs)
    all_text += '\n' + '\n'.join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    all_fold = ' '.join(all_text.casefold().split())
    needed = [docente, institucion, folio]
    # En uno o varios cursos cada nombre debe figurar en el cuerpo o tabla.
    needed.extend(g['curso'] for g in grupos)
    missing = [str(x) for x in needed if str(x).strip() and ' '.join(str(x).casefold().split()) not in all_fold]
    if missing:
        raise ValueError('Se quitó información oficial durante la edición: '+', '.join(missing[:4])+'. Restáurala o cambia los campos de origen.')
    return True
