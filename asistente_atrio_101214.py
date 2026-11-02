"""Asistente ATRIO 10.12.15: chat de consulta, sin operaciones de escritura.

Las respuestas sobre datos proceden de Programación y de estados confirmados.
Gemini es opcional; no se transmiten registros individuales automáticamente.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from zoneinfo import ZoneInfo
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


def normalizar(texto):
    t = unicodedata.normalize('NFKD', str(texto or ''))
    return ''.join(c for c in t if not unicodedata.combining(c)).casefold()


def estadisticas_agrupadas(grupos):
    tipos = Counter(str(g.get('tipo') or 'Sin tipo') for g in grupos)
    return {'grupos_programados': len(grupos), 'por_tipo': dict(sorted(tipos.items()))}


def consulta_local_basica(pregunta, grupos, C, hoy=None):
    """Respuestas comprobables, sin inferir inscripciones ni estatus no confirmados."""
    q = normalizar(pregunta)
    hoy = hoy or date.today()
    if any(k in q for k in ('histori', 'extraordinario')) and any(k in q for k in ('pea', 'curso', 'generar', 'hacer', 'preparar', 'donde', 'como')):
        return ('Para PEA de ciclos anteriores, abre **PEA históricos**. Allí puedes crear un PEA o adaptar un PDF. '
                'Los resultados se guardan en **Mis PEA → Históricos** y no modifican Programación ni el ciclo vigente.', 'Guía operativa de ATRIO')
    if 'programacion' in q and any(k in q for k in ('correg', 'corrig', 'corrij', 'correcci', 'cambi', 'guardar', 'actualizar', 'nombre', 'excel')):
        return ('Las correcciones hechas como propuestas en **Programación** no sustituyen por sí mismas el Excel oficial. '
                'Descarga la copia con propuestas, revisa el cambio, haz respaldo y utiliza **Ajustes → Recursos → Programación** '
                'para validar y cargarla. Comprueba que el grupo siga vinculado a sus registros.', 'Flujo de Programación en ATRIO')
    if 'repositorio' in q and any(k in q for k in ('pea', 'adapt', 'pdf', 'curso', 'preparar', 'como')) and not any(k in q for k in ('cuant', 'numero', 'total', 'hay')):
        return ('Para un curso de **Repositorio del ciclo actual**, entra en **Preparar PEA**, selecciona el docente y el curso de Programación, '
                'adjunta el PDF, revisa los datos administrativos y confirma. Se conservan el original y la adaptación en **Mis PEA → Generados**. '
                'El adaptador debe reconocer la estructura del PDF antes de modificarlo.', 'Flujo Repositorio de ATRIO')
    if 'sisae' in q and any(k in q for k in ('como','corte','donde','subir','concili','actualizar')):
        return ('Consulta **SISAE · Cortes** para importar y analizar la copia de SISAE. La Programación es anual y las capturas SISAE avanzan por periodos; '
                'una diferencia puede deberse a capturas todavía pendientes. Confirma siempre la fecha del corte.', 'Guía de conciliación ATRIO')
    if any(k in q for k in ('mce', 'pendiente')) and any(k in q for k in ('cuant','total','cuantos','cuantas','numero','pendiente')):
        pendientes = []
        sin_pea = []
        for g in grupos:
            estado = C.status(g['id'])
            if str(g.get('tipo')) != 'Regular' and estado.get('mce') == 'No subido':
                pendientes.append(g)
            if estado.get('doc') == 'Sin PEA':
                sin_pea.append(g)
        return (f'En los estados **confirmados** de ATRIO hay **{len(pendientes)} registros marcados «No subido» en MCE** y '
                f'**{len(sin_pea)} marcados «Sin PEA»**. Los estados «Sin verificar» NO se cuentan como atrasos. '
                'Revisa **Seguimiento y MCE** para los detalles.', 'Estados registrados de ATRIO')
    if any(k in q for k in ('cuant','total','numero','cuantos','cuantas','resumen','estadistica')) and any(k in q for k in ('grupo','curso','programacion','repositorio','extension','regular')):
        info = estadisticas_agrupadas(grupos)
        desglose = ' · '.join(f'{tipo}: **{n}**' for tipo,n in info['por_tipo'].items())
        focal = next((t for t in ('Repositorio','Extensión','Regular') if normalizar(t) in q),None)
        comienzo = (f'Hay **{info["por_tipo"].get(focal,0)} registros de {focal}** en Programación. ' if focal else '')
        return (comienzo + f'Programación contiene **{info["grupos_programados"]} registros de grupos/cursos**. {desglose}. '
                'Son registros programados; esto NO equivale a matrícula inscrita en SISAE.', 'Programación cargada en ATRIO')
    if 'inicia' in q and ('hoy' in q or 'mes' in q):
        try:
            if 'hoy' in q:
                rows = [g for g in grupos if g.get('inicio') == hoy.isoformat()]
                descripcion = 'hoy'
            else:
                rows = [g for g in grupos if str(g.get('inicio','')).startswith(hoy.strftime('%Y-%m'))]
                descripcion = 'este mes'
        except Exception:
            return None
        nombres = '; '.join(str(g.get('nombre') or '') for g in rows[:6])
        plus = f' y {len(rows)-6} adicionales' if len(rows) > 6 else ''
        return (f'Hay **{len(rows)} registros con fecha de inicio {descripcion}** en Programación.' + (f' Ejemplos: {nombres}{plus}.' if rows else '') + ' No implica que ya se haya confirmado su apertura.', 'Fechas de Programación')
    return None



def consulta_local(pregunta, grupos, C, hoy=None):
    # Primero los datos reales, sin conexión externa.
    import atrio_consultas_1012141 as REG
    respuesta=REG.responder(pregunta,C,grupos)
    if respuesta is not None:return respuesta
    return consulta_local_basica(pregunta,grupos,C,hoy)


def _clave_gemini():
    key = os.getenv('GEMINI_API_KEY','').strip()
    if key: return key
    try:
        import streamlit as st
        return str(st.secrets.get('GEMINI_API_KEY','') or '').strip()
    except Exception:
        return ''


def _modelos_disponibles(key):
    """Consulta modelos autorizados por la clave, sin revelar su valor ni registros."""
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models?pageSize=100',
                               headers={'x-goog-api-key':key},method='GET')
    with urllib.request.urlopen(req,timeout=15) as resp:
        payload=json.loads(resp.read(500_000).decode('utf-8'))
    return [str(m.get('name','')).removeprefix('models/') for m in payload.get('models',[])
            if 'generateContent' in m.get('supportedGenerationMethods',[]) and str(m.get('name','')).startswith('models/')]


def diagnostico_ia():
    key=_clave_gemini()
    if not key:return ('No hay clave Gemini disponible en esta instancia. Configúrala en Ajustes → Servicio de contenido IA. Las consultas locales funcionan sin ella.',[])
    try:
        modelos=_modelos_disponibles(key)
        cfg=os.getenv('GEMINI_MODELO','gemini-2.5-flash').removeprefix('models/')
        if not modelos:return ('La clave respondió, pero no hay modelos con permiso para generar contenido.',[])
        if cfg not in modelos:return ('El modelo configurado «'+cfg+'» no aparece entre los habilitados para tu clave. Revisa Ajustes o usa uno de los modelos disponibles.',modelos[:12])
        return ('Conexión y modelo configurado disponibles: '+cfg+'. Esto no garantiza cuota suficiente para todas las solicitudes.',modelos[:12])
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403):return ('La clave fue rechazada por el servicio. Comprueba permisos sin compartirla aquí.',[])
        return ('Gemini devolvió HTTP '+str(exc.code)+' al consultar sus modelos.',[])
    except Exception:return ('No se pudo comprobar la conexión o el servicio no está accesible desde Cloud Shell.',[])


import sqlite3
from contextlib import closing
import nucleo_atrio_101215 as core

SOURCE = "Programación · groups (activos)"
PEA = "Mis PEA · artifacts, biblioteca_pea, pea_repo_actual_101213 y pea_hist_101212"
IMPACT = "Programación, Mis PEA, status, calendario y corte SISAE local"
DATES = r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b"

def responder_local(pregunta, C, memoria):
    from atrio_ia_101217.puente import responder_primero
    primera_respuesta = responder_primero(pregunta, C, memoria)
    if primera_respuesta is not None:
        return primera_respuesta
    q = core.normal(pregunta)
    with closing(core.conectar(C.ROOT)) as db:
        groups = core.grupos(db)
        by_id = {g["id"]:g for g in groups}
        previous = [by_id[i] for i in memoria.get("ids",[]) if i in by_id]
        dates = re.findall(DATES, pregunta)
        pending = memoria.get("modo")=="simular"
        index = re.fullmatch(r"(?:(?:el|grupo|opcion|numero)\s+)*(\d+)",q)
        hits = core.buscar(re.sub(DATES," ",pregunta),groups)
        if index and previous:
            k = int(index.group(1))
            if not 1 <= k <= len(previous):
                return "Elige uno de los números de la lista anterior.",SOURCE,memoria
            hits = [previous[k-1]]
        changing = any(w in q for w in ("cambi","mov","muev","aplaz","extiend","recorr","recuer","atras","adelant","pospon","simul","prolong","reprogram","pasaria","pasa si","terminara","terminase"))
        sim = (changing and any(w in q for w in ("termin","fecha","cierre","final","acaba","hasta"))) or (pending and (index or hits or dates) and "pea" not in q and not q.startswith(("cuantos","busca","muestra","que cursos")))
        if sim:
            if len(dates)>1:
                return "Indica solo la fecha nueva y selecciona el grupo por su número.",SOURCE,memoria
            supplied = dates[0] if dates else (memoria.get("fecha") if pending else None)
            if supplied and not core.fecha(supplied):
                return "Esa fecha no es válida. Usa DD/MM/AAAA.",SOURCE,dict(ids=[g["id"] for g in hits or previous],modo="simular")
            if not hits:
                refer = bool(re.search(r"\b(este|ese|su|este mismo|ese mismo|el mismo)\b",q)) or (pending and dates and not changing)
                hits = previous if refer else []
            state = dict(ids=[g["id"] for g in hits],modo="simular",fecha=supplied)
            if not hits:
                return "¿Qué curso o docente quieres analizar? Escribe su nombre. También puedes usar «Elegir grupo y fecha».",SOURCE,state
            if len(hits)>1:
                return listado(hits,"Hay varios grupos. Responde con el número del horario que corresponde."),SOURCE,state
            answer = core.simulation(db,C,hits[0],core.fecha(supplied))
            return answer,IMPACT,(dict(ids=state["ids"]) if supplied else state)
        pea = bool(re.search(r"\bpeas?\b",q))
        requested_count = any(w in q for w in ("cuant","total","cantidad","elabor","generad","hecho","list","cuales","llevo","tenemos","tengo","hay","balance","mis pea","produc","preparad"))
        if pea and requested_count and not any(w in q for w in ("como ","historico","subido","pendiente","falt","sin pea","mce","por elaborar")):
            if re.search(r"\b(este|ese|esos|estos|suyos|sus)\b",q) and not hits: hits=previous
            if not hits and re.search(r"\b(docente|maestr[oa]|profesor|para el curso|del curso)\b",q):
                return "Indica un docente o curso que aparezca en Programación para filtrar el conteo.",SOURCE,{}
            ids=[g["id"] for g in hits] if hits else None
            detail=any(w in q for w in ("list","cuales","muestra","desglos"))
            text=core.conteo(db,ids,detail,C.ROOT)
            if hits: text="Filtro · "+", ".join(sorted({str(g.get("hoja")) for g in hits}))+f" ({len(hits)} grupos coincidentes).\n\n"+text
            return text,PEA,dict(ids=ids or [])
        if hits:
            return listado(hits,f"Encontré {len(hits)} grupo(s) en Programación."),SOURCE,dict(ids=[g["id"] for g in hits])
        if q=="buscar docente" or re.search(r"(?:cursos (?:de|da|imparte)|imparte|maestr[oa]|profesor|docente de)\b",q):
            return "Escribe el nombre o apellido que figura en Programación, o elige el docente en «Elegir grupo y fecha».",SOURCE,{}
        if pea and ("generaron" in q or "cuales" in q) and previous:
            return core.conteo(db,[g["id"] for g in previous],True,C.ROOT),PEA,memoria
        old=consulta_local(pregunta,groups,C)
        if old: return old[0],old[1],{}
        return "No pude identificar el registro o la operación. Prueba con un apellido, el nombre del curso o «Mis PEA». Para una simulación puedes elegir el grupo y la fecha abajo.", "Asistente local",{}

def listado(rows, header):
    return header+"\n\n"+"\n\n".join(f"{i}. {core.ficha(g)}" for i,g in enumerate(rows,1))

def panel(grupos,C):
    import streamlit as st
    st.markdown('<div style="color:#aa8590;letter-spacing:.16em;font-size:11px;font-weight:700;margin-top:.2rem">JEFATURA DE CAPACITACIÓN · CECATI 31</div>',unsafe_allow_html=True)
    top, side = st.columns([7,2],vertical_alignment="center")
    top.markdown("### ✦ Asistente ATRIO")
    top.caption("10.12.17 · Consultas locales verificables · solo lectura")
    history = st.session_state.setdefault("ai215_chat",[])
    if side.button("Limpiar conversación",key="ai215_clear"):
        history.clear()
        st.session_state.pop("ai215_context",None)
        st.rerun()
    ask = None
    direct = None
    buttons = [("Resumen de grupos","¿Cuántos grupos hay en Programación?"),("Mis PEA","¿Cuántos PEA se han elaborado?"),("Buscar docente","Buscar docente"),("Simular término","Simular fecha de término")]
    for col,(label,prompt) in zip(st.columns(4),buttons):
        if col.button(label, key="ai215_"+label,use_container_width=True): ask=prompt
    with st.expander("Elegir grupo y fecha"):
        if grupos:
            teachers=sorted({g["hoja"] for g in grupos})
            teacher=st.selectbox("Docente",teachers,key="ai215_teacher")
            available=[g for g in grupos if g["hoja"]==teacher]
            g=st.selectbox("Curso, fechas y horario",available,format_func=core.ficha,key="ai215_group_"+teacher)
            if st.button("Ver cursos del docente"): ask=teacher
            baseline=core.fecha(g.get("fin")) or date.today()
            proposal=st.date_input("Término propuesto",value=baseline,min_value=date(1900,1,1),max_value=date(2100,12,31),key="ai215_end_"+str(g["id"]))
            if st.button("Analizar este cambio"):
                direct=g["id"]
                ask=f"Simular término al {proposal:%d/%m/%Y} · {core.ficha(g)}"
        else: st.caption("No hay grupos activos para seleccionar.")
    with st.expander("Privacidad y conexión"):
        st.caption("Los mensajes y los resultados de esta versión se consultan localmente. La comprobación manual de Gemini consulta únicamente la disponibilidad del servicio.")
        if st.button("Comprobar conexión con Gemini",key="ai215_diag"):
            message,models=diagnostico_ia()
            st.info(message)
            if models: st.caption(", ".join(models))
    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            if turn.get("source"): st.caption(turn["source"])
    ask=st.chat_input("Pregunta por tus PEA, un docente o una fecha de término…",max_chars=2300) or ask
    if ask:
        try:
            if direct is not None:
                with closing(core.conectar(C.ROOT)) as db:
                    live=next((row for row in core.grupos(db) if row["id"]==direct),None)
                    answer=core.simulation(db,C,live,proposal) if live else "El grupo ya no está activo."
                source,state=IMPACT,dict(ids=[direct])
            else: answer,source,state=responder_local(ask,C,st.session_state.get("ai215_context",{}))
        except (sqlite3.Error,OSError,ValueError,KeyError) as exc:
            answer="No pude verificar la fuente local ("+type(exc).__name__+"). Ejecuta la comprobación del paquete para revisar la instalación."
            source,state="Diagnóstico de lectura",{}
        st.session_state["ai215_context"]=state
        history.extend([dict(role="user",content=ask),dict(role="assistant",content=answer,source=source)])
        del history[:-24]
        st.rerun()
