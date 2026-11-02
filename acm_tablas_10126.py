"""Inserción documental ACM 10.12.6: 1 grupo texto; varios, tabla 2-4 columnas.
No guarda ni modifica los Word originales. Diseñado para usarse en acm_oficios.
"""
from __future__ import annotations
from datetime import datetime, date
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.shared import Pt
import re

MESES=('enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre')

def fecha(v):
    if isinstance(v,(date,datetime)):d=v
    else:
        try:d=date.fromisoformat(str(v)[:10])
        except (ValueError,TypeError):raise ValueError('La fecha del grupo no es válida: '+str(v))
    return f'{d.day:02d} de {MESES[d.month-1]} de {d.year}'

def separar_horario(v):
    """No cortar por último ':': las horas contienen dos puntos internamente."""
    s=' '.join(str(v or '').split())
    m=re.search(r'(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d',s)
    if m:
        dias=s[:m.start()].strip(' :–-;,.')
        horario=s[m.start():].strip()
    else:
        dias='';horario=s
    return dias, horario

def validar_grupos(grupos):
    if not grupos:raise ValueError('Selecciona al menos un grupo ACM.')
    if len(grupos)>12:raise ValueError('Para conservar la legibilidad, genera como máximo 12 grupos por oficio.')
    ids=[]
    for i,g in enumerate(grupos,1):
        for field in ('id','curso','inicio','termino','dias','horario','duracion'):
            if not str(g.get(field,'')).strip():
                raise ValueError(f'Grupo {i}: falta {field}. Revisa Programación y la confirmación de horario.')
        fecha(g['inicio']);fecha(g['termino'])
        if float(g['duracion'])<=0:raise ValueError(f'Grupo {i}: duración no positiva.')
        if str(g['id']) in ids:raise ValueError('Se seleccionó un grupo repetido.')
        ids.append(str(g['id']))

def lineas(g,n,*,distintos=False,sedes_distintas=False):
    line=[f'Grupo {n}']
    if distintos:line.append('Curso: '+str(g['curso']).strip())
    line += [f'Inicio: {fecha(g["inicio"])}',f'Término: {fecha(g["termino"])}',
             'Días: '+str(g['dias']).strip(),'Horario: '+str(g['horario']).strip(),
             f'Duración: {float(g["duracion"]):g} horas']
    if sedes_distintas:line.append('Sede: '+str(g['sede']).strip())
    return line

def _write_cell(cell,g,n,*,distintos=False,sedes_distintas=False):
    cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p=cell.paragraphs[0]
    p.alignment=WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before=Pt(0);p.paragraph_format.space_after=Pt(0)
    for ix,t in enumerate(lineas(g,n,distintos=distintos,sedes_distintas=sedes_distintas)):
        if ix:p.add_run().add_break()
        r=p.add_run(t);r.font.name='Noto Sans';r.font.size=Pt(9)
        if ix==0:r.bold=True

def insertar_grupos(doc,grupos):
    validar_grupos(grupos)
    matches=[p for p in doc.paragraphs if '{{GRUPOS}}' in p.text]
    if len(matches)!=1 or matches[0].text.strip()!='{{GRUPOS}}':
        raise ValueError('El Word debe contener {{GRUPOS}} en un solo párrafo, sin otros textos.')
    anchor=matches[0]
    distintos=len({str(g['curso']).strip().casefold() for g in grupos})>1
    sedes_distintas=len({str(g.get('sede','')).strip().casefold() for g in grupos})>1
    if len(grupos)==1:
        # Reutilizar el run del marcador para conservar el anclaje.
        for r in anchor.runs:
            if '{{GRUPOS}}' in r.text:
                r.text=r.text.replace('{{GRUPOS}}','\n'.join(lineas(grupos[0],1,distintos=False,sedes_distintas=False)))
                r.font.name='Noto Sans';r.font.size=Pt(9)
        if '{{GRUPOS}}' in anchor.text:
            # marcador fragmentado en runs: reemplazar exclusivamente dentro del párrafo.
            for r in anchor.runs:r.text=''
            r=anchor.add_run('\n'.join(lineas(grupos[0],1)))
            r.font.name='Noto Sans';r.font.size=Pt(9)
        anchor.alignment=WD_ALIGN_PARAGRAPH.LEFT
        return {'grupos':1,'columnas':0,'filas':0,'cursos_distintos':distintos}
    ncols=min(4,len(grupos));nrows=(len(grupos)+ncols-1)//ncols
    tab=doc.add_table(rows=nrows,cols=ncols)
    tab.style='Table Grid';tab.alignment=WD_TABLE_ALIGNMENT.CENTER;tab.autofit=False
    sec=doc.sections[0];w=int((sec.page_width-sec.left_margin-sec.right_margin)/ncols)
    for col in tab.columns:col.width=w
    for i,g in enumerate(grupos):
        cell=tab.cell(i//ncols,i%ncols);cell.width=w
        _write_cell(cell,g,i+1,distintos=distintos,sedes_distintas=sedes_distintas)
    # Última fila sin celdas vacías visualmente molestas: se dejan en blanco sin marcadores.
    anchor._p.addnext(tab._tbl)
    anchor._element.getparent().remove(anchor._element)
    # Con 4+ columnas, el membrete trae párrafos espaciadores a ambos lados
    # del marcador. Eliminar SOLO espaciadores inmediatamente contiguos evita
    # que una línea suelta ('LIF / ...') salte a una segunda página en el oficio.
    if len(grupos)>=4:
        from docx.oxml.ns import qn
        for neighbor in (tab._tbl.getprevious(),tab._tbl.getnext()):
            if neighbor is not None and neighbor.tag==qn('w:p'):
                from docx.text.paragraph import Paragraph
                par=Paragraph(neighbor,doc._body)
                if not par.text.strip() and not neighbor.xpath('.//w:drawing'):
                    neighbor.getparent().remove(neighbor)
    return {'grupos':len(grupos),'columnas':ncols,'filas':nrows,'cursos_distintos':distintos}
