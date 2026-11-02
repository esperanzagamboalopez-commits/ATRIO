"""SISAE: exploración de tablas + consultas autorizadas en memoria, solo lectura.

No extrae DBF a disco. Prohibido consultar datos de autenticación o exportar
filas personales en los resultados de herramientas.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile
import re
import struct
import unicodedata

MAX_TABLA = 100_000_000
MAX_FILAS = 500_000
CAMPOS_DIS = {
    'visual': 'DIS_VISUAL',
    'auditiva': 'DIS_AUDITI',
    'lenguaje': 'DIS_LENGUA',
    'motriz': 'DIS_MOTRIZ',
    'mental': 'DIS_MENTAL',
}
CAMPOS_INS = ('CLV_PLA','ID_ALUMNO','CLV_CURSO','CICLO','PERIODO','ELIMINADO',
              'SEXO','NOMBRE','A_PATERNO','A_MATERNO','F_INSCRIP','NVO_INGRES',
              'DIS_VISUAL','DIS_AUDITI','DIS_LENGUA','DIS_MOTRIZ','DIS_MENTAL','DIS_SIN')
CAMPOS_CURSO = ('CLV_PLA','CICLO','CLAVE_CURS','CLV_AREA','CLV_ESP',
                'NOM_CURSO','DOC_NOM','PERIODO','ELIMINADO','F_INICIO','F_TERMINO')
CAMPOS_ESP = ('CLV_AREA','CLV_ESP','NOM_ESP')
CATEGORIAS = {
    'inscripciones': ('INSCRIPCION.DBF','LISTAS.DBF','LISTAS01.DBF','ALUMNOS.DBF'),
    'programacion_docentes': ('PROG_CURSOS1.DBF','ESP.DBF','MATERIA.DBF','PERSONAL.DBF'),
    'discapacidad': ('INSCRIPCION.DBF','ALUMNOS.DBF'),
    'evaluacion': ('CALIF_EBC.DBF','CALIF_T.DBF','EXT.DBF','D_CALIF_EBC.DBF','D_CALIF_T.DBF'),
    'constancias_folios': ('T_CNTCON.DBF','T_D_CNTCON.DBF','T_CNTDIP.DBF','T_D_CNTDIP.DBF','FOLIOSCERT.DBF'),
    'plantel_catalogos': ('PLANTEL.DBF','AREA.DBF','ESP.DBF','ESCOLARIDAD.DBF'),
    'datos_sensibles': ('ALUMNOS.DBF','INSCRIPCION.DBF','PERSONAL.DBF','PERSONAL_VITAE.DBF'),
}
EXCLUIDAS = {'ACCESO.DBF','COKIES.DBF'}  # secretos/autenticación, no leer datos


def norma(x):
    s=unicodedata.normalize('NFKD', str(x or '').casefold())
    return ' '.join(''.join(c for c in s if not unicodedata.combining(c)).split())


def numero(x):
    s=str(x or '').strip()
    if not s or not re.fullmatch(r'\d+(?:\.0+)?', s):
        raise ValueError('ID o clave numérica inválida o vacía.')
    return str(int(float(s))) if '.' in s else str(int(s))


def limpio(x):
    return str(x or '').strip()


def fecha(x):
    s=limpio(x)
    if len(s)==8 and s.isdecimal():
        try: return datetime.strptime(s,'%Y%m%d').strftime('%Y-%m-%d')
        except ValueError: pass
    return None


def _encabezado(z, info):
    with z.open(info) as f:
        head=f.read(32)
        if len(head)!=32: raise ValueError('DBF truncado.')
        count=struct.unpack_from('<I',head,4)[0]
        hlen=struct.unpack_from('<H',head,8)[0]
        rlen=struct.unpack_from('<H',head,10)[0]
        if not 33<=hlen<=65535 or not 2<=rlen<=16384 or count>MAX_FILAS:
            raise ValueError('Encabezado DBF excede límites de seguridad.')
        desc=f.read(hlen-32)
        if len(desc)!=hlen-32: raise ValueError('Descriptores incompletos.')
    cols={}; offset=1
    for i in range(0,len(desc),32):
        d=desc[i:i+32]
        if len(d)<32 or d[0]==13: break
        name=d[:11].split(b'\0')[0].decode('latin1').strip().upper()
        typ=chr(d[11]); size=int(d[16])
        if not name or name in cols or size<=0: raise ValueError('Campo inválido o repetido.')
        cols[name]=(offset,size,typ)
        offset+=size
    if offset>rlen: raise ValueError('Campos mayores que registro DBF.')
    return count,hlen,rlen,cols


class CorteSISAE:
    def __init__(self,ruta):
        self.ruta=Path(ruta)
        if not self.ruta.is_file() or self.ruta.is_symlink() or self.ruta.suffix.lower()!='.zip':
            raise ValueError('Se necesita un ZIP SISAE local y regular.')
        self.z=ZipFile(self.ruta)
        self.index={}
        for i in self.z.infolist():
            if i.is_dir(): continue
            name=PurePosixPath(i.filename.strip()).name.upper()
            if name.endswith('.DBF'):
                if name in self.index: raise ValueError('Tabla DBF repetida: '+name)
                if i.file_size>MAX_TABLA: raise ValueError('Tabla DBF supera límite de lectura.')
                self.index[name]=i
        self._schemas={}
        self._cache={}

    def close(self):
        self._cache.clear()
        self.z.close()

    def __enter__(self): return self
    def __exit__(self,*a): self.close()

    def esquema(self,tabla):
        t=tabla.upper()
        if t not in self.index: raise ValueError('No existe la tabla: '+t)
        if t not in self._schemas:
            self._schemas[t]=_encabezado(self.z,self.index[t])
        return self._schemas[t]

    def inventario(self,tema=None,mostrar_campos=True):
        if tema and tema not in CATEGORIAS: raise ValueError('Tema desconocido.')
        tables = sorted(self.index) if tema is None else [x for x in CATEGORIAS[tema] if x in self.index]
        out=[]
        for t in tables:
            if t in EXCLUIDAS:
                out.append({'tabla':t,'acceso':'bloqueado (autenticación)'})
                continue
            n,_,_,cols=self.esquema(t)
            d={'tabla':t,'filas_cabecera':n,'columnas':len(cols)}
            if mostrar_campos: d['campos']=[{'nombre':k,'tipo':v[2]} for k,v in cols.items()]
            out.append(d)
        return {'tablas_dbf':len(self.index),'tema':tema or 'todos','tablas':out,
                'aviso':'Estructura técnica; no implica que todos los datos estén vigentes o completos.'}

    def leer(self,tabla,campos):
        t=tabla.upper()
        if t in EXCLUIDAS: raise PermissionError('No se permite abrir tablas de autenticación.')
        selected=tuple(campos)
        if (t,selected) in self._cache: return self._cache[(t,selected)]
        info=self.index.get(t)
        if not info: raise ValueError('Falta tabla '+t)
        n,hlen,rlen,cols=self.esquema(t)
        for c in selected:
            if c not in cols: raise ValueError(f'Falta columna {c} en {t}.')
        result=[]
        with self.z.open(info) as f:
            if len(f.read(hlen))!=hlen: raise ValueError('Cabecera truncada.')
            for _ in range(n):
                raw=f.read(rlen)
                if len(raw)!=rlen: raise ValueError('DBF truncado.')
                if raw[:1]==b'*': continue  # borrado físico FoxPro
                if raw[:1]!=b' ': raise ValueError('Marca DBF desconocida.')
                row={}
                for c in selected:
                    pos,size,typ=cols[c]
                    row[c]=raw[pos:pos+size].decode('cp1252','replace').strip()
                result.append(row)
        self._cache[(t,selected)]=result
        return result

    @staticmethod
    def _idpersona(r):
        return (limpio(r['CLV_PLA']),numero(r['ID_ALUMNO']))

    @staticmethod
    def _idcurso(r):
        return (limpio(r['CLV_PLA']),limpio(r['CICLO']),numero(r['CLV_CURSO']))

    def base(self,ciclo='2026-2027',periodo=None):
        if periodo is not None and str(periodo) not in ('1','2','3','4'):
            raise ValueError('Periodo fuera de 1–4.')
        grupos={}
        for g in self.leer('PROG_CURSOS1.DBF',CAMPOS_CURSO):
            if g['ELIMINADO'] not in ('','0'): continue
            k=(g['CLV_PLA'],g['CICLO'],numero(g['CLAVE_CURS']))
            if k in grupos: raise ValueError('Curso/grupo duplicado en programación.')
            grupos[k]=g
        enrolled=[]; sin_grupo=[]
        for r in self.leer('INSCRIPCION.DBF',CAMPOS_INS):
            if r['ELIMINADO'] not in ('','0') or r['CICLO']!=ciclo: continue
            if periodo and r['PERIODO']!=str(periodo): continue
            key=self._idcurso(r)
            if key not in grupos:
                sin_grupo.append(key)
                continue
            enrolled.append(r)
        if sin_grupo:
            raise ValueError(f'Hay {len(sin_grupo)} inscripciones sin curso asociado: conteo detenido.')
        unique={}; repetidas=0
        for r in enrolled:
            key=self._idpersona(r)+(r['CICLO'],r['PERIODO'],numero(r['CLV_CURSO']))
            if key in unique: repetidas+=1
            else: unique[key]=r
        return list(unique.values()), grupos, repetidas

    def _proc(self,ciclo,periodo,unidad,fuentes):
        return {'fuentes':fuentes,'ciclo':ciclo,'periodo_inscripcion':str(periodo) if periodo else 'todos los disponibles del ciclo',
                'unidad_conteo':unidad,'fecha_exportacion':'no confirmada',
                'ultima_inscripcion_no_es_corte':True,
                'tipo':'corte local; no consulta en vivo'}

    def discapacidad(self,ciclo='2026-2027',periodo=None,especialidad=None):
        rows,groups,rep=self.base(ciclo,periodo)
        if especialidad:
            catalog=self._especialidades()
            key=self._especialidad_clave(especialidad,catalog)
            rows=[r for r in rows if (groups[self._idcurso(r)]['CLV_AREA'],groups[self._idcurso(r)]['CLV_ESP'])==key]
        per=defaultdict(list)
        for r in rows: per[self._idpersona(r)].append(r)
        conteos={n:0 for n in CAMPOS_DIS}
        sexos={n:{'hombres':0,'mujeres':0,'sin_clasificar':0} for n in CAMPOS_DIS}
        personas_alguna=0; sin_disc=0; conflicto=0; sin_valor=0
        for key,rr in per.items():
            flags={n:set(limpio(r[c]) for r in rr) for n,c in CAMPOS_DIS.items()}
            sin_flags={limpio(r['DIS_SIN']) for r in rr}
            present={n for n,v in flags.items() if '1' in v}
            if any('0' in v and '1' in v for v in flags.values()) or (present and '1' in sin_flags) or (not present and '0' in sin_flags):
                conflicto+=1
            if all('' in v and len(v)==1 for v in flags.values()): sin_valor+=1
            sexo={norma(r['SEXO']) for r in rr}
            if sexo=={'hombre'}: sx='hombres'
            elif sexo=={'mujer'}: sx='mujeres'
            else: sx='sin_clasificar'
            for n in present:
                conteos[n]+=1; sexos[n][sx]+=1
            if present: personas_alguna+=1
            elif sin_flags=={'1'}: sin_disc+=1
        return {'estado':'requiere_revision' if conflicto or rep else 'calculado_con_corte',
                'personas_unicas_analizadas':len(per),'con_alguna_discapacidad':personas_alguna,
                'por_tipo':conteos,'por_tipo_y_sexo':sexos,
                'sin_discapacidad_declarada':sin_disc,
                'personas_con_flags_contradictorios':conflicto,
                'sin_valor_en_cinco_campos':sin_valor,
                'inscripciones_reiteradas':rep,
                'nota':'Un alumno con varias discapacidades puede contarse en varias categorías, pero una sola vez en «con alguna».',
                'procedencia':self._proc(ciclo,periodo,'personas únicas (por plantel e ID_ALUMNO)',
                                        ['INSCRIPCION.DBF','PROG_CURSOS1.DBF']+(['ESP.DBF'] if especialidad else []))}

    def _especialidades(self):
        return {(e['CLV_AREA'],e['CLV_ESP']):e['NOM_ESP'] for e in self.leer('ESP.DBF',CAMPOS_ESP)}

    def _especialidad_clave(self,nombre, catalog):
        match=[k for k,v in catalog.items() if norma(v)==norma(nombre)]
        if len(match)!=1: raise ValueError('Especialidad no localizada o ambigua en ESP.DBF.')
        return match[0]

    def alumno_cursos(self,id_alumno=None, nombre_completo=None, ciclo='2026-2027', periodo=None):
        if bool(id_alumno) == bool(nombre_completo):
            raise ValueError('Indica exactamente un identificador o nombre completo.')
        rows,groups,rep=self.base(ciclo,periodo)
        if id_alumno is not None:
            id_norm=numero(id_alumno)
            matches=[r for r in rows if numero(r['ID_ALUMNO'])==id_norm]
        else:
            s=norma(nombre_completo)
            if len(s)<7 or len(s.split())<2: raise ValueError('Se necesita el nombre completo, no una palabra aislada.')
            matches=[r for r in rows if norma(' '.join([r['NOMBRE'],r['A_PATERNO'],r['A_MATERNO']]))==s]
        personas={self._idpersona(r) for r in matches}
        if not personas:
            return {'estado':'sin_registro','numero_cursos':0,'cursos':[],
                    'nota':'No hay inscripción en el ciclo/periodo consultado; no significa que nunca se haya inscrito.',
                    'procedencia':self._proc(ciclo,periodo,'cursos distintos por persona', ['INSCRIPCION.DBF','PROG_CURSOS1.DBF'])}
        if len(personas)>1: raise ValueError('Identificación ambigua: coincide más de una persona o plantel.')
        bycourse={}
        for r in matches:
            k=self._idcurso(r)
            g=groups[k]
            bycourse[k]={
                'curso':g['NOM_CURSO'],
                'periodos_inscripcion':sorted({rr['PERIODO'] for rr in matches if self._idcurso(rr)==k}),
                'especialidad_codigo':g['CLV_ESP'],
            }
        return {'estado':'encontrado','numero_cursos':len(bycourse),
                'numero_inscripciones':len(matches),
                'cursos':sorted(bycourse.values(),key=lambda x:x['curso']),
                'inscripciones_reiteradas_en_corte':rep,
                'aviso':'«Inscrito» significa que figura en el corte, no que el curso siga activo hoy.',
                'procedencia':self._proc(ciclo,periodo,'cursos distintos para una persona', ['INSCRIPCION.DBF','PROG_CURSOS1.DBF'])}

    def resumen(self,ciclo='2026-2027',periodo=None,especialidad=None):
        rows,groups,rep=self.base(ciclo,periodo)
        catalog=self._especialidades()
        if especialidad:
            wanted=self._especialidad_clave(especialidad,catalog)
            rows=[r for r in rows if (groups[self._idcurso(r)]['CLV_AREA'],groups[self._idcurso(r)]['CLV_ESP'])==wanted]
        people={self._idpersona(r) for r in rows}
        course_counts=Counter(self._idcurso(r) for r in rows)
        low=sum(n<10 for n in course_counts.values())
        return {'inscripciones':len(rows),'personas_unicas':len(people),
                'grupos_con_inscripciones':len(course_counts),'grupos_con_menos_de_10_inscripciones':low,
                'inscripciones_reiteradas_detectadas':rep,
                'advertencia':'Los grupos sin inscripciones no están incluidos en «grupos con inscripciones».',
                'procedencia':self._proc(ciclo,periodo,'inscripciones y personas únicas',
                                        ['INSCRIPCION.DBF','PROG_CURSOS1.DBF','ESP.DBF'])}

    def docente(self, nombre, ciclo='2026-2027', periodo=None):
        if len(norma(nombre))<5: raise ValueError('Especifica más del nombre del docente.')
        rows,grupos,rep=self.base(ciclo,periodo)
        matches={k:g for k,g in grupos.items() if g['CICLO']==ciclo
                 and norma(nombre) in norma(g['DOC_NOM'])}
        docentes={norma(g['DOC_NOM']) for g in matches.values()}
        if len(docentes)>1: raise ValueError('Coinciden varios docentes; especifica un nombre más preciso.')
        if not matches:
            return {'estado':'sin_registro','grupos_programados':0,'inscripciones':0,
                    'procedencia':self._proc(ciclo,periodo,'grupos e inscripciones',['PROG_CURSOS1.DBF','INSCRIPCION.DBF'])}
        grupos_con_dato={k for k in matches if periodo is None or any(self._idcurso(r)==k for r in rows)}
        relevant=[r for r in rows if self._idcurso(r) in matches]
        return {'estado':'calculado_con_corte','docente':next(iter(matches.values()))['DOC_NOM'],
                'grupos_programados':len(matches) if periodo is None else len(grupos_con_dato),
                'grupos_con_inscripciones':len({self._idcurso(r) for r in relevant}),
                'inscripciones':len(relevant),'personas_unicas':len({self._idpersona(r) for r in relevant}),
                'cursos':sorted({g['NOM_CURSO'] for g in matches.values()}),
                'nota':'Para filtro de periodo, el ámbito son las inscripciones del trimestre, no todos los grupos del ciclo.',
                'procedencia':self._proc(ciclo,periodo,'inscripciones, personas y grupos',['PROG_CURSOS1.DBF','INSCRIPCION.DBF'])}

    def disponibilidad_evaluaciones(self,ciclo='2026-2027',periodo=None):
        """Solo describe qué indicadores aparecen capturados; no suma procesos incompatibles."""
        out=[]
        for tabla in ('CALIF_EBC.DBF','CALIF_T.DBF','EXT.DBF'):
            if tabla not in self.index: continue
            sel=('CICLO','PERIODO','ACRED','NOACRED','DESER')
            rows=self.leer(tabla,sel)
            rows=[r for r in rows if r['CICLO']==ciclo and (not periodo or r['PERIODO']==str(periodo))]
            out.append({'tabla':tabla,'filas':len(rows),
                'marcas_no_vacias':{c:sum(bool(limpio(r[c])) for r in rows) for c in ('ACRED','NOACRED','DESER')}})
        return {'estado':'diagnostico_no_consolidado','fuentes':out,
                'advertencia':'No sumes marcas ACRED/NOACRED/DESER entre tablas hasta verificar códigos, duplicados y estados. Una marca no equivale necesariamente a acreditación final.',
                'procedencia':self._proc(ciclo,periodo,'filas con marcas capturadas por tabla',
                        [r['tabla'] for r in out])}
