# -*- coding: utf-8 -*-
"""Generador PEA CECATI 31 para uso en casa con plantilla configurable.

No modifica ninguna entrada. Entrega PEAs completos PARA REVISION ACADÉMICA.
Sin fingir aprobación, firmas o registros sin fuente. Usa Gemini como IA fija.
La IA nunca recibe CURP, teléfono, correo ni imágenes de firmas.
Dependencias: python-docx, openpyxl, google-genai (solo modo IA).
"""
import argparse
import copy
import csv
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import time
import hashlib
import unicodedata

import control_calidad_pea_v7 as qa_v7  # MEJORAS_ACADEMICAS_V7_INSTALADAS

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

BASE = Path(__file__).resolve().parent
W = lambda label: qn('w:'+label)
PLANTILLA = 'PEA_final en blanco.docx'
PROGRAMACIONES = ('programacion_cursos.xlsx', 'PROGRAMACION DE CURSOS.xlsx')
ARCHIVOS_DOCENTES = ('Plantilla_Datos_Docentes_PEA_CECATI31(1).xlsx', 'Plantilla_Datos_Docentes_PEA_CECATI31.xlsx')
BASE_CASA = Path(r'C:\Users\perit\OneDrive\Escritorio\PEA´S')
AUTORIDAD_VALIDA = 'Lila Inurreta Fernández'
AUTORIDAD_VISTO = 'Lila Inurreta Fernández'
AUTORIDAD_AUTORIZA = 'Sergio López Hernández'
SALIDA = 'PEAs_Finales_Para_Revision'
CACHE = 'cache_ia'
DEMO = 'PRUEBA_INFORMATICA_BASICA_v4.json'
DIAS_EXCLUIDOS = 'DIAS_SIN_CLASE.json'
CONFIGURACION = 'CONFIGURACION_PEA.json'
REGISTRO_INSTITUCIONAL = 'REGISTRO_INSTITUCIONAL_PEA.json'
FUENTES_VERIFICADAS = 'FUENTES_VERIFICADAS_PEA.json'
FUENTES_AMPLIADAS_V62 = 'FUENTES_BASE_VERIFICADAS_v6_2.json'


def normal(s):
    s=' '.join(str(s or '').split()).casefold()
    return ''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn')


def fecha(valor):
    if isinstance(valor,(dt.datetime,dt.date)):return valor.date() if isinstance(valor,dt.datetime) else valor
    if isinstance(valor,(int,float)) and valor>30000:
        return (dt.datetime(1899,12,30)+dt.timedelta(days=valor)).date()
    for f in ('%d/%m/%Y','%Y-%m-%d','%d-%m-%Y'):
        try:return dt.datetime.strptime(str(valor).split(' ')[0],f).date()
        except (TypeError,ValueError):pass
    return None


def horario_simple(raw):
    text=str(raw or '').upper().replace('\n',' ').strip()
    m=re.search(r'(\d{1,2}):(\d{2})\s*(?:A|[-–])\s*(\d{1,2}):(\d{2})',text)
    if not m: return None
    a,b,c,d=map(int,m.groups()); duration=(c*60+d-a*60-b)/60
    if duration<=0 or duration>12:return None
    pref=text[:m.start()].strip(' :;,-')
    pref=re.sub(r'\s+',' ',pref)
    # Advertir, no inventar equivalencias para bloques complejos o varios turnos.
    can_calculate='\n' not in str(raw or '') and len(re.findall(r'\d{1,2}:\d{2}',text))==2
    mapa={'LUNES':0,'MARTES':1,'MIERCOLES':2,'JUEVES':3,'VIERNES':4,'SABADO':5,'DOMINGO':6}
    norma=normal(pref).upper()
    dias=[]
    if 'LUNES A VIERNES' in norma: dias=list(range(5))
    elif 'LUNES A JUEVES' in norma: dias=list(range(4))
    elif 'MARTES A VIERNES' in norma: dias=list(range(1,5))
    elif 'LUNES A SABADO' in norma: dias=list(range(6))
    elif 'SABADO' in norma and 'DOMINGO' not in norma: dias=[5]
    elif 'DOMINGO' in norma and 'SABADO' not in norma: dias=[6]
    elif norma in mapa:dias=[mapa[norma]]
    else:can_calculate=False
    return {'horas':f'{a:02d}:{b:02d} - {c:02d}:{d:02d}', 'h_dia':duration,'dias':dias,'calculable':can_calculate and bool(dias)}


def cargar_dias(base):
    p=base/DIAS_EXCLUIDOS
    if not p.exists():return set()
    valores=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(valores,list):raise ValueError('DIAS_SIN_CLASE.json debe contener una lista de fechas AAAA-MM-DD')
    return {dt.date.fromisoformat(s) for s in valores}


def revisar_calendario(curso, base):
    h=horario_simple(curso['horario'])
    if not h:return 'NO VERIFICABLE: horario no interpretable (sin alterarlo).'
    if not h['calculable']:return 'NO VERIFICABLE: horario variable; comprobar manualmente.'
    ini=fecha(curso['inicio']);fin=fecha(curso['fin'])
    if not ini or not fin or ini>fin:return 'ERROR: fechas ausentes o contradictorias.'
    ex=cargar_dias(base)
    sesiones=sum(d.weekday() in h['dias'] and d not in ex for d in (ini+dt.timedelta(days=x) for x in range((fin-ini).days+1)))
    programadas=round(sesiones*h['h_dia'],2)
    if abs(programadas-curso['duracion'])<0.001:
        return f'COINCIDE: {sesiones} sesiones × {h["h_dia"]:g} h = {curso["duracion"]:g} h (según DIAS_SIN_CLASE.json).'
    return f'DIFERENCIA: {sesiones} sesiones × {h["h_dia"]:g} = {programadas:g} h; oficiales {curso["duracion"]:g} h. No modificar automáticamente.'


def buscar_archivo(base, opciones, etiqueta):
    """Encuentra archivos familiares, avisando si hay más de una versión."""
    # La elección explícita desde el visor evita leer una copia desactualizada
    # cuando existen dos nombres históricos del mismo Excel.
    clave_preferencia = (
        'PEA_PROGRAMACION' if etiqueta == 'la programación de cursos' else
        'PEA_PADRON' if etiqueta == 'el padrón de docentes' else None
    )
    if clave_preferencia and os.environ.get(clave_preferencia):
        elegido=os.environ[clave_preferencia]
        if elegido not in opciones or not (base/elegido).is_file():
            raise FileNotFoundError(f'Archivo seleccionado en {clave_preferencia} no disponible: {elegido}')
        return base/elegido
    disponibles=[base/n for n in opciones if (base/n).is_file()]
    if not disponibles:
        raise FileNotFoundError(f'No se encontró {etiqueta} en {base}. Nombres aceptados: '+', '.join(opciones))
    if len(disponibles)>1:
        print(f'AVISO: se encontraron varias versiones de {etiqueta}. Se usará {disponibles[0].name}.')
    return disponibles[0]


def cargar_configuracion(base):
    """Preferencias operativas definidas UNA SOLA VEZ, sin pedir confirmaciones al generar."""
    defaults={
        'formacion':'PARA EL TRABAJO',
        'modalidad':'PRESENCIAL',
        'usuario':'PÚBLICO EN GENERAL',
        'sede_predeterminada':'CECATI',
        'sede_por_aula':{'ACM':'INSTALACIONES DEL SECTOR'},
        'campo_por_especialidad':{
            'INFORMÁTICA':'Tecnologías de la Información',
            'SOPORTE A INSTALACIONES ELÉCTRICAS Y MOTORES ELÉCTRICOS':'Electricidad',
            'ELECTRICIDAD':'Electricidad',
            'MÁQUINAS - HERRAMIENTA':'Metalmecánica',
            'SOLDADURA Y PAILERÍA':'Metalmecánica',
            'REFRIGERACIÓN Y AIRE ACONDICIONADO':'Equipos y Sistemas',
            'ADMINISTRACIÓN':'Administración',
            'ARTES GRÁFICAS':'Sistemas de Impresión',
            'USO DE LA LENGUA INGLESA EN DIVERSOS CONTEXTOS':'Comunicación',
        },
        'normalizacion':'',
    }
    ruta=base/CONFIGURACION
    if not ruta.is_file(): return defaults
    try:
        actual=json.loads(ruta.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as e:
        raise ValueError('CONFIGURACION_PEA.json no es JSON válido: '+str(e)) from e
    if not isinstance(actual,dict): raise ValueError('CONFIGURACION_PEA.json debe ser un objeto JSON')
    defaults.update({k:v for k,v in actual.items() if k not in ('sede_por_aula','campo_por_especialidad')})
    for sub in ('sede_por_aula','campo_por_especialidad'):
        if sub in actual:
            if not isinstance(actual[sub],dict):raise ValueError('La sección '+sub+' debe ser un objeto JSON')
            defaults[sub].update(actual[sub])
    return defaults


def cargar_catalogo_json(base,nombre):
    path=base/nombre
    if not path.is_file():return {}
    datos=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(datos,dict):raise ValueError(nombre+' debe contener un objeto JSON.')
    return datos


def dato_por_curso(curso,registros):
    """Priorizar coincidencia EXACTA de hoja/fila; luego nombre+hoja.

    Únicamente datos oficiales aportados al catálogo; nunca interpretar ausencia
    como SI o NO, ni considerar que una fecha planeada sea fecha de entrega real.
    """
    item=normal(curso['hoja']).upper()+'|'+str(curso['fila'])
    por_grupo=registros.get('por_grupo',{})
    if not isinstance(por_grupo,dict):return {}
    for k,v in por_grupo.items():
        if normal(k).upper()==normal(item).upper() and isinstance(v,dict):return v
    return {}


def _fecha_real(s):
    d=fecha(s)
    return d.strftime('%d/%m/%Y') if d else ''


def rellenar_campos_institucionales(doc,curso,base,perfil,avisos):
    """Completar solo hechos con fuente en el registro, fuera de consultas Gemini."""
    registro=cargar_catalogo_json(base,REGISTRO_INSTITUCIONAL)
    ficha=dato_por_curso(curso,registro)
    t=doc.tables
    # Fechas de entrega: opcionales según instrucción. NO calcular ni retrofechar.
    controles=t[15]._tbl.xpath('.//w:sdt')
    if len(controles)!=2:raise ValueError('Cambiaron controles de fechas de entrega en tabla 16')
    for sd,k,etiqueta in zip(controles,('entrega_capacitacion','entrega_direccion'),
                           ('Capacitación','Dirección')):
        valor=ficha.get(k,'')
        real=_fecha_real(valor)
        if valor and not real:raise ValueError('Fecha inválida en registro '+k+'; usar AAAA-MM-DD')
        if real:
            actualizar_sdt(sd,real)
            pr=sd.find(W('sdtPr'))
            if pr is not None:
                mostrando=pr.find(W('showingPlcHdr'))
                if mostrando is not None:pr.remove(mostrando)
        else:
            # Quitar la instrucción gris «Haga clic aquí», pero NO inventar fecha.
            # El campo sigue editable y el TXT registra la incidencia.
            actualizar_sdt(sd,'')
            pr=sd.find(W('sdtPr'))
            if pr is not None:
                mostrando=pr.find(W('showingPlcHdr'))
                if mostrando is not None:pr.remove(mostrando)
            # El apartado 18 puede permanecer vacío; no bloquear la entrega.
            pass
    # PUNTO 10: SIEMPRE mostrar SÍ/NO como círculos EDITABLES de Word.
    # La selección se basa ÚNICAMENTE en evidencia documental por curso;
    # sin registro se muestran ambos vacíos (jamás se presume «No»).
    norm=normal(ficha.get('normalizacion',''))
    if norm not in ('si','sí','no'):
        avisos.append('PUNTO 10: sin respuesta oficial documentada Sí/No; se mantienen las dos opciones editables.')
    valor='SÍ' if norm in ('si','sí') else ('NO' if norm=='no' else '')
    destino=next((p for p in doc.paragraphs if 'el curso esta asociado' in normal(p.text)),None)
    siguiente=destino._p.getnext() if destino is not None else None
    if siguiente is None or siguiente.tag!=W('p'):
        raise ValueError('No se identificó el renglón de opciones SÍ/NO de normalización.')
    for x in list(siguiente):
        if x.tag!=W('pPr'):siguiente.remove(x)
    for i,label in enumerate(('SÍ','NO')):
        siguiente.append(casilla_real(label,label==valor,1500+i))
        rr=OxmlElement('w:r');tt=OxmlElement('w:t')
        tt.text=' '+label+'       ';tt.set(qn('xml:space'),'preserve')
        rr.append(tt);siguiente.append(rr)
    if norm in ('si','sí'):
        codigo=str(ficha.get('codigo_norma','')).strip()
        titulo=str(ficha.get('nombre_norma','')).strip()
        if codigo and titulo:
            set_cell(t[9].cell(1,0),codigo,8.0)
            set_cell(t[9].cell(1,1),titulo,8.0)
        else:avisos.append('SIN DATO OFICIAL: falta código y nombre de la norma aplicable.')
    elif norm=='no':
        set_cell(t[9].cell(1,0),'NO APLICA',8.0)
        set_cell(t[9].cell(1,1),'NO APLICA',8.0)
    if ficha.get('convenio_institucion'):
        set_cell(t[6].cell(0,0),str(ficha['convenio_institucion']),8.0)
    elif normal(ficha.get('sin_convenio','')) in ('si','sí','true') or ficha.get('sin_convenio') is True:
        set_cell(t[6].cell(0,0),'NO APLICA',8.0)
    else:avisos.append('SIN DATO OFICIAL: convenio o constancia de que no aplica.')
    # NOTA CRÍTICA: t[16] es la JUSTIFICACIÓN del curso, no el CV.
    # La plantilla coloca el apartado 19 del CV fuera de las tablas de datos.
    # NUNCA escribir «NO APLICA — DOCENTE INTERNO» aquí: borraba el encuadre.
    if normal(perfil.get('tipo',''))=='externo':
        avisos.append('DOCENTE EXTERNO: anexar CV institucional autorizado (no se inventa).')
    # Tipo de usuario: reemplazar preselección global si existe ficha oficial.
    tipo_usuario=ficha.get('tipo_usuario','')
    if tipo_usuario:
        grupo_en_tabla(t[7],[(0,0,'PÚBLICO EN GENERAL'),(0,1,'EMPLEADO'),
                    (0,2,'DESEMPLEADO'),(0,3,'AUTOEMPLEADO'),(1,0,'ADULTO MAYOR'),
                    (1,1,'JUBILADO'),(1,2,'PERSONA CON DISCAPACIDAD'),(1,3,'OTRO'),
                    (2,0,'ESTUDIANTE DE INSTITUCIÓN EDUCATIVA'),
                    (2,2,'GRUPO EN DESVENTAJA SOCIAL Y/O ECONÓMICA')],tipo_usuario,14)
    return ficha


def fuentes_para_curso(curso,base):
    """Combina fuentes comprobadas de v6.3 con el catálogo LOCAL del plantel.

    El archivo institucional FUENTES_VERIFICADAS_PEA.json NO se sobrescribe
    con actualizaciones. Cada categoría que esté curada por el plantel
    prevalece sobre la bibliografía preinstalada de esta versión.
    """
    clave=normal(curso['nombre'])
    finales={}
    for archivo in (FUENTES_AMPLIADAS_V62,FUENTES_VERIFICADAS):
        catalogo=cargar_catalogo_json(base,archivo)
        cursos=catalogo.get('por_curso',{})
        if not isinstance(cursos,dict):continue
        for nombre,v in cursos.items():
            if normal(nombre)==clave and isinstance(v,dict):
                for cat in ('bibliografica','hemerografica','cibergrafica'):
                    valores=v.get(cat)
                    if isinstance(valores,list) and any(str(a).strip() for a in valores):
                        finales[cat]=[str(a).strip() for a in valores if str(a).strip()]
                break
    return finales


def referencias_efectivas(curso,base,datos):
    """La fuente ya comprobada tiene prioridad, sin desechar categorías
    adicionales que la IA haya aportado para revisión académica."""
    val=datos.get('referencias') if isinstance(datos,dict) else {}
    val=val if isinstance(val,dict) else {}
    curadas=fuentes_para_curso(curso,base)
    resultado={}
    for cat in ('bibliografica','hemerografica','cibergrafica'):
        fuente=curadas.get(cat) or val.get(cat) or []
        if isinstance(fuente,str):fuente=[fuente]
        resultado[cat]=[str(x).strip() for x in fuente if str(x).strip()]
    return resultado


def recursos_cuantificados(curso,reqs):
    """Requisitos para impartir el curso, NO inventario disponible en la escuela."""
    n=curso.get('poblacion')
    try: n=int(n)
    except (TypeError,ValueError):n=0
    # Priorizar la propuesta específica de Gemini si pasó la verificación.
    if reqs.get('_procedencia_ia'):return reqs
    nombre_curso=normal(curso.get('nombre',''))
    if 'administracion de recursos financieros' in nombre_curso:
        cantidad=n or 10
        return {
          'equipo':f'Requeridos para el curso: {cantidad} equipos de cómputo con capacidad para manejar libros de cálculo, 1 equipo del docente, proyector o pantalla y calculadoras para ejercicios de razones financieras.',
          'herramientas':'Hoja de cálculo con funciones financieras (VA, VF, PAGO, TIR, VNA), plantillas digitales de presupuesto operativo, flujo de efectivo y análisis de liquidez.',
          'materiales':f'{cantidad} conjuntos de estados financieros ficticios (balance y resultados), {cantidad} casos de presupuestación, ejercicios de capital de trabajo y series de tasas de interés tomadas de fuentes oficiales.',
          'apoyo':'Guías para interpretar razones financieras, prácticas de proyección de efectivo, rúbricas de presupuestos, lista de cotejo de indicadores y calculadora financiera digital.',
          'conectividad':'Acceso a Internet para consulta del Sistema de Información Económica de Banxico y recursos de educación financiera; no utilizar datos personales reales en ejercicios.'
        }
    if 'informatica' not in normal(curso.get('especialidad_programada','')):return reqs
    if n>0:
        reqs['equipo']=(f'Requeridos para {n} participantes: {n} computadoras de práctica '
            '(una por participante), 1 equipo del docente y 1 proyector; '
            'sistema operativo con acceso a almacenamiento local.')
        reqs['herramientas']='Requeridas: procesador de textos y hoja de cálculo instalados en cada computadora; navegador web.'
        reqs['materiales']=(f'Requeridos: {n} juegos de archivos digitales de práctica y '
            f'{n} carpetas electrónicas de evidencias, sin datos personales reales.')
        reqs['apoyo']=f'Requeridos: {n} guías de práctica digital, 1 rúbrica y 1 lista de cotejo por unidad.'
        reqs['conectividad']='Requerido: acceso a Internet durante las prácticas de correo y nube; conexión de red para equipos participantes.'
    return reqs


def revisar_documento_final(doc,curso,base,datos,avisos):
    """Control de calidad PREVIO a guardar: las faltas se listan fuera del Word."""
    text='\n'.join(p.text for p in doc.paragraphs)+'\n'+'\n'.join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    for palabra in ('POR CONFIRMAR','PENDIENTE DE','TEXTO A GENERAR'):
        if palabra in text.upper():avisos.append('TEXTO PROHIBIDO EN EL DOCUMENTO: '+palabra)
    # Verifica la suma directamente del objeto curricular, ya validado antes.
    t=doc.tables
    if not (fuentes_para_curso(curso,base) or datos.get('referencias')):
        avisos.append('SIN FUENTE ACADÉMICA: no existen referencias documentales verificadas para este curso.')
    elif not fuentes_para_curso(curso,base) and datos.get('referencias'):
        avisos.append('REFERENCIAS DE IA: verificar autor, título, fecha y acceso antes de aprobar.')
    if not curso.get('docente'):
        avisos.append('FALTA PERFIL DOCENTE: no constan CURP, correo y teléfono para este curso.')
    if len(t)!=28:avisos.append('La estructura de 28 tablas no se conserva.')
    if curso['tipo']!='Extensión':avisos.append('TIPO NO ADMITIDO: solo cursos de Extensión.')
    return avisos


def _nombre_hoja_especialidad(valor):
    # Encabezado estructural de especialidad, p.ej. 23-I-2022A, 25-A-2022A.
    return bool(re.match(r'^\s*\d{2}[-–][A-Za-z]+[-–]\d{4}', str(valor or '')))


def leer_archivos(base):
    # Lectura de Excel exclusivamente; el programa jamás sobrescribe los originales.
    from openpyxl import load_workbook
    archivo=buscar_archivo(base,PROGRAMACIONES,'la programación de cursos')
    fichero=buscar_archivo(base,ARCHIVOS_DOCENTES,'el padrón de docentes')
    if not (base/PLANTILLA).is_file():
        raise FileNotFoundError('Falta la plantilla Word '+PLANTILLA+' en '+str(base))
    print('Programación:',archivo.name)
    print('Docentes:',fichero.name)
    print('Plantilla:',PLANTILLA)
    w=load_workbook(archivo,read_only=True,data_only=True)
    wd=load_workbook(fichero,read_only=True,data_only=True)
    if 'DOCENTES' not in wd:raise ValueError('La plantilla de docentes debe tener hoja DOCENTES')
    perfiles={}
    for row in wd['DOCENTES'].iter_rows(min_row=2,values_only=True):
        if len(row)<9 or not row[1]:continue
        nombre=str(row[1]).strip()
        registro=dict(zip(('id','nombre','curp','correo','telefono','tipo','especialidad','firma','autorizada'),row[:9]))
        perfiles[normal(nombre)]=registro
    cursos=[]
    for sheet in w:
        especialidad_programada=''
        for n,row in enumerate(sheet.iter_rows(values_only=True),1):
            if _nombre_hoja_especialidad(row[0] if row else None) and len(row)>1 and row[1]:
                especialidad_programada=str(row[1]).strip()
            if n<15:continue
            codigo=str(row[0] or '').strip()
            if normal(codigo) not in {'regular','extension'}:continue
            if len(row)<9 or not row[1]:continue
            try:dur=float(row[6])
            except (TypeError,ValueError):continue
            cursos.append({'hoja':sheet.title,'fila':n,'tipo':'Extensión' if normal(codigo)=='extension' else 'Regular',
                           'nombre':str(row[1]).strip(),'poblacion':row[3],'inicio':row[4],
                           'fin':row[5],'duracion':dur,'horario':str(row[8] or '').strip(),
                           'aula':str(row[9] or '').strip() if len(row)>9 else '',
                           'especialidad_programada':especialidad_programada,
                           'observaciones':str(row[11] or '') if len(row)>11 else '',
                           'docente':perfiles.get(normal(sheet.title))})
    w.close();wd.close()
    return cursos,perfiles


def validator(datos,h,total):
    u=datos.get('unidades',[])
    if not 3<=len(u)<=8:raise ValueError('Se requieren de 3 a 8 unidades para este formato.')
    sumh=h['apertura']+h['cierre']
    claves=('teorizacion_docente','teorizacion_estudiante','ejercitacion_docente',
            'ejercitacion_estudiante','reflexion_docente','reflexion_estudiante')
    for i,uni in enumerate(u,1):
        titulo=uni.get('titulo','')
        if not re.match(rf'^UNIDAD\s+{i}\s*[.:\-]\s+\S',titulo,re.I):raise ValueError(f'Unidad {i}: título no válido')
        if '\n' in titulo or len(titulo)>140:raise ValueError(f'Unidad {i}: el título contiene demasiado texto')
        temas=uni.get('temas',[])
        if not isinstance(temas,list) or len(temas)<2:raise ValueError(f'Unidad {i}: menos de 2 subtemas')
        for j,t in enumerate(temas,1):
            if not re.match(rf'^{i}\.{j}\s+\S',str(t)) or len(str(t))>200:
                raise ValueError(f'Unidad {i}: el tema {j} no está numerado o mezcla narrativas')
        act=uni.get('actividades',{})
        if any(len(str(act.get(k,'')))<75 for k in claves):raise ValueError(f'Unidad {i}: falta desarrollo específico de actividades')
        evaluacion=uni.get('evaluacion',{})
        criterios=evaluacion.get('criterios',[])
        if not isinstance(criterios,list) or len([c for c in criterios if isinstance(c,str) and c.strip()])<2:
            raise ValueError(f'Unidad {i}: faltan criterios evaluables')
        med=uni.get('mediacion_horas');prac=uni.get('practica_horas')
        if not isinstance(med,(int,float)) or not isinstance(prac,(int,float)) or med<0 or prac<0:
            raise ValueError(f'Unidad {i}: horas incorrectas')
        sumh+=med+prac
    if abs(sumh-total)>0.01:raise ValueError(f'El PEA suma {sumh:g} h; la programación indica {total:g} h')
    for k in ('justificacion','objetivo_general','competencia','saberes_teoricos','saberes_procedimentales','saberes_axiologicos'):
        if not str(datos.get(k,'')).strip():raise ValueError('Falta '+k)
    # Puertas de calidad para no entregar campos vacíos o «No aplica» falsos.
    just=str(datos['justificacion']).strip()
    if len(just)<170 or re.search(r'\bNO\s+APLICA\b',just,re.I):
        raise ValueError('JUSTIFICACIÓN insuficiente o sustituida por NO APLICA. Gemini debe redactar problemática, necesidad, oportunidad y beneficio del curso.')
    objetivo=str(datos['objetivo_general']).strip()
    primer=normal(objetivo.split()[0]).lower() if objetivo.split() else ''
    if not primer.endswith(('ar','er','ir')) or len(objetivo)<110:
        raise ValueError('OBJETIVO GENERAL: redactar con verbo inicial en infinitivo, objeto, condición y finalidad (Tema 2).')
    competencia=str(datos['competencia']).strip()
    if len(competencia)<100 or normal(competencia)==normal(objetivo):
        raise ValueError('COMPETENCIA: debe expresar una actuación observable, distinta del objetivo y con verbo en tercera persona.')
    resultados=datos.get('resultados_aprendizaje')
    if not isinstance(resultados,list) or len([x for x in resultados if isinstance(x,str) and len(x.strip())>=40])<3:
        raise ValueError('RESULTADOS DE APRENDIZAJE: se requieren al menos 3 desempeños concretos y verificables.')
    if any(not normal(str(x).split()[0]).endswith(('ar','er','ir')) for x in resultados if isinstance(x,str) and x.split()):
        raise ValueError('RESULTADOS DE APRENDIZAJE: escribir cada uno con verbo inicial en infinitivo, según Tema 2.')


def recuperar_objeto_json(texto):
    """Acepta JSON estricto o un único objeto rodeado de texto/código Markdown.

    No intenta adivinar/completar llaves, valores u horas ausentes: la
    validación académica posterior sigue siendo obligatoria.
    """
    texto=str(texto or '').strip().lstrip('\ufeff').strip()
    if not texto:
        raise ValueError('respuesta vacía')
    texto=re.sub(r'^```(?:json)?\s*', '', texto, flags=re.I)
    texto=re.sub(r'\s*```\s*$', '', texto)
    try:
        datos=json.loads(texto)
    except json.JSONDecodeError as original:
        # Recuperar un JSON completo aunque Gemini haya escrito una frase
        # antes o después. NUNCA rescatar un objeto truncado o inválido.
        donde=texto.find('{')
        if donde<0:
            raise ValueError('no contiene un objeto JSON') from original
        try:
            datos,despues=json.JSONDecoder().raw_decode(texto[donde:])
        except json.JSONDecodeError as exc:
            if ('Unterminated' in str(exc) or 'Expecting' in str(exc)):
                raise ValueError('JSON incompleto o con sintaxis incorrecta') from exc
            raise ValueError('JSON no interpretable') from exc
        # Si hay más de un objeto en la respuesta, no usar uno arbitrariamente.
        cola=texto[donde+despues:].strip()
        if cola.startswith('{') or cola.startswith('['):
            raise ValueError('la respuesta contiene varios objetos JSON')
    if not isinstance(datos,dict):
        raise ValueError('Gemini no devolvió un objeto JSON')
    return datos


def motivo_fin_gemini(respuesta):
    """Lee de forma defensiva el motivo de término sin registrar datos de API."""
    try:
        cands=getattr(respuesta,'candidates',None) or []
        motivo=getattr(cands[0],'finish_reason',None) if cands else None
        return str(getattr(motivo,'name',motivo) or '')
    except (IndexError,TypeError,AttributeError):
        return ''


def guardar_json_atomico(ruta, datos):
    """No deja archivos JSON parcialmente escritos al interrumpirse el programa."""
    temporal = ruta.with_suffix(ruta.suffix + '.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    temporal.replace(ruta)


def criterios_pendientes_reparables(datos, horas, total):
    """Identifica únicamente criterios ausentes cuando TODO lo demás valida.

    Los textos provisionales solo existen en memoria para comprobar el resto;
    nunca pasan a un Word ni se guardan en la caché definitiva.
    """
    if not isinstance(datos,dict):
        return []
    unidades=datos.get('unidades')
    if not isinstance(unidades,list):
        return []
    copia=copy.deepcopy(datos)
    pendientes=[]
    for indice, unidad in enumerate(copia['unidades'],1):
        if not isinstance(unidad,dict):return []
        evaluacion=unidad.get('evaluacion')
        if not isinstance(evaluacion,dict):return []
        criterios=evaluacion.get('criterios',[])
        if not isinstance(criterios,list) or len([x for x in criterios if isinstance(x,str) and x.strip()])<2:
            pendientes.append(indice)
            evaluacion['criterios']=['[POR COMPLETAR]', '[POR COMPLETAR]']
    if not pendientes:return []
    # Rechazar el rescate si, además de los criterios, faltan horas, actividades, etc.
    validator(copia,horas,total)
    return pendientes


def aplicar_criterios_corregidos(datos, respuesta, pendientes, horas, total):
    """Incorpora solamente criterios; nunca reemplaza unidades ya generadas."""
    if not isinstance(respuesta,dict):raise ValueError('La corrección no es un objeto JSON')
    actualizaciones=respuesta.get('unidades')
    if len(pendientes)==1 and 'criterios' in respuesta:
        actualizaciones=[{'indice':pendientes[0],'criterios':respuesta['criterios']}]
    if not isinstance(actualizaciones,list):raise ValueError('No hay lista de criterios corregidos')
    propuestas={}
    for elemento in actualizaciones:
        if not isinstance(elemento,dict):continue
        try:indice=int(elemento.get('indice'))
        except (ValueError,TypeError):continue
        criterios=elemento.get('criterios',[])
        if (indice in pendientes and isinstance(criterios,list) and
                len(criterios)>=2 and all(isinstance(c,str) and len(c.strip())>=20 for c in criterios)):
            propuestas[indice]=criterios
    if any(i not in propuestas for i in pendientes):
        raise ValueError('Faltan criterios específicos para una o más unidades')
    corregido=copy.deepcopy(datos)
    for indice,criterios in propuestas.items():
        corregido['unidades'][indice-1]['evaluacion']['criterios']=criterios
    validator(corregido,horas,total)
    return corregido


def construir_prompt_gemini(curso,base):
    """Construye EXACTAMENTE el texto que el motor enviará a Gemini, sin hacer llamadas ni exponer claves."""
    ap=2 if curso["duracion"]>=40 else 1
    cierre=ap
    perfil=curso.get('docente') or {}
    especialidad=str(curso.get('especialidad_programada') or perfil.get('especialidad') or 'especialidad no especificada')
    ejemplo=json.loads((base/DEMO).read_text(encoding='utf-8'))
    def esquema_vacio(v):
        if isinstance(v,dict):return {k:esquema_vacio(x) for k,x in v.items()}
        if isinstance(v,list):return [esquema_vacio(v[0])] if v else []
        if isinstance(v,(int,float)):return 2
        return 'TEXTO A GENERAR SEGÚN EL CURSO'
    esquema={k:esquema_vacio(v) for k,v in ejemplo.items()}
    # Claves existentes del motor y de las CINCO celdas de recursos del Word.
    esquema['recursos']={'equipo':'Requerimientos con cantidades y especificaciones',
                         'herramientas':'Herramientas o software específico con cantidades',
                         'materiales':'Consumibles y materiales por grupo o participante',
                         'apoyo':'Material de apoyo: ... Mobiliario: ...',
                         'conectividad':'Conexión necesaria y finalidad técnica'}
    esquema['referencias']={'bibliografica':['Cita académica completa pertinente'], 'hemerografica':[], 'cibergrafica':['Autor. (año). Título. URL institucional verificable']}
    prompt=(f'Eres especialista curricular DGCFT. Elabora contenido académico integral de PEA para {curso["nombre"]}, '
        f'{curso["tipo"]}, {curso["duracion"]:g} horas presenciales, especialidad {especialidad}. '
        f'La apertura cuenta {ap} horas y el cierre {cierre} horas. '
        f'POBLACIÓN PROGRAMADA: {curso.get("poblacion") or "sin cifra"}; las cantidades son REQUISITOS PROPUESTOS y no inventario existente. '
        f'OBJETIVO EXACTO 20/80 (criterio operativo del plantel): mediación TOTAL {curso["duracion"]*.2:g} h, que incluye apertura y cierre; unidades mediación {curso["duracion"]*.2-ap-cierre:g} h y unidades práctica {curso["duracion"]*.8:g} h. '
        'El PEA no implica validación ni firma; no inventes normalización, inventario ni bibliografía. '
        'Proporciona de 3 a 6 unidades adecuadas a la complejidad del curso y duración. '
        f'En todas las unidades la suma de mediacion_horas+practica_horas debe ser {curso["duracion"]-ap-cierre:g}. '
        'REQUISITO OBLIGATORIO DE EXTENSIÓN: la justificacion tiene entre 200 y 400 palabras, describe la problemática, necesidad concreta de capacitación, tendencias/u oportunidades, destinatarios y beneficios académicos/laborales específicos. JAMÁS escribas NO APLICA en la justificación. El objetivo_general inicia con UN verbo de acción en INFINITIVO y articula objeto, condición técnica/procedimiento, y finalidad; al menos 110 caracteres. La competencia inicia con verbo de tercera persona del presente, explica desempeño integrador, condiciones y finalidad, distinta del objetivo. Los resultados_aprendizaje son al menos 3 actuaciones observables, separadas y específicas; cada elemento comienza con un verbo en infinitivo e indica objeto y condiciones para valorar evidencias, al menos 40 caracteres. Cumple Tema 2: máximo dos competencias. Saberes teóricos, procedimentales y axiológicos. Secuencias de apertura diagnóstica/contextualización, desarrollo con teorización, ejercitación y reflexión, cierre con evaluación sumativa. Las actividades requieren teorización, ejercitación y reflexión, cada una por docente y estudiante; '
        'seis descripciones originales, específicas de 2-4 oraciones con procedimiento, equipo, evidencia. '
        'Cada unidad precisa 3 criterios de evaluación observables, tipo (Autoevaluación/Coevaluación/Heteroevaluación), instrumento y evidencia. Asigna horas temáticas no redundantes (mediación + práctica) cuya suma sea EXACTA. Cada unidad debe tener un TOTAL DE HORAS ENTERAS (mediación+práctica) y al menos tantas horas como subtemas, de modo que TODOS los subtemas se distribuyan en horas COMPLETAS, nunca 0.5 o 1.5 horas; 20/80 global sigue vigente aunque las horas de mediación y práctica individuales requieran decimales. Contenido específico no genérico. '
        'Cada título de unidad en formato UNIDAD N. TÍTULO, independiente de temas; '
        'temas numerados 1.1, 1.2 etc. No incluyas CURP, nombres, firmas ni teléfonos. '
        'En actividades_extracurriculares propone como mínimo UNA actividad institucional transversal cívica, social, cultural o deportiva (por ejemplo honores a la bandera, periódico mural, campañas de bienestar, ferias o actividades comunitarias) Y UNA acción vinculada con las competencias del curso. Distingue claramente propuestas de actividades oficialmente calendarizadas: NO inventes fechas, participación confirmada ni compromisos del plantel. Vincula con responsabilidad social, cuidado corporal y bienestar socioemocional. '
        'No introduzcas horas independientes computables si la duración ya está ocupada por sesiones. Incluye los cinco rubros de recursos con herramientas ESPECÍFICAS de este curso y cantidades requeridas cuando proceda, sin asegurar inventario del plantel. En referencias elige obras y sitios reales adecuados al curso: autor, título, año, editorial o URL. Diferencia bibliográfica, hemerográfica (artículos de revista) y cibergráfica (sitios web). Jamás inventes referencias ni URLs: si no sabes una fuente usa lista vacía (el programa exigirá una fuente comprobada antes de emitir). No asignes bibliografía de Informática a otros cursos. '
        'Responde SOLO un objeto JSON con el mismo esquema de claves que sigue, sin copiar su temática: '
        +json.dumps(esquema,ensure_ascii=False))
    # Instrucciones académicas centralizadas, visibles y editables (no incluyen datos personales).
    # Este archivo NO es un certificado de autoridad, sino una pauta de calidad.
    ruta_maestra=base/'PROMPT_MAESTRO_PEA_EXTENSION.txt'
    if ruta_maestra.is_file():
        pautas=ruta_maestra.read_text(encoding='utf-8-sig').strip()
        if pautas:
            prompt=pautas+'\n\nDATOS DEL CURSO Y ESQUEMA DE SALIDA (OBLIGATORIOS):\n'+prompt
    return prompt


def contenido_ia(curso,base,modo):
    cachedir=base/'cache_ia';cachedir.mkdir(exist_ok=True)
    sello='|'.join(str(curso.get(k,'')) for k in ('hoja','fila','nombre','tipo','duracion','inicio','fin'))
    # Una modificación del prompt obliga a generar una caché NUEVA, sin eliminar la anterior.
    pm=base/'PROMPT_MAESTRO_PEA_EXTENSION.txt'
    if pm.is_file():sello+='|qa-v7|'+hashlib.sha256(pm.read_bytes()).hexdigest()[:12]
    huella=hashlib.sha256(sello.encode('utf-8')).hexdigest()[:10]
    identificador=f'{normal(curso["hoja"]).replace(" ","_")}_F{curso["fila"]}_{int(curso["duracion"])}h_{huella}'
    ruta=cachedir/(identificador+'.json')
    pendiente=cachedir/(identificador+'.pendiente.json')
    ap=2 if curso['duracion']>=40 else 1
    cierre=ap
    horas={'apertura':ap,'cierre':cierre}
    if modo=='demo':
        demo=base/DEMO
        if not demo.is_file():raise FileNotFoundError('Falta '+DEMO)
        if normal(curso['nombre'])!='informatica basica' or int(curso['duracion'])!=60:
            raise ValueError('La prueba local solo contiene INFORMÁTICA BÁSICA (60 h), no otro curso.')
        return json.loads(demo.read_text(encoding='utf-8'))
    if modo=='cache':
        if not ruta.is_file():raise FileNotFoundError('No hay JSON revisado para este curso: '+ruta.name)
        return json.loads(ruta.read_text(encoding='utf-8'))
    if modo=='gemini' and ruta.is_file():
        try:
            existente=json.loads(ruta.read_text(encoding='utf-8'))
            validator(existente,horas,curso['duracion'])
            qa_v7.validar_o_rechazar(existente,curso,horas)
            refs=referencias_efectivas(curso,base,existente)
            if not refs['bibliografica'] or not refs['cibergrafica']:
                raise ValueError('La caché carece de referencias bibliográficas o cibergráficas.')
            print('  Contenido académico válido encontrado en caché; no se consulta Gemini.')
            return existente
        except (ValueError,TypeError,KeyError,UnicodeError,AttributeError):
            print('  Caché incompleta o desactualizada: se solicitará contenido nuevo.')

    api=os.getenv('GEMINI_API_KEY','').strip()
    if not api:raise RuntimeError('Falta GEMINI_API_KEY; configura la clave en el panel o variable de entorno de Cloud Shell.')
    from google import genai
    prompt=construir_prompt_gemini(curso,base)
    cliente=genai.Client(api_key=api)
    modelo=os.getenv('GEMINI_MODELO','gemini-flash-latest').strip()
    configuracion={'response_mime_type':'application/json', 'temperature':0.25}
    try:max_intentos=min(8,max(1,int(os.getenv('GEMINI_MAX_INTENTOS','6'))))
    except ValueError:max_intentos=6
    ultima_causa='sin respuesta válida'
    errores_temporales=0
    errores_estructura=0
    parcial=None
    faltantes=[]
    # Un JSON académico pendiente puede reanudarse sin volver a generar TODO.
    if pendiente.is_file():
        try:
            candidato=json.loads(pendiente.read_text(encoding='utf-8'))
            indices=criterios_pendientes_reparables(candidato,horas,curso['duracion'])
            if indices:
                parcial=candidato;faltantes=indices
                print('  Recuperé contenido académico parcial de un intento anterior.',flush=True)
                print('  Solo pediré los criterios de evaluación faltantes; NO es un PEA terminado.',flush=True)
            else:
                print('  El archivo pendiente ya no es reparable; solicitaré contenido nuevo.',flush=True)
        except (ValueError,TypeError,KeyError,UnicodeError,AttributeError):
            print('  El contenido pendiente no pasó controles; solicitaré contenido nuevo.',flush=True)

    def prompt_criterios(datos, indices):
        descripciones=[]
        for indice in indices:
            uni=datos['unidades'][indice-1]
            desc={'indice':indice, 'titulo':uni.get('titulo',''), 'temas':uni.get('temas',[]),
                  'evidencia':uni.get('evaluacion',{}).get('evidencia',''),
                  'instrumento':uni.get('evaluacion',{}).get('instrumento','')}
            descripciones.append(desc)
        return ('Completa EXCLUSIVAMENTE los criterios faltantes de evaluación para este BORRADOR académico. '
                'No redactes un PEA nuevo. Para cada unidad devuelve 3 criterios concretos, observables y '
                'verificables, al menos 20 caracteres cada uno, vinculados a las evidencias y subtemas. '
                'Responde exclusivamente JSON con la forma '
                '{"unidades":[{"indice":1,"criterios":["criterio 1","criterio 2","criterio 3"]}]}. '
                'Devuelve cada indice solicitado UNA sola vez. Curso: '
                +curso['nombre']+'. Datos sin información personal: '
                +json.dumps(descripciones,ensure_ascii=False))

    for intento in range(1,max_intentos+1):
        reparando=parcial is not None and bool(faltantes)
        prompt_actual=prompt_criterios(parcial,faltantes) if reparando else prompt
        accion='REPARAR criterios pendientes' if reparando else 'generar contenido académico'
        if not reparando and errores_estructura:
            prompt_actual += ('\nIMPORTANTE: ya hubo una respuesta incorrecta. '
                  'Responde SOLO UN objeto JSON completo, con 3 a 4 unidades, seis actividades '
                  'específicas por unidad, evaluacion.criterios como LISTA de 3 frases, '
                  'sin prefacios ni texto de Markdown. Comprueba todas las horas.')
        print(f'  Consultando Gemini (intento {intento}/{max_intentos}, {accion}, modelo {modelo})...',flush=True)
        try:
            resp=cliente.models.generate_content(model=modelo,contents=prompt_actual,config=configuracion)
        except Exception as exc:
            codigo=str(getattr(exc,'code','') or getattr(exc,'status_code',''))
            mensaje=str(exc)
            temporal=codigo in ('429','503') or bool(re.search(r'\b(?:429|503|UNAVAILABLE|RESOURCE_EXHAUSTED)\b',mensaje,re.I))
            if not temporal:raise
            # Una cuota diaria agotada no se resuelve insistiendo cada pocos segundos.
            cuota_agotada=(('429' in codigo or bool(re.search(r'\b429\b',mensaje)))
                           and bool(re.search(r'quota exceeded|daily|per day|billing|insufficient quota',mensaje,re.I)))
            if cuota_agotada:
                raise RuntimeError('Gemini indicó límite de cuota (429). No se seguirán haciendo solicitudes. '
                                   'Revisa la cuota de tu proyecto y reanuda cuando se restablezca. '
                                   'El contenido parcial, si existe, queda pendiente para repararlo.') from None
            errores_temporales+=1
            ultima_causa=f'Gemini ocupado (429/503): error temporal {errores_temporales}'
            if intento>=max_intentos:break
            espera=(10,30,60,60,60,60,60)[min(errores_temporales-1,6)]
            print(f'  Gemini ocupado (429/503). Esperaré {espera} segundos...',flush=True)
            time.sleep(espera)
            continue
        try:
            respuesta=recuperar_objeto_json(getattr(resp,'text',None) or '')
            if reparando:
                final=aplicar_criterios_corregidos(parcial,respuesta,faltantes,horas,curso['duracion'])
            else:
                try:
                    validator(respuesta,horas,curso['duracion'])
                    final=respuesta
                except (ValueError,TypeError,KeyError,AttributeError):
                    indices=criterios_pendientes_reparables(respuesta,horas,curso['duracion'])
                    if not indices:raise
                    parcial=respuesta;faltantes=indices
                    guardar_json_atomico(pendiente,parcial)
                    ultima_causa=f'Faltan criterios evaluables en unidad(es): {", ".join(map(str,indices))}'
                    print(f'  {ultima_causa}.',flush=True)
                    print('  Guardé una copia PARCIAL para solicitar solo los criterios faltantes.',flush=True)
                    continue
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            errores_estructura+=1
            ultima_causa=str(exc).replace('\n',' ')[:200]
            motivo=motivo_fin_gemini(resp)
            if motivo and ('MAX_TOKENS' in motivo or 'LENGTH' in motivo):
                ultima_causa='Respuesta incompleta por límite de longitud ('+motivo+')'
            print(f'  Gemini devolvió datos incompletos: {ultima_causa}',flush=True)
            if intento<max_intentos:
                print('  Reintentaré sin descartar los datos académicos recuperables.',flush=True)
                time.sleep(2)
            continue
        # Control adicional de 5 ejes académicos. Un contenido insuficiente
        # NO pasa a caché definitiva ni a Word.
        try:
            qa_v7.validar_o_rechazar(final,curso,horas)
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            errores_estructura+=1
            ultima_causa=str(exc).replace('\n',' ')[:350]
            print('  Revisión académica v7: '+ultima_causa,flush=True)
            continue
        # Validar también que la IA proporcione fuentes si no hay catálogo
        # curado. Las listas vacías no se consideran bibliografía completa.
        refs=referencias_efectivas(curso,base,final)
        if not refs['bibliografica'] or not refs['cibergrafica']:
            ultima_causa='Faltan referencias bibliográficas y/o cibergráficas para este curso.'
            errores_estructura+=1
            print('  '+ultima_causa+' Solicitaré fuentes identificables y pertinentes.',flush=True)
            continue
        # ÚNICAMENTE un objeto validado llega a la caché definitiva.
        guardar_json_atomico(ruta,final)
        if pendiente.exists():pendiente.unlink()
        print('  JSON académico COMPLETO: unidades, criterios y horas validados.',flush=True)
        print('  Contenido válido guardado en caché para evitar consultas repetidas.',flush=True)
        return final

    if parcial is not None:
        raise RuntimeError('Gemini no pudo completar los criterios de evaluación. '
                           'Conservé un JSON PARCIAL (no autorizado) para reanudar la corrección '
                           'en el próximo intento, sin regenerar todo. '
                           'No se creó un PEA nuevo. Último problema: '+ultima_causa)
    raise RuntimeError('Gemini no proporcionó contenido académico completo después de '
                       f'{max_intentos} intentos. No se creó un PEA nuevo. '
                       'Puedes reintentar más tarde sin cambiar la clave. Último problema: '+ultima_causa)

def set_cell(cell,lines, size=8, titles=(), centrar=False):
    """Modifica SOLO celdas de contenido, preservando tcPr (fusión, bordes y anchos)."""
    tc=cell._tc
    oldp=next((p for p in cell.paragraphs if p.text.strip()),cell.paragraphs[0] if cell.paragraphs else None)
    ppr=copy.deepcopy(oldp._p.pPr) if oldp and oldp._p.pPr is not None else None
    for ch in list(tc):
        if ch.tag!=W('tcPr'):tc.remove(ch)
    if isinstance(lines,str):lines=[lines]
    for k,line in enumerate(lines):
        if line is None:continue
        p=OxmlElement('w:p')
        if ppr is not None:
            pp=copy.deepcopy(ppr)
            # Normalizar espacios SOLO dentro de contenido generado, no en encabezados.
            for old in list(pp):
                if old.tag == W('spacing'):pp.remove(old)
            spacing=OxmlElement('w:spacing')
            for name,value in (('before','0'),('after','0'),('line','230'),('lineRule','auto')):
                spacing.set(W(name),value)
            pp.append(spacing)
            if centrar:
                for anc in list(pp):
                    if anc.tag == W('jc'): pp.remove(anc)
                jc=OxmlElement('w:jc');jc.set(W('val'),'center');pp.append(jc)
            p.append(pp)
        elif centrar:
            pp=OxmlElement('w:pPr');jc=OxmlElement('w:jc');jc.set(W('val'),'center');pp.append(jc);p.append(pp)
        rp=OxmlElement('w:r');properties=OxmlElement('w:rPr')
        fonts=OxmlElement('w:rFonts');fonts.set(W('ascii'),'Montserrat');fonts.set(W('hAnsi'),'Montserrat');properties.append(fonts)
        sz=OxmlElement('w:sz');sz.set(W('val'),str(round(size*2)));properties.append(sz)
        if k in titles:properties.append(OxmlElement('w:b'))
        rp.append(properties);t=OxmlElement('w:t');t.text=str(line);rp.append(t);p.append(rp);tc.append(p)
    if len(tc)==(1 if tc.tcPr is not None else 0):tc.append(OxmlElement('w:p'))


def assert_plantilla(doc):
    """Comprobar ESTRUCTURA, no asumir que los nombres o firmas son iguales a la plantilla escolar."""
    t=doc.tables
    if len(t)!=28:
        raise ValueError(f'Plantilla de casa: se esperaban 28 tablas, se encontraron {len(t)}')
    configuracion={21:7,22:5,23:4,24:2,25:6,26:3,27:3}
    for i,filas in configuracion.items():
        if len(t[i].rows)!=filas:
            raise ValueError(f'Cambio de estructura en tabla {i+1}: {filas} filas esperadas, {len(t[i].rows)} encontradas')
    comprobaciones=((20,0,0,'1.1'),(21,0,0,'SECUENCIA DIDÁCTICA'),
                    (22,0,0,'SECUENCIA DIDÁCTICA'),(23,3,0,'Cierre del curso'),
                    (24,0,0,'ACCIONES FORMATIVAS'),(25,0,0,'Recursos Didácticos'),
                    (26,0,0,'Elabora'),(27,0,2,'Autoriza'))
    for n,r,c,clave in comprobaciones:
        if normal(clave) not in normal(t[n].cell(r,c).text):
            raise ValueError(f'No se reconoce el campo {clave} en tabla {n+1}')
    if len(t[12]._tbl.xpath('.//w:sdt'))!=2:
        raise ValueError('No se encontraron los dos controles de fecha de inicio/término')
    fila=t[14]._tbl.tr_lst[1]
    if len([x for x in fila if x.tag==W('sdt')])!=3:
        raise ValueError('Cambió la fila de datos de docente (controles Word)')
    if not t[26].cell(1,2).text.strip() or not t[26].cell(1,4).text.strip():
        raise ValueError('No hay nombres en las áreas de Valida y Visto Bueno')


def actualizar_sdt(sdt, texto, centrar=False, tamano=None):
    """Escribir en un control Word, preservando su celda contenedora y formato básico."""
    contenido=sdt.find(W('sdtContent'))
    if contenido is None:raise ValueError('Control de Word sin contenido')
    nodos=list(contenido.iter(W('t')))
    if not nodos:raise ValueError('Control de Word sin texto editable')
    nodos[0].text=str(texto)
    for n in nodos[1:]:n.text=''
    if centrar or tamano is not None:
        for p in contenido.iter(W('p')):
            pp=p.find(W('pPr'))
            if pp is None: pp=OxmlElement('w:pPr');p.insert(0,pp)
            if centrar:
                for old in list(pp):
                    if old.tag==W('jc'):pp.remove(old)
                jc=OxmlElement('w:jc');jc.set(W('val'),'center');pp.append(jc)
        for r in contenido.iter(W('r')):
            rp=r.find(W('rPr'))
            if rp is None: rp=OxmlElement('w:rPr');r.insert(0,rp)
            ff=rp.find(W('rFonts'))
            if ff is None:ff=OxmlElement('w:rFonts');rp.insert(0,ff)
            for campo in ('ascii','hAnsi','eastAsia','cs'):
                ff.set(W(campo),'Montserrat')
            if tamano is not None:
                for campo in ('sz','szCs'):
                    sz=rp.find(W(campo))
                    if sz is None:sz=OxmlElement('w:'+campo);rp.append(sz)
                    sz.set(W('val'),str(round(tamano*2)))


def avisos_institucionales(doc):
    t=doc.tables
    cecati=' '.join(x.text for x in t[5]._tbl.xpath('./w:tr/w:sdt[1]//w:t') if x.text).strip()
    valida=t[26].cell(1,2).text.strip()
    visto=t[26].cell(1,4).text.strip()
    autoriza=t[27].cell(1,2).text.strip()
    return {'plantel':cecati,'valida':valida,'visto':visto,'autoriza':autoriza}


def colocar_autoridades_confirmadas(doc):
    """Actualizar únicamente los tres NOMBRES de validación en cada borrador.

    Mantiene posiciones, cargos, cuatro renglones para firmas y sus estilos.
    No inserta ni replica firmas manuscritas o imágenes de funcionarios.
    """
    celdas = ((26,2,AUTORIDAD_VALIDA),(26,4,AUTORIDAD_VISTO),
              (27,2,AUTORIDAD_AUTORIZA))
    for indice,columna,nombre in celdas:
        celda=doc.tables[indice].cell(1,columna)
        p=celda.paragraphs[-1]
        p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        if p.runs:
            p.runs[0].text=nombre
            for run in p.runs[1:]:run.text=''
        else:
            r=p.add_run(nombre)
            r.font.name='Montserrat'
            r.font.size=Pt(12)
        if indice==27:
            for run in p.runs:
                run.font.size=Pt(12)
        
    # Completar la referencia estatal en el cargo del Subdirector.
    cargo=doc.tables[27].cell(2,2).paragraphs[0]
    for run in cargo.runs:
        if '(anotar el nombre)' in normal(run.text):
            run.text=run.text.replace('(anotar el nombre)','Veracruz')
            run.font.name='Montserrat'
            run.font.size=Pt(12)
            run.font.color.rgb=RGBColor(0,0,0)
            run.font.italic=False
    nombres=avisos_institucionales(doc)
    if any(normal(nombres[clave]) != normal(esperado) for clave,esperado in
           (('valida',AUTORIDAD_VALIDA),('visto',AUTORIDAD_VISTO),('autoriza',AUTORIDAD_AUTORIZA))):
        raise ValueError('No pudieron actualizarse correctamente los nombres de validación.')


def para_texto(doc,texto_nuevo,criterio):
    for p in doc.paragraphs:
        if criterio(normal(p.text)):
            if p.runs:
                p.runs[0].text=texto_nuevo
                for run in p.runs[1:]:run.text=''
            else:p.add_run(texto_nuevo)
            return True
    return False


def actualizar_lista_desplegable(sdt, valor):
    """Selecciona un valor existente SIN perder la lista desplegable de Word."""
    pr=sdt.find(W('sdtPr'))
    ddl=pr.find(W('dropDownList')) if pr is not None else None
    if ddl is None:raise ValueError('La especialidad dejó de ser una lista desplegable Word')
    items=[n.get(W('displayText')) or n.get(W('value')) or '' for n in list(ddl)]
    canon=lambda s:re.sub(r'\s*[-–—]\s*','-',normal(s))
    coincidencia=next((v for v in items if canon(v)==canon(valor)),None)
    if coincidencia is None:
        # No insertar un valor fuera de la oferta autorizada. Conservar la lista
        # para edición directa de quien revisa; registrar incidencia solo en TXT.
        return False
    actualizar_sdt(sdt,coincidencia)
    mostrar=pr.find(W('showingPlcHdr'))
    if mostrar is not None:pr.remove(mostrar)
    return True


def casilla_real(etiqueta,activo,indice):
    """Control de Word editable con aspecto de botón circular (●/○).

    Word no ofrece un grupo de radio exclusivo mediante SDT nativo; los
    controles siguen siendo pulsables individualmente. Se preselecciona
    una opción por grupo y el usuario puede corregirla en Word.
    """
    sdt=OxmlElement('w:sdt'); pr=OxmlElement('w:sdtPr')
    alias=OxmlElement('w:alias');alias.set(W('val'),etiqueta);pr.append(alias)
    tag=OxmlElement('w:tag');tag.set(W('val'),'CECATI31_OPCION_'+str(indice));pr.append(tag)
    wid=OxmlElement('w:id');wid.set(W('val'),str(950000+indice));pr.append(wid)
    chk=OxmlElement('w14:checkbox')
    estado=OxmlElement('w14:checked');estado.set(qn('w14:val'),'1' if activo else '0');chk.append(estado)
    for nom,codigo in (('checkedState','25C9'),('uncheckedState','25CB')):
        e=OxmlElement('w14:'+nom)
        e.set(qn('w14:val'),codigo);e.set(qn('w14:font'),'Segoe UI Symbol')
        chk.append(e)
    pr.append(chk);sdt.append(pr)
    content=OxmlElement('w:sdtContent');rr=OxmlElement('w:r')
    rpr=OxmlElement('w:rPr');f=OxmlElement('w:rFonts')
    f.set(W('ascii'),'Segoe UI Symbol');f.set(W('hAnsi'),'Segoe UI Symbol');rpr.append(f)
    size=OxmlElement('w:sz');size.set(W('val'),'18');rpr.append(size)
    rr.append(rpr);t=OxmlElement('w:t');t.text='◉' if activo else '○';rr.append(t)
    content.append(rr);sdt.append(content)
    return sdt


def opciones_en_celda(celda, etiqueta, activo, indice):
    """Preserva contenedor, borde y medidas de la celda, con casilla Word real."""
    tc=celda._tc
    for p in list(tc):
        if p.tag!=W('tcPr'):tc.remove(p)
    p=OxmlElement('w:p')
    propiedades=OxmlElement('w:pPr');jc=OxmlElement('w:jc');jc.set(W('val'),'center')
    propiedades.append(jc);p.append(propiedades)
    p.append(casilla_real(etiqueta,activo,indice))
    run=OxmlElement('w:r');rpr=OxmlElement('w:rPr')
    tam=OxmlElement('w:sz');tam.set(W('val'),'18');rpr.append(tam);run.append(rpr)
    tx=OxmlElement('w:t');tx.text=' '+etiqueta;tx.set(qn('xml:space'),'preserve')
    run.append(tx);p.append(run);tc.append(p)


def grupo_en_tabla(tab, opciones,seleccionado,identificador):
    """Deja casillas nativas de Word EDITABLES y preselecciona según Excel/config."""
    for i,(fila,col,etiqueta) in enumerate(opciones,1):
        opciones_en_celda(tab.cell(fila,col),etiqueta,
                          normal(etiqueta)==normal(seleccionado),identificador*100+i)


def seleccionar_docente_word(doc, tipo):
    # La plantilla original trae ActiveX. Se transforman en w14:checkbox reales.
    p=next((p for i,p in enumerate(doc.paragraphs[:-1])
            if 'tipo de docente' in normal(p.text)),None)
    if p is None:raise ValueError('No se encontró TIPO DE DOCENTE')
    siguiente=p._p.getnext()
    while siguiente is not None and siguiente.tag!=W('p'):
        siguiente=siguiente.getnext()
    if siguiente is None:raise ValueError('No se encontró el apartado de docente')
    for ch in list(siguiente):
        if ch.tag!=W('pPr'):siguiente.remove(ch)
    for i,l in enumerate(('INTERNO','EXTERNO')):
        siguiente.append(casilla_real(l,normal(tipo)==normal(l),950+i))
        rr=OxmlElement('w:r');tt=OxmlElement('w:t');tt.text=' '+l+'      ';tt.set(qn('xml:space'),'preserve')
        rr.append(tt);siguiente.append(rr)


def recursos_sugeridos(datos, especialidad):
    """Lista de recursos sugeridos, no declaración de inventario existente."""
    s=normal(especialidad)
    if 'informatica' in s or 'tecnologias de la informacion' in s:
        base={'equipo':'Computadora por participante y equipo del docente; proyector para demostraciones.',
              'herramientas':'Sistema operativo, procesador de textos y hoja de cálculo para prácticas.',
              'materiales':'Archivos digitales de práctica y carpeta electrónica de evidencias.',
              'apoyo':'Guías paso a paso, ejercicios y rúbricas de desempeño.',
              'conectividad':'Acceso a Internet para prácticas que lo requieran.'}
    elif 'administracion' in s:
        base={'equipo':'Computadora del docente y equipos de práctica cuando el curso lo requiera.',
              'herramientas':'Hoja de cálculo y formatos de control administrativo.',
              'materiales':'Casos prácticos, formatos de cálculo y documentos de trabajo.',
              'apoyo':'Guías de ejercicios, listas de cotejo y rúbricas.',
              'conectividad':'Conexión a Internet para consultar plataformas o documentación, si aplica.'}
    else:
        base={'equipo':'Equipo técnico adecuado a las prácticas previstas en el curso.',
              'herramientas':'Herramientas y aplicaciones propias de la especialidad.',
              'materiales':'Insumos y materiales de práctica vinculados con cada unidad.',
              'apoyo':'Guías de trabajo, ejercicios, listas de cotejo y rúbricas.',
              'conectividad':'Recursos digitales cuando la actividad los requiera.'}
    rec=datos.get('recursos') or {}
    resultado={k:str(rec.get(k) or v).strip() for k,v in base.items()}
    if isinstance(rec,dict) and all(str(rec.get(k) or '').strip() for k in base):
        resultado['_procedencia_ia']=True
    return resultado



def corregir_espacios(doc):
    # Retirar saltos de página manuales solamente si NO son un salto estructural
    # de sección o título. Nunca borrar saltos automáticos de Word.
    for i in (23,24):
        tab=doc.tables[i]._tbl
        pos=tab.getprevious()
        for _ in range(3):
            if pos is None:break
            if pos.tag==W('p') and not pos.xpath('.//w:t/text()'):
                for br in list(pos.xpath('.//w:br[@w:type="page"]')):
                    br.getparent().remove(br)
            pos=pos.getprevious()


def agregar_firma_docente(cell,ruta,permitido,confirmada):
    if not confirmada or normal(permitido) not in ('si','sí') or not ruta:return False
    ruta=str(ruta).strip().strip('"').strip("'")
    imagen=Path(ruta)
    if not imagen.exists() or imagen.suffix.lower() not in ('.png','.jpg','.jpeg'):
        raise FileNotFoundError('La imagen autorizada de la firma no existe: '+imagen.name)
    par=cell.paragraphs[0].insert_paragraph_before()
    par.alignment=WD_ALIGN_PARAGRAPH.CENTER
    par.add_run().add_picture(str(imagen),height=Inches(.36))
    return True


def listar_sdt_originales(doc):
    """Copias profundas de los desplegables reales de la plantilla oficial."""
    t=doc.tables
    def sdt_celda(tab,fila,col):
        return [copy.deepcopy(s) for s in t[tab].cell(fila,col)._tc.xpath('.//w:sdt')]
    evaluacion=sdt_celda(21,6,3)[:3]
    estrategia=sdt_celda(21,6,1)[:1]
    if len(evaluacion)!=3 or len(estrategia)!=1:
        raise ValueError('No se hallaron los desplegables originales de evaluación y estrategia didáctica.')
    return evaluacion, estrategia


def preparar_dropdown(sdt, valor):
    """Escoge un valor y CONSERVA todas las opciones por defecto de Word."""
    pr=sdt.find(W('sdtPr'));ddl=pr.find(W('dropDownList')) if pr is not None else None
    if ddl is None:raise ValueError('Se perdió una lista desplegable original de Word.')
    opciones=[x.get(W('displayText')) or x.get(W('value')) or '' for x in list(ddl)]
    requested=str(valor or '').strip()
    # Coincidencia exacta primero; equivalencias académicas documentadas.
    wanted=normal(requested)
    actual=next((x for x in opciones if normal(x)==wanted),None)
    if actual is None:
        if 'diagnos' in wanted: base='Diagnóstica'
        elif 'sumativ' in wanted:base='Sumativa'
        elif 'formativ' in wanted:base='Formativa'
        elif 'auto' in wanted:base='Autoevaluación'
        elif 'coevalu' in wanted:base='Coevaluación'
        elif 'hetero' in wanted:base='Heteroevaluación '
        elif 'observacion' in wanted:base='Guía de observación'
        elif 'cotejo' in wanted:base='Lista de cotejo'
        elif 'cuestionario' in wanted:base='Cuestionario'
        elif 'modela' in wanted or 'demostr' in wanted:base='Demostración o Modelación'
        elif 'problema' in wanted:base='Basado en Problemas'
        elif 'proyecto' in wanted:base='Elaboración de Proyectos'
        elif 'caso' in wanted:base='Análisis de Casos'
        elif 'investig' in wanted:base='Investigación-Acción'
        elif 'prototipo' in wanted or 'innovacion' in wanted:base='Innovación o Creación de Prototipos'
        else:base=requested
        actual=next((x for x in opciones if normal(x)==normal(base)),None)
    if actual is None:
        # Agregar como opción específica, sin perder catálogo predeterminado.
        if not requested:requested='No especificado'
        item=OxmlElement('w:listItem');item.set(W('displayText'),requested);item.set(W('value'),requested)
        ddl.append(item);actual=requested
    actualizar_sdt(sdt,actual)
    # Los controles originales son de BLOQUE: w:sdtContent/w:p.
    # Al insertarlos dentro de un párrafo deben transformarse en controles
    # inline w:sdtContent/w:r; de lo contrario Word puede repararlos e
    # incluso LibreOffice omite por completo el texto seleccionado.
    content=sdt.find(W('sdtContent'))
    if content is not None and any(x.tag==W('p') for x in content):
        hijos=[]
        for par in list(content):
            if par.tag==W('p'):
                hijos.extend(copy.deepcopy(x) for x in list(par) if x.tag!=W('pPr'))
            else:hijos.append(copy.deepcopy(par))
        for x in list(content):content.remove(x)
        for x in hijos:content.append(x)
    mostrar=pr.find(W('showingPlcHdr'))
    if mostrar is not None:pr.remove(mostrar)
    # El sdt original recibe ID propio para no repetir identidad al clonarlo.
    id_elem=pr.find(W('id'))
    if id_elem is not None:
        preparar_dropdown.num+=1;id_elem.set(W('val'),str(600000+preparar_dropdown.num))
    return sdt
preparar_dropdown.num=0


def escribir_celda_con_desplegables(celda, plantillas, valores, textos, size=8):
    """Produce tres controles clicables (Evaluación, Tipo, Instrumento).
    Cada uno usa una copia del desplegable ORIGINAL de la plantilla.
    """
    set_cell(celda,['Evaluación:','Tipo:','Instrumento:']+list(textos),size,{0,1,2})
    for i,(base,valor) in enumerate(zip(plantillas,valores)):
        celda.paragraphs[i]._p.append(preparar_dropdown(copy.deepcopy(base),valor))


def escribir_estrategia_desplegable(celda,plantilla,valor):
    p=celda.paragraphs[0]
    # Después del prefijo 'Estrategia:' agregamos control real, seleccionable.
    p._p.append(preparar_dropdown(copy.deepcopy(plantilla),valor))


def centrar_firma_docente(doc, nombre, tamano=11):
    """Alinear exactamente en la fila común con Valida y Visto Bueno."""
    tab=doc.tables[26]
    for col,valor in ((0,nombre),(2,AUTORIDAD_VALIDA),(4,AUTORIDAD_VISTO)):
        celda=tab.cell(1,col)
        # En la fila de validación, los tres nombres se centran con misma fuente.
        ps=celda.paragraphs
        p=next((p for p in ps if normal(valor) in normal(p.text)),ps[-1])
        p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.name='Montserrat';run.font.size=Pt(tamano)
        p.paragraph_format.space_before=Pt(0)
        p.paragraph_format.space_after=Pt(0)


def crear_docx(curso, datos,base, salida, incluir_firma=False):
    if curso.get('tipo')!='Extensión': raise ValueError('Esta versión genera exclusivamente PEA de EXTENSIÓN.')
    doc=Document(base/PLANTILLA)
    assert_plantilla(doc)
    tab=doc.tables
    eval_plantillas, estrategia_plantilla = listar_sdt_originales(doc)
    perfil=curso.get('docente') or {}
    nombre_docente=str(perfil.get('nombre') or curso['hoja']).strip().upper()

    configuracion=cargar_configuracion(base)
    # La especialidad viene de la sección de la programación, incluso cuando no
    # haya ficha completa del docente en el padrón local.
    especialidad=str(curso.get('especialidad_programada') or perfil.get('especialidad') or '').strip()
    aula=normal(curso.get('aula') or '').upper()
    mapeo_sedes=configuracion.get('sede_por_aula') or {}
    sede=next((v for k,v in mapeo_sedes.items() if normal(k).upper()==aula),
              configuracion.get('sede_predeterminada','CECATI'))
    campo=next((v for k,v in (configuracion.get('campo_por_especialidad') or {}).items()
                if normal(k)==normal(especialidad)), '')

    # Usar 10 participantes como estándar institucional de este generador.
    curso=dict(curso,poblacion=int(curso['poblacion']))
    if curso['poblacion'] < 1: raise ValueError('Confirma participantes previstos: debe ser mayor que cero.')
    # Completar portada, sin borrar estilos/logotipos de la plantilla.
    para_texto(doc,curso['nombre'].upper(),lambda x:'(nombre del curso)' in x)
    para_texto(doc,'PARA IMPARTIR CURSO '+('DE EXTENSIÓN' if curso['tipo']=='Extensión' else 'REGULAR'),lambda x:'para impartir' in x)
    para_texto(doc,'',lambda x:'(seleccionar tipo de curso regular o de extension' in x)

    # Los controles ActiveX de las tablas originales se sustituyen en el PEA
    # por casillas modernas de contenido Word; son editables al revisar.
    grupo_en_tabla(tab[0],[(0,0,'PARA EL TRABAJO'),(0,1,'EN EL TRABAJO')],
                   configuracion.get('formacion','PARA EL TRABAJO'),10)
    grupo_en_tabla(tab[1],[(0,0,'PRESENCIAL'),(0,1,'SEMIPRESENCIAL'),(0,2,'VIRTUAL')],
                   configuracion.get('modalidad','PRESENCIAL'),11)
    grupo_en_tabla(tab[2],[(0,0,'CECATI'),(0,1,'UNIDAD MÓVIL'),(0,2,'INSTALACIONES DEL SECTOR')],
                   sede,12)
    grupo_en_tabla(tab[3],[(0,0,'REGULAR'),(0,1,'EXTENSIÓN')],curso['tipo'],13)
    grupo_en_tabla(tab[7],[(0,0,'PÚBLICO EN GENERAL'),(0,1,'EMPLEADO'),
                    (0,2,'DESEMPLEADO'),(0,3,'AUTOEMPLEADO'),(1,0,'ADULTO MAYOR'),
                    (1,1,'JUBILADO'),(1,2,'PERSONA CON DISCAPACIDAD'),(1,3,'OTRO'),
                    (2,0,'ESTUDIANTE DE INSTITUCIÓN EDUCATIVA'),
                    (2,2,'GRUPO EN DESVENTAJA SOCIAL Y/O ECONÓMICA')],
                   configuracion.get('usuario','PÚBLICO EN GENERAL'),14)
    seleccionar_docente_word(doc,perfil.get('tipo',''))
    # Curso asociado a normalización: marcarlo solo si así está configurado.
    # Asociación EC/NOM se establece por curso y solo desde registro institucional.
    set_cell(tab[4].cell(0,0),curso['nombre'].upper(),9)

    # El documento adjunto es del CECATI 151; generar el borrador de CECATI 31
    # SIN modificar el archivo original. Otros nombres de autoridades NO se cambian.
    campos_plantel=tab[5]._tbl.xpath('.//w:sdt')
    if len(campos_plantel)!=2:raise ValueError('Cambió control de plantel/entidad')
    actualizar_sdt(campos_plantel[0],'31')
    # La entidad Veracruz se conserva.

    set_cell(tab[10].cell(0,1),f'{curso["duracion"]:g} HORAS',10,centrar=True)
    h=horario_simple(curso['horario'])
    set_cell(tab[10].cell(0,3),h['horas'] if h and h['calculable'] else curso['horario'],10,centrar=True)
    set_cell(tab[11].cell(0,0),str(curso['poblacion'] if curso['poblacion'] is not None else ''),10,centrar=True)
    fechas_sdt=tab[12]._tbl.xpath('.//w:sdt')
    for sdt,val in zip(fechas_sdt,(curso['inicio'],curso['fin'])):
        actualizar_sdt(sdt,fecha(val).strftime('%d/%m/%Y') if fecha(val) else '',centrar=True,tamano=10)
    # Días completos exactamente como se registran en la programación
    set_cell(tab[12].rows[0].cells[3],curso['horario'],10,centrar=True)
    # El rótulo INICIO de la plantilla original es muy estrecho y se parte.
    # Reducir SOLO sus márgenes interiores: el texto y su tipografía NO cambian.
    primera=tab[12].rows[0].cells[0]
    propiedades_primera=primera._tc.get_or_add_tcPr()
    bordes_int=propiedades_primera.find(W('tcMar'))
    if bordes_int is None:
        bordes_int=OxmlElement('w:tcMar');propiedades_primera.append(bordes_int)
    for extremo in ('left','right'):
        margen=bordes_int.find(W(extremo))
        if margen is None:margen=OxmlElement('w:'+extremo);bordes_int.append(margen)
        margen.set(W('w'),'0');margen.set(W('type'),'dxa')
    for p in primera.paragraphs:p.alignment=WD_ALIGN_PARAGRAPH.CENTER

    # Conservar y seleccionar los dos desplegables originales de Word.
    especialidades_sdt=tab[8]._tbl.xpath('.//w:sdt')
    if len(especialidades_sdt)!=2:raise ValueError('No se encontraron listas de especialidad')
    if campo:actualizar_lista_desplegable(especialidades_sdt[0],campo)
    if especialidad:actualizar_lista_desplegable(especialidades_sdt[1],especialidad)
    skills=datos.get('habilidades_docente',{})
    for j,k in enumerate(('conocimientos','habilidades','actitudes')):
        set_cell(tab[13].cell(1,j),str(skills.get(k,'')).split('\n'),8)

    # Los controles de Word del docente son hijos de fila, NO celdas normales.
    fila_doc=tab[14]._tbl.tr_lst[1]
    controles=[x for x in fila_doc if x.tag==W('sdt')]
    actualizar_sdt(controles[0],nombre_docente,centrar=True,tamano=10)
    actualizar_sdt(controles[1],perfil.get('curp') or '',centrar=True,tamano=10)
    actualizar_sdt(controles[2],perfil.get('correo') or '',centrar=True,tamano=10)
    celdas=[x for x in fila_doc if x.tag==W('tc')]
    if len(celdas)!=2:raise ValueError('No se reconoce la celda de teléfono docente')
    from docx.table import _Cell
    set_cell(_Cell(celdas[0],tab[14]),str(perfil.get('telefono') or ''),10,centrar=True)

    set_cell(tab[16].cell(0,0),str(datos.get('justificacion','')).split('\n\n'),8.5)
    set_cell(tab[17].cell(0,0),str(datos.get('objetivo_general','')),8.8)
    comp=datos.get('competencia','')
    resultados=datos.get('resultados_aprendizaje',[])
    encabezado_resultados=(f'Al concluir el curso {curso["nombre"]}, el estudiante será capaz de:')
    set_cell(tab[18].cell(0,0),[comp,'RESULTADOS DE APRENDIZAJE ESPERADOS',encabezado_resultados]+resultados,8.2,{1})
    for j,k in enumerate(('saberes_teoricos','saberes_procedimentales','saberes_axiologicos')):
        set_cell(tab[19].cell(2,j),str(datos.get(k,'')).split('\n'),8)

    temario=[];negritas=set()
    # Propuesta didáctica automática: repartir las horas de CADA unidad entre
    # sus subtemas sin alterar la duración oficial. La misma cadena se usa
    # en punto 24 y columna de contenido de la secuencia didáctica.
    for u in datos['unidades']:
        temas=u.get('temas',[])
        if temas:
            totalh=float(u['mediacion_horas'])+float(u['practica_horas'])
            # Asignación íntegra, sin ocultar ni redondear horas oficiales.
            # Si la unidad no permite subtemas de horas enteras, requerir
            # que Gemini reorganice la unidad en vez de inventar un reparto.
            if abs(totalh-round(totalh))>0.00001 or round(totalh)<len(temas):
                raise ValueError('UNIDAD CON HORAS FRACCIONARIAS O INSUFICIENTES: '
                                 +str(u.get('titulo'))+' tiene '+f'{totalh:g} h para '
                                 +str(len(temas))+' subtemas. Regenerar distribución académica con horas enteras por subtema.')
            enteras=int(round(totalh))
            baseh,resto=divmod(enteras,len(temas))
            asignacion=[baseh+(1 if k<resto else 0) for k in range(len(temas))]
            assert sum(asignacion)==enteras and min(asignacion)>=1
            u['_temas_con_horas']=[f'{texto} — {horas:d} h' for texto,horas in zip(temas,asignacion)]
        else:u['_temas_con_horas']=[]
    for u in datos['unidades']:
        negritas.add(len(temario));temario.extend([u['titulo']+f' — {u["mediacion_horas"]+u["practica_horas"]:g} horas']+u['_temas_con_horas'])
    if curso['tipo']=='Regular':
        # El apartado 24 del formato se reserva expresamente a cursos de extensión.
        set_cell(tab[20].cell(0,0),'NO APLICA — CONTENIDO TEMÁTICO EXCLUSIVO DE EXTENSIÓN',8.1)
    else:
        set_cell(tab[20].cell(0,0),temario,7.6,negritas)
    from docx.shared import Twips
    ctemas=tab[20].cell(0,0)
    for i,p in enumerate(ctemas.paragraphs):
        p.paragraph_format.left_indent=Twips(180 if i in negritas else 360)
        p.paragraph_format.space_before=Pt(2 if i in negritas and i else 0)
        p.paragraph_format.space_after=Pt(0)
        p.paragraph_format.line_spacing=0.86

    apertura_h=2 if curso['duracion']>=40 else 1
    cierre_h=2 if curso['duracion']>=40 else 1
    seq=tab[21]
    set_cell(seq.cell(1,0),'Competencia: '+comp,8)
    set_cell(seq.cell(4,1),['Encuadre grupal',datos.get('apertura_docente','')],7.8,{0})
    set_cell(seq.cell(4,2),['Encuadre grupal',datos.get('apertura_estudiante','')],7.8,{0})
    escribir_celda_con_desplegables(seq.cell(4,3), eval_plantillas, ('Diagnóstica','Heteroevaluación','Cuestionario'), ['Evidencia: conocimientos previos'],7.8)
    set_cell(seq.cell(4,4),f'{apertura_h} h de mediación docente',7.8)
    set_cell(seq.cell(5,1),['Contextualización','Explica la aplicación cotidiana o laboral de la competencia con ejemplos concretos.'],7.8,{0})
    set_cell(seq.cell(5,2),['Contextualización','Relaciona las competencias con una necesidad concreta de su contexto.'],7.8,{0})

    def colocar_unidad(tabla,fila,u):
        acts=u['actividades'];ev=u['evaluacion']
        set_cell(tabla.cell(fila,0),[u['titulo']]+u['_temas_con_horas'],7.6,{0})
        set_cell(tabla.cell(fila,1),['Estrategia:',
            'Teorización',acts['teorizacion_docente'],
            'Ejercitación',acts['ejercitacion_docente'],
            'Reflexión',acts['reflexion_docente']],7.5,{0,1,3,5})
        escribir_estrategia_desplegable(tabla.cell(fila,1),estrategia_plantilla[0],str(u.get('estrategia','')))
        set_cell(tabla.cell(fila,2),['Actividades del estudiante',
            'Teorización',acts['teorizacion_estudiante'],
            'Ejercitación',acts['ejercitacion_estudiante'],
            'Reflexión',acts['reflexion_estudiante']],7.5,{0,1,3,5})
        escribir_celda_con_desplegables(tabla.cell(fila,3),eval_plantillas,
            (ev.get('momento','Formativa'),ev.get('tipo','Heteroevaluación'),ev.get('instrumento','Lista de cotejo')),
            ['Evidencia: '+str(ev.get('evidencia','')),'Criterios:']+list(ev.get('criterios',[])),7.4)
        set_cell(tabla.cell(fila,4),[
            f'{u["mediacion_horas"]:g} h de mediación docente',
            f'{u["practica_horas"]:g} h de práctica supervisada',
            f'TOTAL: {u["mediacion_horas"]+u["practica_horas"]:g} h'],7.5)

    # Diferencia estructural real: primera unidad en tabla 22, sucesivas en tabla 23.
    colocar_unidad(seq,6,datos['unidades'][0])
    desarrollo=tab[22]
    # Word original define títulos repetibles que LibreOffice superpone a la
    # primera unidad cuando ésta pasa de página. Desactivar encabezados repetidos
    # en esta tabla, sin tocar el texto ni los bordes.
    for r in desarrollo.rows[:2]:
        pr=r._tr.trPr
        if pr is not None:
            cab=pr.find(W('tblHeader'))
            if cab is not None:pr.remove(cab)
    # Repetir solo el título general, no los encabezados con celdas combinadas.
    pr=desarrollo.rows[0]._tr.get_or_add_trPr()
    if pr.find(W('tblHeader')) is None:pr.append(OxmlElement('w:tblHeader'))
    while len(desarrollo.rows)<len(datos['unidades'])+2:
        desarrollo._tbl.append(copy.deepcopy(desarrollo.rows[-1]._tr))
    for i,u in enumerate(datos['unidades'][1:],3):
        colocar_unidad(desarrollo,i,u)
        # Cada unidad se mantiene en un bloque continuo; evitar fragmentos huérfanos.
        propiedades_fila=desarrollo.rows[i]._tr.get_or_add_trPr()
        if propiedades_fila.find(W('cantSplit')) is None:
            propiedades_fila.append(OxmlElement('w:cantSplit'))
    cierre=tab[23]
    set_cell(cierre.cell(3,1),['Reflexión y cierre',datos.get('cierre_docente',''),
        'Criterios del producto final:']+datos.get('criterios_evaluacion',[]),7.8,{0,2})
    set_cell(cierre.cell(3,2),['Reflexión y cierre',datos.get('cierre_estudiante','')],7.8,{0})
    escribir_celda_con_desplegables(cierre.cell(3,3),eval_plantillas,('Sumativa','Heteroevaluación','Guía de observación'), ['Evidencias: producto integrador y desempeño'],7.8)
    set_cell(cierre.cell(3,4),f'{cierre_h} h de mediación docente',7.8)

    set_cell(tab[24].cell(1,0),['Actividades que realizar:',
        datos.get('actividades_extracurriculares','')],8)
    propiedades=tab[25]._tbl.tblPr
    flotante=propiedades.find(W('tblpPr'))
    if flotante is not None:propiedades.remove(flotante)
    reqs=recursos_cuantificados(curso,recursos_sugeridos(datos,especialidad))
    categorias=[('Equipo',reqs['equipo']),('Herramienta',reqs['herramientas']),
                ('Material e insumos',reqs['materiales']),
                ('Material de apoyo didáctico',reqs['apoyo']),
                ('Conectividad',reqs['conectividad'])]
    for r,(ttl,info) in enumerate(categorias,1):
        set_cell(tab[25].cell(r,0),[ttl,info],7.7,{0})
    # Bibliografía: no inventar citas no comprobadas. Si el JSON incluye
    # fuentes sustentadas se trasladan; si no, casillas sin leyendas de confirmación.
    referencias=referencias_efectivas(curso,base,datos)
    if not referencias['bibliografica'] or not referencias['cibergrafica']:
        raise ValueError('La tabla de REFERENCIAS debe incluir al menos una obra bibliográfica y una fuente cibergráfica pertinentes. No se guardó el PEA incompleto.')
    for fila,nombre,clave in ((1,'Bibliográfica','bibliografica'),
                             (2,'Hemerográfica','hemerografica'),
                             (4,'Cibergráfica','cibergrafica')):
        valor=referencias.get(clave,[]) if isinstance(referencias,dict) else []
        if isinstance(valor,str):valor=[valor]
        lista=[str(v) for v in valor if str(v).strip()]
        if not lista and referencias:
            lista=['Sin obras de esta categoría citadas en el desarrollo del curso.']
        set_cell(tab[25].cell(fila,1),[nombre]+lista,7.7,{0})
    # Esta plantilla ya separa los recursos por sus estilos de paginación.
    # NO agregar salto extra: producía una página totalmente en blanco.

    # Registrar cualquier dato administrativo sin inventar fechas o normas.
    avisos_internos=[]
    rellenar_campos_institucionales(doc,curso,base,perfil,avisos_internos)
    # Bloqueo de regresión: el texto del apartado 20 JAMÁS se deja vacío,
    # ni se puede sustituir por «NO APLICA — DOCENTE INTERNO».
    just_en_word=tab[16].cell(0,0).text.strip()
    if len(just_en_word)<160 or 'NO APLICA' in just_en_word.upper():
        raise ValueError('Control de calidad: la JUSTIFICACIÓN quedó vacía o incorrecta en el Word. No se guardó el PEA.')
    revisar_documento_final(doc,curso,base,datos,avisos_internos)
    # Actualizar autoridades CONFIRMADAS, sin incorporar firmas no suministradas.
    colocar_autoridades_confirmadas(doc)
    # En la validación se usa una tipografía uniforme, también para nombres
    # largos: no se permite que el apellido baje a otra línea.
    nombre_firma_docente=' '.join(p.capitalize() for p in nombre_docente.split())
    tam_firma=9.2 if len(nombre_firma_docente)>32 else 10.0
    set_cell(tab[26].cell(1,0),[nombre_firma_docente],tam_firma)
    # En esta plantilla Lila aparece tras cuatro líneas reservadas a firma.
    # Repetir esos espacios sobre nombre docente para alinear horizontalmente.
    celda_docente=tab[26].cell(1,0)
    celda_lila=tab[26].cell(1,2)
    lineas_previas=next((i for i,p in enumerate(celda_lila.paragraphs) if AUTORIDAD_VALIDA in p.text),4)
    contenido=celda_docente.paragraphs[-1]._p
    contenedor=celda_docente._tc
    # Clonar los párrafos de reserva EXACTOS (sus tamaños e interlineados)
    # para situar el nombre de docente a la altura de Lila, no sobre la línea.
    previo_lila=list(celda_lila._tc)
    para_copiar=[x for x in previo_lila if x.tag==W('p')][:lineas_previas]
    for original in para_copiar:
        contenido.addprevious(copy.deepcopy(original))
    centrar_firma_docente(doc,nombre_firma_docente,tam_firma)
    # Evitar que el encabezado del punto 12 quede huérfano al final de
    # la página anterior; no se tocan logos, márgenes ni otras tablas.
    for par_xml in doc.element.body.iter(W('p')):
        texto=''.join(n.text or '' for n in par_xml.iter(W('t')))
        if any(rotulo in texto for rotulo in (
            'DURACIÓN Y HORARIO DEL CURSO', 'NÚMERO DE PARTICIPANTES',
            'FECHA Y DÍAS DE IMPARTICIÓN')):
            pp=par_xml.find(W('pPr'))
            if pp is None:pp=OxmlElement('w:pPr');par_xml.insert(0,pp)
            if pp.find(W('keepNext')) is None:pp.append(OxmlElement('w:keepNext'))
            if 'DURACIÓN Y HORARIO DEL CURSO' in texto and pp.find(W('pageBreakBefore')) is None:
                pp.append(OxmlElement('w:pageBreakBefore'))
    doc.save(salida)
    # Control académico-administrativo trazable y separado del PEA.
    salida.with_name(salida.stem+'_CONTROL_INTEGRIDAD.json').write_text(
        json.dumps({'curso':curso['nombre'],'docente':curso['hoja'],'fila':curso['fila'],
                    'incidencias':avisos_internos,'datos_documentados_sin_observaciones':not bool(avisos_internos),
                    'firmas_institucionales_insertadas':False, 'flujo':'Final para revisión académica; no sustituye autorización oficial'},ensure_ascii=False,indent=2),encoding='utf-8')
    if incluir_firma:
        aprobado=input(f'¿El docente {nombre_docente} autorizó expresamente firmar ESTE PEA de {curso["nombre"]}? (escriba AUTORIZO): ').strip()
        if aprobado=='AUTORIZO':
            doc2=Document(salida)
            agregar_firma_docente(doc2.tables[26].cell(1,0),perfil.get('firma'),perfil.get('autorizada'),True)
            doc2.save(salida)
        else:print('No se incrustó firma docente. Se deja espacio para firma manuscrita.')
    return salida


def comprobar_plantilla(base):
    """Nunca rellenar posiciones de otra plantilla sin comprobar sus tablas/firmas."""
    ruta=base/PLANTILLA
    if not ruta.is_file():
        raise FileNotFoundError('No existe '+str(ruta))
    documento=Document(ruta)
    assert_plantilla(documento)
    return len(documento.tables)


def elegir_de_lista(elementos, pregunta, etiqueta, descripciones=None):
    """Permite elegir un número o buscar por texto en las opciones listadas."""
    if not elementos:
        raise ValueError('No hay '+etiqueta+' para seleccionar.')
    vista=descripciones or [str(x) for x in elementos]
    for n,texto in enumerate(vista,1):
        print(f' {n:2}. {texto}')
    while True:
        respuesta=input(pregunta+' (numero o palabra para buscar): ').strip()
        if respuesta.isdigit():
            pos=int(respuesta)
            if 1<=pos<=len(elementos):return elementos[pos-1]
            print('Número fuera de rango; inténtalo de nuevo.')
            continue
        if not respuesta:
            print('Escribe un número o una palabra del nombre.')
            continue
        indices=[i for i,texto in enumerate(vista) if normal(respuesta) in normal(texto)]
        if len(indices)==1:return elementos[indices[0]]
        if not indices:
            print('No encontré coincidencias. Prueba con otra palabra o un número.')
        else:
            print('Encontré varias coincidencias, elige su número:')
            for i in indices:print(f' {i+1:2}. {vista[i]}')


def main():
    ap=argparse.ArgumentParser(description='Generador PEA CECATI 31 — Extensión, versión 6.4')
    ap.add_argument('--base',default=str(BASE if (BASE/PLANTILLA).is_file() else BASE_CASA),help='Carpeta con los 3 archivos de entrada')
    ap.add_argument('--modo',choices=['diagnostico','demo','cache','gemini'],default='diagnostico')
    ap.add_argument('--hoja',default='')
    ap.add_argument('--fila',type=int,default=0)
    ap.add_argument('--firma-docente',action='store_true',help='Solicitar consentimiento por cada PEA antes de incrustar firma')
    args=ap.parse_args()
    base=Path(args.base)
    print('\nGENERADOR PEA CECATI 31 — EXTENSIÓN v6.4')
    print('Carpeta:',base)
    cursos,perfiles=leer_archivos(base)
    cursos=[c for c in cursos if c['tipo']=='Extensión']
    if args.modo=='diagnostico':
        print('Hojas de programación: 13 esperadas. Cursos identificados:',len(cursos),'Perfiles:',len(perfiles))
        fechas_sin_clase=cargar_dias(base)
        print(f'Calendario: {len(fechas_sin_clase)} días excluidos en DIAS_SIN_CLASE.json; NO se agregan festivos automáticamente.')
        try:
            tablas=comprobar_plantilla(base)
            print('Plantilla COMPATIBLE con esta versión:',tablas,'tablas.')
            inst=avisos_institucionales(Document(base/PLANTILLA))
            print('IMPORTANTE: origen muestra CECATI',inst['plantel'], '(el PEA generado dirá CECATI 31).')
            print('Autoridades que contiene el Word original:',inst['valida'],'/',inst['visto'],
                  '/ AUTORIZA:',inst['autoriza'] or 'EN BLANCO')
            print('EN TODOS LOS PEAs GENERADOS: VALIDA:',AUTORIDAD_VALIDA,
                  '| VISTO BUENO:',AUTORIDAD_VISTO,'| AUTORIZA:',AUTORIDAD_AUTORIZA)
            print('IMPORTANTE: no se insertan firmas institucionales; revisar y validar antes de oficializar.')
        except Exception as e:
            print('ATENCIÓN: PLANTILLA NO COMPROBADA: ',e)
            print('No uses opciones de generación hasta adaptar la nueva plantilla.')
        print('Firmas docentes: validar disponibilidad local y autorización por documento.')
        for perfil in perfiles.values():
            sig=str(perfil.get('firma') or '').strip().strip('"').strip("'")
            estado='DISPONIBLE' if sig and Path(sig).is_file() else 'NO ENCONTRADA EN ESTA COMPUTADORA'
            print('  Firma',perfil['nombre'],'—',estado)

        for name in sorted(set(c['hoja'] for c in cursos)):
            n=sum(c['hoja']==name for c in cursos)
            estado='CON PERFIL' if normal(name) in perfiles else 'FALTA PERFIL'
            print(f' - {name} ({n} grupos) — {estado}')
        if not cursos:raise ValueError('No se localizaron filas de cursos en la programación')
        return
    # Validar también en modos de generación: no alterar plantilla desconocida.
    comprobar_plantilla(base)
    if args.hoja:
        matches=[c for c in cursos if normal(c['hoja'])==normal(args.hoja) and (not args.fila or c['fila']==args.fila)]
    else:
        maestras=sorted(set(c['hoja'] for c in cursos))
        nombre=elegir_de_lista(maestras,'Elige docente','docentes')
        matches=[c for c in cursos if c['hoja']==nombre]
    if not matches:raise ValueError('No se encontró el docente o fila seleccionada')
    if len(matches)>1:
        titulos=[f'Fila {c["fila"]}: {c["nombre"]} — {c["duracion"]:g} h, {c["horario"][:37]}' for c in matches]
        matches=[elegir_de_lista(matches,'Elige curso','cursos',titulos)]
    curso=matches[0]; print('\nCURSO:',curso['nombre'],'| TIPO:',curso['tipo'],'| FILA:',curso['fila'])
    reporte=revisar_calendario(curso,base);print('Calendario:',reporte)
    salida=base/SALIDA;salida.mkdir(exist_ok=True)
    # Las diferencias justificadas en Observaciones de la programación NO se
    # incorporan al PEA. El calendario es aviso interno, no modifica fechas ni horas.
    if args.modo=='gemini' and reporte.startswith('ERROR:'):
        raise ValueError('Fechas ausentes o contradictorias: revisar antes de llamar a IA.')
    if reporte.startswith('DIFERENCIA:'):
        print('AVISO INTERNO: comprobar Observaciones en la programación; no se copiarán al PEA.')
    contenido=contenido_ia(curso,base,args.modo)
    apertura=2 if curso['duracion']>=40 else 1
    validator(contenido,{'apertura':apertura,'cierre':apertura},curso['duracion'])
    limpio=re.sub(r'[^A-Za-z0-9_]+','_',normal(curso['nombre']))[:42].strip('_')
    archivo=salida/f'PEA_{limpio}_{normal(curso["hoja"]).replace(" ","_")}_F{curso["fila"]}_FINAL_PARA_REVISION.docx'
    # No reemplazar automáticamente un PEA previo de este mismo curso.
    if archivo.exists():
        marca=dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        original=archivo
        archivo=original.with_name(original.stem+'_REV_'+marca+'.docx')
        n=2
        while archivo.exists():
            archivo=original.with_name(original.stem+'_REV_'+marca+'_'+str(n)+'.docx')
            n+=1
    crear_docx(curso,contenido,base,archivo,args.firma_docente)
    # Informe separado: nunca se añade una tabla o texto al PEA.
    informe=archivo.with_name(archivo.stem+'_CALIDAD_ACADEMICA_v7.json')
    qa_apertura=2 if curso['duracion']>=40 else 1
    informe.write_text(qa_v7.informe_json(contenido,curso,{'apertura':qa_apertura,'cierre':qa_apertura}),encoding='utf-8')
    print('CONTROL DE CALIDAD:',informe)
    aviso=archivo.with_name(archivo.stem+'_REVISION.txt')
    perfil=curso.get('docente')
    configuracion=cargar_configuracion(base)
    especialidad=curso.get('especialidad_programada') or (perfil or {}).get('especialidad') or ''
    notas=['PEA COMPLETO PARA REVISIÓN ACADÉMICA (NO IMPLICA AUTORIZACIÓN NI FIRMA)',
           'Curso: '+curso['nombre'], 'Docente: '+curso['hoja'],
           'Grupo/fila: '+str(curso['fila']),
           'Duración oficial: '+f'{curso["duracion"]:g} horas',
           'Calendario (aviso interno): '+reporte,
           'Especialidad registrada en programación: '+especialidad,
           'Aula/taller: '+(curso.get('aula') or 'Sin clave en programación'),
           'El documento contiene opciones circulares editables y listas originales de Word preseleccionadas.',
           'Revisar exactitud académica y validez documental antes de aprobar o firmar.',
           'No se insertan automáticamente firmas manuscritas.',]
    if not perfil:notas.append('Sin ficha personal local: CURP/correo/teléfono quedan en blanco.')
    if not (fuentes_para_curso(curso,base) or contenido.get('referencias') or {}):
        notas.append('Referencias: no se suministraron fuentes documentales verificadas; quedaron sin citas inventadas.')
    registro_estado=archivo.with_name(archivo.stem+'_CONTROL_INTEGRIDAD.json')
    if registro_estado.exists():
        control=json.loads(registro_estado.read_text(encoding='utf-8'))
        notas.append('Control de integridad: '+registro_estado.name)
        notas.extend('AVISO: '+x for x in control.get('incidencias',[]))
    aviso.write_text('\n'.join(notas)+'\n',encoding='utf-8')
    print('CREADO:',archivo)
    print('REVISIÓN:',aviso)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('ERROR:',e)
        raise SystemExit(1)
