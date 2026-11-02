# -*- coding: utf-8 -*-
"""Control académico adicional, basado en campos del motor v6.4.
No edita el documento Word ni sustituye la revisión de docentes o autoridades.
Las validaciones semánticas son heurísticas transparentes, no aprobación DGCFT.
"""
from __future__ import annotations
import difflib
import json
import re
import unicodedata
from urllib.parse import urlparse

VERSION='7.0'


def canon(t):
    t=unicodedata.normalize('NFKD',str(t or '').lower())
    return re.sub(r'\s+',' ',''.join(ch for ch in t if not unicodedata.combining(ch))).strip()


def palabras(t):
    return set(re.findall(r'[a-z]{5,}', canon(t)))


def renglones(l):
    return [str(x).strip() for x in (l or []) if str(x).strip()] if isinstance(l,list) else []


def _texto(v):
    return str(v or '').strip()


def analizar(datos,curso,horas,exigir_proporcion=True):
    """Devuelve incidencias independientes en 5 ejes; NO realiza verificación web.

    Se valida por completo únicamente el JSON académico NUEVO de Gemini.
    No mezclar informes semánticos con las decisiones administrativas del PEA.
    """
    errores=[];avisos=[];detalle={}
    def err(codigo,msg):errores.append({'codigo':codigo,'detalle':msg})
    def avis(codigo,msg):avisos.append({'codigo':codigo,'detalle':msg})
    if not isinstance(datos,dict):
        err('JSON','Respuesta académica no es un objeto')
        return {'version':VERSION,'aprobado_estructural':False,'errores':errores,'avisos':avisos,'mediciones':detalle}
    unis=datos.get('unidades') if isinstance(datos.get('unidades'),list) else []
    nombre=_texto(curso.get('nombre'))
    dur=float(curso.get('duracion') or 0)
    ap=float(horas.get('apertura') or 0);ci=float(horas.get('cierre') or 0)
    # 1. Coherencia entre objetivo, competencia y resultados.
    objetivo=_texto(datos.get('objetivo_general'));comp=_texto(datos.get('competencia'))
    if not objetivo or not comp:err('COHERENCIA_VACIA','Faltan objetivo o competencia')
    if objetivo and comp:
        sim=difflib.SequenceMatcher(None,canon(objetivo),canon(comp)).ratio()
        detalle['semejanza_objetivo_competencia']=round(sim,3)
        if sim>0.90:err('COHERENCIA_DUPLICADA','Objetivo y competencia están prácticamente copiados')
        elif sim>0.78:avis('COHERENCIA_SIMILAR','Objetivo y competencia se parecen demasiado; revisar intencionalidad')
    resultados=renglones(datos.get('resultados_aprendizaje'))
    if len(resultados)<3:err('RESULTADOS','Se requieren al menos 3 resultados de aprendizaje')
    if len(set(canon(x) for x in resultados))<len(resultados):err('RESULTADOS_REPETIDOS','Hay resultados repetidos')
    for i,x in enumerate(resultados,1):
        inicio=canon(x).split(' ',1)[0]
        if not inicio.endswith(('ar','er','ir')):err('RESULTADO_VERBO',f'Resultado {i}: falta verbo inicial en infinitivo')
    # 2. Pertinencia y diferenciación de actividades.
    claves=['teorizacion_docente','teorizacion_estudiante','ejercitacion_docente','ejercitacion_estudiante','reflexion_docente','reflexion_estudiante']
    contexto=palabras(nombre+' '+_texto(curso.get('especialidad_programada')))
    stop={'curso','basica','basico','introduccion','manejo','administracion','elaboracion','aplicacion','industrial','nivel','principios','intermedio','avanzado','para','recurso','recursos'}
    contexto-=stop
    menciones=0
    observables=re.compile(r'\b(?:crea|elabora|calcula|prueba|ajusta|realiza|verifica|instala|mide|simula|configura|construye|aplica|documenta|presenta|organiza|analiza|registra|identifica|compara|opera|emplea|desarrolla|revisa)\b',re.I)
    for i,u in enumerate(unis,1):
        if not isinstance(u,dict):err('UNIDAD_TIPO',f'Unidad {i}: no es objeto');continue
        act=u.get('actividades') or {}
        textos=[]
        for k in claves:
            t=_texto(act.get(k)) if isinstance(act,dict) else ''
            if len(t)<75:err('ACTIVIDAD_INCOMPLETA',f'Unidad {i}: actividad {k} requiere más detalle')
            textos.append(t)
        normalizados=[canon(t) for t in textos if t]
        if len(set(normalizados))<len(normalizados):err('ACTIVIDADES_REPETIDAS',f'Unidad {i}: actividades del docente/estudiante copiadas')
        if contexto and any(p in palabras(' '.join(textos)+' '+str(u.get('temas',''))) for p in contexto):menciones+=1
        if not any(observables.search(t) for t in textos if t):
            avis('ACCIONES_POCO_OBSERVABLES',f'Unidad {i}: revisar que las actividades expliciten actuaciones verificables')
    detalle['unidades_con_palabras_del_curso']=menciones
    if contexto and unis and menciones==0:avis('ESPECIALIDAD','No se identifican términos del curso en unidades; revisar pertinencia por un instructor')
    # 3. Evaluación: instrumentos, evidencias y criterios.
    instrumentos=[]
    for i,u in enumerate(unis,1):
        if not isinstance(u,dict):continue
        ev=u.get('evaluacion') or {}
        if not isinstance(ev,dict):err('EVALUACION_TIPO',f'Unidad {i}: evaluación no es objeto');continue
        m=_texto(ev.get('momento'));tipo=_texto(ev.get('tipo'))
        inst=_texto(ev.get('instrumento'));evi=_texto(ev.get('evidencia'))
        crit=renglones(ev.get('criterios'))
        if canon(m)!='formativa':err('MOMENTO',f'Unidad {i}: momento formativo no identificado')
        if not tipo:err('TIPO_EVALUACION',f'Unidad {i}: sin auto/coe/heteroevaluación')
        if len(inst)<8:err('INSTRUMENTO',f'Unidad {i}: instrumento sin especificar')
        if len(evi)<18 or canon(evi) in ('producto','desempeno','conocimiento','producto/desempeno'):
            err('EVIDENCIA',f'Unidad {i}: evidencia no describe un producto o desempeño concreto')
        if len(crit)!=3:err('CRITERIOS',f'Unidad {i}: se requieren exactamente 3 criterios evaluables')
        elif any(len(t)<24 for t in crit):avis('CRITERIOS_BREVES',f'Unidad {i}: revisar especificidad de criterios')
        if 'cuestionario' in canon(inst) and ('procedimiento' in canon(evi) or 'montaje' in canon(evi)):
            avis('INSTRUMENTO_EVIDENCIA',f'Unidad {i}: comprobar si un cuestionario realmente mide ese desempeño práctico')
        if inst:instrumentos.append(canon(inst))
    if len(instrumentos)>2 and len(set(instrumentos))==1:
        avis('VARIAR_INSTRUMENTOS','Todas las unidades usan el mismo instrumento; comprobar que sea pertinente para todas')
    if len(_texto(datos.get('apertura_docente')))<70 or len(_texto(datos.get('cierre_docente')))<70:
        avis('APERTURA_CIERRE','Revisar diagnóstico, contextualización y evaluación final')
    # 4. Horas (apertura/cierre clasificadas como mediación según el motor vigente).
    md=ap+ci;pr=0.0
    for i,u in enumerate(unis,1):
        if not isinstance(u,dict):continue
        try:
            med=float(u.get('mediacion_horas'));p=float(u.get('practica_horas'))
            if med<0 or p<0:raise ValueError
            if dur.is_integer() and (abs((med+p)-round(med+p))>.001 or round(med+p)<len(u.get('temas') or [])):
                err('HORAS_SUBTEMAS',f'Unidad {i}: las horas totales deben ser enteras y suficientes para asignar al menos 1 h por subtema')
            md+=med;pr+=p
        except (TypeError,ValueError):err('HORAS',f'Unidad {i}: faltan horas numéricas válidas')
    detalle.update({'duracion_oficial':dur,'apertura_med':ap,'cierre_med':ci,'mediacion_total':round(md,3),'practica_total':round(pr,3),'teoria_20pct_objetivo':round(.2*dur,3),'practica_80pct_objetivo':round(.8*dur,3)})
    if abs(md+pr-dur)>.05:err('HORAS_TOTAL',f'El total académico calculado es {md+pr:g}, pero el curso exige {dur:g} h')
    if exigir_proporcion and (abs(md-.2*dur)>.051 or abs(pr-.8*dur)>.051):
        err('HORAS_20_80',f'El criterio operativo 20/80 exige {dur*.2:g} h de mediación (incluida apertura/cierre) y {dur*.8:g} h de práctica; el JSON entrega {md:g}/{pr:g}')
    # 5. Recursos y referencias: plausibilidad (no inventario ni revisión externa).
    recurso=datos.get('recursos') or {}
    rubros={'equipo':'equipo','herramientas':'herramientas','materiales':'material e insumos','apoyo':'material de apoyo y mobiliario','conectividad':'conectividad'}
    if not isinstance(recurso,dict):recurso={}
    vaguedades={'equipo tecnico adecuado','herramientas y aplicaciones propias de la especialidad','materiales de practica vinculados','guias de trabajo y ejercicios','recursos digitales cuando','conectividad adecuada'}
    for k,nom in rubros.items():
        val=canon(recurso.get(k,''))
        if len(val)<42:err('RECURSO_VACIO',f'Faltan especificaciones en {nom}')
        elif any(t in val for t in vaguedades):avis('RECURSO_GENERICO',f'Rubro {nom}: descripción genérica, especificar equipos/insumos')
        if val and k!='conectividad' and not re.search(r'\d|por (?:participante|equipo|sesion|grupo)|segun (?:cantidad|numero)',val):
            avis('RECURSO_CANTIDAD',f'Rubro {nom}: revisar cantidades requeridas para la población programada')
    if _texto(recurso.get('apoyo')) and 'mobiliario' not in canon(recurso['apoyo']):
        avis('MOBILIARIO','En apoyo, distinguir material didáctico y mobiliario; el Word reúne ambos en la celda disponible')
    refs=datos.get('referencias') or {}
    if not isinstance(refs,dict):refs={}
    if not renglones(refs.get('bibliografica')):avis('REF_BIBLIO','No se generaron referencias bibliográficas; comprobar catálogo institucional')
    if not renglones(refs.get('cibergrafica')):avis('REF_CIBER','No se generaron referencias cibergráficas; comprobar catálogo institucional')
    for cat in ('bibliografica','hemerografica','cibergrafica'):
        for r in renglones(refs.get(cat)):
            if re.search(r'\b(?:ejemplo\.com|example\.com|por confirmar|autor ficticio|pendiente)\b',canon(r)):
                err('REFERENCIA_FICTICIA',f'Referencia sospechosa en {cat}: {r[:70]}')
            if cat=='cibergrafica' and 'http' in r and not any((urlparse(t).netloc for t in re.findall(r'https?://[^\s)]+',r))):
                avis('URL','Comprobar sintaxis de URL cibergráfica')
    avis('FUENTES_VERIFICACION','Las referencias propuestas por Gemini requieren verificación documental independiente; este programa no consulta URLs en tiempo real')
    return {'version':VERSION,'aprobado_estructural':not errores,'errores':errores,'avisos':avisos,'mediciones':detalle,
            'alcance':'Comprobación automática; no equivale a validación, autorización o certificación académica DGCFT'}


def validar_o_rechazar(datos,curso,horas):
    reporte=analizar(datos,curso,horas,exigir_proporcion=True)
    if reporte['errores']:
        seleccion=reporte['errores'][:5]
        raise ValueError('Control académico v7: '+' | '.join(e['detalle'] for e in seleccion))
    return reporte


def informe_json(datos,curso,horas):
    return json.dumps(analizar(datos,curso,horas),ensure_ascii=False,indent=2)
