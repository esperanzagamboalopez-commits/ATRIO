"""ATRIO 10.10: propuesta automática y conservadora de horas para PEA Word.

El estudio independiente queda separado del total. El 20/80 corresponde al
criterio de mediación/teoría y prácticas usado por el motor actual de PEA.
No reescribe competencias, evidencias ni actividades por su propia cuenta:
la copia requiere revisión académica previa a validación o autorización.
"""
from __future__ import annotations
import io, math, re
from zipfile import ZipFile
from lxml import etree
from docx import Document

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
P_RE=re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*(?:de\s+)?horas?\s+de\s+(mediaci[oó]n\s+docente|estudio\s+independiente|pr[aá]cticas)',re.I)


def _key(value):
    v=value.lower()
    return ('mediacion' if v.startswith('mediaci') else 'independiente' if v.startswith('estudio') else 'practicas')


def _text_nodes(p):
    try:return p.xpath('.//w:t',namespaces=NS)
    except TypeError:return p.xpath('.//w:t')

def _visible(p):
    return ''.join((n.text or '') for n in _text_nodes(p))


def _parts(raw):
    doc=Document(io.BytesIO(raw)); out=[];seen=[]
    for table in doc.tables:
        if not table.rows or 'SECUENCIA DIDÁCTICA' not in table.rows[0].cells[0].text:
            continue
        for row in table.rows:
            tc=row.cells[-1]._tc
            if any(tc is previous for previous in seen):continue
            seen.append(tc)
            vals={k:0 for k in ('mediacion','practicas','independiente')}; count={k:0 for k in vals}
            for p in tc.xpath('.//w:p'):
                m=P_RE.search(_visible(p))
                if m:
                    k=_key(m.group(2)); vals[k]+=float(m.group(1).replace(',','.'));count[k]+=1
            if not any(count.values()):continue
            title=' '.join(row.cells[0].text.split())[:110] or 'Contenido sin título'
            out.append({'index':len(out),'title':title,'old':vals,'count':count,'tc':tc})
    return out


def _spread(total,weights,unit=1):
    """Asignar horas en incrementos representables, minimizando pérdida de proporción."""
    if not weights:return []
    n=int(round(total/unit))
    if abs(n*unit-total)>0.001:raise ValueError('La duración necesita incrementos horarios más precisos.')
    if n==0:return [0.0]*len(weights)
    sw=sum(weights)
    if sw<=0:raise ValueError('No hay horas del tipo requerido en el Word original.')
    shares=[n*w/sw for w in weights]
    units=[math.floor(x) for x in shares]
    for i in sorted(range(len(weights)),key=lambda j:shares[j]-units[j],reverse=True)[:n-sum(units)]:units[i]+=1
    return [round(v*unit,2) for v in units]


def _hour_unit(total):
    # No crear decimales arbitrarios salvo que la propia duración los requiera.
    if abs(total*0.2-round(total*0.2))<0.001:return 1.0
    if abs(total*0.4-round(total*0.4))<0.001:return 0.5
    return 0.1


def proponer(raw,target):
    """Propuesta determinista; requiere revisión académica de actividades/evaluaciones."""
    if not isinstance(target,(float,int)) or target<=0:raise ValueError('Duración programada inválida.')
    records=_parts(raw)
    if not records:raise ValueError('No se detectaron horas didácticas editables en el Word.')
    if any(rec['count']['mediacion']>1 or rec['count']['practicas']>1 or rec['count']['independiente']>1 for rec in records):
        raise ValueError('Hay varios bloques del mismo tipo en una celda. Revisión manual necesaria; no se altera el Word.')
    totals={k:round(sum(rec['old'][k] for rec in records),2) for k in ('mediacion','practicas','independiente')}
    if totals['mediacion']<=0 or totals['practicas']<=0:raise ValueError('No se pudo leer mediación y prácticas de forma completa.')
    if target<10:raise ValueError('La duración es demasiado corta para una propuesta automática segura.')
    target=round(float(target),2)
    theory=round(target*.2,2); practice=round(target*.8,2)
    unit=_hour_unit(target)
    medweights=[r['old']['mediacion'] for r in records];prweights=[r['old']['practicas'] for r in records]
    med=_spread(theory,medweights,unit)
    # Apertura y cierre conservan tiempo explícito dentro de la mediación/teoría.
    a=next((i for i,r in enumerate(records) if 'apertura' in r['title'].lower()),None)
    z=next((i for i,r in enumerate(records) if 'cierre' in r['title'].lower()),None)
    if a is not None and z is not None and a!=z:
        base=2*unit if theory>=8 else unit
        reserve=round(2*base,2)
        if reserve>=theory:raise ValueError('La duración no permite asignar apertura, contenidos y cierre con seguridad.')
        middle=[i for i in range(len(records)) if i not in (a,z)]
        if not middle or sum(medweights[i] for i in middle)==0:raise ValueError('No hay contenidos suficientes para distribuir la mediación.')
        medi=_spread(round(theory-reserve,2),[medweights[i] for i in middle],unit)
        med=[0.0]*len(records);med[a]=base;med[z]=base
        for i,v in zip(middle,medi):med[i]=v
    prac=_spread(practice,prweights,unit)
    rows=[]
    for i,r in enumerate(records):
        rows.append({'actividad':r['title'],'mediacion_original':r['old']['mediacion'],
                     'practicas_original':r['old']['practicas'],
                     'estudio_independiente':r['old']['independiente'],
                     'mediacion_propuesta':med[i], 'practicas_propuesta':prac[i]})
    if not math.isclose(sum(med)+sum(prac),target,abs_tol=.001):raise ValueError('Error interno al repartir horas.')
    return {'rows':rows,'originales':totals,'objetivo':target,'teoria':theory,'practicas':practice,
            'estudio_independiente':totals['independiente'],
            'nota':'Estudio independiente se conserva por separado; NO forma parte de la duración ni del 20/80. Las actividades y evaluaciones originales requieren revisión para comprobar su viabilidad.'}


def _number_text(value):
    return str(int(round(value))) if abs(value-round(value))<.001 else format(value,'.2f').rstrip('0').rstrip('.')


def _replace_first_num_preserve_runs(p,old,new):
    nodes=_text_nodes(p)
    text=''.join(n.text or '' for n in nodes)
    m=P_RE.search(text)
    if not m:raise ValueError('No se identifica el valor horario de la fila.')
    observed=float(m.group(1).replace(',','.'))
    if abs(observed-old)>.001:raise ValueError('Las horas del Word cambiaron mientras se preparaba la propuesta.')
    a,b=m.span(1)
    buf=[];pos=0;inserted=False
    for n in nodes:
        s=n.text or '';start=pos;end=pos+len(s);pos=end
        if not s:continue
        left=max(0,min(len(s),a-start));right=max(0,min(len(s),b-start))
        if right<=left:continue
        replacement=_number_text(new) if not inserted else ''
        n.text=s[:left]+replacement+s[right:]
        inserted=True
    if not inserted:raise ValueError('No fue posible ajustar horas sin reconstruir la celda.')


def _duration_cell(root,target):
    for tbl in root.xpath('.//w:tbl',namespaces=NS):
        cells=tbl.xpath('./w:tr/w:tc',namespaces=NS)
        # Solo fila de DURACIÓN TOTAL / HORARIO DEL CURSO.
        if len(cells)<4:continue
        labels=[' '.join(x.xpath('.//w:t/text()',namespaces=NS)).upper() for x in cells]
        if any('DURACIÓN TOTAL' in s for s in labels) and any('HORARIO DEL CURSO' in s for s in labels):
            pos=next(i for i,s in enumerate(labels) if 'DURACIÓN TOTAL' in s)
            if pos+1>=len(cells):break
            tc=cells[pos+1];ts=tc.xpath('.//w:t',namespaces=NS)
            joined=''.join((n.text or '') for n in ts)
            m=re.search(r'\d+(?:[.,]\d+)?',joined)
            if not m:break
            _update_range(ts,m.start(),m.end(),_number_text(target))
            return
    raise ValueError('No se encontró con seguridad el campo DURACIÓN TOTAL.')


def _update_range(nodes,a,b,new):
    pos=0;inserted=False
    for n in nodes:
        s=n.text or '';start=pos;end=pos+len(s);pos=end
        left=max(0,min(len(s),a-start));right=max(0,min(len(s),b-start))
        if right<=left:continue
        n.text=s[:left]+(new if not inserted else '')+s[right:];inserted=True
    if not inserted:raise ValueError('No se encontró el segmento de Word que contiene el número.')


def aplicar(raw,plan,ediciones_admin=()):
    """Cambios de números dentro de las mismas celdas OOXML; no reordena tablas ni estilos."""
    from pea_biblioteca_109 import _root, _replace_in_table, _tables, diagnostico
    root=_root(raw)
    original=diagnostico(raw)
    for name,old,new in ediciones_admin:
        if name in ('Fecha de inicio','Fecha de término','Días y horario'):
            fn=lambda s:'DÍAS Y HORARIO' in s and 'INICIO' in s
        elif name=='Horario':fn=lambda s:'HORARIO DEL CURSO' in s and 'DURACIÓN TOTAL' in s
        else:raise ValueError('Cambio administrativo no admitido: '+name)
        if _replace_in_table(root,fn,old,new)<1:raise ValueError('No se encontró el valor administrativo '+name)
    _duration_cell(root,plan['objetivo'])
    matches=[];seen=[]
    for tbl in root.xpath('.//w:tbl',namespaces=NS):
        rows=tbl.xpath('./w:tr',namespaces=NS)
        if not rows or 'SECUENCIA DIDÁCTICA' not in ' '.join(rows[0].xpath('.//w:t/text()',namespaces=NS)):
            continue
        for row in rows:
            cells=row.xpath('./w:tc',namespaces=NS)
            if not cells:continue
            tc=cells[-1]
            if any(tc is previous for previous in seen):continue
            seen.append(tc)
            pars=tc.xpath('.//w:p',namespaces=NS)
            if any(P_RE.search(_visible(p)) for p in pars):matches.append(pars)
    if len(matches)!=len(plan['rows']):raise ValueError('La estructura didáctica cambió; no se generó copia.')
    for pars,rec in zip(matches,plan['rows']):
        for p in pars:
            m=P_RE.search(_visible(p))
            if not m:continue
            k=_key(m.group(2))
            if k=='mediacion':_replace_first_num_preserve_runs(p,rec['mediacion_original'],rec['mediacion_propuesta'])
            elif k=='practicas':_replace_first_num_preserve_runs(p,rec['practicas_original'],rec['practicas_propuesta'])
            # Horas de estudio independiente permanecen intactas.
    removed=0
    for tbl,labels in _tables(root):
        if 'elabora' in labels.lower() and 'valida' in labels.lower():
            for graphic in list(tbl.xpath('.//w:drawing|.//w:pict|.//w:object',namespaces=NS)):
                graphic.getparent().remove(graphic);removed+=1
    output=io.BytesIO()
    with ZipFile(io.BytesIO(raw)) as src,ZipFile(output,'w') as dst:
        for info in src.infolist():
            data=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True) if info.filename=='word/document.xml' else src.read(info.filename)
            dst.writestr(info,data)
    result=output.getvalue()
    after=diagnostico(result)
    if (original['tablas'],original['secciones'])!=(after['tablas'],after['secciones']):raise ValueError('La edición modificó la estructura del Word.')
    if after['firmas_graficas']:raise ValueError('Quedaron firmas anteriores en la copia.')
    again=proponer(result,plan['objetivo'])
    if abs(again['originales']['mediacion']-plan['teoria'])>.001 or abs(again['originales']['practicas']-plan['practicas'])>.001:
        raise ValueError('No coinciden las horas del Word después de aplicar la propuesta.')
    if abs(again['originales']['independiente']-plan['estudio_independiente'])>.001:
        raise ValueError('Se alteraron las horas independientes; se descarta la copia.')
    if abs(after['duracion']-plan['objetivo'])>.001:raise ValueError('La duración declarada no coincide con la programada.')
    return result,removed
