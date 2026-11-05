"""Evaluación académica trimestral: fuente única SISAE, resultados visibles primero.

No escribe ni corrige datos SISAE. No expone datos personales de alumnos.
Las recomendaciones son criterios para revisión humana, no evaluaciones docentes.
"""
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import hashlib
import html
import io
import re
import unicodedata
import zipfile
import centro as C
import cortes

MINIMO = 10
MESES = {1:'julio–septiembre', 2:'octubre–diciembre', 3:'enero–marzo', 4:'abril–junio'}

def norm(s):
    s=unicodedata.normalize('NFD',str(s or '').strip())
    return re.sub(r'\s+',' ',''.join(c for c in s if unicodedata.category(c)!='Mn').upper())

def integer(v):
    try:return int(str(v).strip())
    except (TypeError,ValueError):return 0

def period(v):
    n=integer(v)
    return n if n in (1,2,3,4) else None

def specialty_names(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            found=next((n for n in z.namelist() if Path(n.strip()).name.upper()=='ESP.DBF'),None)
            if not found:return {}
            return {(x.get('CLV_AREA','').strip(),x.get('CLV_ESP','').strip()):x.get('NOM_ESP','').strip() for x in C.dbf(z.read(found))}
    except (KeyError,zipfile.BadZipFile):return {}

def analyse(raw,selected_cycle,selected_period):
    tables=C.sisae_bytes(raw)
    groups=tables['PROG_CURSOS1.DBF']; enrol=tables['INSCRIPCION.DBF']
    specialties=specialty_names(raw)
    # Enrollment row is counted for the group identified by its SISAE course key.
    counts=Counter(i['CLV_CURSO'].strip() for i in enrol)
    # Group identity and period come from SISAE's group table; not end dates.
    found=set();out=[]
    for g in groups:
        if g.get('CICLO','').strip()!=selected_cycle or period(g.get('PERIODO'))!=selected_period:continue
        k=g.get('CLAVE_CURS','').strip()
        if not k or k in found:raise ValueError('Hay claves de grupo duplicadas o vacías en el periodo seleccionado.')
        found.add(k)
        n=counts[k]
        area=g.get('CLV_AREA','').strip(); esp=g.get('CLV_ESP','').strip()
        # Los campos indican condición de acción móvil; el tipo de servicio no basta para inferirlo.
        lu_am=g.get('LU_AM','').strip()
        am_td=g.get('AM_TD','').strip()
        con_am=g.get('CON_AM','').strip()
        is_am=(lu_am=='1' or am_td=='1' or (con_am not in ('','0')))
        out.append({
            'Acción móvil SISAE': 'Sí' if is_am else 'No identificada',
            'Indicadores AM': f'LU_AM={lu_am}; AM_TD={am_td}; CON_AM={con_am}',
            'Referencia AM':con_am if con_am not in ('','0') else '',
            'Tipo de servicio (clave)':g.get('SERV','').strip(),
            'Clave especialidad':f'{area}/{esp}',
            'Periodo SISAE auxiliar':g.get('PERIOD','').strip(),
            'Periodo esperado':str(selected_period),
            'Clave SISAE':k,'Curso':g.get('NOM_CURSO','').strip() or 'Sin nombre',
            'Grupo / horario':g.get('DES_CURSO','').strip(),
            'Docente':g.get('DOC_NOM','').strip() or 'Sin docente',
            'Especialidad':specialties.get((area,esp),f'Clave {area}/{esp}'),
            'Inicio':str(g.get('F_INICIO','')).strip(),
            'Término':str(g.get('F_TERMINO','')).strip(),
            'Horario':', '.join(x for x in [g.get('DIA1','').strip(),g.get('DIA1A','').strip(),g.get('DIA1_DE','').strip(),g.get('DIA1_A','').strip(),g.get('DIA2','').strip(),g.get('DIA2A','').strip(),g.get('DIA2_DE','').strip(),g.get('DIA2_A','').strip()] if x),
            'Inscripciones':n,'Estado de matrícula':'Sin matrícula' if n==0 else 'Menos de 10' if n<MINIMO else '10 o más',
            'Tipo SISAE':g.get('SERV','').strip(),
        })
    orphans=sum(1 for e in enrol if e['CLV_CURSO'].strip() not in {g.get('CLAVE_CURS','').strip() for g in groups})
    return {'rows':out,'orphans':orphans,'all_rows':len(groups),'all_enrollments':len(enrol)}

def summarise(rows):
    total=sum(r['Inscripciones'] for r in rows)
    n=len(rows)
    return {'grupos':n,'con_matricula':sum(r['Inscripciones']>0 for r in rows),
            'sin_matricula':sum(r['Inscripciones']==0 for r in rows),
            'de_1_a_9':sum(0<r['Inscripciones']<MINIMO for r in rows),
            'con_10_mas':sum(r['Inscripciones']>=MINIMO for r in rows),
            'inscripciones':total,'promedio':round(total/n,2) if n else 0}

def grouped(rows,key,normalise=False):
    acc={}
    for r in rows:
        val=r[key];id_=norm(val) if normalise else val
        if id_ not in acc:acc[id_]={'Nombre':val,'Grupos':0,'Inscripciones':0,'Con 10 o más':0,'Con menos de 10':0}
        it=acc[id_];it['Grupos']+=1;it['Inscripciones']+=r['Inscripciones']
        it['Con 10 o más']+=int(r['Inscripciones']>=MINIMO)
        it['Con menos de 10']+=int(r['Inscripciones']<MINIMO)
    return sorted((dict(it, **{'Promedio por grupo':round(it['Inscripciones']/it['Grupos'],2)}) for it in acc.values()),key=lambda x:(-x['Inscripciones'],x['Nombre']))

def recommendations(course_summaries):
    out=[]
    for c in course_summaries:
        avg=c['Promedio por grupo'];k=c['Grupos']; name=c['Nombre']
        if k>=2 and avg>=15 and c['Con menos de 10']==0:
            text=f'{k} grupos; {c["Inscripciones"]} inscripciones; promedio {avg:.2f}. Comparar horarios, cupos y capacidad antes de repetir.'
            out.append(('Considerar repetir',name,text))
        elif c['Con menos de 10']:
            text=f'{c["Con menos de 10"]} de {k} grupos por debajo del mínimo; promedio {avg:.2f}. Revisar horario, difusión, sede y demanda antes de cambiar o retirar la oferta.'
            out.append(('Revisar oferta',name,text))
    return out

def fmt_date(s):
    try:
        if re.fullmatch(r'\d{8}',str(s)):return date(int(s[:4]),int(s[4:6]),int(s[6:8])).strftime('%d/%m/%Y')
        return date.fromisoformat(s).strftime('%d/%m/%Y')
    except (ValueError,TypeError):return s or 'No identificado'

def make_html_report(rows,info,cycle,pnum,cut_label,course,teachers,specialties):
    """Report as a complete local HTML file, no personal student data."""
    esc=lambda s:html.escape(str(s))
    def tbl(data):
        if not data:return '<p>Sin registros.</p>'
        cols=list(data[0]); th=''.join('<th>'+esc(c)+'</th>' for c in cols)
        tbody=''.join('<tr>'+''.join('<td>'+esc(r.get(c,''))+'</td>' for c in cols)+'</tr>' for r in data)
        return f'<table><thead><tr>{th}</tr></thead><tbody>{tbody}</tbody></table>'
    summary=' '.join(f'{esc(k)}: <b>{esc(v)}</b> ·' for k,v in info.items())
    parts=[f'<h1>Evaluación académica · Periodo {pnum}</h1><p>Ciclo {esc(cycle)} · Periodo de inscripción: {esc(MESES[pnum])} · Corte SISAE: {esc(cut_label)}</p>',
           f'<p>{summary}</p><p>El análisis incluye todos los grupos inscritos en el periodo aunque terminen posteriormente. Las cifras son inscripciones, no alumnos distintos ni acreditados.</p>',
           '<h2>Ranking completo de grupos (de mayor a menor)</h2>'+tbl(sorted(rows,key=lambda r:(-r['Inscripciones'],r['Clave SISAE']))),
           '<h2>Demanda por denominación de curso</h2>'+tbl(course),
           '<h2>Matrícula por docente (sin evaluación de desempeño)</h2>'+tbl(teachers),
           '<h2>Matrícula por especialidad</h2>'+tbl(specialties),
           '<h2>Propuestas para revisión humana</h2>'+tbl([dict(Acción=a,Curso=b,Fundamento=c) for a,b,c in recommendations(course)])]
    style='body{font:14px Arial,sans-serif;color:#282127;padding:32px;max-width:1150px;margin:auto;background:#fffdfa}h1,h2{font-family:Georgia,serif}h1{color:#603048}table{border-collapse:collapse;width:100%;margin-bottom:20px;font-size:12px}td,th{padding:7px;border:1px solid #e5dcd5;text-align:left}th{background:#f4e4ea}tr:nth-child(even){background:#fbf7f3}p{line-height:1.5}@media print{body{padding:5mm}tr{break-inside:avoid}}'
    return ('<!doctype html><html lang="es"><meta charset="UTF-8"><title>Evaluación SISAE</title><style>'+style+'</style><body>'+''.join(parts)+'</body></html>').encode('utf-8')


# ATRIO 10.1 · presentación de evaluación, sin cambiar reglas SISAE.
_ICON = {
 'layers': '<path d="M12 2 2 7l10 5 10-5-10-5Zm-10 10 10 5 10-5M2 17l10 5 10-5"/>',
 'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
 'person': '<circle cx="12" cy="7" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
 'trend': '<path d="M3 3v18h18M7 16l5-5 3 2 5-7"/>',
 'check': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
 'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 'alert': '<circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 4h.01"/>',
 'chart': '<path d="M3 3v18h18M7 18v-6h3v6M13 18V8h3v10M19 18V5h2v13"/>',
 'filter': '<path d="M4 7h16M7 12h10M10 17h4"/>',
 'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12V8zM14 2v6h6M8 13h8M8 17h8"/>',
}
def eval_icon(name):
    body=_ICON[name]
    return '<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+body+'</svg>'

def eval_styles():
    return '''<style>
    .ae-intro{margin:.2rem 0 1rem;color:#6e5c63;line-height:1.55;font-size:14px}
    .ae-source{display:flex;align-items:flex-start;gap:11px;background:var(--atrio-surface);color:var(--atrio-tinta);border:1px solid rgba(212,175,55,.45);border-radius:13px;padding:14px 17px;margin:8px 0 22px;box-shadow:0 5px 20px #291b2312}
    .ae-source svg{flex-shrink:0;color:#e5b4cb;margin-top:2px}
    .ae-source strong{color:var(--atrio-titulo);font-size:13px;display:block;margin-bottom:3px}
    .ae-source span{color:#e6d9df;font-size:12.5px;line-height:1.55}
    .ae-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:10px 0 13px}
    .ae-kpi{background:#fffdfa;border:1px solid #eadbd6;box-shadow:0 6px 16px #34232c0a;border-radius:13px;padding:17px 18px;min-height:133px;position:relative;overflow:hidden}
    .ae-kpi:before{position:absolute;content:"";height:3px;left:0;right:0;top:0;background:linear-gradient(90deg,#edb0c9,#d7b78e)}
    .ae-kpi.green:before{background:#9cbba4}.ae-kpi.amber:before{background:#dbb384}.ae-kpi.red:before{background:#dca0a4}
    .ae-kpi .ico{width:29px;height:29px;display:flex;align-items:center;justify-content:center;border-radius:9px;background:#f6e4ea;color:#9b4a72;margin-bottom:10px}
    .ae-kpi.green .ico{background:#e5f0e6;color:#3e7855}.ae-kpi.amber .ico{background:#f8eee1;color:#ae7942}.ae-kpi.red .ico{background:#f7e6e7;color:#b05e64}
    .ae-kpi .number{font-family:Georgia,serif;font-size:29px;font-weight:600;line-height:1.1;color:#2b2229}
    .ae-kpi .label{font-size:12px;line-height:1.4;color:#6d5863;margin-top:7px}
    .ae-kpi .hint{font-size:10.5px;color:#91818a;margin-top:6px}
    .ae-progress-card{background:#fffdfa;border:1px solid #eadbd6;border-radius:13px;padding:16px 19px;margin:7px 0 23px}
    .ae-progress-title{font-weight:650;font-size:13px;color:#392b34;margin-bottom:11px}
    .ae-progress-track{display:flex;height:12px;overflow:hidden;border-radius:15px;background:#f2e5e8}
    .ae-progress-legend{display:flex;flex-wrap:wrap;gap:18px;margin-top:10px;color:#66525d;font-size:12px}
    .ae-dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px;vertical-align:middle}
    .ae-sec{display:flex;align-items:center;gap:11px;margin:27px 0 8px}
    .ae-sec .sec-icon{background:#f2e3e9;color:#9b4a72;border:1px solid #e5d1d9;border-radius:11px;width:37px;height:37px;display:flex;align-items:center;justify-content:center;flex:0 0 37px}
    .ae-sec h2{font-family:Georgia,serif;color:#2c2228!important;font-size:22px;line-height:1.3;margin:0!important;padding:0!important}
    .ae-sec .count{font-family:Arial,sans-serif;font-size:11px;color:#8f6d7d;border-radius:20px;border:1px solid #dfc8d2;padding:4px 8px;margin-left:auto}
    .ae-note{font-size:12.5px;color:#827079;line-height:1.5;margin:2px 0 15px}
    .ae-table-shell{background:#fffdfa;border:1px solid #e7dcd7;border-radius:13px;overflow:hidden;box-shadow:0 5px 15px #34232c09;margin:10px 0 19px}
    .ae-scroll{overflow:auto;max-height:560px}
    .ae-table{width:100%;border-collapse:collapse;font-size:12px;line-height:1.45;color:#342c31;min-width:690px}
    .ae-table th{position:sticky;top:0;z-index:2;background:#f5e8ed;color:#5d354b;font-weight:700;letter-spacing:.03em;text-align:left;border-bottom:1px solid #e8d4dd;padding:12px 13px;white-space:nowrap}
    .ae-table td{border-bottom:1px solid #f0e7e2;padding:11px 13px;vertical-align:top}
    .ae-table tr:nth-child(even) td{background:#fcf9f6}
    .ae-table tr:hover td{background:#f8f0f2}
    .ae-rank{color:#956078;font-family:Georgia,serif;font-weight:700;font-size:16px}
    .ae-pill{display:inline-block;padding:4px 8px;border-radius:15px;font-weight:650;font-size:11px;white-space:nowrap;background:#e7f0e8;color:#3e7855}
    .ae-pill.warn{background:#fbefde;color:#996534}.ae-pill.zero{background:#f8e2e4;color:#a14b59}
    .ae-course{font-weight:650;color:#35292e}
    .ae-minibar{height:5px;border-radius:8px;background:#f1e5e9;min-width:65px;margin-top:5px;overflow:hidden}
    .ae-minibar i{display:block;height:100%;background:linear-gradient(90deg,#b8668b,#e9acc9);border-radius:8px}
    .ae-insight{display:flex;gap:10px;margin:10px 0;background:#fffdfa;padding:13px 15px;border-radius:11px;border:1px solid #e8ddd8}
    .ae-insight .ae-action{color:#8a496a;font-size:12px;font-weight:700;flex:0 0 130px}
    .ae-insight .ae-desc{color:#5a4c55;font-size:12px;line-height:1.5}
    .ae-foot{font-size:11px;color:#99898f;margin:4px 0 12px}
    @media(max-width:900px){.ae-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:480px){.ae-kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ae-kpi{padding:13px 12px;min-height:123px}.ae-kpi .number{font-size:24px}.ae-progress-legend{gap:8px}.ae-sec h2{font-size:19px}}
    </style>'''

def eval_kpis(info):
    specs=[('layers','Grupos registrados',info['grupos'],'','Todos los grupos del periodo'),
           ('users','Con matrícula',info['con_matricula'],'','Al menos una inscripción'),
           ('person','Inscripciones',info['inscripciones'],'','Registros SISAE'),
           ('trend','Promedio por grupo',f"{info['promedio']:.2f}",'','Todos los grupos, incluso cero'),
           ('check','10 o más inscritos',info['con_10_mas'],'green','Cumplen el mínimo'),
           ('clock','Entre 1 y 9',info['de_1_a_9'],'amber','Debajo del mínimo'),
           ('alert','Sin inscritos',info['sin_matricula'],'red','Matrícula cero')]
    cards=[]
    for icon,title,value,variant,hint in specs:
        cards.append(f'<div class="ae-kpi {variant}"><div class="ico">{eval_icon(icon)}</div><div class="number">{html.escape(str(value))}</div><div class="label">{html.escape(title)}</div><div class="hint">{html.escape(hint)}</div></div>')
    return '<div class="ae-kpis">'+''.join(cards)+'</div>'

def eval_progress(info):
    n=max(1,info['grupos'])
    ok=info['con_10_mas'];low=info['de_1_a_9'];zero=info['sin_matricula']
    return f'''<div class="ae-progress-card"><div class="ae-progress-title">Distribución de grupos por matrícula</div>
    <div class="ae-progress-track"><div style="background:#84ac91;width:{100*ok/n:.3f}%"></div><div style="background:#d9b17d;width:{100*low/n:.3f}%"></div><div style="background:#d78f9a;width:{100*zero/n:.3f}%"></div></div>
    <div class="ae-progress-legend"><span><i class="ae-dot" style="background:#84ac91"></i>{ok} con 10 o más</span><span><i class="ae-dot" style="background:#d9b17d"></i>{low} con 1–9</span><span><i class="ae-dot" style="background:#d78f9a"></i>{zero} sin inscripciones</span></div></div>'''

def eval_section(title,icon,meta=''):
    return '<div class="ae-sec"><div class="sec-icon">'+eval_icon(icon)+'</div><h2>'+html.escape(title)+'</h2>'+('<span class="count">'+html.escape(str(meta))+'</span>' if meta else '')+'</div>'

def eval_table(rows,kind='general',max_people=0):
    if not rows:return '<p class="ae-note">No existen registros para estos filtros.</p>'
    esc=lambda v:html.escape(str(v))
    if kind=='ranking':
        columns=['#','Curso / grupo','Docente','Especialidad','Inicio','Término','Inscripciones','Situación']
        output=[]
        for i,r in enumerate(rows,1):
            n=r['Inscripciones'];cls='' if n>=10 else 'warn' if n else 'zero'
            badge='10 o más' if n>=10 else '1–9' if n else 'Cero'
            output.append('<tr><td class="ae-rank">'+str(i).zfill(2)+'</td><td><div class="ae-course">'+esc(r['Curso'])+'</div><div class="ae-foot">'+esc(r['Clave SISAE'])+' · '+esc(r['Grupo / horario'])+' · '+esc(r['Horario'])+'</div></td><td>'+esc(r['Docente'])+'</td><td>'+esc(r['Especialidad'])+'</td><td>'+esc(fmt_date(r['Inicio']))+'</td><td>'+esc(fmt_date(r['Término']))+'</td><td><strong>'+str(n)+'</strong></td><td><span class="ae-pill '+cls+'">'+badge+'</span></td></tr>')
    else:
        columns=['Nombre','Grupos','Inscripciones','Promedio','10 o más','Menos de 10']
        maximum=max([r['Inscripciones'] for r in rows],default=1) or 1
        output=[]
        for r in rows:
            rate=100*r['Inscripciones']/maximum
            output.append('<tr><td class="ae-course">'+esc(r['Nombre'])+'</td><td>'+str(r['Grupos'])+'</td><td><strong>'+str(r['Inscripciones'])+'</strong><div class="ae-minibar"><i style="width:'+f'{rate:.1f}'+'%"></i></div></td><td>'+str(r['Promedio por grupo'])+'</td><td>'+str(r['Con 10 o más'])+'</td><td>'+str(r['Con menos de 10'])+'</td></tr>')
    return '<div class="ae-table-shell"><div class="ae-scroll"><table class="ae-table"><thead><tr>'+''.join('<th>'+esc(c)+'</th>' for c in columns)+'</tr></thead><tbody>'+''.join(output)+'</tbody></table></div></div>'



def action_group(rows):
    """Retorna agregados por indicadores SISAE de acción móvil, sin inventar sedes."""
    result=[]
    for label,selected in [('Con indicadores de acción móvil',[r for r in rows if r['Acción móvil SISAE']=='Sí']),
                           ('Sin indicadores de acción móvil',[r for r in rows if r['Acción móvil SISAE']!='Sí'])]:
        info=summarise(selected)
        result.append({'Ámbito':label,'Grupos':info['grupos'],'Inscripciones':info['inscripciones'],
                       'Promedio por grupo':info['promedio'],'Con 10 o más':info['con_10_mas'],
                       'Con 1 a 9':info['de_1_a_9'],'Con 0':info['sin_matricula']})
    return result

def audit_findings(rows, analysis, cut):
    issues=[]
    def add(priority,scope,detail,next_step):
        issues.append({'Prioridad':priority,'Ámbito':scope,'Hallazgo':detail,'Acción de verificación':next_step})
    if 'verificar' in str(cut).lower() or 'sin fecha' in str(cut).lower():
        add('Validar fuente','Corte SISAE','La fecha del respaldo no se encuentra validada en ATRIO.',
            'Registrar o comprobar la fecha real del corte antes de emitir informe oficial.')
    if analysis['orphans']:
        add('Revisar integridad','Inscripciones',f"{analysis['orphans']} inscripciones del ZIP completo no enlazan con un grupo presente en la tabla de cursos.",
            'Conciliar claves y verificar si corresponden a otros ciclos o grupos no incluidos.')
    for r in rows:
        key=r['Clave SISAE']
        if r['Inscripciones']==0:
            add('Verificar registro','Grupo '+key,
                f"{r['Curso']} · {r['Grupo / horario']}: cero inscripciones en este corte.",
                'Confirmar registro, convenio, apertura, situación documental y captura SISAE. No presumir cancelación.')
        elif r['Inscripciones']<MINIMO:
            add('Revisar matrícula','Grupo '+key,
                f"{r['Curso']} · {r['Grupo / horario']}: {r['Inscripciones']} inscripciones (referencia interna: 10).",
                'Revisar horario, sede, difusión, periodo de captura y condiciones de atención antes de decidir.')
        if r['Periodo SISAE auxiliar'] not in ('',r.get('Periodo esperado','')):
            add('Validar periodo','Grupo '+key,'El periodo auxiliar SISAE requiere confirmación.',
                'Comparar PERIODO y PERIOD en la fuente original.')
        if not r['Docente'] or r['Docente']=='Sin docente':
            add('Validar registro','Grupo '+key,'No se identifica docente en la tabla de cursos.',
                'Validar en SISAE con el registro oficial.')
        if r['Especialidad'].startswith('Clave '):
            add('Validar especialidad','Grupo '+key,'Especialidad sin nombre en catálogo ESP.DBF.',
                'Verificar clave contra catálogo del corte.')
    return issues

def recommendations_cecati(rows,course,teachers,specialties,issues):
    rec=[]
    def add(priority,scope,label,evidence,proposal):
        rec.append({'Prioridad':priority,'Ámbito':scope,'Curso o referencia':label,'Evidencia SISAE':evidence,'Recomendación para revisión':proposal})
    common=[r for r in rows if r['Acción móvil SISAE']!='Sí']
    actions=[r for r in rows if r['Acción móvil SISAE']=='Sí']
    for c in grouped(common,'Curso',normalise=True):
        if c['Grupos']>=2 and c['Promedio por grupo']>=15 and c['Con menos de 10']==0:
            add('Oportunidad','Oferta por curso',c['Nombre'],
                f"{c['Grupos']} grupos; {c['Inscripciones']} inscripciones; media {c['Promedio por grupo']:.1f}.",
                'Estudiar repetición según cupo, capacidad de taller, horario, solicitud y conclusión académica.')
        if c['Con menos de 10']:
            add('Atención','Oferta por curso',c['Nombre'],
                f"{c['Con menos de 10']} de {c['Grupos']} grupos debajo de 10.",
                'Comparar grupos y horarios; explorar ajustes de difusión, programación y sede; no cancelar automáticamente.')
    if actions:
        n=sum(x['Inscripciones'] for x in actions)
        zero=sum(x['Inscripciones']==0 for x in actions)
        add('Revisión diferenciada','Acciones móviles (ACM por confirmar)',
            'Grupos con indicadores LU_AM/AM_TD',f'{len(actions)} grupos; {n} inscripciones; {zero} sin matrícula.',
            'Examinar atención a convenio, sede externa, población acordada, calendario y captura antes de comparar con grupos abiertos.')
    for r in rows:
        if r['Inscripciones']==0:
            add('Verificar antes de decidir','Grupo sin matrícula',r['Curso'],
                f"Clave {r['Clave SISAE']}; {r['Grupo / horario']}; indicadores AM: {r['Acción móvil SISAE']}.",
                'Solicitar aclaración de registro, inicio real y situación de inscripciones. No inferir inexistencia de demanda.')
    return rec

def make_cecati_report(rows,summary,cycle,pnum,cut,raw_sha,course,teachers,specialties,actions,issues,recs):
    """Reporte descargable tras acción explícita, basado en los datos VISIBLES de SISAE."""
    esc=lambda x:html.escape(str(x))
    def tab(table):
        if not table:return '<p>Sin registros.</p>'
        cols=list(table[0].keys())
        head=''.join('<th>'+esc(c)+'</th>' for c in cols)
        body=''.join('<tr>'+''.join('<td>'+esc(r.get(c,''))+'</td>' for c in cols)+'</tr>' for r in table)
        return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    status='BORRADOR · CORTE SIN FECHA VALIDADA' if 'verificar' in str(cut).lower() or 'sin fecha' in str(cut).lower() else 'REVISIÓN INTERNA · REQUIERE VALIDACIÓN'
    parts=[f'<p class="kicker">CECATI N.º 31 · Departamento de Capacitación · {esc(status)}</p>',
           '<h1>Evaluación académica y revisión de matrícula</h1>',
           f'<p>Ciclo {esc(cycle)} · Periodo {pnum}: {esc(MESES[pnum])} · Corte SISAE: {esc(cut)} · Huella SHA-256: {esc(raw_sha)}</p>',
           '<p><strong>Alcance:</strong> grupos inscritos en el periodo, aunque concluyan en otro. Inscripciones son registros de alumnos en grupos, no personas únicas ni acreditados. No es auditoría oficial ni dictamen de desempeño.</p>',
           '<h2>1. Resumen del periodo</h2>'+tab([summary]),
           '<h2>2. Ranking completo por grupo</h2>'+tab(sorted(rows,key=lambda r:(-r['Inscripciones'],r['Clave SISAE']))),
           '<h2>3. Matrícula por docente</h2>'+tab(teachers),
           '<h2>4. Demanda por especialidad</h2>'+tab(specialties),
           '<h2>5. Demanda por curso</h2>'+tab(course),
           '<h2>6. Acciones móviles y otras sedes</h2>'+tab(actions),
           '<p>Los indicadores LU_AM/AM_TD/CON_AM se interpretan como señales de acción móvil pendientes de ratificación con el procedimiento del plantel. No equivalen a demanda abierta ni identifican por sí solos un convenio validado.</p>',
           '<h2>7. Hallazgos de revisión interna</h2>'+tab(issues),
           '<h2>8. Recomendaciones sujetas a revisión</h2>'+tab(recs),
           '<h2>9. Validación y seguimiento</h2><p>Responsable de revisión: ____________________ · Fecha: __________ · Evidencia / acuerdos: ____________________</p>',
           '<p>Generado desde ATRIO con datos del respaldo seleccionado. Este documento no modifica SISAE, no prueba conclusión académica y no sustituye actas ni autorización institucional.</p>']
    css="body{font:13px/1.55 Arial,sans-serif;background:#fffdf9;color:#30252b;max-width:1150px;margin:auto;padding:35px}h1,h2{font-family:Georgia,serif;color:#3b2833}h1{font-size:28px}h2{margin-top:28px;border-bottom:1px solid #dbc7d0;padding-bottom:8px} .kicker{color:#925677;text-transform:uppercase;letter-spacing:1.5px;font-size:11px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:11px;margin-top:10px}th,td{padding:9px;border:1px solid #e5d6d8;text-align:left;vertical-align:top}th{background:#f5e7ed;white-space:nowrap}tr:nth-child(even){background:#fbf8f6} @page{size:A4 landscape;margin:12mm}@media print{body{padding:0}tr{break-inside:avoid}}"
    return ('<!doctype html><html lang="es"><meta charset="utf-8"><title>Evaluación académica CECATI 31</title><style>'+css+'</style><body>'+''.join(parts)+'</body></html>').encode('utf-8')

def report_status(cut):
    return ('Borrador: falta validar fecha del corte.' if 'verificar' in str(cut).lower() or 'sin fecha' in str(cut).lower()
            else 'Revisión interna: requiere validación administrativa antes de circularse como definitivo.')



def _evaluation_index(items):
    """Indice de navegación, con datos visibles sin pestañas ni expanders."""
    import html as _h
    links=[]
    for i,(slug,title,desc) in enumerate(items,1):
        links.append('<a class="ae-index-link" href="#atrio-ev-'+_h.escape(slug)+'">'
            +'<span class="ae-index-number">'+str(i).zfill(2)+'</span>'
            +'<span class="ae-index-copy"><strong>'+_h.escape(title)+'</strong><small>'+_h.escape(desc)+'</small></span>'
            +'<span class="ae-index-arrow" aria-hidden="true">↗</span></a>')
    return ('<div id="atrio-ev-indice" class="ae-index"><div class="ae-index-heading">'
        '<div><div class="ae-index-kicker">CONSULTA COMPLETA</div>'
        '<h3>Secciones de evaluación del periodo</h3>'
        '<p>Todos los apartados aparecen desarrollados debajo, sin pestañas ni contenido oculto. '
        'Selecciona uno para desplazarte hasta él.</p></div>'
        '</div><nav class="ae-index-grid" aria-label="Ir a una sección de evaluación">'
        +''.join(links)+'</nav></div>')


def _evaluation_anchor(slug):
    return '<div id="atrio-ev-'+slug+'" class="ae-section-anchor"></div>'


def _evaluation_nav_styles():
    return '''<style>
    .ae-index{background:#fffdfa;border:1px solid #e4d6d1;border-radius:17px;padding:21px 22px;margin:25px 0 28px;box-shadow:0 5px 19px #211d2011}
    .ae-index-heading{margin-bottom:14px}
    .ae-index-kicker{font-size:10px;color:#a46380;letter-spacing:.13em;font-weight:750;margin-bottom:5px}
    .ae-index h3{font:25px/1.2 Georgia,serif!important;color:#33252e!important;margin:0 0 5px!important;padding:0!important}
    .ae-index p{font-size:12.5px;color:#75656f!important;line-height:1.5;margin:0}
    .ae-index-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}
    .ae-index-link{display:flex;gap:10px;align-items:center;text-decoration:none!important;border:1px solid #e9dadc!important;border-radius:11px;background:#fbf6f5;padding:12px 10px;min-height:76px;color:#392b34!important;transition:background .15s ease,border-color .15s ease}
    .ae-index-link:hover{background:#f7e7ec;border-color:#d9afbf!important}
    .ae-index-number{font-size:13px;font-weight:750;color:#9e5b79;background:#f1dce5;border-radius:8px;padding:7px 8px}
    .ae-index-copy{display:flex;flex:1;flex-direction:column;gap:4px;min-width:0}
    .ae-index-copy strong{font-size:12px;line-height:1.25}
    .ae-index-copy small{font-size:10.5px;color:#846d79;line-height:1.3}
    .ae-index-arrow{font-size:15px;color:#936078}
    .ae-section-anchor{scroll-margin-top:80px;height:0px}
    .ae-eval-section{margin:35px 0 13px;padding-top:6px;border-top:1px solid #eadcdf}
    .ae-section-nudge{display:inline-block;color:#9d5d7c;font-size:11px;text-decoration:none!important;margin-top:7px}
    @media(max-width:850px){.ae-index-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:560px){.ae-index-grid{grid-template-columns:1fr}.ae-index{padding:16px}.ae-index-link{min-height:62px}}
    @media(prefers-reduced-motion:reduce){.ae-index-link{transition:none}}
    </style>'''


def _start_eval_section(slug,title,icon,meta=''):
    import streamlit as st
    st.markdown(_evaluation_anchor(slug),unsafe_allow_html=True)
    st.markdown('<div class="ae-eval-section"></div>',unsafe_allow_html=True)
    st.markdown(eval_section(title,icon,meta),unsafe_allow_html=True)


def panel():
    import streamlit as st
    st.markdown(eval_styles(),unsafe_allow_html=True)
    st.markdown(_evaluation_nav_styles(),unsafe_allow_html=True)
    st.markdown('<div class="ae-intro"><strong>Evaluación de gestión CECATI</strong> · matrícula y cobertura de la oferta con lectura diferenciada de acciones móviles. Datos visibles, revisión interna y después informe.</div>',unsafe_allow_html=True)
    paths,active=cortes.history()
    if not paths:
        st.warning('No hay un corte SISAE adoptado. Carga uno desde «SISAE · Cortes».')
        return
    def label(h):
        meta=C.setting('corte_'+h,{})
        cut=meta.get('date') or cortes.KNOWN.get(h) or 'Fecha del corte sin verificar'
        return str(cut)+(' · activo' if h==active else ' · histórico')+' · '+h[:8]
    keys=sorted(paths,key=lambda h:(C.setting('corte_'+h,{}).get('date') or cortes.KNOWN.get(h,'')),reverse=True)
    a,b=st.columns([2,1])
    key=a.selectbox('Respaldo SISAE',keys,index=keys.index(active) if active in keys else 0,format_func=label,key='eval_corte')
    raw=paths[key].read_bytes()
    tables=C.sisae_bytes(raw)
    cycles=sorted({g.get('CICLO','').strip() for g in tables['PROG_CURSOS1.DBF'] if g.get('CICLO','').strip()},reverse=True)
    if not cycles:st.warning('No hay ciclos para analizar.');return
    cycle=b.selectbox('Ciclo escolar',cycles,key='eval_ciclo')
    pnum=st.selectbox('Periodo de inscripción',[1,2,3,4],format_func=lambda v:f'{v} · {MESES[v]}',key='eval_periodo')
    cut=C.setting('corte_'+key,{}).get('date') or cortes.KNOWN.get(key,'Sin fecha verificable')
    try:analysis=analyse(raw,cycle,pnum)
    except Exception as exc:st.error('No se pudo leer este corte SISAE: '+str(exc));return
    rows=analysis['rows'];info=summarise(rows)
    raw_sha=hashlib.sha256(raw).hexdigest()
    course=grouped(rows,'Curso',normalise=True)
    teacher=grouped(rows,'Docente',normalise=True)
    specialty=grouped(rows,'Especialidad')
    action=action_group(rows)
    findings=audit_findings(rows,analysis,cut)
    recs=recommendations_cecati(rows,course,teacher,specialty,findings)
    st.markdown(f'<div class="ae-source">{eval_icon("file")}<div><strong>Fuente: SISAE · {html.escape(str(cut))}</strong><span>Periodo de inscripción {pnum}: se incluyen todos sus grupos sin importar el término. Archivo identificado por SHA-256: {raw_sha[:16]}…; no se utiliza Excel para calcular la matrícula.</span></div></div>',unsafe_allow_html=True)
    st.markdown(eval_kpis(info),unsafe_allow_html=True)
    st.markdown(eval_progress(info),unsafe_allow_html=True)
    st.caption('Umbral de 10 inscripciones: referencia de gestión indicada para el plantel; no se presenta como criterio normativo universal.')
    if analysis['orphans']:st.warning(f"{analysis['orphans']} registros de inscripción del ZIP no enlazan con los grupos de la tabla general. Requieren aclaración.")

    st.markdown(_evaluation_index([
        ('resumen','Resumen y ranking',f'{len(rows)} grupos · clasificación completa'),
        ('docentes','Matrícula por docente',f'{len(teacher)} docentes'),
        ('especialidades','Demanda por especialidad',f'{len(specialty)} especialidades'),
        ('cursos','Demanda por curso',f'{len(course)} denominaciones'),
        ('acm','ACM y sedes',f'{action[0]["Grupos"]} grupos con indicadores'),
        ('auditoria','Auditoría interna',f'{len(findings)} hallazgos a verificar'),
        ('recomendaciones','Recomendaciones',f'{len(recs)} propuestas preliminares'),
        ('informe','Generar análisis e informe','Último paso · HTML imprimible'),
    ]),unsafe_allow_html=True)

    # Todas las secciones se dibujan SIEMPRE. No usar st.tabs ni st.expander.
    _start_eval_section('resumen','1 · Resumen y ranking completo de grupos','chart',f'{len(rows)} grupos')
    st.markdown(f'<p class="ae-note">El corte registra <strong>{info["grupos"]} grupos</strong>, <strong>{info["inscripciones"]} inscripciones</strong> y <strong>{info["con_10_mas"]} grupos con al menos 10</strong>. Para interpretar las diferencias también debe revisarse sede, acción móvil, periodo de captura y disponibilidad del curso.</p>',unsafe_allow_html=True)
    st.markdown(eval_section('Distribución por condición de atención','layers'),unsafe_allow_html=True)
    st.markdown(eval_table([dict(Nombre=r['Ámbito'],Grupos=r['Grupos'],Inscripciones=r['Inscripciones'],**{'Promedio por grupo':r['Promedio por grupo'],'Con 10 o más':r['Con 10 o más'],'Con menos de 10':r['Con 1 a 9']+r['Con 0']}) for r in action]),unsafe_allow_html=True)
    st.markdown(f'<p class="ae-note">Hay <strong>{len(findings)} hallazgos por revisar</strong>, detallados en Auditoría interna. Las propuestas no constituyen sanciones ni dictámenes docentes.</p>',unsafe_allow_html=True)
    c1,c2=st.columns(2)
    direction=c1.radio('Orden de matrícula',['Mayor a menor','Menor a mayor'],horizontal=True,key='eval_orden')
    bucket=c2.selectbox('Mostrar grupos',['Todos','10 o más','1 a 9','Cero (0)'],key='eval_bucket')
    results=[r for r in rows if bucket=='Todos' or (bucket=='10 o más' and r['Inscripciones']>=MINIMO) or (bucket=='1 a 9' and 0<r['Inscripciones']<MINIMO) or (bucket=='Cero (0)' and r['Inscripciones']==0)]
    results.sort(key=lambda x:((-x['Inscripciones'] if direction=='Mayor a menor' else x['Inscripciones']),x['Clave SISAE']))
    st.markdown(eval_table(results,'ranking'),unsafe_allow_html=True)
    st.caption('El filtro solo cambia el ranking de esta pantalla. Los demás apartados y el informe utilizan TODOS los grupos del periodo.')

    _start_eval_section('docentes','2 · Matrícula por docente','users',f'{len(teacher)} docentes')
    st.caption('Comparativo de grupos, matrícula y promedio por docente. No equivale a evaluación del desempeño pedagógico.')
    st.markdown(eval_table(teacher),unsafe_allow_html=True)

    _start_eval_section('especialidades','3 · Demanda por especialidad','chart',f'{len(specialty)} especialidades')
    st.caption('Inscripciones por especialidad y número de grupos. Examinar aparte las acciones móviles y los grupos por convenio.')
    st.markdown(eval_table(specialty),unsafe_allow_html=True)

    _start_eval_section('cursos','4 · Demanda por curso','layers',f'{len(course)} denominaciones')
    st.caption('Cursos con mayor y menor captación dentro del periodo de inscripción seleccionado.')
    st.markdown(eval_table(course),unsafe_allow_html=True)

    _start_eval_section('acm','5 · ACM · Acciones móviles y sedes','users',f'{action[0]["Grupos"]} grupos identificados')
    st.caption('Identificación preliminar mediante LU_AM, AM_TD y CON_AM de SISAE; confirmar su interpretación, sede, convenio y población objetivo antes de atribuir demanda abierta o decidir cambios.')
    st.markdown(eval_table([dict(Nombre=r['Ámbito'],Grupos=r['Grupos'],Inscripciones=r['Inscripciones'],**{'Promedio por grupo':r['Promedio por grupo'],'Con 10 o más':r['Con 10 o más'],'Con menos de 10':r['Con 1 a 9']+r['Con 0']}) for r in action]),unsafe_allow_html=True)
    st.markdown(eval_table(sorted([r for r in rows if r['Acción móvil SISAE']=='Sí'],key=lambda x:-x['Inscripciones']),'ranking'),unsafe_allow_html=True)

    _start_eval_section('auditoria','6 · Auditoría académica interna','alert',f'{len(findings)} hallazgos')
    st.caption('Hallazgos para verificar, no irregularidades demostradas. Incluye grupos sin matrícula, debajo de diez, integridad y fecha del corte.')
    if findings:st.markdown(_rich_table(findings),unsafe_allow_html=True)
    else:st.success('No se detectaron observaciones con los controles automáticos disponibles.')
    st.caption('Para auditar la operación y los resultados académicos es necesario incorporar posteriormente asistencia, acreditación, constancias, autorización y convenios. SISAE por sí solo no acredita esos resultados.')

    _start_eval_section('recomendaciones','7 · Recomendaciones para la programación','check',f'{len(recs)} propuestas')
    st.caption('Propuestas sujetas a revisión de Jefatura: repetición, horario, difusión, acciones móviles y registro con matrícula cero. No modifican la programación.')
    st.markdown(_rich_table(recs),unsafe_allow_html=True)

    _start_eval_section('informe','8 · Generar análisis e informe del periodo','file')
    st.caption(report_status(cut))
    fingerprint=(key,cycle,pnum)
    if st.button('Generar análisis del periodo',type='primary',key='eval_make_analysis'):
        st.session_state['atrio_eval_analysis_ready']=fingerprint
    if st.session_state.get('atrio_eval_analysis_ready')==fingerprint:
        st.success('Análisis preparado con el corte SISAE seleccionado y todos los grupos del periodo.')
        st.markdown(f'**Síntesis para revisión:** {info["grupos"]} grupos, {info["inscripciones"]} inscripciones. {info["con_10_mas"]} cumplen la referencia de 10; {info["de_1_a_9"]} registran de 1 a 9; {info["sin_matricula"]} tienen cero. {action[0]["Grupos"]} presentan indicadores ACM; hay {len(findings)} observaciones y {len(recs)} recomendaciones preliminares.')
        if st.button('Generar informe completo para revisión',key='eval_make_report'):
            st.session_state['atrio_eval_report_ready']=fingerprint
        if st.session_state.get('atrio_eval_report_ready')==fingerprint:
            report=make_cecati_report(rows,info,cycle,pnum,cut,raw_sha,course,teacher,specialty,action,findings,recs)
            st.download_button('Descargar informe completo · HTML imprimible',data=report,
                file_name=f'ATRIO_REVISION_P{pnum}_{cycle}_{raw_sha[:10]}.html',mime='text/html',key='eval_download_102')
            st.caption('Incluye resumen, ranking, docentes, especialidades, cursos, acciones móviles, hallazgos y recomendaciones. No modifica SISAE.')
    else:
        st.info('Cuando termines de revisar los datos anteriores, pulsa «Generar análisis del periodo». Después podrás generar y descargar el informe.')

def _rich_table(records):
    if not records:return '<p class="ae-note">Sin registros para esta sección.</p>'
    cols=list(records[0])
    th=''.join('<th>'+html.escape(c)+'</th>' for c in cols)
    trs=[]
    for row in records:
        cells=''.join('<td>'+html.escape(str(row.get(c,'')))+'</td>' for c in cols)
        trs.append('<tr>'+cells+'</tr>')
    return '<div class="ae-table-shell"><div class="ae-scroll"><table class="ae-table"><thead><tr>'+th+'</tr></thead><tbody>'+''.join(trs)+'</tbody></table></div></div>'
