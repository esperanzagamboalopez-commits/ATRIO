"""Consultas verificables de matrícula de SISAE para el asistente ATRIO.

Solo lectura; no necesita Gemini, no accede al padrón, no expone datos
personales. El estado de verificación se refiere al cotejo entre claves de
INSCRIPCION y LISTAS, no a la vigencia del corte exportado.
"""
from __future__ import annotations

from pathlib import Path
import re
from zipfile import ZipFile

from . import fuentes
from .lector_sisae_101218 import _leer_dbf, CAMPOS, analizar, normalizar


def _periodo(q: str) -> str | None:
    """Solo interpreta expresiones inequívocas de los cuatro trimestres."""
    reglas = {
        '1': (r'\b(?:primer|primero|1er|1o)\s+(?:periodo|trimestre)\b',
              r'\b(?:periodo|trimestre)\s*(?:numero\s*)?1\b',
              r'\b(?:julio|jul)\s+(?:a|hasta)\s+(?:septiembre|sep)\b'),
        '2': (r'\b(?:segundo|2do)\s+(?:periodo|trimestre)\b',
              r'\b(?:periodo|trimestre)\s*(?:numero\s*)?2\b',
              r'\b(?:octubre|oct)\s+(?:a|hasta)\s+(?:diciembre|dic)\b'),
        '3': (r'\b(?:tercer|tercero|3er)\s+(?:periodo|trimestre)\b',
              r'\b(?:periodo|trimestre)\s*(?:numero\s*)?3\b',
              r'\b(?:enero|ene)\s+(?:a|hasta)\s+(?:marzo|mar)\b'),
        '4': (r'\b(?:cuarto|4to)\s+(?:periodo|trimestre)\b',
              r'\b(?:periodo|trimestre)\s*(?:numero\s*)?4\b',
              r'\b(?:abril|abr)\s+(?:a|hasta)\s+(?:junio|jun)\b'),
    }
    matches = [p for p, patterns in reglas.items() if any(re.search(x, q) for x in patterns)]
    if len(matches) > 1:
        raise ValueError('La pregunta menciona más de un periodo; indica uno solo para el desglose.')
    return matches[0] if matches else None


def _ciclo(q: str) -> str:
    found = set(re.findall(r'\b(20\d\d)[\s\-/]+(20\d\d)\b', q))
    if len(found) > 1:
        raise ValueError('La pregunta contiene varios ciclos. Indica cuál deseas consultar.')
    if found:
        year1, year2 = next(iter(found))
        return f'{year1}-{year2}'
    return '2026-2027'  # Vigente en esta versión. Se indica expresamente en la respuesta.


def _catalogo(ruta: Path) -> list[str]:
    with ZipFile(ruta) as z:
        matches = [i for i in z.infolist() if not i.is_dir()
                   and Path(i.filename.strip()).name.upper() == 'ESP.DBF']
        if len(matches) != 1:
            raise ValueError('El corte SISAE no contiene una tabla ESP.DBF única.')
        rows, _ = _leer_dbf(z, matches[0], CAMPOS['ESP.DBF'])
        return sorted({r['NOM_ESP'] for r in rows if r['NOM_ESP'].strip()})


def _especialidad(q: str, nombres: list[str]) -> str | None:
    """No inventa especialidades ni elige coincidencias ambiguas."""
    a = normalizar(q)
    coincidencias = []
    for nombre in nombres:
        n = normalizar(nombre)
        if n and re.search(r'(?<!\w)' + re.escape(n) + r'(?!\w)', a):
            coincidencias.append(nombre)
    if len(coincidencias) == 1:
        return coincidencias[0]
    if len(coincidencias) > 1:
        # Ej. 'informática' dentro de una denominación más extensa.
        maxlen = max(len(normalizar(n)) for n in coincidencias)
        mas_largas = [n for n in coincidencias if len(normalizar(n)) == maxlen]
        if len(mas_largas) == 1:
            return mas_largas[0]
        raise ValueError('Varias especialidades coinciden. Especifica el nombre exacto.')
    # Se permite una expresión parcial de longitud significativa SOLO si
    # identifica de forma inequívoca una especialidad oficial.
    for fragmento in re.findall(r'\b[a-z]{6,}\b', a):
        if fragmento in {'cuantos','cuantas','alumnos','alumnas','estudiantes',
                        'inscritos','inscritas','matricula','especialidad',
                        'tenemos','periodo','durante','segundo','primero',
                        'primer','ciclo','actuales','registrados'}:
            continue
        parciales = [n for n in nombres if fragmento in normalizar(n).split()]
        if len(parciales) == 1: return parciales[0]
    return None


def _aviso_no_verificado(causa: str, periodo: str = 'sin determinar'):
    msg = ('**No pude verificar la matrícula solicitada.** ' + causa +
           ' No sustituiré el resultado por el número de grupos de Programación.')
    return (fuentes.anotar(msg, fuente='SISAE · consulta no completada',
                          unidad='inscripciones/personas únicas', periodo=periodo,
                          corte='no comprobado', estado='no verificado'),
            'SISAE · sin cifra comprobada', {})


def responder_matricula(pregunta, C):
    """Devuelve la tupla esperada por la pestaña existente (texto,fuente,contexto)."""
    q = normalizar(pregunta)
    ruta = Path(C.ROOT) / 'datos' / 'recursos' / 'SISAE.zip'
    if not ruta.is_file() or ruta.is_symlink():
        return _aviso_no_verificado('No encontré el ZIP vigente en datos/recursos/SISAE.zip.')
    try:
        periodo = _periodo(q)
        ciclo = _ciclo(q)
        nombres = _catalogo(ruta)
        nombre = _especialidad(q, nombres)
        if not nombre:
            return _aviso_no_verificado(
                'Indica una especialidad registrada en el corte (por ejemplo, «Artes Gráficas»).',
                periodo=periodo or 'sin filtro')
        datos = analizar(ruta, nombre, ciclo, periodo)
    except (OSError, KeyError, ValueError, RuntimeError, EOFError) as exc:
        # Nunca hacer fallback a groups u otros totales si la matrícula falló.
        return _aviso_no_verificado(f'La consulta local de SISAE requiere revisión ({type(exc).__name__}).')
    estado = datos['estado']
    titulo = f"**SISAE · {datos['especialidad']} · ciclo {ciclo}**"
    if periodo:
        alcance = f'Periodo {periodo} (de inscripción)'
    else:
        alcance = 'Todos los periodos de inscripción encontrados para el ciclo en el archivo'
    cifra = (f"**{datos['inscripciones']} inscripciones** · "
             f"**{datos['personas_unicas']} personas únicas**" if datos['personas_unicas'] is not None
             else f"**{datos['inscripciones']} inscripciones provisionales** (personas únicas sin verificar)")
    cuerpo = [titulo, alcance, cifra,
              f"**Grupos con inscripciones:** {datos['grupos_con_inscripciones']}."]
    if estado != 'verificado':
        cuerpo.insert(1, '**Requiere revisión:** las fuentes no concilian plenamente; los conteos son provisionales.')
    else:
        cuerpo.append('**Conciliación:** coincidencias únicas de INSCRIPCION y LISTAS verificadas.')
    if datos['listas_filas_reiteradas']:
        cuerpo.append(f"**Control de duplicados:** {datos['listas_filas_reiteradas']} filas reiteradas en LISTAS no se sumaron.")
    if datos['inscripciones_filas_reiteradas']:
        cuerpo.append(f"**Advertencia:** {datos['inscripciones_filas_reiteradas']} filas reiteradas en INSCRIPCION; revisar la fuente principal.")
    if datos['solo_inscripcion'] or datos['solo_listas']:
        cuerpo.append(f"**Diferencias:** solo INSCRIPCION {datos['solo_inscripcion']}, solo LISTAS {datos['solo_listas']}.")
    fecha = datos['fecha_nominal_del_archivo']
    if fecha:
        corte = f'fecha incluida en nombre del ZIP: {fecha} (no prueba hora de exportación)'
    else:
        corte = 'fecha de exportación no identificada (SISAE.zip sin fecha en el nombre)'
    ultima = datos['ultima_fecha_inscripcion_registrada']
    if ultima:
        cuerpo.append(f'**Última fecha de inscripción detectada en el archivo:** {ultima} (no es fecha de exportación).')
    if datos['ultima_fecha_inscripcion_especialidad']:
        cuerpo.append(f"**Última inscripción de esta especialidad:** {datos['ultima_fecha_inscripcion_especialidad']}.")
    cuerpo.append('El ZIP es una **copia de SISAE**, no necesariamente la matrícula vigente a esta hora.')
    texto = fuentes.anotar('\n\n'.join(cuerpo), fuente='SISAE.zip: ESP.DBF + PROG_CURSOS1.DBF + INSCRIPCION.DBF + LISTAS.DBF',
                            unidad='inscripciones y personas únicas', periodo=f'ciclo {ciclo}; {alcance}',
                            corte=corte, estado=estado)
    return texto, 'SISAE · DBF conciliados (solo lectura)', {}
