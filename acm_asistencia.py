# -*- coding: utf-8 -*-
"""ATRIO · Listas mensuales de asistencia para Acciones Móviles.

Lee Programación y el corte SISAE en modo de solo lectura. Solo genera una
lista cuando existe un vínculo único y exacto entre el grupo programado y el
grupo SISAE. No modifica SQLite, Excel de Programación ni archivos SISAE.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from io import BytesIO
import json
import re
import unicodedata

import streamlit as st
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

MESES = (
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
)
DIAS = {
    'lunes': 0, 'martes': 1, 'miercoles': 2, 'jueves': 3,
    'viernes': 4, 'sabado': 5, 'domingo': 6,
}


def _normal(value: object) -> str:
    raw = unicodedata.normalize('NFKD', str(value or '').casefold())
    return ' '.join(''.join(c for c in raw if not unicodedata.combining(c)).split())


def _es_acm(group: dict) -> bool:
    fields = ('modalidad', 'subtipo', 'tipo_accion', 'observaciones', 'aula', 'nombre')
    source = ' '.join(str(group.get(k, '') or '') for k in fields)
    return bool(re.search(r'(?<![a-z])acm(?![a-z])|acci[oó]n(?:es)? m[oó]vil(?:es)?', source, re.I))


def _identificador_hojas(group: dict) -> str:
    """Replica el ID estable de hojas.snapshot() para consultar su vínculo exacto."""
    raw = str(group.get('id') or '').replace('-', '')
    if len(raw) < 13 or not re.fullmatch(r'[0-9a-fA-F]+', raw):
        raise ValueError('El identificador del grupo no permite verificar su vínculo SISAE.')
    return str(int(raw[:13], 16))


def _meses_del_grupo(group: dict) -> list[tuple[int, int]]:
    start = date.fromisoformat(str(group['inicio'])[:10])
    end = date.fromisoformat(str(group['fin'])[:10])
    if end < start:
        raise ValueError('El término del curso es anterior a su fecha de inicio.')
    result = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        result.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def _dias_programados(schedule: str) -> set[int]:
    text = _normal(schedule)
    names = list(DIAS)
    result: set[int] = set()

    # Expande rangos explícitos, por ejemplo «lunes a viernes».
    for match in re.finditer(
        r'\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\s+(?:a|al|hasta)\s+'
        r'(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b', text
    ):
        start, end = DIAS[match.group(1)], DIAS[match.group(2)]
        current = start
        result.add(current)
        while current != end:
            current = (current + 1) % 7
            result.add(current)

    # Conserva también los días mencionados individualmente.
    for name, index in DIAS.items():
        if re.search(rf'\b{re.escape(name)}\b', text):
            result.add(index)
    return result


def _dias_sin_clase(C) -> set[date]:
    path = None
    try:
        path = C.ruta_dias_sin_clase()
    except Exception:
        pass
    if not path:
        candidates = (C.RES / 'DIAS_SIN_CLASE.json', C.ROOT / 'DIAS_SIN_CLASE.json')
        path = next((p for p in candidates if p.is_file()), None)
    if not path or not Path(path).is_file():
        return set()
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if not isinstance(raw, list):
            return set()
        return {date.fromisoformat(str(item)[:10]) for item in raw if item}
    except (OSError, ValueError, TypeError):
        return set()


def _fechas_sesion(group: dict, year: int, month: int, weekdays: set[int], blocked: set[date]) -> list[date]:
    start = date.fromisoformat(str(group['inicio'])[:10])
    end = date.fromisoformat(str(group['fin'])[:10])
    last = monthrange(year, month)[1]
    dates = []
    for day in range(1, last + 1):
        current = date(year, month, day)
        if start <= current <= end and current.weekday() in weekdays and current not in blocked:
            dates.append(current)
    return dates


def _slug(value: str) -> str:
    text = _normal(value)
    return re.sub(r'[^a-z0-9]+', '_', text).strip('_')[:48] or 'grupo'


def _color_hex(value: str, fallback: str) -> str:
    value = str(value or '').strip().lstrip('#')
    return value.upper() if re.fullmatch(r'[0-9a-fA-F]{6}', value) else fallback.lstrip('#').upper()


def _text_color(hex_color: str) -> str:
    h = _color_hex(hex_color, 'FF1493')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return '2A2326' if luminance > 0.58 else 'FFFFFF'


def crear_libro_asistencia(group: dict, students: list[dict], dates: list[date], *, sede: str,
                           institucion: str, cut_label: str, theme_config: dict | None = None) -> bytes:
    """Crea un Excel imprimible sin alterar las plantillas institucionales existentes."""
    if not students:
        raise ValueError('El grupo SISAE no tiene alumnos inscritos en el corte actual.')
    if not dates:
        raise ValueError('No hay fechas de clase seleccionadas para este mes.')

    cfg = theme_config or {}
    accent = _color_hex(cfg.get('accent'), 'FF1493')
    gold = _color_hex(cfg.get('gold'), 'D4AF37')
    bg = _color_hex(cfg.get('bg'), 'FBF7F2')
    surface = _color_hex(cfg.get('surface'), 'FFFFFF')
    ink = _color_hex(cfg.get('text'), '2A2326')
    muted = _color_hex(cfg.get('muted'), '6B6063')
    accent_ink = _text_color(accent)

    wb = Workbook()
    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
        wb.calculation.calcMode = 'auto'
    except Exception:
        pass
    ws = wb.active
    ws.title = 'Lista de asistencia'
    ws.sheet_view.showGridLines = False

    date_start_col = 4
    total_col = date_start_col + len(dates)
    observations_col = total_col + 1
    last_col = observations_col
    last_letter = get_column_letter(last_col)

    title_fill = PatternFill('solid', fgColor=accent)
    gold_fill = PatternFill('solid', fgColor=gold)
    light_fill = PatternFill('solid', fgColor=bg)
    header_fill = PatternFill('solid', fgColor=ink)
    white_fill = PatternFill('solid', fgColor=surface)
    line = Side(style='thin', color='D8CDD0')
    medium = Side(style='medium', color=accent)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, 'CENTRO DE CAPACITACIÓN PARA EL TRABAJO INDUSTRIAL No. 31')
    ws.cell(1, 1).font = Font(name='Playfair Display', size=13, bold=True, color=accent_ink)
    ws.cell(1, 1).fill = title_fill
    ws.cell(1, 1).alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 29

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, 'ACCIONES MÓVILES DE CAPACITACIÓN · LISTA DE ASISTENCIA')
    ws.cell(2, 1).font = Font(name='Playfair Display', size=12, bold=True, color=ink)
    ws.cell(2, 1).fill = gold_fill
    ws.cell(2, 1).alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[2].height = 25

    month_text = f'{MESES[dates[0].month - 1].capitalize()} de {dates[0].year}'
    meta = [
        ('Curso', group.get('nombre', '')),
        ('Especialidad', group.get('especialidad_programada', '')),
        ('Docente', group.get('hoja', '')),
        ('Institución', institucion or 'No especificada'),
        ('Sede', sede or group.get('aula', '') or 'No especificada'),
        ('Periodo de lista', month_text),
        ('Vigencia del curso', f"{group.get('inicio', '')} a {group.get('fin', '')}"),
        ('Horario programado', group.get('horario', '')),
        ('Inscripción consultada', cut_label or 'Corte SISAE actual'),
    ]
    # Dos columnas de metadatos, adaptadas al ancho de la tabla.
    row = 4
    for label, value in meta:
        ws.cell(row, 1, label.upper())
        ws.cell(row, 1).font = Font(name='Inter', size=8, bold=True, color=muted)
        ws.cell(row, 1).fill = light_fill
        ws.cell(row, 1).alignment = Alignment(vertical='center')
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=last_col)
        cell = ws.cell(row, 2, str(value or '—'))
        cell.font = Font(name='Inter', size=9, color=ink)
        cell.fill = white_fill
        cell.alignment = Alignment(vertical='center', wrap_text=True)
        for col in range(1, last_col + 1):
            ws.cell(row, col).border = Border(bottom=line)
        ws.row_dimensions[row].height = 23 if len(str(value or '')) < 90 else 32
        row += 1

    header_row = row + 1
    labels = ['No.', 'Número de control', 'Nombre completo']
    labels.extend(d.strftime('%d/%m') for d in dates)
    labels.extend(['Total', 'Observaciones'])
    for col, label in enumerate(labels, 1):
        cell = ws.cell(header_row, col, label)
        cell.font = Font(name='Inter', size=8, bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = Border(top=medium, bottom=medium, left=line, right=line)
    ws.row_dimensions[header_row].height = 32

    first_student_row = header_row + 1
    sorted_students = sorted(
        students,
        key=lambda s: (_normal(s.get('nombre', '')), str(s.get('id', '')))
    )
    for index, student in enumerate(sorted_students, 1):
        current_row = first_student_row + index - 1
        values = [index, str(student.get('id') or ''), str(student.get('nombre') or '').strip()]
        for col, value in enumerate(values, 1):
            cell = ws.cell(current_row, col, value)
            cell.font = Font(name='Inter', size=8, color=ink)
            cell.fill = light_fill if index % 2 == 0 else white_fill
            cell.alignment = Alignment(vertical='center', wrap_text=col == 3,
                                       horizontal='center' if col == 1 else 'left')
            cell.border = Border(bottom=line, left=line, right=line)
        for col in range(date_start_col, total_col):
            cell = ws.cell(current_row, col, '')
            cell.font = Font(name='Inter', size=8, color=ink)
            cell.fill = light_fill if index % 2 == 0 else white_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(bottom=line, left=line, right=line)
        total = ws.cell(current_row, total_col, f'=COUNTA({get_column_letter(date_start_col)}{current_row}:{get_column_letter(total_col - 1)}{current_row})')
        total.font = Font(name='Inter', size=8, bold=True, color=ink)
        total.fill = light_fill
        total.alignment = Alignment(horizontal='center', vertical='center')
        total.border = Border(bottom=line, left=line, right=line)
        obs = ws.cell(current_row, observations_col, '')
        obs.font = Font(name='Inter', size=8, color=ink)
        obs.fill = white_fill
        obs.alignment = Alignment(vertical='center', wrap_text=True)
        obs.border = Border(bottom=line, left=line, right=line)
        ws.row_dimensions[current_row].height = 29

    last_student_row = first_student_row + len(sorted_students) - 1
    note_row = last_student_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=last_col)
    note = ws.cell(note_row, 1, 'Registrar la asistencia en la columna de cada sesión. La columna Total cuenta las celdas que tengan una marca o anotación.')
    note.font = Font(name='Inter', size=8, italic=True, color=muted)
    note.alignment = Alignment(wrap_text=True, vertical='center')
    note.fill = light_fill
    ws.row_dimensions[note_row].height = 25

    signature_row = note_row + 3
    signature_split = max(2, last_col // 2)
    ws.merge_cells(start_row=signature_row, start_column=1, end_row=signature_row, end_column=signature_split)
    ws.merge_cells(start_row=signature_row, start_column=signature_split + 1, end_row=signature_row, end_column=last_col)
    ws.cell(signature_row, 1, '________________________________________\nNombre y firma de la persona instructora')
    ws.cell(signature_row, signature_split + 1, '________________________________________\nSello o firma de la institución receptora')
    for cell in (ws.cell(signature_row, 1), ws.cell(signature_row, signature_split + 1)):
        cell.font = Font(name='Inter', size=8, color=ink)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[signature_row].height = 38

    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 19
    ws.column_dimensions['C'].width = 34
    for col in range(date_start_col, total_col):
        ws.column_dimensions[get_column_letter(col)].width = 10
    ws.column_dimensions[get_column_letter(total_col)].width = 9
    ws.column_dimensions[get_column_letter(observations_col)].width = 24

    ws.freeze_panes = f'D{first_student_row}'
    ws.auto_filter.ref = f'A{header_row}:{last_letter}{last_student_row}'
    ws.print_title_rows = f'1:{header_row}'
    ws.print_area = f'A1:{last_letter}{signature_row}'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=0.25, right=0.25, top=0.45, bottom=0.45, header=0.2, footer=0.2)
    ws.oddFooter.center.text = 'CECATI 31 · Acciones Móviles de Capacitación'
    ws.oddFooter.right.text = 'Página &[Page] de &[Pages]'

    output = BytesIO()
    wb.save(output)
    data = output.getvalue()
    # Reabre el libro para comprobar que el Excel se puede leer.
    check = load_workbook(BytesIO(data), read_only=True, data_only=False)
    if 'Lista de asistencia' not in check.sheetnames:
        check.close()
        raise ValueError('No se pudo validar la hoja de asistencia generada.')
    check.close()
    return data


def _deduplicar_estudiantes(rows: list[dict]) -> tuple[list[dict], int]:
    """Elimina reiteraciones de un mismo número de control sin combinar personas."""
    unique = []
    seen = set()
    repeated = 0
    for row in rows:
        control = str(row.get('id') or '').strip()
        if not control:
            continue
        key = str(int(control)) if control.isdecimal() else control.casefold()
        if key in seen:
            repeated += 1
            continue
        seen.add(key)
        unique.append({'id': control, 'nombre': str(row.get('nombre') or '').strip()})
    return unique, repeated


def _label_month(value: tuple[int, int]) -> str:
    year, month = value
    return f'{MESES[month - 1].capitalize()} {year}'


def _panel_generar(groups, C):
    mobile_groups = [g for g in groups if _es_acm(g)]
    if not mobile_groups:
        st.info('No se identificaron grupos ACM en Programación. Revisa que el curso o sus observaciones incluyan “ACM” o “Acciones Móviles”.')
        return

    sisae_path = C.RES / 'SISAE.zip'
    if not sisae_path.is_file():
        st.warning('No hay un corte SISAE cargado. Importa SISAE.zip en SISAE · Cortes antes de generar listas.')
        return

    try:
        import hojas
        _rows, _ids, _sisae, links, students_by_ident, digest = hojas.snapshot(groups)
    except Exception as exc:
        st.error('No se pudo verificar la matrícula con el corte SISAE. No se generará una lista parcial.')
        st.caption('Detalle: ' + str(exc))
        st.caption('Revisa el ZIP vigente en SISAE · Cortes y confirma que contenga PROG_CURSOS1.DBF e INSCRIPCION.DBF.')
        return

    teachers = sorted({g.get('hoja', '') for g in mobile_groups if g.get('hoja')})
    if not teachers:
        st.info('No hay docentes asociados a los grupos ACM detectados.')
        return

    st.markdown('#### Lista mensual de asistencia')
    st.caption('La matrícula proviene del corte SISAE vigente. ATRIO solo utiliza coincidencias únicas de curso, docente, fechas, duración y horario.')
    teacher = st.selectbox('Docente', teachers, key='acm_asistencia_docente')
    teacher_groups = sorted(
        [g for g in mobile_groups if g.get('hoja') == teacher],
        key=lambda g: (str(g.get('inicio', '')), str(g.get('nombre', '')))
    )
    selected_group = st.selectbox(
        'Curso o grupo ACM', teacher_groups,
        format_func=lambda g: f"{g.get('nombre', 'Curso')} · {g.get('inicio', '')} a {g.get('fin', '')}",
        key='acm_asistencia_grupo'
    )

    try:
        ident = _identificador_hojas(selected_group)
    except ValueError as exc:
        st.error(str(exc))
        return
    linked = links.get(ident)
    roster, duplicados = _deduplicar_estudiantes(students_by_ident.get(ident, []))
    if not linked:
        st.error('Este grupo no tiene una coincidencia única y exacta en SISAE. No se asignarán alumnos por parecido de nombre.')
        st.caption('Revisa docente, fechas, duración y horario en Programación y en el corte SISAE. Si corresponde a una acción móvil todavía no capturada en SISAE, no es posible extraer una matrícula real.')
        return
    if not roster:
        st.warning('El grupo está vinculado, pero el corte SISAE no devuelve alumnos con número de control para esa clave.')
        return
    if duplicados:
        st.caption(f'Se consolidaron {duplicados} registros repetidos del mismo número de control.')

    st.success(f"Vínculo SISAE confirmado · {len(roster)} alumnos únicos · clave de curso {linked.get('key', '—')}")
    st.caption(f"Curso SISAE: {linked.get('curso', selected_group.get('nombre', ''))} · docente: {linked.get('docente', teacher)}")

    months = _meses_del_grupo(selected_group)
    month_labels = {_label_month(m): m for m in months}
    chosen_label = st.selectbox('Mes de asistencia', list(month_labels), key=f'acm_asistencia_mes_{ident}')
    year, month = month_labels[chosen_label]

    parsed_days = _dias_programados(selected_group.get('horario', ''))
    all_day_labels = list(DIAS)
    default_days = [name for name, index in DIAS.items() if index in parsed_days]
    if not parsed_days:
        st.warning('No pude reconocer automáticamente los días escritos en el horario. Confírmalos antes de generar la lista.')
    chosen_day_names = st.multiselect(
        'Días de clase que deben aparecer', all_day_labels,
        default=default_days,
        format_func=lambda x: x.capitalize(),
        key=f'acm_asistencia_dias_{ident}'
    )
    weekdays = {DIAS[x] for x in chosen_day_names}
    blocked = _dias_sin_clase(C)
    if not blocked:
        st.caption('No se encontró un calendario DIAS_SIN_CLASE.json legible; las fechas se calculan únicamente con los días y vigencia programados.')
    else:
        st.caption('Se excluyen del calendario las fechas institucionales no laborables registradas en DIAS_SIN_CLASE.json.')
    candidate_dates = _fechas_sesion(selected_group, year, month, weekdays, blocked) if weekdays else []
    date_labels = {d.strftime('%d/%m/%Y'): d for d in candidate_dates}
    chosen_date_labels = st.multiselect(
        'Sesiones incluidas en la lista', list(date_labels), default=list(date_labels),
        key=f'acm_asistencia_fechas_{ident}_{year}_{month}'
    )
    chosen_dates = [date_labels[label] for label in chosen_date_labels]

    with st.expander('Datos de institución y sede', expanded=True):
        catalog = C.setting('acm_instituciones_v1', [])
        catalog = [item for item in catalog if isinstance(item, dict) and item.get('id')] if isinstance(catalog, list) else []
        options = [None] + catalog
        picked_institution = st.selectbox(
            'Institución receptora del catálogo', options,
            format_func=lambda item: '— Elegir o capturar manualmente —' if item is None else str(item.get('nombre') or 'Institución'),
            key=f'acm_asistencia_institucion_catalogo_{ident}'
        )
        if picked_institution:
            institution = str(picked_institution.get('nombre') or '')
            default_site = str(picked_institution.get('sede') or selected_group.get('aula') or '')
        else:
            institution = st.text_input('Nombre de la institución receptora', key=f'acm_asistencia_institucion_manual_{ident}')
            default_site = str(selected_group.get('aula') or '')
        site = st.text_input(
            'Sede de impartición', value=default_site,
            key=f'acm_asistencia_sede_{ident}_{_slug(institution or "sin_institucion")}'
        )

    active_theme = None
    try:
        import tema
        active_theme = tema.PRESETS.get(tema.activo(), tema.PRESETS.get(tema.DEFECTO, {}))
    except Exception:
        active_theme = {}

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric('Alumnos inscritos', len(roster))
    with c2:
        st.metric('Sesiones del mes', len(chosen_dates))
    with c3:
        st.metric('Duración', f"{float(selected_group.get('duracion') or 0):g} h")

    st.caption('Horario de Programación: ' + str(selected_group.get('horario') or 'Sin horario registrado'))
    if not chosen_dates:
        st.warning('Selecciona al menos una fecha de clase para generar la lista.')
    if st.button('Generar y guardar lista de asistencia', type='primary', disabled=not chosen_dates,
                 key='acm_asistencia_generar'):
        try:
            cut_record = C.setting('corte_' + digest, {})
            cut_label = str(cut_record.get('date') or 'Corte SISAE cargado')
            content = crear_libro_asistencia(
                selected_group, roster, sorted(chosen_dates), sede=site.strip(),
                institucion=institution.strip(), cut_label=cut_label,
                theme_config=active_theme
            )
            output_dir = C.OUT / 'acm_asistencia'
            output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"Lista_Asistencia_ACM_{_slug(selected_group.get('nombre', 'curso'))}_{year}_{month:02d}_{stamp}.xlsx"
            output_path = output_dir / filename
            output_path.write_bytes(content)
            st.session_state['acm_asistencia_ultimo_archivo'] = str(output_path)
            st.session_state['acm_asistencia_ultimo_nombre'] = filename
            st.success('Lista guardada en datos/salidas/acm_asistencia/.')
        except Exception as exc:
            st.error('No se pudo crear la lista de asistencia: ' + str(exc))

    last = Path(str(st.session_state.get('acm_asistencia_ultimo_archivo') or ''))
    if last.is_file() and last.parent == (C.OUT / 'acm_asistencia'):
        st.download_button(
            'Descargar lista Excel', data=last.read_bytes(),
            file_name=str(st.session_state.get('acm_asistencia_ultimo_nombre') or last.name),
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            key='acm_asistencia_descargar', use_container_width=True
        )


def _panel_guardadas(C):
    folder = C.OUT / 'acm_asistencia'
    if not folder.is_dir():
        st.info('Todavía no hay listas de asistencia guardadas.')
        return
    files = sorted(folder.glob('Lista_Asistencia_ACM_*.xlsx'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        st.info('Todavía no hay listas de asistencia guardadas.')
        return
    search = st.text_input('Buscar lista por curso o periodo', key='acm_asistencia_buscar')
    filtered = [p for p in files if _normal(search) in _normal(p.name)] if search.strip() else files
    st.caption(f'{len(filtered)} lista(s) disponibles')
    for idx, path in enumerate(filtered):
        with st.container(border=True):
            st.write('**' + path.name.replace('_', ' ') + '**')
            st.caption(datetime.fromtimestamp(path.stat().st_mtime).strftime('Generada: %d/%m/%Y %H:%M'))
            st.download_button(
                'Descargar', data=path.read_bytes(), file_name=path.name,
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key='acm_asistencia_guardada_' + str(idx), use_container_width=True
            )


def panel_listas(groups, C):
    generar, guardadas = st.tabs(['Generar lista', 'Listas guardadas'])
    with generar:
        _panel_generar(groups, C)
    with guardadas:
        _panel_guardadas(C)