"""Respuestas agregadas SISAE; función segura para el puente 10.12.19.

Solo lectura, jamás devuelve identidades. No sustituye las consultas filtradas
por especialidad ni el módulo de discapacidad preexistente.
"""
from __future__ import annotations
import re
from pathlib import Path
from .lector_integral_101219 import CorteSISAE, norma
from .sisae_ampliado_101219 import _periodo, _ciclo, _especialidad
from . import fuentes


def _numero(q):
    return bool(re.search(r'\b(cuantos|cuantas|cuanto|total|numero|cantidad|matricula)\b', q))


def _procedencia(r, texto, unidad, periodo):
    proc = r.get('procedencia', {})
    ciclo = proc.get('ciclo','no determinado')
    return fuentes.anotar(
        texto,
        fuente='SISAE.zip · INSCRIPCION.DBF + PROG_CURSOS1.DBF + ESP.DBF',
        unidad=unidad,
        periodo=f'Ciclo {ciclo} · periodo de inscripción {periodo or "todos los disponibles"}',
        corte='fecha de exportación no confirmada',
        estado='cálculo del corte local (no en vivo)',
    )


def responder_indicadores(pregunta, contexto):
    q=norma(pregunta)
    if not _numero(q): return None
    # Dejar el desglose médico a la herramienta 10.12.19 ya probada.
    if 'discap' in q: return None

    menos10=bool(re.search(r'\b(?:grupos?|cursos?)\b',q) and re.search(r'\bmenos\s+de\s+10\b',q)
                 and re.search(r'\b(?:inscrit\w*|alumn\w*|participantes)\b',q))
    grupos_sisae=(not menos10 and 'sisae' in q and re.search(r'\b(?:grupos?|cursos?)\b',q)
                 and _numero(q) and not re.search(r'\b(?:alumn\w*|inscripci\w*)\b',q))
    personas=bool(re.search(r'\b(?:alumn\w*|personas?|estudiantes?|matricula|inscripciones?)\b',q))
    if not (menos10 or grupos_sisae or personas):return None

    # Si la pregunta incluye una especialidad, conserva la conciliación
    # INSCRIPCION.DBF ↔ LISTAS.DBF del lector 10.12.18.
    # Para una pregunta general exigimos una referencia de ámbito general
    # y no confundimos "en Soldadura" con el total del plantel.
    general=any(s in q for s in ('sisae','en el ciclo','del ciclo','este ciclo',
               'en total','total de alumnos','total de inscripciones','en el plantel','del plantel',
               'cuantos alumnos distintos hay','cuantos alumnos tenemos',
               'cuantas inscripciones tenemos'))
    if not menos10 and not grupos_sisae and not general:return None

    ruta=Path(contexto.ROOT)/'datos'/'recursos'/'SISAE.zip'
    if not ruta.is_file() or ruta.is_symlink():
        return ('No se encontró una exportación SISAE local válida. No presentaré datos de Programación como matrícula.',
                'SISAE · corte ausente',{})
    try:
        ciclo=_ciclo(q)
        periodo=_periodo(q)
        with CorteSISAE(ruta) as corte:
            esp=_especialidad(q,corte)
            if esp is not None:
                # El puente ya tiene un lector validado para consultas por especialidad.
                return None
            # Evita dar totales generales cuando hay un filtro personal o de docente.
            if any(t in q for t in ('docente','profesor','maestro','grupo id','alumno id')):
                return None
            resumen=corte.resumen(ciclo=ciclo,periodo=periodo)
        label=f'**SISAE · ciclo {ciclo}** · periodo {periodo or "todos los disponibles"}.'
        if menos10:
            texto=(f'{label}\n\n**{resumen["grupos_con_menos_de_10_inscripciones"]} grupos con entre 1 y 9 inscripciones** '
                   f'de **{resumen["grupos_con_inscripciones"]} grupos con matrícula registrada**. '
                   'Los grupos todavía sin inscripciones no están incluidos y no se consideran automáticamente grupos vacíos.')
            unidad='grupos con inscripciones (1–9)'
        elif grupos_sisae:
            texto=(f'{label}\n\n**{resumen["grupos_con_inscripciones"]} grupos con inscripciones** en el corte. '
                   'Esta cifra no representa todos los grupos de Programación; los que aún no tienen matrícula capturada no se incluyen.')
            unidad='grupos con inscripciones'
        else:
            texto=(f'{label}\n\n**{resumen["personas_unicas"]} alumnos distintos** y '
                   f'**{resumen["inscripciones"]} inscripciones** en el corte consultado. '
                   'Una misma persona puede estar inscrita en varios cursos; por eso las dos cifras son diferentes.')
            unidad='personas únicas e inscripciones'
        texto+='\n\n**Alcance:** exportación local de SISAE; fecha de exportación no confirmada, no equivale a la matrícula en vivo.'
        if resumen['inscripciones_reiteradas_detectadas']:
            texto+=f' Se detectaron {resumen["inscripciones_reiteradas_detectadas"]} inscripciones reiteradas en la fuente principal; revisar antes de utilizar el indicador como definitivo.'
        return _procedencia(resumen,texto,unidad,periodo),'SISAE · corte local verificado por estructura',{}
    except (ValueError,KeyError,PermissionError,OSError,EOFError) as e:
        return ('No fue posible comprobar esta consulta del corte SISAE ('+type(e).__name__+'). '
                'No utilizaré el total de Programación como sustituto.',
                'SISAE · sin cifra validada',{})
