from pathlib import Path
import io,zipfile,copy
from lxml import etree as E
import centro as C
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def datos(raw,clave,seleccion):
    t=C.sisae_bytes(raw)
    grupos=[g for g in t['PROG_CURSOS1.DBF'] if g['CLAVE_CURS']==clave]
    if len(grupos)!=1:raise ValueError('Revisa el vínculo del grupo con SISAE.')
    g=grupos[0]
    if g['LU_AM']!='0':raise ValueError('Acción móvil o sin confirmar. Tu macro excluye estos grupos.')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name=next((n for n in z.namelist() if Path(n.strip()).name.upper()=='ESP.DBF'),None)
        if not name:raise ValueError('Falta el catálogo ESP.DBF en este respaldo.')
        esp={r['NOM_ESP'].strip() for r in C.dbf(z.read(name)) if (r['CLV_AREA'],r['CLV_ESP'])==(g['CLV_AREA'],g['CLV_ESP'])}
    if len(esp)!=1 or not all(esp):raise ValueError('La especialidad SISAE no es única para este grupo.')
    especialidad=' '.join(w.lower() if i and w.lower() in ('y','de','del','en') else w.title() for i,w in enumerate(esp.pop().split()))
    ids=set(seleccion);rows=[]
    for r in t['INSCRIPCION.DBF']:
        if r['CLV_CURSO']!=clave or r['ID_ALUMNO'] not in ids:continue
        control=r['ID_ALUMNO']
        if not control.isdigit() or not all(r[k].strip() for k in ('A_PATERNO','NOMBRE','CURP')):raise ValueError('Hay una ficha seleccionada incompleta. Revisa sus datos en SISAE.')
        rows.append(dict(NOMBRE=' '.join(r[k].strip() for k in ('A_PATERNO','A_MATERNO','NOMBRE') if r[k].strip()),CURP=r['CURP'],ESPECIALIDAD=especialidad,NCONTROL='|'+'|'.join(control)+'|'))
    if not ids or len(rows)!=len(ids) or {r['NCONTROL'].replace('|','') for r in rows}!=ids:raise ValueError('Selecciona inscripciones únicas del grupo y del corte actual.')
    return rows

def powerpoint(rows):
    if not rows:raise ValueError('Selecciona al menos un alumno.')
    with zipfile.ZipFile(Path(__file__).with_name('FORMATO_CREDENCIALES.pptx')) as src:
        parts={n:src.read(n) for n in src.namelist()}
    def xml(key):return E.fromstring(parts[key])
    def put(key,node):parts[key]=E.tostring(node,encoding='UTF-8',xml_declaration=True,standalone=True)
    pres='ppt/presentation.xml';rels='ppt/_rels/presentation.xml.rels';types='[Content_Types].xml'
    p=xml(pres);rel=xml(rels);ct=xml(types);lst=p.find('p:sldIdLst',NS)
    initial=copy.deepcopy(lst[0]);source=parts['ppt/slides/slide1.xml']
    for offset in range(0,len(rows),4):
        num=1+offset//4;slide=E.fromstring(source)
        for field in ('NOMBRE','CURP','NCONTROL','ESPECIALIDAD'):
            matches=[sh for sh in slide.xpath('./p:cSld/p:spTree/p:sp',namespaces=NS) if ''.join(sh.xpath('./p:txBody//a:t/text()',namespaces=NS))==field]
            if len(matches)!=4:raise ValueError('Cambió el formato de credencial.')
            for i,shape in enumerate(matches):
                value=rows[offset+i][field] if offset+i<len(rows) else ''
                runs=shape.xpath('./p:txBody/a:p/a:r',namespaces=NS);run=runs[0];parent=run.getparent()
                index=parent.index(run)
                for old in runs:parent.remove(old)
                for j,chunk in enumerate(list(value) if field=='NCONTROL' else [value]):
                    node=copy.deepcopy(run);node.find('a:t',NS).text=chunk
                    prop=node.find('a:rPr',NS)
                    if prop is None:prop=E.Element('{'+NS['a']+'}rPr');node.insert(0,prop)
                    if field=='NCONTROL':prop.set('u','sng' if chunk.isdigit() else 'none')
                    if field=='NOMBRE' and len(value)>25:prop.set('sz','800')
                    if field=='ESPECIALIDAD' and len(value)>22:prop.set('sz','600')
                    parent.insert(index+j,node)
        path=f'ppt/slides/slide{num}.xml';put(path,slide)
        if num>1:
            rid='credSlide'+str(num);entry=copy.deepcopy(initial);entry.set('id',str(int(initial.get('id'))+num-1));entry.set('{'+NS['r']+'}id',rid);lst.append(entry)
            E.SubElement(rel,rel[0].tag,Id=rid,Type=NS['r']+'/slide',Target=f'slides/slide{num}.xml')
            E.SubElement(ct,'{'+ct.nsmap[None]+'}Override',PartName='/'+path,ContentType='application/vnd.openxmlformats-officedocument.presentationml.slide+xml')
            parts[f'ppt/slides/_rels/slide{num}.xml.rels']=parts['ppt/slides/_rels/slide1.xml.rels']
    put(pres,p);put(rels,rel);put(types,ct);buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for k,v in parts.items():z.writestr(k,v)
    return buf.getvalue()
