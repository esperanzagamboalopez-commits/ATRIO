"""ATRIO 10.12.12.4 · Edición ampliada de PEA PDF oficiales.

Compatibilidad inicial: familia de 17 páginas del ejemplo Soldador y Oxicortador.
Opera sobre PDF original en memoria; redacción real, pruebas de integridad y DOCX
híbrido con fondo visual y campos administrativos VML editables.
NO reconvierte tablas ni altera el contenido académico.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from hashlib import sha256
import io, re, json, zipfile, html

import fitz


class ErrorAdaptacion(ValueError):
    def __init__(self, incidencias):
        self.incidencias = incidencias
        super().__init__('No se generó documento: '+ '; '.join(
            f"página {x['pagina']}, {x['campo']}: {x['causa']}" for x in incidencias))

@dataclass(frozen=True)
class Spec:
    campo: str
    pagina: int
    box: tuple[float,float,float,float]
    old: str|None = None
    size: float = 9
    min_size: float = 7
    font: str = 'cour'
    align: int = 0
    required: bool = True
    mode: str = 'replace' # replace / blank

# Áreas de los VALORES del formulario (no incluyen sus rótulos), calibradas para
# la estructura verificada del PDF de prueba; otros diseños deben rechazarse.
SPECS = [
    Spec('cecati_p2',2,(76,271,175,285),'114',9),
    Spec('cecati_p5',5,(528,181,570,196),'114',9),
    Spec('entidad_p5',5,(607,181,746,197),'Pachuca de soto, hidalgo',8),
    Spec('horario_p3',3,(77,330,294,345),'8:00 a 14:00 horas',9),
    Spec('dias_p3',3,(77,395,294,410),'Sábado',9),
    Spec('inicio_p3',3,(116.5,526,181,543),'09/01/2021',9),
    Spec('termino_p3',3,(245,526,311,543),'13/03/2021',9),
    Spec('curp_p3',3,(75,695,184,711),'VAGJ831221HDFZRL07',8),
    Spec('nombre_p3',3,(201,691,322,716),'JULIO CESAR VAZQUEZ GARCIA',8),
    Spec('tel_p3',3,(330,695,393,711),'7721204202',8),
    Spec('email_p3',3,(397,695,562,711),'Vazquezgarcia1983@hotmail.com',8),
    Spec('elabora_p17',17,(73,264,270,293),'Julio Cesar Vázquez García',10),
    Spec('valida_p17',17,(315,264,517,293),'Ing. Pedro Vivanco Jiménez',10),
    Spec('vobo_p17',17,(558,264,735,296),'Lic. Diana Patricia Laurrabaquio Flores',10),
    Spec('aprueba_p17',17,(92,407,352,442),None,10,7,'cour',1,False,'blank'),
    Spec('autoriza_p17',17,(443,407,745,442),None,10,7,'cour',1,True,'blank'),
    # El área vacía entre los puntos 13 y 14 se utiliza para identificar sede.
    Spec('sede_p3',3,(77,481,548,501),None,8,7,'cour',0,True,'blank'),
    # Campos administrativos opcionales del formulario de Extensión.
    Spec('con_quien_p2',2,(76,374.8,552,390.0),'Estudiantes',9),
    Spec('especialidad_p2',2,(76,533.0,550,548.0),'Soldadura y pailería',9),
    Spec('especialidad_p5',5,(70,181.5,505,197),'Soldadura y Pailería',9),
    Spec('participantes_p3',3,(77,265.7,293,282.0),'1',9),
    Spec('clave_p5',5,(520,230.0,630,245.0),None,9,7,'cour',0,False,'blank'),
    # Punto 8 (código y nombre de norma) ocupa una tabla vacía en página 3.
    Spec('norma_codigo_p3',3,(77,137.0,158,154.0),None,8,7,'cour',0,False,'blank'),
    Spec('norma_nombre_p3',3,(170,137.0,548,154.0),None,8,7,'cour',0,False,'blank'),
]

ALIASES = {
    'cecati_p2':'31','cecati_p5':'31','entidad_p5':'ubicacion',
    'horario_p3':'horario','dias_p3':'dias',
    'inicio_p3':'inicio','termino_p3':'fin',
    'curp_p3':'curp','nombre_p3':'docente','tel_p3':'telefono',
    'email_p3':'correo','elabora_p17':'docente',
    'con_quien_p2':'con_quien','especialidad_p2':'especialidad','especialidad_p5':'especialidad',
    'participantes_p3':'participantes','clave_p5':'clave_curso',
    'norma_codigo_p3':'norma_codigo','norma_nombre_p3':'norma_nombre',
    'valida_p17':'valida','vobo_p17':'visto',
    'aprueba_p17':'aprueba','autoriza_p17':'autoriza','sede_p3':'sede'
}

# Casillas que pertenecen al formato CALIBRADO (17 páginas, PDF de ejemplo).
# La X antigua se elimina por redacción real en su glyph; nunca sobre la línea
# del recuadro. La X nueva se dibuja en la coordenada exacta del recuadro.
# Para documentos con disposición distinta se bloquea la edición.
_MARCAS = [
 # (id, pagina, bbox, originalmente_marcada, clave, valor_de_opcion)
 ('marca_servicio_ce',2,(232.4,321.9,239.4,332.2),True,'servicio_pdf','CE'),
 ('marca_servicio_cae',2,(310.4,321.9,317.4,332.2),False,'servicio_pdf','CAE'),
 ('marca_estudiantes',2,(75.5,443.5,82.7,455.0),True,'perfiles_usuario','Estudiantes'),
 ('marca_empleados',2,(152.0,442.0,159.2,453.5),False,'perfiles_usuario','Empleados'),
 ('marca_autoempleado',2,(283.0,441.0,290.0,453.2),True,'perfiles_usuario','Autoempleado'),
 ('marca_desventaja',2,(371.0,441.0,379.0,453.2),False,'perfiles_usuario','Grupos en desventaja social y/o económica'),
 ('marca_jubilados',2,(75.5,463.4,82.7,475.0),False,'perfiles_usuario','Jubilados'),
 ('marca_mayores',2,(152.0,463.4,159.2,475.0),False,'perfiles_usuario','Adultos mayores'),
 ('marca_desempleados',2,(283.0,462.7,290.0,474.7),True,'perfiles_usuario','Desempleados'),
 ('marca_discapacidad',2,(371.0,462.7,379.0,474.7),False,'perfiles_usuario','Personas con discapacidad'),
 ('marca_norma_si',2,(76.7,598.3,84.0,610.0),False,'normalizacion','SI'),
 ('marca_norma_no',2,(237.7,598.3,245.0,610.0),True,'normalizacion','NO'),
 ('marca_sede_cecati',3,(74.5,459.8,82.5,471.4),False,'modalidad_sede','CECATI'),
 ('marca_sede_acm',3,(213.2,460.1,221.0,471.4),True,'modalidad_sede','Acción móvil'),
 ('marca_docente_interno',4,(75.0,185.9,82.1,196.5),True,'tipo_docente','Interno'),
 ('marca_docente_externo',4,(216.5,185.9,223.6,196.5),False,'tipo_docente','Externo'),
]
for mid,pag,box,old_checked,_,_ in _MARCAS:
    SPECS.append(Spec(mid,pag,box,'X' if old_checked else None,
                      7,7,'cour',0,False,'replace' if old_checked else 'blank'))

def _valor_marca(spec,data):
    for ident,_,_,_,key,option in _MARCAS:
        if spec.campo == ident:
            selected=data.get(key,[])
            return 'X' if ((_norm(option) in {_norm(x) for x in selected}) if isinstance(selected,list) else (_norm(option)==_norm(str(selected)))) else ''
    raise KeyError(spec.campo)

def _valor(spec,data):
    if spec.campo.startswith('marca_'):
        return _valor_marca(spec,data)
    alias=ALIASES[spec.campo]
    value=alias if alias=='31' else str(data.get(alias,'') or '').strip()
    if spec.campo=='sede_p3' and value:value='Sede: '+value
    return value


# Confirmar anclas, no basarse solo en coordenadas.
REQUIRED_PAGE_LABELS = {
    2: ['NOMBRE DEL CURSO','CECATI'],
    3: ['DURACIÓN DEL CURSO','NÚMERO DE PARTICIPANTES','HORARIO',
        'DÍAS DE IMPARTICIÓN','LUGAR DE IMPARTICIÓN',
        'FECHA DE IMPARTICIÓN','PERFIL DEL DOCENTE','DOCENTE PARA LA ACCIÓN FORMATIVA'],
    5: ['CECATI No.','Soldador y oxicortador'],
    17:['VALIDACIÓN Y APROBACIÓN ACADÉMICA','Elabora','Valida','Vo. Bo','Aprueba','Autoriza']
}


def _norm(s):
    # PDF contiene espacios dentro de palabras en determinados rótulos.
    import unicodedata
    s=''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+','',s.upper())


def _hash(raw):return sha256(raw).hexdigest()


def _text(page,rect):
    return page.get_text('text',clip=fitz.Rect(rect),sort=True).strip()


def _safe_validate(doc,data):
    failures=[]
    if len(doc)!=17:
        failures.append(dict(pagina=0,campo='formato',causa=f'Se esperaban 17 páginas, hay {len(doc)}. Formato no reconocido.'))
        return failures
    for page_no,labels in REQUIRED_PAGE_LABELS.items():
        txt=_norm(doc[page_no-1].get_text(sort=True))
        for label in labels:
            if _norm(label) not in txt:
                failures.append(dict(pagina=page_no,campo='plantilla',causa='No se encontró el rótulo '+label))
    for key,allowed in [('servicio_pdf',('CE','CAE')),('normalizacion',('SI','NO')),
                        ('modalidad_sede',('CECATI','Acción móvil')),('tipo_docente',('Interno','Externo'))]:
        if _norm(str(data.get(key,'') or '')) not in {_norm(x) for x in allowed}:
            failures.append(dict(pagina=0,campo=key,causa='Selección administrativa obligatoria no válida.'))
    if not isinstance(data.get('perfiles_usuario'),list) or not data['perfiles_usuario']:
        failures.append(dict(pagina=2,campo='perfil_usuario',causa='Selecciona al menos un perfil de usuario.'))
    if _norm(str(data.get('normalizacion',''))) == 'SI' and not (str(data.get('norma_codigo','')).strip() and str(data.get('norma_nombre','')).strip()):
        failures.append(dict(pagina=3,campo='normalizacion',causa='La normalización requiere código y nombre de la norma.'))
    for spec in SPECS:
        new=_valor(spec,data)
        if spec.required and not new:
            failures.append(dict(pagina=spec.pagina,campo=spec.campo,causa='Dato administrativo obligatorio vacío'))
        if spec.old:
            candidate=_text(doc[spec.pagina-1],spec.box)
            if _norm(spec.old) not in _norm(candidate):
                failures.append(dict(pagina=spec.pagina,campo=spec.campo,causa=f'El valor anterior no coincide en el campo esperado ({candidate[:55]!r})'))
        elif spec.mode=='blank':
            # No debe borrar un dato anterior desconocido en un campo supuestamente vacío.
            candidate=_text(doc[spec.pagina-1],spec.box)
            if candidate.strip() and spec.campo not in ('sede_p3',):
                failures.append(dict(pagina=spec.pagina,campo=spec.campo,causa='El campo previsto como vacío tiene contenido; requiere calibración.'))
    if len(doc)==17:
        p3=doc[2].get_text(sort=True)
        for protected in ('60 horas','Ing. Industrial y TSU mecánica'):
            if _norm(protected) not in _norm(p3):failures.append(dict(pagina=3,campo='datos protegidos',causa=f'No se identificó {protected}'))
        # Número de participantes ahora es administrativo y editable.
        # Se comprueba su valor original mediante SPECS antes de redactar.
    return failures


def _blank_and_insert(doc, spec, val, incidencias, operation_log):
    page=doc[spec.pagina-1];r=fitz.Rect(spec.box)
    if spec.mode=='replace':
        # redactar exclusivamente la región de VALOR. No se redibujan gráficos.
        redact=fitz.Rect(r.x0,r.y0,r.x1,r.y1)
        page.add_redact_annot(redact,fill=False)
    operation_log.append(dict(pagina=spec.pagina,campo=spec.campo,bbox=list(spec.box),anterior=spec.old or '',nuevo=val,
            operacion=spec.mode))


def _insert_value(page,spec,val):
    # La caja útil se mantiene dentro de la celda, sin tocar líneas.
    r=fitz.Rect(spec.box)
    if not val:return None
    if spec.campo.startswith('marca_'):
        # No se usa insert_textbox para una sola X: la caja oficial es diminuta.
        page.insert_text((r.x0+1,r.y1-2.0), 'X',fontname='cour',fontsize=7,color=(0,0,0))
        return 7.0
    for size in (spec.size-i*.25 for i in range(int((spec.size-spec.min_size)/.25)+1)):
        if size<spec.min_size:break
        # Fit sobre copia temporal, para no insertar dos veces si no cabe.
        test=fitz.open();test_page=test.new_page(width=page.rect.width,height=page.rect.height)
        rc=test_page.insert_textbox(r,val,fontname=spec.font,fontsize=size,lineheight=1.08,
                    align=spec.align, color=(0,0,0))
        test.close()
        if rc>=0:
            actual=page.insert_textbox(r,val,fontname=spec.font,fontsize=size,lineheight=1.08,
                    align=spec.align,color=(0,0,0))
            if actual>=0:return round(size,2)
    return None


def adaptar_pdf(raw:bytes, data:dict[str,Any], crear_word=True):
    if not isinstance(raw,bytes) or not raw.startswith(b'%PDF-') or len(raw)>25*1024*1024:
        raise ErrorAdaptacion([dict(pagina=0,campo='archivo',causa='Se necesita PDF válido de hasta 25MB.')])
    data=dict(data)
    data.setdefault('ubicacion','Coatzacoalcos, Veracruz')
    # La modalidad del punto 13 se cambia modificando únicamente la X de las casillas.
    original_hash=_hash(raw)
    source=fitz.open(stream=raw,filetype='pdf')
    if source.needs_pass:
        raise ErrorAdaptacion([dict(pagina=0,campo='archivo',causa='PDF protegido con contraseña.')])
    errs=_safe_validate(source,data)
    if errs:
        source.close();raise ErrorAdaptacion(errs)
    # Revisión estricta de la fuente para que ninguna página académica cambie.
    original_texts=[p.get_text(sort=True) for p in source]
    original_images=[len(p.get_images(full=True)) for p in source]
    clean=fitz.open(stream=raw,filetype='pdf')
    log=[]
    regions={}
    for spec in SPECS:
        value=_valor(spec,data)
        # La X anterior también debe redactarse cuando la casilla se desmarca.
        if not value and not (spec.campo.startswith('marca_') and spec.old):continue
        _blank_and_insert(clean,spec,value,[],log)
        regions.setdefault(spec.pagina,[]).append(spec)
    for pno in regions:
        page=clean[pno-1]
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,text=fitz.PDF_REDACT_TEXT_REMOVE)
    # La base Word se renderizará antes de escribir el texto nuevo.
    clean_bytes=clean.tobytes(garbage=4,deflate=True)
    # Inspección post-redacción de contenido antiguo.
    incidences=[]
    for spec in SPECS:
        if spec.old and spec.campo in [item['campo'] for item in log]:
            zone=_text(clean[spec.pagina-1],spec.box)
            if _norm(spec.old) in _norm(zone):
                incidences.append(dict(pagina=spec.pagina,campo=spec.campo,causa='La redacción no eliminó el texto anterior.'))
    if incidences:
        clean.close();source.close();raise ErrorAdaptacion(incidences)
    sizes={}
    for spec in SPECS:
        value=_valor(spec,data)
        if not value:continue
        size=_insert_value(clean[spec.pagina-1],spec,value)
        if size is None:incidences.append(dict(pagina=spec.pagina,campo=spec.campo,causa='El valor nuevo no cabe a 7 pt o más.'))
        sizes[spec.campo]=size
    if incidences:
        clean.close();source.close();raise ErrorAdaptacion(incidences)
    # Comprobar TODOS los valores nuevos en su área administrativa, no solo algunos.
    for spec in SPECS:
        val=_valor(spec,data)
        if val and _norm(val) not in _norm(_text(clean[spec.pagina-1],spec.box)):
            incidences.append(dict(pagina=spec.pagina,campo=spec.campo,
                                   causa='El valor nuevo no aparece completo en la zona prevista.'))
    # El punto 17 exige exactamente UNA X en la casilla seleccionada.
    # Se inspeccionan los cuadros originales ya calibrados, sin reemplazar
    # rótulos, redibujar recuadros ni alterar el contenido académico.
    tipo_p17=str(data.get('tipo_docente') or '').strip().casefold()
    marcas_p17={
        'interno':_text(clean[3],(75.0,185.9,82.1,196.5)),
        'externo':_text(clean[3],(216.5,185.9,223.6,196.5))
    }
    for opcion,texto_marca in marcas_p17.items():
        marcada=_norm(texto_marca)=='X'
        if marcada!=(opcion==tipo_p17):
            incidences.append(dict(pagina=4,campo='tipo_docente',
                causa='El punto 17 no coincide con la casilla seleccionada: '+opcion))
    if incidences:
        clean.close();source.close();raise ErrorAdaptacion(incidences)
    # Verificar contenido académico intacto y páginas no administrativas idénticas.
    for i in range(17):
        cur=clean[i].get_text(sort=True)
        if i not in [1,2,3,4,16]:
            if cur!=original_texts[i]:
                incidences.append(dict(pagina=i+1,campo='contenido académico',causa='Cambió el texto de una página protegida.'))
            if clean[i].get_pixmap(matrix=fitz.Matrix(0.5,0.5),alpha=False).samples != source[i].get_pixmap(matrix=fitz.Matrix(0.5,0.5),alpha=False).samples:
                incidences.append(dict(pagina=i+1,campo='formato académico',causa='Cambió visualmente una página protegida.'))
        if len(clean[i].get_images(full=True))!=original_images[i]:
            incidences.append(dict(pagina=i+1,campo='membrete',causa='Cambió la cantidad de imágenes del documento.'))
    # La página 4 solo permite cambiar la marca del punto 17;
    # su texto académico (puntos 18-20) se conserva literalmente.
    if source[3].get_text('text',clip=fitz.Rect(45,215,565,750)) != clean[3].get_text('text',clip=fitz.Rect(45,215,565,750)):
        incidences.append(dict(pagina=4,campo='contenido académico',causa='Cambió la sección académica de la página 4.'))
    original_p15=_text(source[2],(75,595,295,615))
    new_p15=_text(clean[2],(75,595,295,615))
    if _norm(original_p15)!=_norm(new_p15):
        incidences.append(dict(pagina=3,campo='punto 15',causa='Se modificó el perfil profesional protegido.'))
    protected_course=_text(source[1],(73,210,295,226))
    if _norm(protected_course)!=_norm(_text(clean[1],(73,210,295,226))):
        incidences.append(dict(pagina=2,campo='curso',causa='Se alteró el nombre académico del curso.'))
    for bbox,field in [((73,199,125,220),'horas')]:
        if _norm(_text(source[2],bbox))!=_norm(_text(clean[2],bbox)):
            incidences.append(dict(pagina=3,campo=field,causa='Cambió un valor académico protegido.'))
    if incidences:
        clean.close();source.close();raise ErrorAdaptacion(incidences)
    pdf_bytes=clean.tobytes(garbage=4,deflate=True)
    result={'original_sha256':original_hash,'adaptado_sha256':_hash(pdf_bytes),
            'paginas':17,'reemplazos':[{**item,'tamano_fuente':sizes.get(item['campo'])} for item in log],
            'estado':'BORRADOR_PENDIENTE_REVISION_VISUAL','contenido_academico':'no_modificado',
            'word':'No generado'}
    word_bytes=None
    if crear_word:
        word_bytes=crear_docx_hibrido(clean_bytes,pdf_bytes, data, sizes)
        result['word']='Documento híbrido: fondos de página como imagen, campos administrativos editables; contenido académico no editable.'
    source.close();clean.close()
    return pdf_bytes,word_bytes,result


def crear_docx_hibrido(pdf_sin_valores:bytes,pdf_adaptado:bytes,data:dict,sizes:dict):
    """DOCX híbrido: cada página es imagen de PDF redactado, con campos VML editables.
    La base es el PDF sin los valores anteriores ni los nuevos; no hay textos duplicados.
    """
    from docx import Document
    from docx.shared import Pt
    from docx.enum.section import WD_SECTION
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from lxml import etree

    def anchor_picture(run,binary,w,h):
        inline=run.add_picture(io.BytesIO(binary),width=Pt(w),height=Pt(h))._inline
        inline.tag=qn('wp:anchor')
        for k,v in {'distT':'0','distB':'0','distL':'0','distR':'0','simplePos':'0','relativeHeight':'0',
                   'behindDoc':'1','locked':'1','layoutInCell':'1','allowOverlap':'1'}.items():inline.set(k,v)
        pos=OxmlElement('wp:simplePos');pos.set('x','0');pos.set('y','0');inline.insert(0,pos)
        for axis,n in [('H',1),('V',2)]:
            p=OxmlElement('wp:position'+axis);p.set('relativeFrom','page')
            off=OxmlElement('wp:posOffset');off.text='0';p.append(off);inline.insert(n,p)
        wrap=OxmlElement('wp:wrapNone');inline.insert(4,wrap)

    def edit_box(par,sp:Spec,value:str,font_size):
        r=sp.box;x,y=sp.box[0],sp.box[1];w=sp.box[2]-x;h=sp.box[3]-y
        # La página del fondo ya está redactada; el cuadro es transparente.
        # Desplazar su origen para evitar recorte de descensos de letras en Word.
        y-=5.0;h+=10.0
        shapeid=10000+SPECS.index(sp)
        # En Word los cuadros flotantes necesitan un interlineado fijo para
        # evitar que los descensos queden ocultos bajo el borde de la celda.
        word_font=max(7.0,float(font_size)-0.5)
        e=html.escape(value,quote=False)
        xml=(f'<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
             f'xmlns:v="urn:schemas-microsoft-com:vml">'
             f'<w:pict><v:shape id="_x0000_s{shapeid}" type="#_x0000_t202" '
             f'style="position:absolute;left:{x:.2f}pt;top:{y:.2f}pt;width:{w:.2f}pt;height:{h:.2f}pt;'
             f'z-index:251659264;mso-position-horizontal-relative:page;mso-position-vertical-relative:page" '
             'stroked="f" filled="f">'
             '<v:textbox inset="0pt,0pt,0pt,0pt"><w:txbxContent><w:p><w:pPr>'
             '<w:spacing w:before="0" w:after="0" w:line="190" w:lineRule="exact"/></w:pPr>'
             f'<w:r><w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/><w:sz w:val="{round(word_font*2)}"/>'
             f'</w:rPr><w:t xml:space="preserve">{e}</w:t></w:r></w:p></w:txbxContent></v:textbox>'
             '</v:shape></w:pict></w:r>')
        par._p.append(etree.fromstring(xml))

    with fitz.open(stream=pdf_sin_valores,filetype='pdf') as d:
        doc=Document()
        for i,page in enumerate(d):
            sec=doc.sections[0] if i==0 else doc.add_section(WD_SECTION.NEW_PAGE)
            sec.page_width=Pt(page.rect.width);sec.page_height=Pt(page.rect.height)
            sec.left_margin=sec.right_margin=sec.top_margin=sec.bottom_margin=Pt(0)
            sec.header_distance=sec.footer_distance=Pt(0)
            pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
            par=doc.add_paragraph()
            par.paragraph_format.space_before=par.paragraph_format.space_after=Pt(0)
            par.paragraph_format.line_spacing=1
            anchor_picture(par.add_run(),pix.tobytes('png'),page.rect.width,page.rect.height)
            for spec in SPECS:
                if spec.pagina!=i+1:continue
                val=_valor(spec,data)
                if val:edit_box(par,spec,val,sizes.get(spec.campo) or spec.size)
        mem=io.BytesIO();doc.save(mem);return mem.getvalue()
