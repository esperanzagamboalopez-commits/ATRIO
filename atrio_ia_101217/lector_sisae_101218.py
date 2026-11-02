#!/usr/bin/env python3
"""Lector agregado y de SOLO LECTURA de cortes SISAE FoxPro/DBF en ZIP.
Versión revisada: conciliación por claves únicas; diagnóstico de reiteraciones en LISTAS.

No extrae ZIP, no imprime datos personales ni altera ATRIO.
Uso: python3 lector_sisae.py '/ruta/SISAE.zip' --especialidad 'Artes Gráficas' --ciclo 2026-2027 --periodo 1
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import struct
import unicodedata
from zipfile import ZipFile, BadZipFile

TABLAS = ('ESP.DBF', 'PROG_CURSOS1.DBF', 'INSCRIPCION.DBF', 'LISTAS.DBF', 'LISTAS01.DBF')
CAMPOS = {
    'ESP.DBF': ('CLV_AREA', 'CLV_ESP', 'NOM_ESP'),
    'PROG_CURSOS1.DBF': ('CLV_PLA', 'CLV_AREA', 'CLV_ESP', 'CLAVE_CURS', 'CICLO', 'PERIODO', 'NOM_CURSO', 'ELIMINADO'),
    'INSCRIPCION.DBF': ('CLV_PLA', 'ID_ALUMNO', 'CLV_CURSO', 'CICLO', 'PERIODO', 'F_INSCRIP', 'ELIMINADO'),
    'LISTAS.DBF': ('CLV_PLA', 'ID_ALUMNO', 'CLAVE_CURS', 'CICLO', 'PERIODO', 'CLV_ESP'),
    'LISTAS01.DBF': ('CLV_PLA', 'ID_ALUMNO', 'CLAVE_CURS', 'PERIODO'),
}


def normalizar(s: str) -> str:
    s = unicodedata.normalize('NFKD', str(s).casefold())
    return ' '.join(''.join(c for c in s if not unicodedata.combining(c)).split())


def numero_clave(s) -> str:
    """Usa texto canónico, evitando duplicaciones por ceros a la izquierda."""
    s = str(s).strip()
    if not s: return ''
    if not s.isdecimal(): raise ValueError('Se encontró una clave de curso/ID no numérica.')
    return str(int(s))


def _leer_dbf(z: ZipFile, info, seleccion: tuple[str, ...]):
    # Abre directamente la entrada comprimida: no copia expedientes a disco.
    if info.file_size > 90_000_000:
        raise ValueError('Tabla demasiado grande para esta lectura de diagnóstico.')
    with z.open(info) as f:
        h = f.read(32)
        if len(h) != 32: raise ValueError('Encabezado DBF incompleto.')
        n = struct.unpack_from('<I', h, 4)[0]
        hlen = struct.unpack_from('<H', h, 8)[0]
        rlen = struct.unpack_from('<H', h, 10)[0]
        if not 33 <= hlen <= 65535 or not 2 <= rlen <= 10000:
            raise ValueError('Encabezado DBF inválido.')
        if n > 3_000_000: raise ValueError('Demasiados registros para esta revisión.')
        descr = f.read(hlen-32)
        fields = {}
        cursor = 1
        for i in range(0, len(descr), 32):
            b = descr[i:i+32]
            if len(b) < 32 or b[0] == 0x0d: break
            nombre = b[:11].split(b'\0',1)[0].decode('latin1').strip()
            tipo = chr(b[11])
            longitud = int(b[16])
            if nombre in seleccion:
                fields[nombre] = (cursor, longitud, tipo)
            cursor += longitud
        faltan = set(seleccion) - fields.keys()
        if faltan:
            raise ValueError('Faltan campos obligatorios: ' + ', '.join(sorted(faltan)))
        if cursor > rlen: raise ValueError('Campos DBF exceden registro declarado.')
        filas=[]
        eliminadas=0
        for _ in range(n):
            rec=f.read(rlen)
            if len(rec) != rlen: raise ValueError('DBF truncado.')
            if rec[:1] == b'*':
                eliminadas += 1
                continue
            if rec[:1] != b' ':
                raise ValueError('Marca de registro DBF no reconocida.')
            row={}
            for nombre in seleccion:
                inicio,longitud,tipo=fields[nombre]
                raw=rec[inicio:inicio+longitud]
                row[nombre]=raw.decode('cp1252','replace').strip()
            filas.append(row)
        return filas, eliminadas


def _fecha_en_nombre(ruta: Path):
    # Fecha nominal del archivo, NO garantía de que sea la fecha de extracción.
    m=re.search(r'(?<!\d)(20\d\d)[._-](\d\d)[._-](\d\d)(?!\d)',ruta.name)
    if not m:return None
    try:return datetime(int(m[1]),int(m[2]),int(m[3])).strftime('%Y-%m-%d')
    except ValueError:return None


def analizar(ruta: Path, especialidad: str, ciclo: str = '2026-2027', periodo: str | None = None) -> dict:
    if not ruta.is_file() or not ruta.suffix.lower() == '.zip':
        raise ValueError('Se necesita la ruta de un archivo ZIP existente.')
    if periodo is not None and periodo not in ('1','2','3','4'):
        raise ValueError('Periodo inválido: debe ser 1, 2, 3 o 4.')
    try:
        with ZipFile(ruta) as z:
            # Los ZIP de SISAE contienen nombres como "INSCRIPCION.DBF        "
            # (espacios de relleno), por eso es obligatorio strip().
            index={}
            for info in z.infolist():
                if info.is_dir():continue
                name=Path(info.filename.strip()).name.upper()
                if name in TABLAS:
                    if name in index: raise ValueError('Tabla repetida en ZIP: '+name)
                    index[name]=info
            requeridas=('ESP.DBF','PROG_CURSOS1.DBF','INSCRIPCION.DBF','LISTAS.DBF')
            if not all(n in index for n in requeridas):
                raise ValueError('Faltan tablas: '+', '.join(n for n in requeridas if n not in index))
            rows={}
            eliminadas={}
            for t in requeridas:
                rows[t], eliminadas[t]=_leer_dbf(z,index[t],CAMPOS[t])
            # LISTAS01 es auxiliar (y puede estar duplicada); no entra al conteo.
            n_dbf=sum(not i.is_dir() and i.filename.strip().lower().endswith('.dbf') for i in z.infolist())
    except BadZipFile as e:
        raise ValueError('El archivo no es un ZIP válido.') from e
    esp=rows['ESP.DBF']
    candidatas=[e for e in esp if normalizar(e['NOM_ESP']) == normalizar(especialidad)]
    if len(candidatas) != 1:
        raise ValueError('La especialidad no tiene una coincidencia única en ESP.DBF. '
                         'Opciones: '+', '.join(e['NOM_ESP'] for e in esp))
    e=candidatas[0]
    grupos={}
    for r in rows['PROG_CURSOS1.DBF']:
        if r['ELIMINADO'] not in ('','0'):continue
        k=(r['CLV_PLA'],r['CICLO'],numero_clave(r['CLAVE_CURS']))
        if k in grupos: raise ValueError('Clave de grupo ambigua en PROG_CURSOS1.DBF.')
        grupos[k]=r
    inscripciones=[]
    sin_grupo=0
    filtradas=[]
    for r in rows['INSCRIPCION.DBF']:
        if r['ELIMINADO'] not in ('','0'):continue
        if r['CICLO'] != ciclo:continue
        if periodo is not None and r['PERIODO'] != periodo:continue
        k=(r['CLV_PLA'],r['CICLO'],numero_clave(r['CLV_CURSO']))
        g=grupos.get(k)
        if g is None:
            sin_grupo += 1
            continue
        if g['CLV_AREA']==e['CLV_AREA'] and g['CLV_ESP']==e['CLV_ESP']:
            inscripciones.append(r)
            filtradas.append(g)
    if sin_grupo:
        raise ValueError(f'{sin_grupo} inscripciones del ámbito no enlazan a un grupo. No se emite conteo parcial.')
    # Validamos por (plantel, curso, alumno), no por multiplicidad de filas.
    # LISTAS.DBF puede tener múltiples filas para una misma inscripción.
    # Esas reiteraciones se INFORMAN, pero no se convierten en matrícula.
    def clave_ins(r):
        return (r['CLV_PLA'], r['CICLO'], r['PERIODO'],
                numero_clave(r['CLV_CURSO']), numero_clave(r['ID_ALUMNO']))

    def clave_lista(r):
        return (r['CLV_PLA'], r['CICLO'], r['PERIODO'],
                numero_clave(r['CLAVE_CURS']), numero_clave(r['ID_ALUMNO']))

    claves_ins = Counter(clave_ins(r) for r in inscripciones)
    # Conjunto de grupos de esta especialidad en el ciclo; no depende de que
    # tengan inscripciones, así se detectan también LISTAS sin INSCRIPCION.
    claves_grupos_esp = {
        (g['CLV_PLA'], numero_clave(g['CLAVE_CURS']))
        for g in grupos.values()
        if g['CICLO'] == ciclo and
        g['CLV_AREA'] == e['CLV_AREA'] and g['CLV_ESP'] == e['CLV_ESP']
    }
    filas_listas = [
        r for r in rows['LISTAS.DBF']
        if r['CICLO'] == ciclo
        and (periodo is None or r['PERIODO'] == periodo)
        and r['CLV_ESP'] == e['CLV_ESP']
        and (r['CLV_PLA'], numero_clave(r['CLAVE_CURS'])) in claves_grupos_esp
    ]
    claves_lista = Counter(clave_lista(r) for r in filas_listas)
    ids_ins, ids_listas = set(claves_ins), set(claves_lista)
    solo_ins = len(ids_ins - ids_listas)
    solo_listas = len(ids_listas - ids_ins)
    coincide = not solo_ins and not solo_listas
    repetidas_listas = len(filas_listas) - len(ids_listas)
    repetidas_ins = len(inscripciones) - len(ids_ins)
    faltan_ids = sum(not r['ID_ALUMNO'].strip() for r in inscripciones)
    personas = {(r['CLV_PLA'], numero_clave(r['ID_ALUMNO']))
                for r in inscripciones if r['ID_ALUMNO'].strip()}
    cursos = {numero_clave(g['CLAVE_CURS']):g['NOM_CURSO'] for g in filtradas}
    cortes = sorted(x for x in (r['F_INSCRIP'] for r in rows['INSCRIPCION.DBF'])
                    if len(x)==8 and x.isdecimal())
    cortes_especialidad = sorted(x for x in (r['F_INSCRIP'] for r in inscripciones)
                                if len(x)==8 and x.isdecimal())
    def formatear_fecha(xs):
        return f'{xs[-1][:4]}-{xs[-1][4:6]}-{xs[-1][6:]}' if xs else None
    advertencias = []
    if repetidas_listas:
        advertencias.append(
            f'LISTAS.DBF contiene {repetidas_listas} filas reiteradas: '
            'no se suman a la matrícula. Se compararon identificadores únicos.'
        )
    if repetidas_ins:
        advertencias.append(
            f'INSCRIPCION.DBF contiene {repetidas_ins} combinaciones repetidas; '
            'requiere revisión de la fuente principal.'
        )
    if not coincide:
        advertencias.append(
            f'Diferencias entre fuentes: {solo_ins} solo en INSCRIPCION; '
            f'{solo_listas} solo en LISTAS.'
        )
    if faltan_ids:
        advertencias.append(f'{faltan_ids} inscripciones sin identificador de alumno.')
    estado = 'verificado' if coincide and not faltan_ids and not repetidas_ins else 'requiere_revision'
    respuesta={
        'estado':estado,
        'especialidad':e['NOM_ESP'], 'codigo_especialidad':e['CLV_ESP'],
        'ciclo':ciclo, 'periodo':periodo or 'todos los periodos del ciclo',
        'inscripciones':len(inscripciones),
        'inscripciones_claves_unicas':len(ids_ins),
        'inscripciones_filas_reiteradas':repetidas_ins,
        'listas_filas':len(filas_listas),
        'listas_claves_unicas':len(ids_listas),
        'listas_filas_reiteradas':repetidas_listas,
        'solo_inscripcion':solo_ins,
        'solo_listas':solo_listas,
        'advertencias':advertencias,
        'personas_unicas':len(personas) if not faltan_ids else None,
        'grupos_con_inscripciones':len(cursos),
        'cursos':sorted(cursos.values()),
        'fuentes':['ESP.DBF','PROG_CURSOS1.DBF','INSCRIPCION.DBF','LISTAS.DBF'],
        'coincide_con_listas':coincide,
        'dbf_en_zip':n_dbf,
        'ultima_fecha_inscripcion_registrada':formatear_fecha(cortes),
        'ultima_fecha_inscripcion_especialidad':formatear_fecha(cortes_especialidad),
        'fecha_nominal_del_archivo':_fecha_en_nombre(ruta),
        'aviso':'Archivo histórico/parcial: no representa necesariamente la matrícula actual de SISAE.'
    }
    return respuesta


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip',type=Path)
    parser.add_argument('--especialidad',required=True)
    parser.add_argument('--ciclo',default='2026-2027')
    parser.add_argument('--periodo',choices=('1','2','3','4'))
    args=parser.parse_args()
    try:
        print(json.dumps(analizar(args.zip,args.especialidad,args.ciclo,args.periodo),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,RuntimeError) as exc:
        parser.exit(1,'ERROR: '+str(exc)+'\n')

if __name__=='__main__':main()
