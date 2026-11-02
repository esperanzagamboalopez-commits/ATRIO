"""ATRIO 10.12.12 - PDF existente -> borrador Word EDITABLE de adaptación supervisada.
No modifica el PDF fuente ni su parte académica. Su formato Word es reconstruido,
por lo que NO sustituye una revisión visual de tablas/maquetación.
"""
from __future__ import annotations
import io, re, hashlib
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT

MAX_PDF = 25 * 1024 * 1024
MAX_PAGES = 80

def _fitz():
    try: import fitz; return fitz
    except ImportError as exc:
        raise RuntimeError('Falta PyMuPDF. En Cloud Shell instala: .venv/bin/python -m pip install --no-cache-dir pymupdf') from exc

def _next_value(text, label):
    m = re.search(label + r'\s*\n\s*(?:\n\s*)*([^\n]+)', text, re.I)
    return m.group(1).strip() if m else ''

def inspeccionar(raw):
    if not isinstance(raw,bytes) or len(raw)<200 or len(raw)>MAX_PDF or not raw.startswith(b'%PDF-'):
        raise ValueError('Se necesita un PDF válido de máximo 25 MB.')
    fitz=_fitz()
    try:
        with fitz.open(stream=raw,filetype='pdf') as p:
            if p.needs_pass: raise ValueError('El PDF tiene contraseña; se requiere una versión sin bloqueo.')
            if not 1 <= len(p) <= MAX_PAGES:raise ValueError('El PDF debe contener entre 1 y 80 páginas.')
            texts=[x.get_text(sort=True) for x in p]
            pages=len(texts)
            base=texts[1] if pages>1 else texts[0]
            details=texts[2] if pages>2 else texts[-1]
            # Campos detectados solo si se puede identificar inequívocamente su etiqueta.
            course=_next_value(base,r'1\.\s*NOMBRE\s+DEL\s+CURSO')
            dur=_next_value(details,r'9\.\s*DURACI[ÓO]N\s+DEL\s+CURSO')
            count=_next_value(details,r'10\.\s*N[ÚU]MERO\s+DE\s+PARTICIPANTES')
            origen=_next_value(base,r'2\.\s*CECATI\s*:')
            perfil_profesional=_next_value(details,r'15\.\s*PERFIL\s+DEL\s+DOCENTE\s*:')
            match_place=(re.search(r'(?m)\b'+re.escape(origen.strip())+r'\s+([^\n]+)', texts[4]) if pages>4 and origen.strip().isdigit() else None)
            place=match_place.group(1).strip() if match_place else ''
            hours=re.search(r'(\d+(?:[.,]\d+)?)\s*horas?', dur, re.I)
            students=re.fullmatch(r'\d+',count)
            return dict(paginas=pages,caracteres=sum(len(t.strip()) for t in texts),
                con_texto=sum(len(t.strip()) for t in texts)>=150,
                paginas_sin_texto=sum(len(t.strip())<40 for t in texts),
                orientaciones=sorted(set('horizontal' if x.rect.width>x.rect.height else 'vertical' for x in p)),
                curso=course,cecatiorigen=origen,entidadorigen=place,perfil_docente=perfil_profesional,horas=float(hours.group(1).replace(',','.')) if hours else None,
                participantes=int(count) if students else None,
                sha256=hashlib.sha256(raw).hexdigest(),
                aviso='Word reconstruido y editable; revisar distribución de tablas y contenido antes de emitir.')
    except (ValueError,RuntimeError):raise
    except Exception as exc:raise ValueError('No se pudo leer el PDF; verifica que no esté dañado.') from exc

def _validate(data,info):
    if not info['con_texto'] or info['paginas_sin_texto']>2:
        raise ValueError('El PDF no permite extraer suficientemente el texto. No se generará un Word incompleto.')
    if info['paginas']<7:
        raise ValueError('Este formato no tiene suficientes páginas para separar los campos administrativos. Necesita una revisión individual.')
    if not (info['curso'] and info['horas'] and info['participantes'] is not None):
        raise ValueError('No se pudieron identificar nombre, duración y participantes del PDF. No se sustituyen ni se inventan; revisar el original.')
    if not str(info.get('cecatiorigen','')).isdigit():
        raise ValueError('No se identificó el número de CECATI original. Para evitar sustituir contenido académico por error, esta adaptación requiere revisión manual.')
    needed=('docente','curp','telefono','correo','horario','dias','inicio','fin','sede','ciclo','valida','visto','autoriza')
    missing=[k for k in needed if not str(data.get(k) or '').strip()]
    if missing:
        labels={'curp':'CURP del docente','telefono':'teléfono del docente','correo':'correo del docente',
                'valida':'Valida','visto':'Vo. Bo.','autoriza':'Autoriza'}
        raise ValueError('Faltan datos del expediente: '+', '.join(labels.get(k,k) for k in missing)+'. Revisa los campos visibles y Autoridades.')

def _add_table(doc,items):
    table=doc.add_table(rows=0,cols=2);table.style='Table Grid';table.autofit=False
    table.columns[0].width=Inches(2.1);table.columns[1].width=Inches(4.7)
    for key,val in items:
        cells=table.add_row().cells
        cells[0].text=str(key);cells[1].text=str(val)
        for run in cells[0].paragraphs[0].runs:run.bold=True
    return table

def _academic_text(source,idx,info):
    """Solo retira membrete y datos personales antiguos; no reescribe contenidos.
    El documento resultante genera su propio encabezado institucional."""
    academic=source
    if idx==3:
        start=re.search(r'II\.\s*ENCUADRE\s+DEL\s+CURSO',academic,re.I)
        if not start:raise ValueError('No se encontró el encuadre del curso; no se generó el Word.')
        academic=academic[start.start():]
    else:
        header=re.search(r'SUBDIRECCI[ÓO]N\s+ACAD[ÉE]MICA',academic,re.I)
        if header and 'SUBSECRETARÍA DE EDUCACIÓN MEDIA SUPERIOR' in academic[:header.start()]:
            academic=academic[header.end():].lstrip()
    if idx==4:
        academic=re.sub(r'(?<![0-9])'+re.escape(str(info['cecatiorigen']))+r'(?![0-9])','31',academic,count=1)
        if info.get('entidadorigen'):
            academic=academic.replace(info['entidadorigen'],'Coatzacoalcos, Veracruz',1)
    return academic


def convertir(raw, data):
    """Separa campos administrativos de la parte académica original.
    La sección académica se transcribe en el mismo orden, sin reescritura por IA.
    Se excluye la hoja de firmas del original y se crea una hoja nueva SIN firmas.
    """
    info=inspeccionar(raw);_validate(data,info)
    fitz=_fitz();d=Document();section=d.sections[0]
    section.top_margin=Inches(.72);section.bottom_margin=Inches(.65)
    section.left_margin=Inches(.72);section.right_margin=Inches(.72)
    style=d.styles['Normal'];style.font.name='Arial';style.font.size=Pt(9)
    style.paragraph_format.space_after=Pt(4)
    t=d.add_heading('CECATI N.º 31',0);t.alignment=WD_ALIGN_PARAGRAPH.CENTER
    sub=d.add_paragraph('PLAN DE ESTUDIOS Y ADAPTACIÓN DE CURSO DE EXTENSIÓN');sub.alignment=WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph('BORRADOR PARA REVISIÓN · No autorizado · El PDF original se conserva por separado.').italic=True
    d.add_heading('I. Datos generales actualizados',1)
    _add_table(d,[('1. Nombre del curso · PDF original',info['curso']),
      ('2. CECATI','31 · Coatzacoalcos, Veracruz'),('Ciclo escolar',data['ciclo']),
      ('Tipo de curso',data.get('tipo','Extensión')),
      ('9. Duración · PDF original',f"{info['horas']:g} horas"),
      ('10. Participantes · PDF original',info['participantes']),
      ('11. Horario',data['horario']),('12. Días de impartición',data['dias']),
      ('13. Lugar de impartición',data['sede']),
      ('14. Inicio',data['inicio']),('14. Término',data['fin']),
      ('15. Perfil profesional del docente · original',info.get('perfil_docente','')),
      ('16. Docente',data['docente']),('CURP',data['curp']),
      ('Teléfono',data['telefono']),('Correo',data['correo'])])
    d.add_paragraph('Los campos del nombre, duración y participantes se recuperan del PDF y no se cambian en esta adaptación.')
    d.add_page_break()
    # Se conserva íntegro el TEXTO extraíble de las páginas académicas.
    # Todo valor administrativo antiguo del CECATI se retira únicamente de un
    # bloque específico de la primera página del programa de estudio.
    checks=[]
    with fitz.open(stream=raw,filetype='pdf') as p:
        # Este formato: páginas 4 a 16 son contenido académico; la última es firmas.
        for idx in range(3,len(p)-1):
            source=p[idx].get_text(sort=True)
            academic=_academic_text(source,idx,info)
            if not academic.strip(): raise ValueError('Una página académica carece de texto recuperable. Word no generado.')
            d.add_heading(f'Contenido académico · página {idx+1} del PDF',2)
            ptext=d.add_paragraph(academic)
            ptext.paragraph_format.keep_together=False
            ptext.paragraph_format.space_after=Pt(0)
            checks.append({'pagina_pdf':idx+1,'texto_sha256':hashlib.sha256(academic.encode('utf-8')).hexdigest(),
                           'caracteres':len(academic)})
            if idx<len(p)-2:d.add_page_break()
    d.add_page_break()
    d.add_heading('Validación y aprobación académica',1)
    d.add_paragraph('Los cargos y nombres siguientes se consignan para revisión. No se incluyen imágenes de firma.')
    _add_table(d,[('Elabora · Docente',data['docente']),
     ('Valida · Jefatura de Capacitación',data['valida']),
     ('Vo. Bo. · Dirección',data['visto']),
     ('Aprueba',data.get('aprueba','') or '____________________________'),
     ('Autoriza · Subdirección de Enlace Operativo',data['autoriza'])])
    d.add_paragraph('Espacios para firmas, sujetos a la autorización institucional correspondiente.')
    buff=io.BytesIO();d.save(buff);word=buff.getvalue()
    # Prueba literal de integridad académica sobre el Word generado.
    roundtrip='\n'.join(par.text for par in Document(io.BytesIO(word)).paragraphs)
    with fitz.open(stream=raw,filetype='pdf') as p:
        for item in checks:
            idx=item['pagina_pdf']-1;text=_academic_text(p[idx].get_text(sort=True),idx,info)
            if text not in roundtrip:
                raise ValueError('La comprobación de contenido académico no fue satisfactoria; no se guardó Word.')
    return word,dict(info,paginas_academicas_verificadas=len(checks),
                     academic_checks=checks,estatus='Borrador editable; requiere revisión visual de tablas')
