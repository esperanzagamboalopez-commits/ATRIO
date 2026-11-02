"""Lectura de los campos visibles y controles seleccionados del Word institucional."""
import re
from docx import Document
from lxml import etree

NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'w14':'http://schemas.microsoft.com/office/word/2010/wordml'}

def leer_pea(source):
    doc = Document(source)
    if len(doc.tables) != 28:
        raise ValueError('Se requiere el PEA de extensión en la plantilla institucional de 28 tablas.')
    tables = [etree.fromstring(t._tbl.xml.encode()) for t in doc.tables]
    body = etree.fromstring(doc._element.xml.encode())
    def texts(node, path):
        return [str(v).strip() for v in node.xpath(path, namespaces=NS) if str(v).strip()]
    def controls(n):
        return [' '.join(texts(x,'.//w:t/text()')) for x in tables[n].xpath('.//w:sdtContent', namespaces=NS)]
    def selected(node, options):
        labels=texts(node,'.//w:sdt[w:sdtPr/w14:checkbox/w14:checked[@w14:val="1" or @w14:val="true"]]/w:sdtPr/w:alias/@w:val')
        matches=[s for s in labels if s in options]
        return matches[0] if len(matches)==1 else ''
    def cell(t,r,c):
        return doc.tables[t].cell(r,c).text.strip()
    dates=controls(12)
    profile=controls(14)
    if len(dates)!=2 or len(profile)<3 or len(controls(8))!=2:
        raise ValueError('Los controles del documento cambiaron. Revisa la plantilla de este PEA.')
    norm=selected(body,{'SÍ','NO'})
    schedule=cell(12,0,3)
    days=re.sub(r'\s*:?\s*\d{1,2}:\d{2}\s*(?:HRS?\.?|H\.?)?\s*(?:A|–|-)\s*\d{1,2}:\d{2}\s*(?:HRS?\.?|H\.?)?',' ',schedule,flags=re.I).strip(' :;.')
    venue=selected(tables[2],{'CECATI','UNIDAD MÓVIL','INSTALACIONES DEL SECTOR'})
    campus=controls(5)
    if venue=='CECATI' and len(campus)==2:venue=f'CECATI {campus[0]}, {campus[1]}'
    text=' '.join(texts(body,'.//w:t/text()'))
    phone=texts(tables[14],'./w:tr[2]/w:tc[1]//w:t/text()')
    return {'Nombre del curso':cell(4,0,0),'Especialidad':controls(8)[1],
            'Asociado a normativa':{'NO':'No','SÍ':'Sí'}.get(norm,''),
            'Código':'N/A' if norm=='NO' else cell(9,1,0),
            'Norma':'N/A' if norm=='NO' else cell(9,1,1),'Duración':cell(10,0,1),
            'Número de participantes':cell(11,0,0),'Horario':cell(10,0,3),
            'Días de impartición':days,'Lugar de impartición':venue,
            'Fecha de inicio':dates[0],'Fecha de término':dates[1],
            'Tipo de docente':selected(body,{'INTERNO','EXTERNO'}).title(),
            'CURP':profile[1],'Teléfono':' '.join(phone),'Correo':profile[2],
            'Objetivo general':cell(17,0,0),'Justificación':cell(16,0,0),
            'Temática':cell(20,0,0),'Menciona CERESO':'Sí' if re.search(r'\bCERESO\b',text,re.I) else 'No'}
