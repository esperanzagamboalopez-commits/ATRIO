"""Intercepción conservadora de consultas SISAE: solo funciones autorizadas.

No envía datos a red, no ejecuta SQL libre, no devuelve expedientes.
"""
from __future__ import annotations
from pathlib import Path
import re
import unicodedata
from .lector_integral_101219 import CorteSISAE, norma, CATEGORIAS
from . import fuentes


def _periodo(q):
    patrones={
        '1':r'\b(?:primer|primero|1er|periodo\s*1|trimestre\s*1)\b',
        '2':r'\b(?:segundo|2do|periodo\s*2|trimestre\s*2)\b',
        '3':r'\b(?:tercer|tercero|3er|periodo\s*3|trimestre\s*3)\b',
        '4':r'\b(?:cuarto|4to|periodo\s*4|trimestre\s*4)\b',
    }
    found=[k for k,regex in patrones.items() if re.search(regex,q)]
    if len(found)>1: raise ValueError('Hay más de un periodo en la pregunta.')
    return found[0] if found else None


def _ciclo(q):
    found=set(re.findall(r'\b20\d\d\s*[-/]\s*20\d\d\b',q))
    if len(found)>1: raise ValueError('Indica un solo ciclo.')
    if found: return re.sub(r'\s','',next(iter(found))).replace('/','-')
    return '2026-2027'


def _especialidad(q, c):
    esps=c._especialidades()
    matches=[nombre for nombre in esps.values() if norma(nombre) in q]
    if len(matches)==1:return matches[0]
    if len(matches)>1: raise ValueError('Múltiples especialidades; precisa una.')
    return None


def _anotar(r, texto, unidad, periodo):
    p=r.get('procedencia',{})
    return fuentes.anotar(texto, fuente=', '.join(p.get('fuentes',[])) or 'SISAE',
           unidad=unidad, periodo=f'Ciclo {p.get("ciclo","?")} · periodo {periodo or "todos"}',
           corte=p.get('fecha_exportacion','no confirmada'),
           estado='revisar' if r.get('estado')=='requiere_revision' else 'corte local')


def responder_sisae_ampliado(pregunta,C):
    q=norma(pregunta)
    es_disc='discap' in q or 'discapacidad' in q
    es_alumno=('alumno' in q or 'estudiante' in q) and any(x in q for x in ('cuantos cursos','en cuantos cursos','cursos esta inscrito','cursos tiene','cursos ha tomado'))
    es_inventario=any(x in q for x in ('que datos tiene sisae','que puede consultar sisae',
                    'que contiene sisae','que informacion hay en sisae'))
    if not (es_disc or es_alumno or es_inventario): return None
    ruta=Path(C.ROOT)/'datos'/'recursos'/'SISAE.zip'
    if not ruta.is_file() or ruta.is_symlink():
        return ('No encontré una exportación local SISAE.zip para esta consulta.', 'SISAE · sin corte',{})
    try:
        ciclo=_ciclo(q); periodo=_periodo(q)
        with CorteSISAE(ruta) as c:
            if es_inventario:
                items=', '.join(CATEGORIAS)
                txt=f'En el corte existen **{len(c.index)} tablas DBF**. Categorías: {items}. '
                txt+='Las tablas de acceso y los campos de credenciales no se consultan. La existencia de un campo no confirma que esté capturado.'
                return (txt,'SISAE · metadatos de tablas',{})
            esp=_especialidad(q,c)
            if es_disc:
                r=c.discapacidad(ciclo,periodo,esp)
                tipos=[k for k in r['por_tipo'] if k in q]
                if 'audicion' in q or 'auditiv' in q: tipos=['auditiva']
                if 'lengua' in q: tipos=['lenguaje']
                if 'movilidad' in q or 'motriz' in q: tipos=['motriz']
                if 'vision' in q or 'visual' in q: tipos=['visual']
                if len(tipos)!=1: tipos=list(r['por_tipo'])
                if ('hombre' in q or 'mujer' in q or 'sexo' in q):
                    desglose='\n'.join(f'- {nombre}: hombres {r["por_tipo_y_sexo"][nombre]["hombres"]}, mujeres {r["por_tipo_y_sexo"][nombre]["mujeres"]}' for nombre in tipos)
                else:
                    desglose='\n'.join(f'- {k}: **{r["por_tipo"][k]}**' for k in tipos)
                aviso=(f' **Precaución: {r["personas_con_flags_contradictorios"]} personas tienen marcas contradictorias.**' if r['personas_con_flags_contradictorios'] else '')
                txt=(f'**Discapacidad registrada en SISAE** · ciclo {ciclo} · '
                     f'periodo {periodo or "todos los disponibles"}' + (f' · {esp}' if esp else '') + '\n'
                     f'**{r["con_alguna_discapacidad"]} personas únicas con alguna discapacidad** '
                     f'de {r["personas_unicas_analizadas"]} personas registradas.\n'+desglose+'\n'
                     'Se cuenta cada alumno una sola vez por tipo, aunque tenga varias inscripciones.'+aviso)
                return (_anotar(r,txt,'personas únicas por tipo de discapacidad',periodo),'SISAE · INSCRIPCION.DBF',{})
            if es_alumno:
                # Ningún nombre/ID se comunica a servicios externos: Gemini sigue apagado.
                # La consulta por nombre se reserva para un control de sesión validado.
                m=re.search(r'\b(?:id\s*(?:del?\s*)?alumno|alumno\s*(?:id|numero|n[uú]mero)?\s*)\s*[:#-]?\s*(\d{1,12})\b',q)
                if not m:
                    return ('Para consultar los cursos de una persona, indica **su identificador interno de SISAE**. '
                            'La búsqueda por nombre quedará disponible al validar el acceso de Jefatura. '
                            'No escribas CURP ni datos médicos en el chat.',
                            'SISAE · falta identificador',{})
                r=c.alumno_cursos(id_alumno=m.group(1),ciclo=ciclo,periodo=periodo)
                if r['estado']=='sin_registro':
                    txt='No encontré inscripciones de ese identificador en el ciclo y periodo consultados.'
                else:
                    names='\n'.join('- '+i['curso']+' (periodos de inscripción: '+', '.join(i['periodos_inscripcion'])+')' for i in r['cursos'])
                    txt=(f'En esta exportación el alumno aparece en **{r["numero_cursos"]} cursos distintos** '
                         f'({r["numero_inscripciones"]} inscripciones):\n'+names+'\n'
                         '**Esto no garantiza que los cursos estén activos actualmente.**')
                return (_anotar(r,txt,'cursos distintos de un alumno',periodo),'SISAE · INSCRIPCION.DBF',{})
    except (ValueError,OSError,KeyError,PermissionError,EOFError) as exc:
        # No exponer contenido sensible ni rutas completas en el error.
        return ('No pude validar esa consulta SISAE. Revisa el corte, el periodo y el identificador. '
                'Error de validación: '+type(exc).__name__, 'SISAE · consulta pendiente',{})
    return None
