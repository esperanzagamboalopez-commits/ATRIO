"""Puente de entrada, compatible con la interfaz 10.12.15 / 10.12.16.

Sólo intercepta consultas para las que tiene una respuesta más segura; el resto
continúa al asistente existente, conservando PEA, fechas e interfaz.
"""
from __future__ import annotations
import re
import unicodedata
from . import fuentes, db
from .sisae_indicadores_1012191 import responder_indicadores
from .sisae_ampliado_101219 import responder_sisae_ampliado
from .sisae_consultas_101218 import responder_matricula


def _norm(text):
    t=unicodedata.normalize('NFKD',str(text or '').casefold())
    return ' '.join(re.findall(r'[a-z0-9]+',''.join(c for c in t if not unicodedata.combining(c))))


def _quiere_numero(q):
    return any(w in q for w in ('cuant', 'total', 'numero', 'cantidad', 'matricula',
                              'promedio', 'mas ', 'menos ', 'mayor ', 'menor ',
                              'estadistic', 'hay ', 'tienen ', 'tiene '))


def _es_matricula(q):
    return (any(w in q for w in ('alumn', 'inscrit', 'matricula', 'estudiant', 'participantes'))
            and _quiere_numero(q))


def _es_grupos_generales(q):
    return (('grupo' in q or 'curso' in q or 'programacion' in q)
            and any(w in q for w in ('cuant', 'total', 'numero', 'cantidad', 'hay '))
            and (('programacion' in q and not any(w in q for w in ('especialidad', 'de ', 'del ', 'docente', 'profesor', 'maestro'))) or
                 q in {'cuantos grupos hay', 'cuantos grupos tenemos', 'total de grupos',
                       'cuantos cursos hay', 'cuantos grupos activos hay'})
            and not any(w in q for w in ('especialidad', 'docente', 'profesor',
                                       'maestro', 'mujer', 'hombre', 'alumno',
                                       'extension', 'repositorio', 'regular')))


def responder_primero(pregunta, C, memoria):
    q=_norm(pregunta)
    if not q: return None
    indicador = responder_indicadores(pregunta, C)
    if indicador is not None: return indicador
    ampliado=responder_sisae_ampliado(pregunta, C)
    if ampliado is not None: return ampliado

    if _es_matricula(q):
        return responder_matricula(pregunta, C)

    if _quiere_numero(q) and ('especialidad' in q or
           any(w in q for w in ('constancia', 'folio', 'asistencia', 'acreditacion'))):
        text=('No tengo una consulta **verificada para esa cifra**. '
              'Necesito comprobar la fuente y el ámbito solicitado antes de dar una cantidad.')
        return (fuentes.anotar(text,fuente='Consulta no implementada',
              unidad='indicador solicitado', periodo='por confirmar',
              corte='sin corte verificado',estado='no verificado'),
              'Indicador no verificado',{})

    # Las cuentas generales se pueden obtener realmente del SQLite actual.
    if _es_grupos_generales(q):
        n=db.ejecutar_lectura(C.ROOT, 'grupos_activos')
        text=fuentes.anotar(f'Actualmente hay **{n} grupos activos registrados en Programación**. '
             'Son registros de grupos, **no alumnos inscritos**.',
             fuente='sqlite:groups (active=1)', unidad='grupos activos',
             periodo='Programación activa, sin filtro de ciclo',corte='consulta en vivo')
        return text,'SQLite: groups (active=1)',{}

    # Los subconjuntos de grupos requieren un filtro verificado; no sustituir
    # por el total institucional, ni siquiera cuando el lector viejo lo intente.
    if ('grupo' in q or 'curso' in q) and _quiere_numero(q) and not ('pea' in q):
        return (fuentes.anotar('No tengo un **conteo verificado para ese filtro de grupos**. '
                'No presentaré el total de la Programación como si fuera el subconjunto solicitado.',
                fuente='Programación · filtro sin validar',unidad='grupos filtrados',
                periodo='por confirmar',corte='consulta no realizada',estado='no verificado'),
                'Programación · filtro sin verificar',{})

    # No interceptamos PEA ni simulaciones: conservan el lector especializado validado.
    return None
