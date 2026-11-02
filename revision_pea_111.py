"""ATRIO 10.11 — revisión documental y pedagógica orientativa de PEA DGCFT.

Motor LOCAL determinista, no IA: separa hallazgos verificables de preguntas
pedagógicas para revisión humana. No altera PEA ni prompts del generador.
"""
from __future__ import annotations
from datetime import datetime
from collections import Counter
import io, re, unicodedata, hashlib
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import pea_biblioteca_109 as P

VERSION='10.11'
MAX_BYTES=20*1024*1024


def norm(s):
    s=unicodedata.normalize('NFD',str(s or ''))
    return ' '.join(''.join(x for x in s if unicodedata.category(x)!='Mn').casefold().split())


def validar_docx(raw):
    if len(raw)>MAX_BYTES:raise ValueError('El archivo supera 20 MB.')
    P._root(raw)  # protección de ZIP/OOXML que ya utiliza ATRIO
    return Document(io.BytesIO(raw))


def _contenido(doc):
    # Únicamente lectura; las tablas conservan los datos incluso con celdas combinadas.
    parts=[p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            parts.extend(c.text for c in row.cells)
    return '\n'.join(parts)


def _hallazgo(code,area,tipo,asunto,evidencia,sugerencia,ubicacion,prioridad='Media'):
    return dict(id=code,area=area,tipo=tipo,asunto=asunto,evidencia=evidencia,
                sugerencia=sugerencia,ubicacion=ubicacion,prioridad=prioridad)


def analizar(raw,grupo):
    doc=validar_docx(raw)
    d,fields=P.campos(raw,grupo)
    bloques,horas=P.auditoria_didactica(raw)
    body=_contenido(doc);flat=norm(body)
    found=[]
    for f in fields:
        if not f['diferente']:continue
        code={'Fecha de inicio':'FECHA_INICIO','Fecha de término':'FECHA_TERMINO',
              'Duración':'DURACION','Horario':'HORARIO','Días y horario':'DIAS_HORARIO'}.get(f['campo'],'CAMPO')
        critical=f['campo']=='Duración'
        found.append(_hallazgo(code,'Correspondencia con Programación','Diferencia comprobable',f['campo'],
            f"PEA: {f['anterior'] or 'no legible'} · Programación: {f['nuevo'] or 'sin dato'}.",
            'Verificar el dato oficial y actualizarlo en una nueva copia; conservar el original.' if not critical else
            'Conciliar la duración declarada con Programación y revisar el desglose de la secuencia didáctica antes de aprobar.',
            'I. Datos generales, apartados 12–14','Alta' if critical else 'Media'))
    declaradas=d['duracion'];presencial=round(horas.get('mediación docente',0)+horas.get('prácticas',0),2)
    indep=round(horas.get('estudio independiente',0),2)
    declared_text=f'{declaradas:g} h' if declaradas is not None else 'No legible'
    if not bloques:
        found.append(_hallazgo('HORAS_INCOMPLETAS','Planeación didáctica','Requiere revisión',
          'Desglose de horas no identificable','El sistema no pudo reconocer los bloques de mediación y prácticas.',
          'Revisar las celdas de duración en la secuencia didáctica; no modificar números sin verificar el formato.',
          'III. Planeación didáctica','Alta'))
    elif abs(presencial-float(grupo['duracion']))>.01:
        found.append(_hallazgo('HORAS_SECUENCIA','Distribución de horas','Diferencia comprobable',
            'Total computable de la secuencia',
            f"Mediación {horas.get('mediación docente',0):g} h + prácticas {horas.get('prácticas',0):g} h = {presencial:g} h; Programación: {grupo['duracion']:g} h. Estudio independiente: {indep:g} h adicionales (NO computables).",
            'Revisar la distribución de apertura, desarrollo, prácticas y cierre. No sumar estudio independiente al total oficial.',
            'III. Planeación didáctica','Alta'))
    if bloques and declaradas is not None and abs(presencial-declaradas)>.01:
        found.append(_hallazgo('DECLARADO_VS_SECUENCIA','Distribución de horas','Diferencia comprobable',
            'Duración declarada frente a secuencia',
            f'Datos generales: {declared_text}; mediación + prácticas en la secuencia: {presencial:g} h. Estudio independiente: {indep:g} h fuera del total.',
            'Conciliar duración declarada con la suma computable. Mantener las horas independientes registradas aparte.',
            'I. Datos generales 12 y III. Planeación didáctica','Alta'))
    if bloques:
        theory=round(float(grupo['duracion'])*.2,2);practice=round(float(grupo['duracion'])*.8,2)
        med=horas.get('mediación docente',0);pr=horas.get('prácticas',0)
        if abs(med-theory)>.01 or abs(pr-practice)>.01:
            found.append(_hallazgo('DISTRIBUCION_2080','Distribución de horas','Requiere revisión',
                'Clasificación de teoría y práctica',
                f"La plantilla identifica {med:g} h de mediación y {pr:g} h de prácticas. El criterio operativo del plantel para {grupo['duracion']:g} h es {theory:g} h teórico-explicativas y {practice:g} h prácticas. La presencia del docente no equivale necesariamente a teoría.",
                'Clasificar las actividades reales y verificar el 20/80; no declarar incumplimiento solamente por el encabezado «mediación».',
                'III. Planeación didáctica','Media'))
    # La existencia puede verificarse por texto; la calidad curricular profunda no se infiere.
    required=[
      ('JUSTIFICACION','Justificación','II. Encuadre del curso',('justificacion',)),
      ('OBJETIVO','Objetivo general','II. Encuadre del curso',('objetivo general',)),
      ('COMPETENCIAS','Competencias','II. Encuadre del curso',('competencia(s) del curso','competencias del curso')),
      ('SABERES','Saberes','II. Encuadre del curso',('saberes para el desarrollo',)),
      ('TEMARIO','Contenido temático','II. Encuadre del curso',('contenido tematico',)),
      ('SECUENCIA','Secuencia didáctica','III. Planeación didáctica',('secuencia didactica',)),
      ('RECURSOS','Recursos didácticos','Recursos',('recursos didacticos',)),
      ('REFERENCIAS','Referencias','Recursos',('referencias',)),
    ]
    for code,name,section,options in required:
        if not any(x in flat for x in options):
            found.append(_hallazgo('ESTRUCTURA_'+code,'Integridad documental','Requiere revisión',
                'Apartado de '+name+' no localizado',
                'La lectura automática no identificó claramente el encabezado «'+name+'».',
                'Comprobar si el apartado está presente dentro de tablas, imágenes o controles Word; completar si falta.',section,'Media'))
    # Evaluación: cotejar evidencias e instrumentos; no prejuzgar pertinencia.
    instrument_labels=('cuestionario','lista de cotejo','guia de observacion','rubrica','escala estimativa','portafolio')
    evidence_labels=('evidencia','producto','desempeno','archivo electronico','practica')
    if not any(x in flat for x in instrument_labels):
        found.append(_hallazgo('INSTRUMENTOS','Evaluación del aprendizaje','Requiere revisión','Instrumentos de evaluación',
            'No se localizaron instrumentos reconocibles por texto en el documento.',
            'Identificar instrumentos específicos para cada actividad/competencia y comprobar que permiten evaluar desempeños observables.',
            'III. Planeación didáctica','Alta'))
    elif not any(x in flat for x in evidence_labels):
        found.append(_hallazgo('EVIDENCIAS','Evaluación del aprendizaje','Requiere revisión','Evidencias del aprendizaje',
            'Se localizaron instrumentos, pero no se identificaron claramente evidencias por lectura textual.',
            'Relacionar competencia, actividad, evidencia e instrumento de evaluación.',
            'III. Planeación didáctica','Media'))
    else:
        found.append(_hallazgo('TRAZABILIDAD','Evaluación del aprendizaje','Sugerencia pedagógica',
            'Correspondencia competencia–actividad–evidencia–instrumento',
            'El Word contiene referencias a instrumentos y evidencias; la detección textual no prueba que cada competencia esté efectivamente evaluada.',
            'Revisar en cada unidad que el desempeño previsto produzca una evidencia verificable y que el instrumento mida ese desempeño.',
            'II. Encuadre y III. Planeación didáctica','Media'))
    if 'seguridad' not in flat and ('electric' in norm(grupo['nombre']) or 'soldadura' in norm(grupo['nombre'])):
        found.append(_hallazgo('SEGURIDAD','Pertinencia técnica','Requiere revisión','Seguridad en taller',
            'No se identificaron menciones textuales a seguridad en el PEA de esta especialidad.',
            'Verificar medidas, equipo y procedimientos de seguridad pertinentes a las prácticas; no inventar disponibilidad de equipo.',
            'Recursos y secuencia didáctica','Media'))
    if d.get('firmas_graficas'):
        found.append(_hallazgo('FIRMA_ORIGINAL','Validación documental','Requiere revisión',
            'Firma gráfica en documento de origen',
            'El original contiene una imagen en el apartado de validación.',
            'Conservarla únicamente en el original. No trasladarla como autorización del PEA actualizado.',
            'IV. Validación académica','Media'))
    # La antigüedad de referencias es sugerencia, nunca defecto normativo automático.
    dates=re.findall(r'\b(?:19\d{2}|20\d{2})\b',body)
    older=[int(y) for y in dates if 1900<=int(y)<=2015]
    if older and any(x in flat for x in ('referencias','bibliografica')):
        found.append(_hallazgo('REFERENCIAS_ACTUALIZACION','Recursos y referencias','Sugerencia pedagógica',
          'Vigencia de las referencias',
          'Se identificaron años de publicación antiguos; pueden corresponder a fuentes válidas que todavía aportan fundamentos.',
          'Valorar si las referencias técnicas necesitan complementarse con documentación vigente, sin sustituir automáticamente fuentes válidas.',
          'Recursos didácticos y referencias','Baja'))
    counters=Counter(x['tipo'] for x in found)
    codes={x['id'] for x in found}
    checks=[
      ('Integridad documental','Revisar' if any(x.startswith('ESTRUCTURA_') for x in codes) else 'Encabezados localizados',
       'Se verificó presencia textual de los apartados, no su suficiencia pedagógica.'),
      ('Correspondencia con Programación','Diferencias detectadas' if any(x in codes for x in ('DURACION','FECHA_INICIO','FECHA_TERMINO','HORARIO','DIAS_HORARIO')) else 'Sin diferencias detectadas',
       'Comparación de fechas, horas, días y horario del documento con el grupo seleccionado.'),
      ('Objetivos y competencias','Revisar' if any(x in codes for x in ('ESTRUCTURA_OBJETIVO','ESTRUCTURA_COMPETENCIAS')) else 'Presencia localizada; calidad por verificar',
       'La existencia de texto no certifica que la competencia sea observable ni medible.'),
      ('Saberes y contenido temático','Revisar' if any(x in codes for x in ('ESTRUCTURA_SABERES','ESTRUCTURA_TEMARIO')) else 'Presencia localizada; coherencia por verificar',
       'El juicio sobre progresión y alineación requiere leer el contenido de cada unidad.'),
      ('Secuencia didáctica','Revisar' if not bloques else 'Bloques horarios identificados',
       f'Se identificaron {len(bloques)} bloques con duraciones. Se debe revisar la secuencia apertura–desarrollo–cierre.'),
      ('Horas y criterio 20/80','Revisar' if any(x in codes for x in ('DURACION','HORAS_SECUENCIA','DECLARADO_VS_SECUENCIA','DISTRIBUCION_2080')) else 'Cómputo compatible; clasificación por revisar',
       'Las horas independientes se excluyen. Mediación docente no equivale necesariamente a teoría.'),
      ('Evaluación del aprendizaje','Revisar' if any(x in codes for x in ('INSTRUMENTOS','EVIDENCIAS')) else 'Elementos localizados; pertinencia por verificar',
       'Comprobar por unidad competencia–actividad–evidencia–instrumento.'),
      ('Recursos y pertinencia ocupacional','Revisar' if any(x in codes for x in ('ESTRUCTURA_RECURSOS','ESTRUCTURA_REFERENCIAS','SEGURIDAD')) else 'Apartados localizados; pertinencia por verificar',
       'La disponibilidad del equipo y la actualidad de fuentes no se presumen.'),
    ]
    rubrica=[{'Área':a,'Resultado':b,'Alcance de la comprobación':c} for a,b,c in checks]
    return dict(rubrica=rubrica,curso=grupo['nombre'],docente=grupo['hoja'],tipo=grupo['tipo'],
        duracion_programada=float(grupo['duracion']),duracion_declarada=declaradas,
        computables=presencial,independiente=indep,horas=horas,bloques=bloques,
        sha256=hashlib.sha256(raw).hexdigest(),hallazgos=found,conteo=dict(counters),
        metodo='Reglas locales; no reemplaza evaluación pedagógica experta ni autorización DGCFT.')


def informe_word(resultado,observaciones,para_docente=False):
    """Documento independiente del PEA institucional, editable y sin firma oficial."""
    doc=Document();sec=doc.sections[0]
    sec.top_margin=Cm(2);sec.bottom_margin=Cm(2);sec.left_margin=Cm(2.2);sec.right_margin=Cm(2.2)
    normal=doc.styles['Normal'];normal.font.name='Aptos';normal.font.size=Pt(10)
    normal.paragraph_format.space_after=Pt(7)
    h=doc.add_paragraph();h.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=h.add_run('CECATI N.º 31 · ÁREA DE CAPACITACIÓN');r.bold=True;r.font.size=Pt(11);r.font.color.rgb=RGBColor(128,50,82)
    title='INFORME DE OBSERVACIONES PARA EL DOCENTE' if para_docente else 'DIAGNÓSTICO ACADÉMICO INTERNO DEL PEA'
    p=doc.add_paragraph(style='Title');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.add_run(title)
    doc.add_paragraph(f"Curso: {resultado['curso']}\nDocente: {resultado['docente']}\nDuración programada: {resultado['duracion_programada']:g} horas\nFecha de elaboración del reporte: {datetime.now():%d/%m/%Y}")
    if para_docente:
        doc.add_paragraph('Estimado(a) docente: Se comparten los siguientes hallazgos para su revisión y, en su caso, atención. Este documento no constituye un dictamen definitivo ni implica autorización del PEA.')
    else:
        doc.add_paragraph('Documento de trabajo para Jefatura de Capacitación. La revisión automática distingue diferencias comprobables, cuestiones que requieren juicio académico y sugerencias de mejora.')
    doc.add_heading('Criterio de cómputo de horas',level=2)
    doc.add_paragraph(f"Duración oficial de referencia: {resultado['duracion_programada']:g} h. Horas computables detectadas (mediación + prácticas): {resultado['computables']:g} h. Estudio independiente: {resultado['independiente']:g} h adicionales, NO se suma al total oficial ni al 20/80.")
    if not para_docente:
        doc.add_heading('Matriz de revisión documental y pedagógica',level=2)
        for item in resultado.get('rubrica',[]):
            doc.add_paragraph(item['Área']+': '+item['Resultado']+' — '+item['Alcance de la comprobación'])
    doc.add_heading('Observaciones seleccionadas',level=2)
    if not observaciones:doc.add_paragraph('No se seleccionaron observaciones para este informe.')
    for index,x in enumerate(observaciones,1):
        doc.add_heading(f"{index}. {x['asunto']}",level=3)
        doc.add_paragraph(f"Tipo: {x['tipo']} · Prioridad: {x['prioridad']} · Apartado: {x['ubicacion']}")
        doc.add_paragraph('Hallazgo: '+x['evidencia'])
        doc.add_paragraph('Recomendación: '+x.get('sugerencia_editada',x['sugerencia']))
        if para_docente:doc.add_paragraph('Atención del docente: ______________________________________________')
    doc.add_heading('Seguimiento',level=2)
    doc.add_paragraph('Estado de observaciones: para revisión y atención; la comprobación de correcciones se registrará posteriormente.')
    doc.add_paragraph('Nota: esta revisión local no certifica por sí sola pertinencia pedagógica, cumplimiento normativo general ni autorización por instancias de la DGCFT.')
    b=io.BytesIO();doc.save(b);return b.getvalue()
