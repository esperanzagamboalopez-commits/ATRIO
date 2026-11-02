"""Consultas SOLO LECTURA a registros reales de ATRIO.

No hace SQL generado por un modelo. No transmite datos al exterior.
Fuentes: Programación activa, status, artifacts, biblioteca_pea,
pea_repo_actual_101213, pea_hist_101212 y SISAE.zip (solo al preguntarlo).
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
from datetime import date
import sqlite3
import re
import unicodedata


def normal(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(s or '')) if not unicodedata.combining(c)).lower()


def _db_ro(C):
    path=Path(C.DATA)/'atrio.sqlite3'
    if not path.is_file():return None
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def _tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _rows(db,tables,table,sql):
    if db is None or table not in tables:return None
    return [dict(r) for r in db.execute(sql)]


def contexto(C, grupos):
    """Cifras verificables: versiones y grupos por separado; no inventa tablas ausentes."""
    result={'programados':len(grupos),'tipos':dict(Counter(str(g.get('tipo') or 'Sin tipo') for g in grupos)),
            'grupos':list(grupos),'base_disponible':False,'tablas_disponibles':[]}
    db=_db_ro(C)
    if db is None:return result
    try:
        ts=_tables(db);result['base_disponible']=True;result['tablas_disponibles']=sorted(ts)
        result['artefactos']=_rows(db,ts,'artifacts','SELECT id,group_id,created,path,reviewed FROM artifacts')
        result['biblioteca']=_rows(db,ts,'biblioteca_pea',"SELECT id,group_id,origen,curso,docente,estado,creado,ruta FROM biblioteca_pea")
        result['repositorio']=_rows(db,ts,'pea_repo_actual_101213',"SELECT id,group_id,curso,docente,estado,creado,pdf_adaptado FROM pea_repo_actual_101213")
        result['historicos']=_rows(db,ts,'pea_hist_101212',"SELECT id,ciclo,curso,docente,estado,creado FROM pea_hist_101212")
        result['estados']=_rows(db,ts,'status',"SELECT group_id,doc,mce FROM status")
        result['trabajos']=_rows(db,ts,'pea_jobs',"SELECT id,group_id,status,title FROM pea_jobs")
    finally:db.close()
    return result


def resumen(ctx):
    arts=ctx.get('artefactos')
    bib=ctx.get('biblioteca')
    repo=ctx.get('repositorio')
    hist=ctx.get('historicos')
    # None: tabla no disponible. []: existe, sin registros.
    r={'programacion':ctx['programados'],'por_tipo':ctx['tipos'],
       'pea_extension_generados':len(arts) if arts is not None else None,
       'pea_repositorio_vigente':len(repo) if repo is not None else None,
       'pea_copias_actualizadas':sum(x['origen']!='Subido' for x in bib) if bib is not None else None,
       'pea_subidos_originales':sum(x['origen']=='Subido' for x in bib) if bib is not None else None,
       'pea_historicos':len(hist) if hist is not None else None,
       'fuentes_disponibles':[]}
    counts=[(k,r[k]) for k in ('pea_extension_generados','pea_repositorio_vigente','pea_copias_actualizadas')]
    r['pea_elaborados_ciclo_actual']=sum(x for k,x in counts if x is not None)
    r['pea_fuentes_faltantes']=[k for k,x in counts if x is None]
    r['pea_grupos_distintos']=len({row.get('group_id') for part in (arts,repo,bib) if part is not None
                                  for row in part if row.get('group_id') and (part is not bib or row.get('origen')!='Subido')})
    statuses=ctx.get('estados')
    if statuses is not None:
        active={g.get('id') for g in ctx['grupos']}
        relevant=[s for s in statuses if s.get('group_id') in active]
        r['estados_documentos']=dict(Counter(s.get('doc') or 'Sin verificar' for s in relevant))
        r['estados_mce']=dict(Counter(s.get('mce') or 'Sin verificar' for s in relevant))
    else:
        r['estados_documentos']=None;r['estados_mce']=None
    return r


def _nombre_curso(g):return str(g.get('nombre') or '')


def responder(pregunta,C,grupos):
    q=normal(pregunta)
    ctx=contexto(C,grupos);r=resumen(ctx)
    cuantos=bool(re.search(r'\b(cuant|cuantos|cuantas|total|numero|numero de|cantidad|cuanto|cuanta|resumen|estadistica|balance|desglose|lista|listado|cuales|muestra|dime|hay)\b',q)) or 'se han' in q
    verbos_pea=any(k in q for k in ('elaborad','generad','preparad','cread','hechos','realizad','producid','documentos','expedientes'))
    sobre_pea=bool(re.search(r'\bpea(s)?\b',q))
    if sobre_pea and any(k in q for k in ('pendiente','faltan','sin pea','por elaborar')) and cuantos:
        states=r.get('estados_documentos')
        if states is None:
            return ('No hay estados PEA disponibles para confirmar pendientes. No se inferirán a partir de la programación.', 'Seguimiento · Estados')
        missing=sum(n for k,n in states.items() if normal(k)=='sin pea')
        unverified=states.get('Sin verificar',0)
        return (f'Hay **{missing} grupos marcados explícitamente «Sin PEA»** en Seguimiento del ciclo vigente. '
                f'Adicionalmente, **{unverified} tienen estado «Sin verificar»**; no deben contarse automáticamente como pendientes.',
                'Seguimiento y MCE · Estado guardado')
    if sobre_pea and (cuantos or verbos_pea) and not any(k in q for k in ('como elaborar','como generar','como preparar','como hacer','pasos para','pendiente','sin pea','faltan')):
        if not ctx['base_disponible']:
            return ('No puedo acceder a la base de registros de ATRIO. **No voy a inventar un total de PEA.** Comprueba que exista `datos/atrio.sqlite3`.', 'Diagnóstico local · SQLite')
        if any(k in q for k in ('historico','anteriores','otro ciclo')) and not any(k in q for k in ('total general','todos los ciclos')):
            if r['pea_historicos'] is None:return ('No está disponible la tabla de PEA históricos; no puedo confirmar su total.', 'Mis PEA · Históricos')
            return (f'En **Mis PEA → Históricos** hay **{r["pea_historicos"]} expediente(s) registrado(s) de ciclos anteriores**. No se mezclan con 2026–2027.', 'Registro local `pea_hist_101212`')
        if any(k in q for k in ('subido','subidos','recibido','original del docente')) and 'mce' not in q:
            if r['pea_subidos_originales'] is None:return ('No está disponible la tabla de Word subidos.', 'Mis PEA · Subidos')
            return (f'En **Mis PEA → Subidos** hay **{r["pea_subidos_originales"]} Word original(es) recibido(s)**. No son PEA elaborados por el generador.', 'Registro local `biblioteca_pea`')
        total=r['pea_elaborados_ciclo_actual']
        parts=[]
        if r['pea_extension_generados'] is not None:parts.append(f'**{r["pea_extension_generados"]}** PEA de Extensión generados')
        if r['pea_repositorio_vigente'] is not None:parts.append(f'**{r["pea_repositorio_vigente"]}** adaptaciones de Repositorio vigente')
        if r['pea_copias_actualizadas'] is not None:parts.append(f'**{r["pea_copias_actualizadas"]}** copias Word actualizadas')
        msg=(f'En los registros de **Mis PEA del ciclo actual** encuentro **{total} versiones/documentos elaborados** '
             f'en **{r["pea_grupos_distintos"]} grupos distintos**. Desglose: '+ '; '.join(parts)+'.')
        if r['pea_fuentes_faltantes']:msg+=' **Total parcial**: no están disponibles todas las fuentes ('+', '.join(r['pea_fuentes_faltantes'])+').'
        msg+=' **Una versión no equivale necesariamente a un PEA distinto**: un grupo puede tener varias versiones.'
        if r['pea_subidos_originales'] is not None:msg+=f' Por separado hay **{r["pea_subidos_originales"]} original(es) subido(s)**.'
        if r['pea_historicos'] is not None:msg+=f' Y **{r["pea_historicos"]} expediente(s) histórico(s)**, que no sumé al ciclo vigente.'
        if any(k in q for k in ('cuales','lista','listado','muestra','que pea','nombres')):
            allnames=[]
            ids={g['id']:g for g in grupos}
            for a in (ctx.get('artefactos') or []):
                g=ids.get(a.get('group_id'))
                if g:allnames.append(g.get('nombre',''))
            for a in (ctx.get('repositorio') or []):allnames.append(a.get('curso',''))
            for a in (ctx.get('biblioteca') or []):
                if a.get('origen')!='Subido':allnames.append(a.get('curso',''))
            uniq=list(dict.fromkeys(x for x in allnames if x))
            if uniq:msg+='\n\n**Cursos con PEA elaborado:** '+', '.join(uniq[:12])+(' (y más)' if len(uniq)>12 else '')+'.'
        return msg,'Mis PEA · Base local (solo lectura): artifacts, biblioteca_pea, pea_repo_actual_101213, pea_hist_101212'
    if cuantos and any(k in q for k in ('mce','pendiente','revisad','sin pea')):
        docs=r.get('estados_documentos');mce=r.get('estados_mce')
        if docs is None:return ('No encuentro la tabla de estados confirmados; no calcularé pendientes a partir de fechas.', 'Seguimiento · Estados')
        detalle=' · '.join(f'{k}: **{n}**' for k,n in sorted(docs.items())) or 'sin estados registrados'
        ms=' · '.join(f'{k}: **{n}**' for k,n in sorted((mce or {}).items())) or 'sin estados MCE registrados'
        return (f'En **Seguimiento y MCE** constan estos estados para grupos activos:\n\n**Documento PEA:** {detalle}.\n\n**MCE:** {ms}.\n\nLos grupos sin estado confirmado no se consideran atrasados automáticamente.', 'ATRIO · Estado guardado por grupo (solo lectura)')
    if cuantos and any(k in q for k in ('curso','grupo','programacion','docente','especialidad','extension','repositorio','regular')):
        ts=r['por_tipo'];part=' · '.join(f'{k}: **{v}**' for k,v in sorted(ts.items()))
        for tipo in ('repositorio','extension','regular'):
            if tipo in q:
                matched=sum(n for k,n in ts.items() if normal(k)==tipo)
                return (f'En **Programación** hay **{matched} grupos tipo {tipo.capitalize()}**. Desglose completo: {part}. Estos son grupos programados, **no PEA elaborados ni alumnos inscritos**.', 'Programación activa · grupos')
        if 'docente' in q:
            n=len({g.get('hoja') for g in grupos if g.get('hoja')})
            return (f'En Programación aparecen **{n} docentes** y **{len(grupos)} grupos**. No implica que todos tengan PEA generado.', 'Programación activa · grupos')
        return (f'Hay **{len(grupos)} registros de grupos/cursos en Programación**. {part}. No equivale a matrícula SISAE.', 'Programación activa · grupos')
    if any(k in q for k in ('sisae','inscrit','matricula','alumno')) and cuantos:
        path=Path(C.RES)/'SISAE.zip'
        if not path.is_file():return ('No encuentro una copia SISAE activa en Recursos. Para datos de matrícula necesito un corte de SISAE, no Programación.', 'SISAE · Cortes')
        try:
            if path.stat().st_size>100_000_000:raise ValueError('El corte supera el tamaño permitido para consulta rápida')
            data=C.sisae_bytes(path.read_bytes())
            return (f'En el **archivo SISAE.zip actualmente cargado**, encuentro **{len(data["PROG_CURSOS1.DBF"])} registros de cursos** y **{len(data["INSCRIPCION.DBF"])} registros de inscripción**. Son registros del archivo, no necesariamente alumnos únicos ni matrícula de un periodo filtrado. Revisa **SISAE · Cortes** para la fecha y selección del corte.', 'Recurso local SISAE.zip · DBF')
        except Exception as exc:return ('No pude leer el corte SISAE. Revisa **SISAE · Cortes**; no voy a suponer cifras.', 'SISAE · Recurso local')
    # Búsqueda libre local por docente o por nombre de curso, con datos reales.
    # No se ejecuta SQL libre ni se exponen estos nombres a Gemini.
    matches=[]
    for g in grupos:
        docente=normal(g.get('hoja',''))
        curso=normal(g.get('nombre',''))
        if (len(docente)>=9 and docente in q) or (len(curso)>=9 and curso in q):
            matches.append(g)
    if matches and any(x in q for x in ('curso','docente','horario','inicio','fecha','termin','pea','sede','grupo','imparte','informacion')):
        byid={s.get('group_id'):s for s in ctx.get('estados') or []}
        rows=[]
        for g in matches[:8]:
            estado=byid.get(g.get('id'),{})
            rows.append('**'+_nombre_curso(g)+'** · '+str(g.get('hoja',''))+' · '+str(g.get('tipo',''))+
                        ' · '+str(g.get('duracion','?'))+' h · '+str(g.get('inicio',''))+
                        ' al '+str(g.get('fin',''))+' · PEA: '+str(estado.get('doc','Sin verificar'))+
                        ' · MCE: '+str(estado.get('mce','Sin verificar')))
        return ('Encontré **'+str(len(matches))+' grupo(s) coincidente(s)** en Programación:\n\n- '+
                '\n- '.join(rows)+('\n\nHay otros resultados.' if len(matches)>8 else '')+
                '\n\nEstas fechas y estados provienen de ATRIO; no significan que el curso tenga matrícula confirmada.',
                'Programación y Seguimiento · Consultas locales')
    if cuantos and 'docente' in q and any(k in q for k in ('mas grupo','mayor carga','mayor numero de grupo','ranking')):
        totals=Counter(str(g.get('hoja') or '') for g in grupos)
        rows=[f'{name}: **{n} grupos**' for name,n in totals.most_common(7) if name]
        return ('Según Programación, los docentes con más grupos son: '+ '; '.join(rows)+'. No representa carga horaria semanal.', 'Programación · Conteo por docente')
    return None
