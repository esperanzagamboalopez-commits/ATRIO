"""ATRIO · Adaptar PDF (Fase 2).

Adapta únicamente PEA oficiales de 17 páginas: actualiza los campos administrativos
y la marca del punto 17 sobre el PDF original. El contenido académico no se toca.
Salida: PDF adaptado (descarga) y guardado opcional en Históricos con estado
BORRADOR_REVISION_VISUAL. No autoriza ni sube nada a MCE.
"""
from __future__ import annotations

import hashlib
import html
import json
import uuid
from datetime import datetime

import streamlit as st

import centro as C
import pea_historicos_101212 as H
import pea_pdf_101212 as PDF
import pea_pdf_fiel_1012123 as FIEL

PAGINAS_OFICIALES = 17
PAGINAS_REVISION = [2, 3, 4, 5, 17]
PERFILES = ['Estudiantes', 'Empleados', 'Autoempleado', 'Grupos en desventaja social y/o económica',
            'Jubilados', 'Adultos mayores', 'Desempleados', 'Personas con discapacidad']

CSS = """
<style>
.adp-head{margin:4px 0 14px}
.adp-eyebrow{font-size:11px;letter-spacing:.12em;color:#D4AF37;text-transform:uppercase;font-weight:800}
.adp-title{font-family:'Playfair Display',Georgia,serif;font-size:30px;font-weight:700;color:var(--atrio-titulo);margin:2px 0 4px}
.adp-sub{font-size:12px;color:var(--atrio-tenue)}
.adp-box{background:var(--atrio-surface);box-shadow:var(--atrio-sombra);border:1px solid rgba(212,175,55,.22);border-radius:14px;
  padding:12px 14px;color:var(--atrio-tinta);font-size:13px;margin:8px 0}
</style>
"""


def _store_pdf(ciclo, tipo, vals, nota, original, pdf_adaptado, record):
    """Guarda PDF original, PDF adaptado y registro de control en Históricos.
    Reutiliza la tabla y la carpeta de PEA históricos; no genera Word."""
    if ciclo == f'{H._current_cycle()}–{H._current_cycle() + 1}':
        raise ValueError('El ciclo vigente no puede guardarse en Históricos.')
    uid = str(uuid.uuid4())
    folder = H.HIST / uid
    try:
        pdf_path = H._save(uid, 'PEA_PDF_ORIGINAL.pdf', original)
        H._save(uid, 'PEA_PDF_ADAPTADO.pdf', pdf_adaptado)
        record_path = H._save(uid, 'DATOS_DE_CONTROL.json',
                              json.dumps(record, ensure_ascii=False, indent=2, default=str).encode())
        with H._db() as con:
            con.execute('INSERT INTO pea_hist_101212 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (uid, ciclo, 'Adaptar PDF conservando formato', tipo, vals['docente'], vals['curso'],
                         vals['especialidad'], float(vals['duracion']), vals['inicio'], vals['fin'],
                         vals['horario'] + ' · ' + vals['dias'], vals['sede'], int(vals['participantes']),
                         nota, C.now(), 'Borrador pendiente de revisión visual', pdf_path, '', record_path,
                         hashlib.sha256(original).hexdigest()))
    except Exception:
        import shutil
        if folder.is_dir():
            shutil.rmtree(folder)
        raise
    return uid


def _clave_fuente(source, data, authorities):
    payload = hashlib.sha256(source).hexdigest() + json.dumps([data, authorities], sort_keys=True,
                                                                ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def panel():
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="adp-head"><div class="adp-eyebrow">Jefatura de Capacitación · CECATI 31</div>'
                '<div class="adp-title">Adaptar PDF</div>'
                '<div class="adp-sub">Solo PEA oficiales de 17 páginas · el contenido académico se conserva</div></div>',
                unsafe_allow_html=True)

    current = H._current_cycle()
    years = [f'{y}–{y + 1}' for y in range(current - 1, current - 20, -1)]
    a, b = st.columns([1, 1.8], gap='small')
    ciclo = a.selectbox('Ciclo escolar anterior', years, key='adp_ciclo')
    try:
        people = H._teachers()
    except (OSError, ValueError, KeyError) as ex:
        st.error(f'No se pudieron leer los recursos de docentes: {ex}. Revisa Ajustes · Recursos.')
        return
    if not people:
        st.error('No se encontraron docentes en Padrón ni Programación.')
        return
    teacher = b.selectbox('Docente', people, key='adp_teacher')
    profile = H._profile(teacher)
    c_tipo, c_clase = st.columns([1, 1], gap='small')
    tipo = c_clase.selectbox('Tipo de curso', ('Extensión', 'Repositorio'), key='adp_tipo')

    up = st.file_uploader('PDF oficial original del curso (17 páginas)', type=['pdf'], key='adp_pdf')
    if up is None:
        st.info('Sube el PDF oficial para comenzar.')
        return
    source = up.getvalue()
    try:
        paginas = len(PDF._fitz().open(stream=source, filetype='pdf'))
    except Exception:
        st.error('No se pudo abrir el PDF. Verifica que no esté protegido con contraseña.')
        return
    if paginas != PAGINAS_OFICIALES:
        st.error(f'Este PDF tiene {paginas} página(s). Adaptar PDF solo acepta PEA oficiales de {PAGINAS_OFICIALES} páginas.')
        return
    try:
        meta = PDF.inspeccionar(source)
    except (ValueError, RuntimeError) as e:
        st.error(str(e))
        return
    if meta.get('curso') and meta.get('horas') and meta.get('participantes') is not None:
        st.markdown(f"<div class='adp-box'><b>Del PDF original:</b> {html.escape(meta['curso'])} · "
                    f"{meta['horas']:g} horas · {meta['participantes']} participante(s) · {paginas} páginas</div>",
                    unsafe_allow_html=True)
    else:
        st.warning('No se identificaron todos los datos protegidos: curso, duración y participantes. Revisa el PDF.')

    src_key = hashlib.sha256(source).hexdigest()[:12]
    st.markdown('**Datos administrativos del expediente**')
    c1, c2, c3 = st.columns(3, gap='small')
    curp = c1.text_input('CURP del docente', value=str(profile.get('curp') or ''), key=f'adp_curp_{src_key}')
    tel = c2.text_input('Teléfono del docente', value=str(profile.get('telefono') or ''), key=f'adp_tel_{src_key}')
    mail = c3.text_input('Correo del docente', value=str(profile.get('correo') or ''), key=f'adp_mail_{src_key}')

    tipo_padron = str(profile.get('tipo') or '').strip()
    tipo_inicial = next((op for op in ('Interno', 'Externo') if op.casefold() == tipo_padron.casefold()), 'Interno')
    tipo_doc = st.radio('17 · Tipo de docente (página 4)', ('Interno', 'Externo'),
                        index=('Interno', 'Externo').index(tipo_inicial), horizontal=True,
                        key=f'adp_p17_{src_key}',
                        help='Solo aplica a este expediente; no cambia el Padrón.')

    options, index, from_pdf, programadas, aviso = H._opciones_especialidad(profile, teacher, source, 'Adaptar PDF existente')
    a, b, c = st.columns([1.6, 1, 1], gap='small')
    esp = a.selectbox('Especialidad del curso', options, index=index, key=f'adp_esp_{src_key}')
    especialidad = '' if esp == 'Seleccionar especialidad' else esp
    participantes = b.number_input('10 · Participantes', min_value=1, max_value=9999,
                                   value=max(1, int(meta.get('participantes') or 1)), step=1, key=f'adp_part_{src_key}')
    horas = c.number_input('Horas oficiales', min_value=0.0, max_value=1000.0,
                           value=float(meta.get('horas') or 0), step=1.0, key=f'adp_horas_{src_key}')
    if from_pdf:
        st.caption('Especialidad recuperada del punto 6 del PDF; puedes corregirla para este expediente.')
    elif aviso:
        st.caption('No fue posible consultar las especialidades de Programación. Selecciona una del catálogo.')

    a, b, c, d = st.columns(4, gap='small')
    inicio = a.text_input('Fecha de inicio', placeholder='DD/MM/AAAA', key=f'adp_ini_{src_key}')
    fin = b.text_input('Fecha de término', placeholder='DD/MM/AAAA', key=f'adp_fin_{src_key}')
    dias = c.text_input('Días registrados', placeholder='Lunes y miércoles', key=f'adp_dias_{src_key}')
    horario = d.text_input('Horario registrado', placeholder='08:00 a 11:00', key=f'adp_hor_{src_key}')

    a, b, c = st.columns([1, 1, 1], gap='small')
    sede = a.text_input('Sede registrada', value='CECATI N.º 31', key=f'adp_sede_{src_key}')
    ubicacion = b.text_input('Localidad · página 5', value='Coatzacoalcos, Veracruz', key=f'adp_ubi_{src_key}')
    modalidad = c.radio('13 · Lugar de impartición', ('CECATI', 'Acción móvil'), index=1, horizontal=True,
                        key=f'adp_mod_{src_key}')

    with st.expander('Datos del formulario · páginas 2 a 5', expanded=False):
        x, y = st.columns([1.4, 1], gap='small')
        con_quien = x.text_input('4 · Con quién se impartirá', value='Estudiantes', key=f'adp_conq_{src_key}')
        servicio = y.radio('3 · Tipo de servicio del PDF', ('CE', 'CAE'), index=0, horizontal=True,
                           key=f'adp_serv_{src_key}')
        audiencia = st.multiselect('5 · Perfil de usuario', PERFILES,
                                   default=['Estudiantes', 'Autoempleado', 'Desempleados'], key=f'adp_perf_{src_key}')
        z1, z2 = st.columns([1, 2], gap='small')
        norma = z1.radio('7 · Normalización asociada', ('NO', 'SI'), horizontal=True, key=f'adp_norma_{src_key}')
        codigo = z2.text_input('8 · Código EC o norma', key=f'adp_ncod_{src_key}')
        nombre_norma = st.text_input('8 · Nombre de la norma o estándar', key=f'adp_nnom_{src_key}')
        clave = st.text_input('21 · Clave del curso (si existe)', key=f'adp_clave_{src_key}')

    with st.expander('Autoridades del ciclo histórico · obligatorio', expanded=True):
        st.caption('No se usan las autoridades del ciclo actual. No se insertan imágenes de firma.')
        a, b, c = st.columns(3, gap='small')
        valida = a.text_input('Valida · Jefatura Capacitación', key=f'adp_valida_{src_key}')
        visto = b.text_input('Vo. Bo. · Dirección', key=f'adp_visto_{src_key}')
        autoriza = c.text_input('Autoriza · Subdirección', key=f'adp_autoriza_{src_key}')
        aprueba = st.text_input('Aprueba · si corresponde', key=f'adp_aprueba_{src_key}')

    nota = st.text_area('Notas internas · no se imprimen en el PEA', height=70, key=f'adp_nota_{src_key}')

    data = dict(docente=teacher, curso=meta.get('curso', ''), especialidad=especialidad, duracion=horas,
                participantes=participantes, inicio=inicio, fin=fin, dias=dias, horario=horario, sede=sede,
                ciclo=ciclo, tipo=tipo, curp=curp.strip(), correo=mail.strip(), telefono=tel.strip(),
                tipo_docente=tipo_doc, ubicacion=ubicacion, modalidad_sede=modalidad, con_quien=con_quien,
                servicio_pdf=servicio, perfiles_usuario=audiencia, normalizacion=norma,
                norma_codigo=codigo.strip(), norma_nombre=nombre_norma.strip(), clave_curso=clave.strip())
    authorities = dict(valida=valida, visto=visto, autoriza=autoriza, aprueba=aprueba)
    clave_vista = _clave_fuente(source, data, authorities)

    if st.button('Preparar vista previa', type='primary', key=f'adp_prev_{src_key}'):
        st.session_state.pop('adp_vista', None)
        try:
            clean = H._validate(data)
            H._validate_authorities(authorities)
            if not meta.get('curso') or not meta.get('horas') or meta.get('participantes') is None:
                raise ValueError('No se reconocen curso, horas o participantes del PDF original.')
            if norma == 'SI' and not (codigo.strip() and nombre_norma.strip()):
                raise ValueError('Si el curso tiene normalización, indica código y nombre de la norma.')
            if not audiencia:
                raise ValueError('Selecciona al menos un perfil de usuario.')
            with st.spinner('Actualizando campos y casillas oficiales sin modificar el contenido académico…'):
                pdf_final, _, reporte = FIEL.adaptar_pdf(source, dict(clean, **authorities), crear_word=False)
            st.session_state['adp_vista'] = {'clave': clave_vista, 'pdf': pdf_final, 'reporte': reporte,
                                             'data': clean, 'authorities': authorities, 'nota': nota,
                                             'origen': up.name}
        except (FIEL.ErrorAdaptacion, ValueError, RuntimeError, OSError) as ex:
            st.error(str(ex))

    vista = st.session_state.get('adp_vista')
    if not vista:
        return
    if vista['clave'] != clave_vista:
        st.caption('Los datos cambiaron desde la vista previa. Vuelve a prepararla antes de descargar o guardar.')
        return

    st.success('Vista previa lista: datos y casillas actualizados; contenido académico intacto. Revísala antes de descargar.')
    import fitz
    pagina = st.selectbox('Página a revisar', PAGINAS_REVISION, format_func=lambda k: f'Página {k}',
                          key=f'adp_pag_{src_key}')
    with fitz.open(stream=vista['pdf'], filetype='pdf') as ver:
        pix = ver[pagina - 1].get_pixmap(matrix=fitz.Matrix(1.1, 1.1), alpha=False)
        st.image(pix.tobytes('png'), caption=f'Página {pagina} · Borrador pendiente de validación visual',
                 use_container_width=True)

    nombre_pdf = 'PEA_adaptado_' + vista['origen'].rsplit('.', 1)[0] + '.pdf'
    col_d, col_g = st.columns(2, gap='small')
    with col_d:
        st.download_button('Descargar PDF adaptado', data=vista['pdf'], file_name=nombre_pdf,
                           mime='application/pdf', key=f'adp_dl_{src_key}')
    with col_g:
        if st.button('Guardar en Históricos', key=f'adp_save_{src_key}'):
            try:
                rec = {'accion': 'Adaptar PDF conservando formato', 'datos': vista['data'],
                       'autoridades': vista['authorities'], 'reporte': vista['reporte'],
                       'estado': 'BORRADOR_REVISION_VISUAL', 'origen_pdf': vista['origen']}
                uid = _store_pdf(ciclo, tipo, vista['data'], vista['nota'], source, vista['pdf'], rec)
                st.session_state['adp_ultimo'] = uid
                st.success('PDF original y PDF adaptado guardados en Mis PEA → Históricos. '
                           'Quedan como borrador: no autorizados ni subidos a MCE.')
            except (ValueError, RuntimeError, OSError) as ex:
                st.error(str(ex))
