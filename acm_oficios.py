"""Acciones Móviles · catálogo editable y oficios Word.

La información de Programación se lee sin alterarla. Los oficios se crean sobre
los tres formatos oficiales entregados por la usuaria; nunca se sobrescriben.
No modifica el seguimiento académico ni los datos de SISAE.
"""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import html
import json
import re
import uuid

import streamlit as st
from docx import Document

KEY = 'acm_instituciones_v1'
KINDS = ['Presentación', 'Vinculación', 'Asignación']
FILES = {
    'Presentación': 'Formato_Presentacion.docx',
    'Vinculación': 'Formato_Vinculacion.docx',
    'Asignación': 'Formato_Asignacion.docx',
}
MESES = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
         'septiembre','octubre','noviembre','diciembre']
EJEMPLO = {
    'id':'duport-ostion-ejemplo',
    'tipo':'CERESO',
    'nombre':'Centro de Reinserción Social “Duport Ostión”',
    'sede':'Cereso',
    'direccion':'',
    'responsable':'Próculo Bandala Tejeda',
    'cargo':'Director del Centro de Reinserción Social “Duport Ostión”',
    'beneficiarios':'las personas participantes',
}


def fecha_larga(value):
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return str(value or '')
    return f'{d.day:02d} de {MESES[d.month-1]} de {d.year}'


def ciclo_de(inicio):
    d = date.fromisoformat(str(inicio)[:10])
    y = d.year if d.month >= 7 else d.year-1
    return f'{y}–{y+1}'


def catalogo(C):
    rows = C.setting(KEY, [])
    return [x for x in rows if isinstance(x, dict) and x.get('id')] if isinstance(rows, list) else []


def guardar_catalogo(C, rows):
    C.set_setting(KEY, rows)


def _paragraphs(doc):
    """Incluye textos de tablas, encabezados y pies sin recrear sus estructuras."""
    def walk(obj):
        for p in obj.paragraphs:
            yield p
        for t in obj.tables:
            for row in t.rows:
                for cell in row.cells:
                    yield from walk(cell)
    yield from walk(doc)
    for sec in doc.sections:
        yield from walk(sec.header)
        yield from walk(sec.footer)


def _replace_runs(paragraph, key, value):
    """Sustituye tokens partidos entre runs conservando el estilo inicial."""
    count = 0
    runs = paragraph.runs
    if not runs:
        return 0
    text = ''.join(r.text for r in runs)
    while key in text:
        start = text.index(key); end = start + len(key)
        pos = 0; left = right = None
        for ix, run in enumerate(runs):
            following = pos + len(run.text)
            if left is None and pos <= start < following:
                left = (ix, start-pos)
            if right is None and pos < end <= following:
                right = (ix, end-pos)
                break
            pos = following
        if left is None or right is None:
            raise ValueError('No se pudo ubicar un marcador en el Word original.')
        i, oi = left; j, oj = right
        if i == j:
            runs[i].text = runs[i].text[:oi] + str(value) + runs[i].text[oj:]
        else:
            runs[i].text = runs[i].text[:oi] + str(value)
            for k in range(i+1,j):
                runs[k].text = ''
            runs[j].text = runs[j].text[oj:]
        count += 1
        text = ''.join(r.text for r in runs)
    return count


def render_word(template, variables, ciclo, *, sede_alterna=None, grupos=None):
    """Relleno seguro sin tocar la plantilla. Admite N cursos y tablas dinámicas."""
    doc = Document(template)
    grupos = list(grupos or [])
    distintos = len({str(g['curso']).strip().casefold() for g in grupos}) > 1 if grupos else False
    for p in _paragraphs(doc):
        if distintos:
            # No poner 'curso denominado varios cursos' ni verbos en singular.
            frases={
                'impartiendo el curso denominado "{{CURSO}}", correspondiente al Ciclo Escolar':
                    'impartiendo los cursos descritos en la relación siguiente, correspondientes al Ciclo Escolar',
                'del curso denominado "{{CURSO}}", en la modalidad':
                    'de los cursos descritos en la relación siguiente, en la modalidad',
                'para impartir el curso denominado “{{CURSO}}”, correspondiente a la especialidad de {{Especialidad}},':
                    'para impartir los cursos descritos en la relación siguiente, correspondientes a la especialidad de {{Especialidad}},',
                'Dicho curso se impartirá':'Los cursos se impartirán',
                'Dicho {{TEXTO_GRUPOS}} {{VERBO_GRUPOS}}':'Dichos {{TEXTO_GRUPOS}} {{VERBO_GRUPOS}}',
            }
            for a,b in frases.items():_replace_runs(p,a,b)
        if sede_alterna:
            _replace_runs(p,'en las instalaciones del {{INSTITUCION}}',
                          'en la sede '+sede_alterna+', correspondiente a {{INSTITUCION}}')
        for k,v in variables.items():
            if k=='GRUPOS' and grupos:continue
            _replace_runs(p,'{{'+k+'}}',str(v))
        if ciclo!='2026–2027':
            _replace_runs(p,'2026–2027',ciclo)
            _replace_runs(p,'2026-2027',ciclo)
    if grupos:
        from acm_tablas_10126 import insertar_grupos
        insertar_grupos(doc,grupos)
    for p in _paragraphs(doc):
        if re.search(r'\{\{[^}]+\}\}',p.text):
            raise ValueError('El formato tiene un marcador sin resolver: '+p.text[:130])
    output=BytesIO();doc.save(output);data=output.getvalue()
    Document(BytesIO(data))
    return data


def _course_values(grupos, instit, *, lugar, oficio_fecha, trato, especialidad, beneficiaries):
    """Campos comunes y gramática según uno o varios cursos, no por fila de Excel."""
    g=grupos[0]
    fem=trato=='Femenino'
    distintos=len({str(x['nombre']).strip().casefold() for x in grupos})>1
    ciclo=ciclo_de(g['inicio'])
    if any(ciclo_de(x['inicio'])!=ciclo for x in grupos):
        raise ValueError('Los cursos pertenecen a ciclos escolares distintos; genera oficios separados.')
    return {
        'INSTITUCION':str(instit['nombre']).strip(),
        'DIRECTOR_NOMBRE':str(instit['responsable']).strip().upper(),
        'DIRECTOR_CARGO':str(instit['cargo']).strip().upper(),
        'DOCENTE':str(g['hoja']).strip().upper(),
        'ESPECIALIDAD':str(especialidad).strip(),
        'Especialidad':str(especialidad).strip(),
        'CURSO':str(g['nombre']).strip(),
        'FECHA_ACTUAL':fecha_larga(oficio_fecha),
        'BENEFICIARIOS':str(beneficiaries).strip(),
        'GRUPOS':'{{GRUPOS}}',
        'EL_LA_C':'a la C.' if fem else 'al C.',
        'TRABAJADOR':'trabajadora' if fem else 'trabajador',
        'EL_LA_CARGO':'la docente' if fem else 'el docente',
        'MENCIONADO':'mencionada' if fem else 'mencionado',
        'PARTICIPACION_DEL':'de la' if fem else 'del',
        'cargo_lower':'instructora' if fem else 'instructor',
        'CARGO':'INSTRUCTORA' if fem else 'INSTRUCTOR',
        'asignacion':'asignada' if fem else 'asignado',
        'TEXTO_GRUPOS':'cursos' if distintos else 'curso',
        'VERBO_GRUPOS':'se impartirán' if distintos else 'se impartirá',
        'TEXTO_GRUPOS_PROG':'los cursos y grupos programados' if distintos else 'los datos de programación',
        'TEXTO_SIGUIENTES':'los siguientes grupos' if len(grupos)>1 else 'el siguiente grupo',
    }, ciclo


def _slug(s):
    import unicodedata
    s = ''.join(x for x in unicodedata.normalize('NFKD',str(s)) if not unicodedata.combining(x))
    return re.sub('[^A-Za-z0-9]+','_',s).strip('_')[:48] or 'curso'


def panel_catalogo(C):
    st.markdown('#### Instituciones y sedes · Acciones Móviles')
    st.caption('Edita los datos vigentes. No se guarda un historial de directores; los oficios emitidos anteriormente no se modifican.')
    rows = catalogo(C)
    labels = ['+ Nueva institución']+[f'{r.get("nombre", "Institución")} · {r.get("tipo", "")} ' for r in rows]
    selected = st.selectbox('Institución a consultar o editar', range(len(labels)), format_func=lambda x:labels[x], key='acm_cat_select')
    r = rows[selected-1] if selected else {}
    if not rows and st.button('Usar los datos de ejemplo · Duport Ostión',key='acm_duport'):
        guardar_catalogo(C,[dict(EJEMPLO)])
        st.rerun()
    with st.form('acm_catalog_form',clear_on_submit=False):
        uno, dos = st.columns([2,1])
        with uno: nombre = st.text_input('Nombre oficial de la institución',value=r.get('nombre',''))
        with dos:
            tipos = ['CERESO','Institución educativa','Empresa','Organismo público','Otra']
            current = r.get('tipo','Otra')
            tipo = st.selectbox('Tipo', tipos, index=tipos.index(current) if current in tipos else len(tipos)-1)
        uno, dos = st.columns(2)
        with uno:
            sede = st.text_input('Sede de impartición',value=r.get('sede',''))
            responsable = st.text_input('Nombre del destinatario o responsable',value=r.get('responsable',''))
        with dos:
            direccion = st.text_input('Dirección (si corresponde)',value=r.get('direccion',''))
            cargo = st.text_input('Cargo del destinatario',value=r.get('cargo',''))
        beneficiarios = st.text_input('Denominación de beneficiarios en los oficios',value=r.get('beneficiarios','las personas participantes'))
        save = st.form_submit_button('Guardar institución',type='primary')
    if save:
        if not nombre.strip() or not sede.strip():
            st.error('Completa como mínimo el nombre de la institución y su sede.')
        else:
            new = dict(id=r.get('id') or uuid.uuid4().hex, nombre=nombre.strip(), tipo=tipo,
                       sede=sede.strip(), direccion=direccion.strip(), responsable=responsable.strip(),
                       cargo=cargo.strip(), beneficiarios=beneficiarios.strip())
            if selected: rows[selected-1]=new
            else: rows.append(new)
            guardar_catalogo(C,rows)
            st.success('Datos actuales guardados. No se han generado ni modificado oficios.')
    if selected:
        if st.checkbox('Confirmo que quiero eliminar esta institución del catálogo',key='acm_confirm_delete'):
            if st.button('Eliminar del catálogo',key='acm_delete'):
                guardar_catalogo(C,[x for x in rows if x['id']!=r.get('id')])
                st.session_state.pop('acm_confirm_delete',None)
                st.rerun()
    st.caption('Para actualizar las tres plantillas Word de ACM, entra en Ajustes → Recursos. Se conservará la versión anterior.')


def validar_formato_acm(tipo, datos, previo=None):
    """Valida Word institucional antes de actualizar un membrete o una plantilla ACM."""
    if tipo not in FILES:
        raise ValueError('Tipo de oficio ACM desconocido.')
    if not isinstance(datos, bytes) or len(datos) < 1024:
        raise ValueError('El archivo Word no es válido o está vacío.')
    import zipfile
    try:
        with zipfile.ZipFile(BytesIO(datos)) as z:
            names=set(z.namelist())
            if 'word/document.xml' not in names or '[Content_Types].xml' not in names:
                raise ValueError('El archivo no contiene la estructura DOCX.')
            if any('vbaproject.bin' in n.lower() for n in names):
                raise ValueError('No se admiten macros en las plantillas de oficios.')
        doc=Document(BytesIO(datos))
    except (zipfile.BadZipFile, KeyError) as e:
        raise ValueError('El archivo cargado no es un Word .docx válido.') from e
    paragraphs=list(_paragraphs(doc))
    nuevo='\n'.join(p.text for p in paragraphs)
    tokens=set(re.findall(r'\{\{([A-Za-z_]+)\}\}',nuevo))
    minimos={'OFICIO','FECHA_ACTUAL','DOCENTE','INSTITUCION','GRUPOS'}
    faltan=minimos-tokens
    if faltan:
        raise ValueError('La plantilla ACM carece de marcadores necesarios: '+', '.join(sorted(faltan)))
    if previo:
        anterior=Document(BytesIO(previo))
        texto_anterior='\n'.join(p.text for p in _paragraphs(anterior))
        tokens_anterior=set(re.findall(r'\{\{([A-Za-z_]+)\}\}',texto_anterior))
        faltan=tokens_anterior-tokens
        if faltan:
            raise ValueError('La nueva plantilla perdió variables utilizadas por este oficio: '+', '.join(sorted(faltan)) + '. Conserva los marcadores al cambiar el membrete.')
    if not doc.paragraphs or not doc.sections:
        raise ValueError('La plantilla parece incompleta.')
    return {'tipo':tipo,'marcadores':sorted(tokens),'tamano':len(datos)}


def actualizar_formato_acm(C, tipo, datos):
    """Actualiza solo una plantilla ACM, con respaldo y sustitución atómica."""
    import os, tempfile
    if tipo not in FILES:raise ValueError('Oficio no reconocido.')
    destino=C.RES/'acm'/FILES[tipo]
    previo=destino.read_bytes() if destino.is_file() else None
    resumen=validar_formato_acm(tipo,datos,previo)
    destino.parent.mkdir(parents=True,exist_ok=True)
    if previo is not None:
        carpeta=C.ARCH/'acm'
        carpeta.mkdir(parents=True,exist_ok=True)
        copia=carpeta/(datetime.now().strftime('%Y%m%d_%H%M%S_%f_')+FILES[tipo])
        copia.write_bytes(previo)
        if hashlib.sha256(copia.read_bytes()).digest()!=hashlib.sha256(previo).digest():
            raise RuntimeError('No se pudo verificar el respaldo; no se reemplazó la plantilla.')
    fd,temporal=tempfile.mkstemp(prefix='.acm_word_',suffix='.docx',dir=str(destino.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(datos);f.flush();os.fsync(f.fileno())
        os.replace(temporal,destino)
    finally:
        if os.path.exists(temporal):os.unlink(temporal)
    return resumen


def _resumen_oficio(datos):
    """Metadatos capturados y CONFIRMADOS para la vista previa, nunca tomados de IA."""
    return {
        'Documento': ', '.join(datos['tipos']),
        'Institución': datos['institucion'],
        'Sede': datos['sede'],
        'Docente': datos['docente'],
        'Cursos o grupos': str(len(datos['grupos'])),
        'Fecha de emisión': fecha_larga(datos['fecha_emision']),
        'Folios': ' · '.join(k+': CECATI 31/'+v for k,v in datos['folios'].items()),
    }


def _mostrar_redaccion_word(data):
    """Lee el CUERPO del DOCX generado con la misma función que producirá el archivo."""
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    from docx.table import Table
    doc=Document(BytesIO(data))
    elementos=[]
    for child in doc.element.body.iterchildren():
        if child.tag==qn('w:p'):
            p=Paragraph(child,doc._body)
            if p.text.strip():elementos.append(('p',p.text))
        elif child.tag==qn('w:tbl'):
            table=Table(child,doc._body)
            rows=[]
            for row in table.rows:
                rows.append([cell.text.strip() for cell in row.cells])
            if any(any(c for c in row) for row in rows):elementos.append(('t',rows))
    with st.container(border=True):
        st.caption('Redacción extraída del Word real · no es una reproducción de su paginación')
        for kind,val in elementos:
            if kind=='p':
                st.markdown('<p style="font-size:0.88rem;line-height:1.65;margin:0.3rem 0;color:inherit">'+
                            html.escape(val).replace('\n','<br>')+'</p>',unsafe_allow_html=True)
            else:
                for row in val:
                    cols=st.columns(max(1,len(row)))
                    for c,txt in zip(cols,row):
                        with c:
                            with st.container(border=True):
                                st.markdown('<div style="font-size:0.78rem;line-height:1.5">'+
                                            html.escape(txt).replace('\n','<br>')+'</div>',unsafe_allow_html=True)
    st.caption('Antes de emitir, revisa también el Word descargado: membrete, firmante, tablas y saltos de página.')


def _ruta_segura_acm(base, folder, original):
    """Nunca descargar rutas arbitrarias de un manifest; solo archivos dentro de ACM."""
    root=base.resolve()
    name=Path(str(original or '')).name
    if not name.lower().endswith('.docx'):
        return None
    try:
        candidates=[(folder/name).resolve()]
        if original:candidates.append(Path(str(original)).resolve())
        for p in candidates:
            if p.is_relative_to(root) and p.is_file() and p.stat().st_size<=40*1024*1024:
                return p
    except (OSError,ValueError):
        return None
    return None


def _listar_expedientes_acm(C):
    root=C.OUT/'acm'
    if not root.is_dir():return []
    results=[]
    for f in sorted(root.glob('*/manifest.json'),key=lambda x:x.stat().st_mtime,reverse=True)[:300]:
        try:
            meta=json.loads(f.read_text(encoding='utf-8'))
            if not isinstance(meta,dict):continue
            docs=[]
            for item in meta.get('oficios',[]):
                if not isinstance(item,dict):continue
                p=_ruta_segura_acm(root,f.parent,item.get('path') or item.get('name'))
                if p:docs.append({'tipo':str(item.get('kind') or item.get('tipo') or ''),'path':p,'nombre':p.name})
            if docs:
                results.append({'meta':meta,'docs':docs,'carpeta':f.parent.name})
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
            continue
    return results


def _panel_mis_oficios(C):
    st.caption('Archivo de oficios generados · conservados en datos/salidas/acm. Descargar no vuelve a generarlos.')
    registros=_listar_expedientes_acm(C)
    if not registros:
        st.info('Todavía no hay oficios guardados. Al confirmar una vista previa y generar el Word, aparecerá aquí.')
        return
    st.caption(f'{len(registros)} expediente(s) de oficios disponibles')
    buscar=st.text_input('Buscar por docente, institución, curso o folio',key='acm_buscar_mis_oficios')
    filtro=buscar.strip().casefold()
    mostrados=0
    for n,entry in enumerate(registros):
        m=entry['meta']
        grupos=m.get('grupos',[])
        folios=m.get('folios',{})
        haystack=' '.join(str(x) for x in [m.get('docente',''),m.get('institucion',''),m.get('sede',''),
                    *[g.get('curso','') for g in grupos if isinstance(g,dict)],
                    *(list(folios.values()) if isinstance(folios,dict) else [])]).casefold()
        if filtro and filtro not in haystack:continue
        mostrados+=1
        fecha=fecha_larga(m.get('fecha_emision',''))
        label=f'{fecha} · {m.get("docente","Docente")} · {m.get("institucion","Institución")} · {len(entry["docs"])} oficio(s)'
        with st.expander(label,expanded=False):
            st.caption('Estado: '+str(m.get('estado','Generado para revisión · entrega por confirmar')))
            st.write('**Cursos/grupos:** '+str(len(grupos))+' · **Sede:** '+str(m.get('sede','')))
            for g in grupos:
                if isinstance(g,dict):st.caption(str(g.get('curso',''))+' · '+fecha_larga(g.get('inicio',''))+' a '+fecha_larga(g.get('termino','')))
            for j,item in enumerate(entry['docs']):
                a,b=st.columns([2,1],vertical_alignment='center')
                with a:
                    st.write('**'+str(item['tipo'])+'** · CECATI 31/'+str(folios.get(item['tipo'],'—')))
                with b:
                    st.download_button('Descargar Word',data=item['path'].read_bytes(),
                        file_name=item['nombre'],mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        key='acm_archivo_'+entry['carpeta']+'_'+str(j),use_container_width=True)
    if not mostrados:st.caption('No hay expedientes que coincidan con la búsqueda.')


def generar_oficio_para_ia(groups, C, docente, curso="", institucion="", tipo_oficio="Los tres oficios", folio="S/N"):
    """
    Función expuesta para el Asistente Virtual (Gemini).
    Busca el grupo, la institución, prepara las variables y genera el oficio Word.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    # 1. Filtrar grupos ACM
    def _es_acm(g):
        fields = ('modalidad','subtipo','tipo_accion','observaciones','aula','nombre')
        s = ' '.join(str(g.get(k,'') or '') for k in fields).lower()
        return bool(re.search(r'(?<![a-z])acm(?![a-z])|acci[oó]n(?:es)? m[oó]vil(?:es)?', s))
    
    acm_groups = [g for g in groups if _es_acm(g)]
    
    # 2. Buscar docente y curso
    docente_norm = str(docente).strip().lower()
    grupos_docente = [g for g in acm_groups if docente_norm in str(g['hoja']).lower()]
    if not grupos_docente:
        return {"status": "error", "mensaje": f"No se encontraron cursos ACM para el docente '{docente}'."}
    
    if curso:
        curso_norm = str(curso).strip().lower()
        grupos_curso = [g for g in grupos_docente if curso_norm in str(g['nombre']).lower()]
        if not grupos_curso:
            return {"status": "error", "mensaje": f"No se encontró el curso '{curso}' para {docente}."}
        grupo = grupos_curso[0]
    else:
        grupo = grupos_docente[0]
        
    # 3. Buscar institución
    rows = catalogo(C)
    if not rows:
        return {"status": "error", "mensaje": "El catálogo de instituciones ACM está vacío."}
        
    if institucion:
        inst_norm = str(institucion).strip().lower()
        inst_match = [r for r in rows if inst_norm in str(r.get('nombre', '')).lower()]
        inst = inst_match[0] if inst_match else rows[0]
    else:
        inst = rows[0]

    # 4. Determinar plantillas a generar
    if tipo_oficio == "Los tres oficios" or not tipo_oficio:
        kinds = KINDS
    else:
        # Buscar coincidencia flexible (ej. "presentacion" -> "Presentación")
        kinds = [k for k in KINDS if str(tipo_oficio).strip().lower() in k.lower()]
        if not kinds:
            kinds = [KINDS[0]] # Por defecto Presentación

    # 5. Preparar datos para el renderizado
    try:
        # Datos por defecto para los campos que la IA no extrajo
        oficio_fecha = datetime.now(ZoneInfo('America/Mexico_City')).date()
        lugar = inst.get('sede', '')
        esp = grupo.get('especialidad_programada') or grupo.get('especialidad') or 'Capacitación para el Trabajo'
        beneficiaries = inst.get('beneficiarios', 'las personas participantes')
        
        # Crear el registro detallado del grupo (lo que va en la tabla)
        details = [dict(
            id=str(grupo['id']), curso=grupo['nombre'], inicio=grupo['inicio'],
            termino=grupo['fin'], dias=grupo.get('horario',''), horario=grupo.get('horario',''),
            duracion=grupo['duracion'], sede=lugar
        )]
        
        # Si el grupo tiene un formato de horario específico, intentar separarlo
        from acm_tablas_10126 import separar_horario
        dias, horario = separar_horario(grupo.get('horario',''))
        details[0]['dias'] = dias
        details[0]['horario'] = horario

        inst_dict = dict(inst, responsable=inst.get('responsable',''), cargo=inst.get('cargo',''))
        
        variables, ciclo = _course_values(
            [grupo], inst_dict, lugar=lugar, oficio_fecha=oficio_fecha,
            trato='Masculino', especialidad=esp, beneficiaries=beneficiaries
        )
        
        # Determinar si hay sede alterna
        sede_alterna = (lugar.strip() if lugar.strip().casefold() not in str(inst['nombre']).casefold() 
                        and lugar.strip().casefold() not in str(inst.get('tipo','')).casefold() else None)

        # Generar los documentos
        output_files = {}
        for kind in kinds:
            template_path = C.RES / 'acm' / FILES[kind]
            if not template_path.is_file():
                return {"status": "error", "mensaje": f"Falta el formato institucional: {FILES[kind]}"}
            
            output_bytes = render_word(
                template_path, 
                dict(variables, OFICIO=folio), 
                ciclo, 
                sede_alterna=sede_alterna, 
                grupos=details
            )
            output_files[kind] = output_bytes

        # Si es un solo oficio, devolverlo directo; si son varios, empaquetarlos en ZIP
        if len(output_files) == 1:
            kind = list(output_files.keys())[0]
            filename = f"Oficio_{_slug(kind)}_{_slug(grupo['hoja'])}_{_slug(folio)}.docx"
            return {
                "status": "ok",
                "mensaje": f"Oficio de {kind} generado para {grupo['hoja']}.",
                "filename": filename,
                "bytes": output_files[kind],
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
        else:
            import zipfile
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for kind, data in output_files.items():
                    name = f"Oficio_{_slug(kind)}_{_slug(grupo['hoja'])}.docx"
                    zip_file.writestr(name, data)
            
            filename = f"Oficios_ACM_{_slug(grupo['hoja'])}.zip"
            return {
                "status": "ok",
                "mensaje": f"Los 3 oficios fueron generados para {grupo['hoja']}.",
                "filename": filename,
                "bytes": zip_buffer.getvalue(),
                "mime": "application/zip"
            }
            
    except Exception as e:
        return {"status": "error", "mensaje": f"Error al generar el oficio: {str(e)}"}


def panel_oficios(groups,C):
    preparar,mis=st.tabs(['Preparar oficio','Mis oficios'])
    with preparar:_panel_preparar_oficios(groups,C)
    with mis:_panel_mis_oficios(C)


def _panel_preparar_oficios(groups,C):
    from acm_tablas_10126 import separar_horario, validar_grupos
    st.caption('Oficios ACM · un oficio puede incluir varios cursos o grupos del mismo docente.')
    rows=catalogo(C)
    if not rows:
        st.info('Registra primero la institución en Ajustes → Instituciones y sedes ACM.')
        if st.button('Ir a Ajustes',key='acm_go_settings'):
            st.session_state['_atrio_pagina_actual']='Ajustes';st.rerun()
        return
    if not groups:
        st.info('No hay grupos disponibles en Programación.');return
    def es_acm(g):
        fields=('modalidad','subtipo','tipo_accion','observaciones','aula','nombre')
        s=' '.join(str(g.get(k,'') or '') for k in fields).lower()
        return bool(re.search(r'(?<![a-z])acm(?![a-z])|acci[oó]n(?:es)? m[oó]vil(?:es)?',s))
    acm=[g for g in groups if es_acm(g)]
    if not acm:
        st.warning('Programación no identifica claramente cursos ACM. No los incluiremos automáticamente.')
    with st.expander('No aparece un curso ACM en el listado',expanded=False):
        opt=st.checkbox('Mostrar otros cursos solo para identificarlos manualmente como ACM',key='acm_other_manual')
        st.caption('La confirmación se aplica al oficio, no cambia la clasificación de Programación.')
    disponible=groups if opt else acm
    if not disponible:
        return
    st.markdown('##### 1 · Seleccionar oficio e institución')
    una,otra=st.columns([1,2])
    with una:
        modalidad=st.selectbox('Documento a generar',['Los tres oficios','Presentación','Vinculación','Asignación'],key='acm_tipo_oficio')
    with otra:
        instit=st.selectbox('Institución receptora',rows,format_func=lambda x:x.get('nombre','Institución'),key='acm_institucion')
    st.markdown('##### 2 · Elegir docente y cursos/grupos ACM')
    teachers=sorted({g['hoja'] for g in disponible})
    docente=st.selectbox('Docente',teachers,key='acm_docente_elegido')
    sub=sorted([g for g in disponible if g['hoja']==docente],key=lambda g:(str(g['inicio']),str(g['nombre']),str(g.get('horario',''))))
    byid={str(g['id']):g for g in sub}
    chosen=st.multiselect('Cursos o grupos que se incluirán en el mismo oficio',list(byid),
         format_func=lambda k:(f'{byid[k]["nombre"]} · {fecha_larga(byid[k]["inicio"])} a '
                               f'{fecha_larga(byid[k]["fin"])} · {byid[k].get("horario","")}'),
         key='acm_cursos_multiples')
    if not chosen:
        st.caption('Selecciona uno o varios. Con 1 no se inserta tabla; con 2 a 4 se crea una tabla del mismo número de columnas.')
        return
    selected=[byid[k] for k in chosen]
    if len(selected)>12:
        st.error('Selecciona como máximo 12 grupos por oficio para evitar documentos ilegibles.');return
    if any(not es_acm(g) for g in selected):
        st.warning('La selección contiene cursos no marcados como ACM en Programación.')
        manual=st.checkbox('Confirmo que estos cursos corresponden a Acciones Móviles de Capacitación',key='acm_confirm_modalidad')
    else:manual=True
    especialidades={str(g.get('especialidad_programada') or '').strip() for g in selected if str(g.get('especialidad_programada') or '').strip()}
    if len(especialidades)>1:
        st.error('Los cursos tienen especialidades distintas. Por seguridad, el oficio debe elaborarse por especialidad para no identificar mal el cargo del docente.')
        return
    st.markdown('##### 3 · Confirmar datos para el oficio')
    with st.form('acm_emision_multiples'):
        uno,otra=st.columns([1,1],gap='large')
        with uno:
            lugar=st.text_input('Sede de impartición',value=instit.get('sede',''))
            esp=st.text_input('Especialidad que aparecerá en el oficio',value=next(iter(especialidades),'') )
            beneficiarios=st.text_input('Población beneficiaria',value=instit.get('beneficiarios','las personas participantes'))
        with otra:
            emission=st.date_input('Fecha de emisión',value=datetime.now(ZoneInfo('America/Mexico_City')).date(),format='DD/MM/YYYY')
            trato=st.selectbox('Tratamiento del docente',['Masculino','Femenino'],help='No se deduce por el nombre.')
            if modalidad in ('Los tres oficios','Presentación'):
                responsable=st.text_input('Destinatario de Presentación',value=instit.get('responsable',''))
                cargo=st.text_input('Cargo del destinatario',value=instit.get('cargo',''))
            else:
                responsable=instit.get('responsable','');cargo=instit.get('cargo','')
        kinds=KINDS if modalidad=='Los tres oficios' else [modalidad]
        st.caption('El formato ya contiene «CECATI 31/»; escribe solo el consecutivo sin repetir el prefijo.')
        folios={}
        c=st.columns(len(kinds))
        for i,kind in enumerate(kinds):
            with c[i]:folios[kind]=st.text_input('Folio · '+kind,placeholder='Ej. 124/2026')
        details=[]
        with st.expander('Días y horarios de cada grupo · confirmar si es necesario',expanded=False):
            st.caption('ATRIO recupera el horario de Programación. Puedes corregir su lectura para este oficio sin alterar Programación.')
            for i,g in enumerate(selected,1):
                dias,horario=separar_horario(g.get('horario',''))
                st.markdown('**Grupo '+str(i)+' · '+str(g['nombre'])+'**')
                x,y=st.columns(2)
                with x:dia_ok=st.text_input('Días · grupo '+str(i),value=dias,key='acm_dias_'+str(g['id']))
                with y:hora_ok=st.text_input('Horario · grupo '+str(i),value=horario,key='acm_hora_'+str(g['id']))
                details.append(dict(id=str(g['id']),curso=g['nombre'],inicio=g['inicio'],termino=g['fin'],
                                    dias=dia_ok,horario=hora_ok,duracion=g['duracion'],sede=lugar))
        confirm=st.checkbox('Confirmé grupos, datos institucionales, folios y vigencia del firmante que aparece en el Word.')
        do=st.form_submit_button('Revisar redacción antes de generar',type='primary')
    identity=tuple(sorted(chosen))+(instit['id'],modalidad)
    previa=st.session_state.get('acm_vista127')
    if previa is not None and previa.get('identity')!=identity:
        st.session_state.pop('acm_vista127',None)
        st.session_state.pop('acm_aprobacion127',None)
        previa=None
    if do:
        st.session_state.pop('acm_vista127',None)
        st.session_state.pop('acm_aprobacion127',None)
        if not manual or not confirm or not all(str(f).strip() for f in folios.values()):
            st.error('Confirma la modalidad ACM, los datos y los folios de los oficios seleccionados.')
        elif not lugar.strip() or not esp.strip() or not beneficiarios.strip():
            st.error('Debes confirmar la sede, especialidad y población beneficiaria.')
        elif 'Presentación' in kinds and (not responsable.strip() or not cargo.strip()):
            st.error('El oficio de Presentación requiere nombre y cargo del destinatario.')
        elif any(str(v).strip().upper().startswith('CECATI 31/') for v in folios.values()):
            st.error('No repitas CECATI 31/ en el folio; ya figura en el Word.')
        elif any(not re.fullmatch(r'[0-9A-Za-z/_-]{1,32}',str(v).strip()) for v in folios.values()):
            st.error('Revisa los caracteres de cada folio.')
        else:
            try:
                validar_grupos(details)
                inst=dict(instit,responsable=responsable.strip(),cargo=cargo.strip())
                variables,ciclo=_course_values(selected,inst,lugar=lugar,oficio_fecha=emission,
                     trato=trato,especialidad=esp,beneficiaries=beneficiarios)
                sede_alterna=(lugar.strip() if lugar.strip().casefold() not in str(inst['nombre']).casefold() and
                              lugar.strip().casefold() not in str(inst.get('tipo','')).casefold() else None)
                output={};template_hashes={}
                for kind in kinds:
                    template=C.RES/'acm'/FILES[kind]
                    if not template.is_file():raise FileNotFoundError('Falta el formato ACM: '+FILES[kind])
                    template_hashes[kind]=hashlib.sha256(template.read_bytes()).hexdigest()
                    output[kind]=render_word(template,dict(variables,OFICIO=folios[kind].strip()),ciclo,
                                             sede_alterna=sede_alterna,grupos=details)
                meta={'grupos':[{'id':str(g['id']),'curso':g['nombre'],'inicio':str(g['inicio']),
                       'termino':str(g['fin']),'horario':d['horario'],'dias':d['dias']} for g,d in zip(selected,details)],
                       'docente':docente,'institucion':inst['nombre'],'sede':lugar,'especialidad':esp,
                       'fecha_emision':emission.isoformat(),'ciclo':ciclo,'folios':folios,
                       'estado':'Borradores Word para revisión; sin firma ni autorización'}
                st.session_state['acm_vista127']=dict(identity=identity,output=output,meta=meta,
                      template_hashes=template_hashes,hashes={k:hashlib.sha256(v).hexdigest() for k,v in output.items()})
                st.caption('Vista previa preparada usando el Word real. Todavía no se ha guardado ningún oficio.')
            except Exception as e:
                st.error('No fue posible preparar la vista previa: '+str(e))
    previa=st.session_state.get('acm_vista127')
    if previa and previa.get('identity')==identity:
        from acm_editor_10128 import extraer_parrafos_editables, aplicar_ediciones, validar_integridad
        st.markdown('##### 4 · Redactar y revisar antes de emitir')
        st.caption('Datos de Programación, grupos, membrete y firma protegidos. '
                   'Modifica los párrafos del cuerpo; la vista previa se actualiza al confirmar cada campo.')
        with st.expander('Resumen del oficio · datos confirmados', expanded=False):
            metadata=_resumen_oficio({**previa['meta'],'tipos':list(previa['output'])})
            for k,v in metadata.items():
                a,b=st.columns([1,3]);a.caption(k);b.write(v)
        original=previa['output']  # bytes reales renderizados desde los formatos institucionales
        huella_origen=hashlib.sha256(b''.join(original[k] for k in sorted(original))).hexdigest()
        if st.session_state.get('acm_editor_base128') != huella_origen:
            st.session_state['acm_editor_base128']=huella_origen
            st.session_state.pop('acm_aprobacion127',None)
            # Limpiar SOLO widgets de redacción de un expediente anterior.
            for key in list(st.session_state):
                if str(key).startswith('acm128_texto_'):
                    del st.session_state[key]
        st.caption('El texto que edites será exclusivo de estos oficios; no cambiará Programación, '
                   'el catálogo de instituciones ni las plantillas originales.')
        actualizados={}; cambios_todos={}
        tabs=st.tabs(list(original))
        hay_error=False
        for tab,(tipo,base) in zip(tabs,original.items()):
            with tab:
                izq,der=st.columns([1,1], gap='medium')
                elegibles=extraer_parrafos_editables(base)
                modificaciones={}
                with izq:
                    st.markdown('**Editar la redacción**')
                    st.caption('Los campos oficiales deben corregirse en Confirmar datos. Aquí puedes '
                               'cambiar la redacción de los párrafos. No se altera el Word institucional.')
                    for n,p in enumerate(elegibles,1):
                        key=f'acm128_texto_{tipo}_{p["indice"]}'
                        if key not in st.session_state:
                            st.session_state[key]=p['texto']
                        value=st.text_area(f'Párrafo {n}',key=key,height=100,
                                           max_chars=3200,help='El texto del oficio cambia al confirmar este campo.')
                        if value!=p['texto']:
                            modificaciones[p['indice']]=value
                    if st.button('Restaurar redacción original · '+tipo,
                                 key='acm128_restaurar_'+_slug(tipo)):
                        for p in elegibles:
                            st.session_state[f'acm128_texto_{tipo}_{p["indice"]}']=p['texto']
                        st.session_state.pop('acm_aprobacion127',None)
                        st.rerun()
                with der:
                    st.markdown('**Vista previa del texto**')
                    try:
                        data,diffs=aplicar_ediciones(base,modificaciones)
                        validar_integridad(data,docente=previa['meta']['docente'],
                            institucion=previa['meta']['institucion'],
                            grupos=previa['meta']['grupos'],folio=previa['meta']['folios'][tipo])
                        actualizados[tipo]=data
                        cambios_todos[tipo]=diffs
                        _mostrar_redaccion_word(data)
                    except Exception as ex:
                        hay_error=True
                        st.error('Revisa la redacción: '+str(ex))
                if modificaciones:
                    st.caption(f'{len(modificaciones)} párrafo(s) modificado(s) en {tipo}.')
        if not hay_error and len(actualizados)==len(original):
            huellas={tipo:hashlib.sha256(data).hexdigest() for tipo,data in actualizados.items()}
            firma_textos={'base':huella_origen,'cambios':cambios_todos}
            huella_editor=hashlib.sha256(json.dumps(
                firma_textos,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
            if st.session_state.get('acm_editor_final128')!=huella_editor:
                st.session_state['acm_editor_final128']=huella_editor
                st.session_state.pop('acm_aprobacion127',None)
            previa['output_editado128']=actualizados
            previa['ediciones128']=cambios_todos
            previa['huellas_editadas128']=huellas
            st.caption('La vista previa procede del mismo Word que guardarás. '
                       'Verifica los saltos de página, logotipos y membrete en Word antes de emitir.')
            ok=st.checkbox('Revisé la redacción y confirmo guardar estos Word como borradores, sin firma ni autorización.',
                           key='acm_aprobacion127')
            if st.button('Generar y guardar '+('los tres oficios' if len(actualizados)>1 else 'oficio Word'),
                         type='primary',disabled=not ok,key='acm_guardar_127'):
                try:
                    for tipo,digest in previa['template_hashes'].items():
                        if hashlib.sha256((C.RES/'acm'/FILES[tipo]).read_bytes()).hexdigest()!=digest:
                            raise RuntimeError('La plantilla '+tipo+' cambió; debes revisar el documento de nuevo.')
                    for tipo,data in actualizados.items():
                        if hashlib.sha256(data).hexdigest()!=huellas[tipo]:
                            raise RuntimeError('La edición cambió; no se guardó ningún documento.')
                    stamp=datetime.now(ZoneInfo('America/Mexico_City')).strftime('%Y%m%d_%H%M%S_%f')
                    folder=C.OUT/'acm'/('varios_'+stamp)
                    folder.mkdir(parents=True,exist_ok=False)
                    result=[]
                    for kind,content in actualizados.items():
                        name=f'ACM_{_slug(kind)}_{_slug(docente)}_{stamp}.docx'
                        path=folder/name;path.write_bytes(content)
                        result.append(dict(kind=kind,name=name,path=str(path)))
                    registro=dict(previa['meta'],oficios=result,version_emisor='10.12.8',
                        ediciones_redaccion={tipo:dif for tipo,dif in cambios_todos.items() if dif},
                        huellas_sha256={r['kind']:hashlib.sha256(Path(r['path']).read_bytes()).hexdigest() for r in result})
                    (folder/'manifest.json').write_text(json.dumps(registro,ensure_ascii=False,indent=2),encoding='utf-8')
                    for g in selected:
                        C.event(str(g['id']),'Oficios ACM para revisión',
                                {'carpeta':str(folder),'tipos':list(actualizados)})
                    st.session_state['acm_generados']=result
                    st.session_state['acm_generados_de']=tuple(sorted(chosen))+(instit['id'],)
                    st.session_state.pop('acm_vista127',None)
                    st.session_state.pop('acm_aprobacion127',None)
                    st.success('Oficios guardados en Mis oficios. Son borradores; entrega y firma pendientes.')
                    st.toast('✅ Oficios generados y guardados', icon='📄')
                except Exception as ex:
                    st.error('No fue posible guardar: '+str(ex))
        else:
            st.caption('Corrige la redacción señalada antes de generar los oficios.')
    result=st.session_state.get('acm_generados',[])
    if result and st.session_state.get('acm_generados_de')==tuple(sorted(chosen))+(instit['id'],):
        st.markdown('##### 5 · Word guardados · Mis oficios')
        for item in result:
            p=Path(item['path'])
            if p.is_file():
                st.download_button('Descargar '+item['kind'],data=p.read_bytes(),file_name=item['name'],
                    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    key='acm_download_'+item['kind'])
        st.caption('Puedes encontrar estos Word de nuevo en la pestaña Mis oficios, sin regenerarlos.')