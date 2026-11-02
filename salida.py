"""ATRIO 10.6 · Exportación horizontal de datos leídos del PEA (solo este módulo)."""
from io import BytesIO
from datetime import datetime
import hashlib
import re
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import centro as C
from pea_excel import leer_pea

# The order is controlled centrally; a course is one row and each field one column.
COLUMN_WIDTHS = {
    'Nombre del curso': 33,
    'Especialidad': 24,
    'Asociado a normativa': 21,
    'Código': 18,
    'Norma': 23,
    'Duración': 17,
    'Número de participantes': 24,
    'Horario': 21,
    'Días de impartición': 28,
    'Lugar de impartición': 28,
    'Fecha de inicio': 17,
    'Fecha de término': 17,
    'Tipo de docente': 19,
    'CURP': 25,
    'Teléfono': 18,
    'Correo': 32,
    'Objetivo general': 63,
    'Justificación': 63,
    'Temática': 63,
    'Menciona CERESO': 19,
}

def _excel_text(raw):
    """Prevent formula injection and preserve literal strings from a Word document."""
    if raw is None:
        return ''
    value = str(raw).strip()
    if value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value

def crear_excel_horizontal(values):
    """Creates an in-memory .xlsx: row 1 headers, row 2 extracted values. No DB writes."""
    headers = list(C.HEADERS)
    if not headers or len(set(headers)) != len(headers):
        raise ValueError('Encabezados MCE ausentes o duplicados.')
    wb = Workbook()
    sheet = wb.active
    sheet.title = 'DATOS_MCE'
    sheet.append(headers)
    sheet.append([_excel_text(values.get(field,'')) for field in headers])
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = f'A1:{get_column_letter(len(headers))}2'
    thin = Side(style='hair', color='D7D2CC')
    for col, field in enumerate(headers, start=1):
        letter = get_column_letter(col)
        sheet.column_dimensions[letter].width = COLUMN_WIDTHS.get(field, 25)
        title = sheet.cell(1,col)
        title.fill = PatternFill('solid', fgColor='F4EBE8')
        title.font = Font(name='Aptos',size=10,bold=True,color='402B38')
        title.alignment = Alignment(vertical='center',horizontal='left',wrap_text=True)
        title.border = Border(bottom=Side(style='thin',color='B8989D'))
        cell = sheet.cell(2,col)
        cell.font = Font(name='Aptos',size=10,color='292426')
        cell.alignment = Alignment(vertical='top',horizontal='left',wrap_text=True)
        cell.border = Border(bottom=thin)
        cell.number_format = '@'
        if not cell.value:
            cell.fill = PatternFill('solid', fgColor='FFF2E7')
    sheet.row_dimensions[1].height = 35
    sheet.row_dimensions[2].height = 145
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.fitToWidth = 1
    sheet.print_options.horizontalCentered = False
    data = BytesIO()
    wb.save(data)
    return data.getvalue()

def _coincide_grupo(values,group):
    if C.motor.normal(str(values.get('Nombre del curso',''))) != C.motor.normal(str(group['nombre'])):
        return False
    for field,k in [('Fecha de inicio','inicio'),('Fecha de término','fin')]:
        try:
            doc_date = datetime.strptime(str(values.get(field,'')),'%d/%m/%Y').date().isoformat()
            if doc_date != str(group[k]):
                return False
        except (ValueError, TypeError):
            return False
    return True

def present(g):
    st.subheader('Excel para MCE')
    if g['tipo']=='Regular':
        st.info('Curso regular. Registra el alta en MCE y usa la ficha del grupo para la captura de alumnos.')
        return
    versions=[a for a in C.artifacts(g['id']) if a['reviewed'] and a['fingerprint']==g['fingerprint'] and (C.ROOT/a['path']).is_file()]
    file=st.file_uploader('Usar un PEA revisado en Word',type=['docx'],key='pea_origen_'+g['id'],help='Puedes usar un documento corregido en Word o generado anteriormente con la misma plantilla institucional.')
    if file:
        raw=file.getvalue();label=file.name
    elif versions:
        chosen=st.selectbox('Versión revisada del grupo',versions,format_func=lambda a:a['created']+' · '+a['id'][:8])
        raw=(C.ROOT/chosen['path']).read_bytes();label=chosen['created']
    else:
        st.info('Aquí aparecerá el Excel cuando revises el PEA del grupo. Si ya tienes el Word revisado, selecciónalo arriba.')
        return
    try:
        values=leer_pea(BytesIO(raw))
    except Exception as exc:
        st.error('No se pudo leer el PEA en esta plantilla. '+str(exc))
        return
    st.caption('Fuente de los datos · '+label)
    st.table([{'Campo':k,'Valor leído del PEA':values.get(k) or 'Falta en el PEA'} for k in C.HEADERS])
    matches=_coincide_grupo(values,g)
    missing=[k for k in C.HEADERS if not str(values.get(k,'') or '').strip()]
    if not matches:
        st.error('ATENCIÓN: el nombre o las fechas del Word NO corresponden al grupo seleccionado. No se vinculará este archivo al grupo. Puedes descargar solo una copia de revisión con lo leído del Word.')
    if missing:
        st.warning('Hay campos sin información en el PEA: '+', '.join(missing)+'. En el Excel quedarán VACÍOS y se resaltarán para revisión; no se inventarán datos.')
    with st.expander('Ver vista previa horizontal · como quedará en Excel',expanded=False):
        st.caption('Una columna por campo; una fila por curso. Desplázate horizontalmente para ver todo.')
        st.dataframe([{k:values.get(k,'') or '' for k in C.HEADERS}],hide_index=True,use_container_width=True)
    tag=hashlib.sha256(raw).hexdigest()[:12]
    if not matches:
        acceptable=st.checkbox('Entiendo que el PEA pertenece a otro curso o fechas; descargaré únicamente un borrador sin vincularlo al grupo.',key='mce_pea_incongruente_'+g['id']+tag)
    else:
        acceptable=st.checkbox('Revisé el nombre, fechas, docente y horario. Confirmo que el Excel será revisado antes de capturarlo en MCE.',key='mce_pea_verificado_'+g['id']+tag)
    if not acceptable:
        st.caption('Confirma la revisión anterior para habilitar la descarga.')
        return
    try:
        output=crear_excel_horizontal(values)
    except Exception as exc:
        st.error('No se pudo preparar el Excel horizontal: '+str(exc))
        return
    is_draft=bool(missing or not matches)
    name=('BORRADOR_DATOS_PEA_' if is_draft else 'DATOS_MCE_PEA_')+tag+'.xlsx'
    st.download_button('Descargar Excel horizontal'+(' · BORRADOR' if is_draft else ''),output,file_name=name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='mce_horizontal_'+g['id']+tag,type='primary')
    st.caption('Formato: encabezados en fila 1 y datos del PEA en fila 2. La descarga no carga nada a MCE ni modifica SISAE, el PEA original o la programación.')
