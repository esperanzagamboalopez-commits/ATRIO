"""Lista de asistencia ACM · usa TU plantilla .xlsx como molde."""

from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
import json
import re
import unicodedata
import shutil

import streamlit as st
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Side

MESES_LARGO = ['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO','JULIO',
               'AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE']
MESES_SHORT = ['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGOS','SEP','OCT','NOV','DIC']
DIAS_SEMANA = ['LUNES','MARTES','MIERCOLES','JUEVES','VIERNES','SÁBADO','DOMINGO']

CATALOG_KEY = 'acm_instituciones_v1'
TEMPLATE_KEY = 'ACM_Asistencia_Plantilla.xlsx'


def _template_path(C):
    """Ruta oficial de la plantilla dentro de datos/recursos/acm/."""
    return C.RES / 'acm' / TEMPLATE_KEY


def _template_exists(C):
    return _template_path(C).is_file()


def _dias_de_horario(horario):
    s = str(horario or '').upper()
    out = set()
    for idx, names in {
        0: ('LUNES',), 1: ('MARTES',),
        2: ('MIERCOLES','MIÉRCOLES'), 3: ('JUEVES',),
        4: ('VIERNES',), 5: ('SÁBADO','SABADO'), 6: ('DOMINGO',)
    }.items():
        for n in names:
            if re.search(r'\b' + re.escape(n) + r'\b', s):
                out.add(idx)
                break
    return out


def _horas_label(horario):
    m = re.search(r'(\d{1,2}):\d{2}\s*(?:A|–|-)\s*(\d{1,2}):\d{2}',
                  str(horario or ''), re.I)
    return f'{int(m.group(1))} A {int(m.group(2))}' if m else ''


def _quincena(y, m, q):
    if q == 1:
        return date(y, m, 1), date(y, m, 15)
    nxt = date(y+1, 1, 1) if m == 12 else date(y, m+1, 1)
    return date(y, m, 16), nxt - timedelta(days=1)


def _quincenas_de(inicio, fin):
    out = []
    y, m = inicio.year, inicio.month
    while date(y, m, 1) <= fin:
        for q in (1, 2):
            d1, d2 = _quincena(y, m, q)
            if max(d1, inicio) <= min(d2, fin):
                out.append((y, m, q))
        y, m = (y+1, 1) if m == 12 else (y, m+1)
    return out


def _ciclo_de(inicio):
    y = inicio.year if inicio.month >= 7 else inicio.year - 1
    return f'{y} - {y + 1}'


def _festivos(C):
    try:
        rows = json.loads((C.RES / 'DIAS_SIN_CLASE.json').read_text())
        return {date.fromisoformat(str(x)[:10]) for x in rows}
    except Exception:
        return set()


def _slug(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s))
                if not unicodedata.combining(c))
    return re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_')[:48] or 'archivo'


def _fila_fecha(f, inicio, fin, dias_clase, festivos):
    nombre = DIAS_SEMANA[f.weekday()]
    finde = f.weekday() >= 5
    if f in festivos:
        return 'SUSPENSIÓN', 'SUSPENSIÓN', 'SUSPENSIÓN'
    if f < inicio:
        return ((nombre, nombre, 'FIN DE SEMANA') if finde
                else (nombre, nombre, 'SIN CURSO INICIADO'))
    if f > fin:
        return ((nombre, nombre, 'FIN DE SEMANA') if finde
                else (nombre, nombre, 'DÍA OCUPADO EN OTRO CURSO'))
    if f.weekday() in dias_clase:
        return '', '', ''
    return ((nombre, nombre, 'FIN DE SEMANA') if finde
            else (nombre, nombre, 'DÍA OCUPADO EN OTRO CURSO'))


def _find_date_rows(ws):
    header_row = None
    for row in ws.iter_rows(min_row=1, max_row=30):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.strip().upper() == 'DIA':
                header_row = cell.row
                break
        if header_row:
            break
    if not header_row:
        raise ValueError('No se encontró la celda "DIA" en la plantilla.')
    first = last = None
    for r in range(header_row + 1, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if v is None:
            continue
        if hasattr(v, 'year'):
            first = first or r
            last = r
        elif isinstance(v, str):
            try:
                date.fromisoformat(v[:10])
                first = first or r
                last = r
            except (ValueError, TypeError):
                pass
    if first is None:
        raise ValueError('No se encontraron filas de fecha en la plantilla.')
    return first, last


def _update_header(ws, grupo, inst, inicio, fin, ciclo, m, q):
    target = {
        'CICLO ESCOLAR': f'CICLO ESCOLAR:   {ciclo}',
        'NOMBRE DEL INSTRUCTOR': f'NOMBRE DEL INSTRUCTOR:  {str(grupo.get("hoja","")).upper()}',
        'QUINCENA': f'QUINCENA: {q}° DE {MESES_LARGO[m-1]}',
        'LUGAR DE ASIGNACIÓN': f'LUGAR DE ASIGNACIÓN: {str(inst.get("nombre","")).upper()}',
        'DURACIÓN': f'DURACIÓN: {inicio.strftime("%d/%m/%Y")} AL  {fin.strftime("%d/%m/%Y")}',
        'NOMBRE DEL CURSO': f'NOMBRE DEL CURSO:    {str(grupo.get("nombre","")).upper()}',
        'HORARIO': f'HORARIO: {str(grupo.get("horario","")).upper()}',
    }
    for row in ws.iter_rows(min_row=1, max_row=15):
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            upper = cell.value.strip().upper()
            for label, new in target.items():
                if upper.startswith(label + ':') or upper.startswith(label + ' '):
                    cell.value = new
                    break


def _update_signatures(ws, inst, last_date_row):
    for offset in range(2, 8):
        r = last_date_row + offset
        if r > ws.max_row:
            break
        for c in range(1, min(ws.max_column, 12) + 1):
            cell = ws.cell(r, c)
            if not isinstance(cell.value, str):
                continue
            up = cell.value.upper()
            if 'INURRETA' in up:
                for cc in range(c-1, 0, -1):
                    left = ws.cell(r, cc)
                    if isinstance(left.value, str) and left.value.strip():
                        left.value = str(inst.get('responsable', '')).upper()
                        break
                break
            if 'RESPONSABLE DE LAS FUNCIONES' in up:
                for cc in range(c-1, 0, -1):
                    left = ws.cell(r, cc)
                    if isinstance(left.value, str) and left.value.strip():
                        left.value = str(inst.get('cargo', '')).upper()
                        break
                break


def _apply_date_style(ws, first_row, n_rows):
    thin = Side(style='thin', color='000000')
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    al = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for r in range(first_row, first_row + n_rows):
        for c in range(1, 5):
            cell = ws.cell(r, c)
            cell.border = box
            cell.alignment = al


def generar_excel(template_bytes, base_sheet_name, grupo, inst, dias_inhabiles):
    inicio = date.fromisoformat(str(grupo['inicio'])[:10])
    fin    = date.fromisoformat(str(grupo['fin'])[:10])
    dias   = _dias_de_horario(grupo.get('horario', '')) or {inicio.weekday()}
    ciclo  = _ciclo_de(inicio)
    horas  = _horas_label(grupo.get('horario', ''))

    wb = load_workbook(BytesIO(template_bytes))
    if base_sheet_name not in wb.sheetnames:
        raise ValueError(f'La hoja "{base_sheet_name}" ya no existe en la plantilla.')
    base = wb[base_sheet_name]

    quincenas = _quincenas_de(inicio, fin)
    if not quincenas:
        raise ValueError('El rango del curso no cubre ninguna quincena completa.')

    sheet_map = []
    for i, (y, m, q) in enumerate(quincenas):
        base_name = f'{horas} ({q} {MESES_SHORT[m-1]})' if horas else f'{q} {MESES_SHORT[m-1]}'
        name = base_name[:31]
        n = 2
        while name in wb.sheetnames:
            suf = f' ({n})'
            name = base_name[:31-len(suf)] + suf
            n += 1
        
        ws = wb.copy_worksheet(base)
        ws.title = name
        sheet_map.append((ws, (y, m, q)))

    del wb[base_sheet_name]

    for ws, (y, m, q) in sheet_map:
        _update_header(ws, grupo, inst, inicio, fin, ciclo, m, q)

        first, last = _find_date_rows(ws)
        existing = last - first + 1
        d1, d2 = _quincena(y, m, q)
        needed = (d2 - d1).days + 1

        if needed < existing:
            ws.delete_rows(first + needed, existing - needed)
        elif needed > existing:
            ws.insert_rows(first + existing, needed - existing)
            _apply_date_style(ws, first + existing, needed - existing)

        cur = d1
        for i in range(needed):
            e, s, o = _fila_fecha(cur, inicio, fin, dias, dias_inhabiles)
            r = first + i
            ws.cell(r, 1, cur.isoformat())
            ws.cell(r, 2, e)
            ws.cell(r, 3, s)
            ws.cell(r, 4, o)
            cur += timedelta(days=1)

        _update_signatures(ws, inst, first + needed - 1)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _render_template_manager(C):
    st.markdown(
        'Sube tu Excel de muestra **en formato .xlsx**. Si tu archivo es `.xls`, '
        'ábrelo en Excel y usa **Guardar como → Libro de Excel (.xlsx)** antes de '
        'subirlo. ATRIO conservará ese archivo como plantilla y **no lo modifica**: '
        'lo usa como molde para generar los entregables.'
    )
    if _template_exists(C):
        st.success('Ya hay una plantilla guardada. Si subes otra, la anterior queda respaldada.')
    
    upload = st.file_uploader('Plantilla (.xlsx)', type=['xlsx'], key='asist_upload')
    if upload is not None:
        try:
            wb = load_workbook(BytesIO(upload.getvalue()))
            sheets = wb.sheetnames
            del wb
            if not sheets:
                raise ValueError('El archivo no contiene hojas.')
            st.caption('Hojas detectadas: ' + ', '.join(sheets))
            
            if st.button('Guardar plantilla', key='asist_save_template'):
                dest = _template_path(C)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_file():
                    shutil.copy2(dest, dest.with_name('ACM_Asistencia_Plantilla_backup.xlsx'))
                
                dest.write_bytes(upload.getvalue())
                st.success('Plantilla guardada exitosamente.')
                st.rerun()
        except Exception as e:
            st.error(f'No se pudo procesar o guardar el archivo: {e}')


def render(groups, C):
    st.caption(
        '**Lista de asistencia · con tu propia plantilla.** '
        'ATRIO toma una hoja de tu Excel de muestra (membrete, bordes, logotipo, '
        'celdas combinadas y ambas firmas) y genera un `.xlsx` nuevo por cada '
        'quincena del curso, rellenando instructor, quincena, duración, curso, '
        'horario y clasificando cada día.'
    )

    with st.expander('Plantilla institucional · una sola vez',
                     expanded=not _template_exists(C)):
        _render_template_manager(C)
        
    if not _template_exists(C):
        st.info('Primero sube una plantilla .xlsx para usar esta función.')
        return

    if not groups:
        st.info('No hay grupos disponibles en Programación.')
        return

    # --- FILTRO ESTRICTO PARA CURSOS ACM ---
    def _es_acm(g):
        fields = ('modalidad','subtipo','tipo_accion','observaciones','aula','nombre')
        s = ' '.join(str(g.get(k,'') or '') for k in fields).lower()
        return bool(re.search(r'(?<![a-z])acm(?![a-z])|acci[oó]n(?:es)? m[oó]vil(?:es)?', s))

    acm_groups = [g for g in groups if _es_acm(g)]
    
    if not acm_groups:
        st.info('No se encontraron cursos marcados como Acciones Móviles (ACM) en la Programación actual.')
        return
    # ---------------------------------------

    teachers = sorted({g['hoja'] for g in acm_groups if g.get('hoja')})
    if not teachers:
        return
    
    c1, c2 = st.columns(2)
    with c1:
        docente = st.selectbox('Docente', teachers, key='asist_doc')
    
    # Filtramos los cursos del docente seleccionado, usando solo los que son ACM
    sub = sorted([g for g in acm_groups if g['hoja'] == docente],
                 key=lambda g: (str(g['inicio']), str(g['nombre'])))
    
    with c2:
        grupo = st.selectbox(
            'Curso / grupo', sub, key='asist_grupo',
            format_func=lambda g: (f"{g['nombre']} · "
                                   f"{str(g['inicio'])[:10]} a {str(g['fin'])[:10]}"),
        )
        
    dias = _dias_de_horario(grupo.get('horario', ''))
    st.caption(
        f"Horario: **{grupo.get('horario', '')}** · "
        f"Días de clase: **"
        f"{', '.join(DIAS_SEMANA[d] for d in sorted(dias)) or 'no identificado'}**"
    )

    rows = C.setting(CATALOG_KEY, [])
    rows = [r for r in rows if isinstance(r, dict) and r.get('id')] if isinstance(rows, list) else []
    if not rows:
        st.warning('El catálogo ACM está vacío. Registra la institución en '
                   '**Ajustes → Instituciones y sedes ACM**.')
        return
    inst = st.selectbox(
        'Institución (firma)', rows, key='asist_inst',
        format_func=lambda x: f"{x.get('nombre', '')} · {x.get('sede', '')}"
    )

    template_bytes = _template_path(C).read_bytes()
    wb = load_workbook(BytesIO(template_bytes))
    base_sheet = st.selectbox(
        'Hoja base de la plantilla', wb.sheetnames, key='asist_base',
        help='Hoja de tu Excel que se usa como molde (se reproduce en cada quincena).'
    )
    del wb

    try:
        inicio = date.fromisoformat(str(grupo['inicio'])[:10])
        fin    = date.fromisoformat(str(grupo['fin'])[:10])
        qs = _quincenas_de(inicio, fin)
        if qs:
            st.info(f'Se generarán **{len(qs)} hoja(s)**: ' +
                    ', '.join(f'{q}° {MESES_LARGO[m-1]}' for y, m, q in qs))
    except Exception as e:
        st.error(f'No se pudo interpretar el rango del curso: {e}')
        return

    estado_key = f'{grupo["id"]}|{base_sheet}'
    if st.button('Generar lista de asistencia', type='primary', key='asist_btn'):
        try:
            data = generar_excel(template_bytes, base_sheet, grupo, inst, _festivos(C))
            st.session_state['asist_bytes'] = data
            st.session_state['asist_key'] = estado_key
            st.success('Lista generada exitosamente.')
            st.toast('✅ Lista de asistencia generada', icon='📊')
        except Exception as e:
            st.error(f'No se pudo generar el Excel: {e}')

    if (st.session_state.get('asist_bytes')
            and st.session_state.get('asist_key') == estado_key):
        fname = (f"Asistencia_{_slug(grupo.get('nombre', 'curso'))}"
                 f"_{_slug(docente)}.xlsx")
        st.download_button(
            'Descargar Excel', st.session_state['asist_bytes'],
            file_name=fname,
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            key='asist_dl',
        )

    with st.expander('Cómo se rellena la plantilla', expanded=False):
        st.markdown(
            '- **No se modifica tu archivo original**: se lee como molde.\n'
            '- **Una hoja por quincena** entre el inicio y el fin del curso. '
            'El nombre combina horas y quincena: `9 A 15 (2 AGOS)`.\n'
            '- **Filas 1–14**: se reemplazan los textos de ciclo, instructor, '
            'quincena, lugar, duración, curso y horario. El membrete, logos y '
            'estilos no se tocan.\n'
            '- **Días de clase** (según el horario del grupo): quedan en blanco '
            'para que el instructor capture ENTRADA / SALIDA.\n'
            '- **Antes del inicio** → `SIN CURSO INICIADO`.\n'
            '- **Después del inicio y no-clase** → `DÍA OCUPADO EN OTRO CURSO` '
            '(o `FIN DE SEMANA` si cae sábado o domingo).\n'
            '- **Días inhábiles** de Ajustes → `SUSPENSIÓN`.\n'
            '- **Firmas**: se actualiza el responsable y el cargo de la '
            'institución desde el catálogo ACM; la firma del CECATI queda a '
            'nombre de la responsable actual.\n'
            '- El número de filas de fecha se ajusta automáticamente a la '
            'quincena (15 o 16 según el mes).\n'
        )

def generar_asistencia_para_ia(groups, C, docente, curso="", institucion=""):
    """
    Función expuesta para el Asistente Virtual (Gemini).
    Busca el grupo ACM, valida la institución y genera el Excel.
    """
    if not _template_exists(C):
        return {"status": "error", "mensaje": "No hay una plantilla de asistencia subida en Acciones Móviles."}
    
    # 1. Filtrar grupos ACM
    def _es_acm(g):
        fields = ('modalidad','subtipo','tipo_accion','observaciones','aula','nombre')
        s = ' '.join(str(g.get(k,'') or '') for k in fields).lower()
        return bool(re.search(r'(?<![a-z])acm(?![a-z])|acci[oó]n(?:es)? m[oó]vil(?:es)?', s))
    
    acm_groups = [g for g in groups if _es_acm(g)]
    
    # 2. Buscar docente
    docente_norm = str(docente).strip().lower()
    grupos_docente = [g for g in acm_groups if docente_norm in str(g['hoja']).lower()]
    if not grupos_docente:
        return {"status": "error", "mensaje": f"No se encontraron cursos ACM para el docente '{docente}'."}
    
    # 3. Buscar curso
    if curso:
        curso_norm = str(curso).strip().lower()
        grupos_curso = [g for g in grupos_docente if curso_norm in str(g['nombre']).lower()]
        if not grupos_curso:
            return {"status": "error", "mensaje": f"No se encontró el curso '{curso}' para {docente}."}
        grupo = grupos_curso[0]
    else:
        grupo = grupos_docente[0]  # Si no especifica curso, toma el primero que encuentre
        
    # 4. Buscar institución
    rows = C.setting(CATALOG_KEY, [])
    rows = [r for r in rows if isinstance(r, dict) and r.get('id')] if isinstance(rows, list) else []
    if not rows:
        return {"status": "error", "mensaje": "El catálogo de instituciones ACM está vacío."}
        
    if institucion:
        inst_norm = str(institucion).strip().lower()
        inst_match = [r for r in rows if inst_norm in str(r.get('nombre', '')).lower()]
        inst = inst_match[0] if inst_match else rows[0]
    else:
        inst = rows[0]
        
    # 5. Generar Excel
    try:
        template_bytes = _template_path(C).read_bytes()
        wb = load_workbook(BytesIO(template_bytes))
        base_sheet = wb.sheetnames[0]
        del wb
        
        excel_bytes = generar_excel(template_bytes, base_sheet, grupo, inst, _festivos(C))
        filename = f"Asistencia_{_slug(grupo.get('nombre', 'curso'))}_{_slug(grupo.get('hoja', 'docente'))}.xlsx"
        
        return {
            "status": "ok",
            "mensaje": f"Lista de asistencia generada para {grupo['hoja']} · {grupo['nombre']} · {inst['nombre']}.",
            "filename": filename,
            "bytes": excel_bytes
        }
    except Exception as e:
        return {"status": "error", "mensaje": f"Error al generar la asistencia: {str(e)}"}