# -*- coding: utf-8 -*-
""" 
Módulo de Auditoría SISAE: conciliación histórica de alumnos e inscripciones.

Conserva el punto de entrada render_auditoria_sisae() para que el panel actual
pueda seguir llamándolo sin cambiar sus demás módulos.

Este archivo reemplaza únicamente el módulo de auditoría anterior. No modifica
centro.py, los ZIP originales ni otras partes de la aplicación.
"""

from __future__ import annotations

import html
import math
import re
import os
import io
import json
import uuid
import hashlib
import sqlite3
import zipfile
from pathlib import Path
from contextlib import contextmanager
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import streamlit as st
import centro as C


# -----------------------------------------------------------------------------
# CONFIGURACIÓN LOCAL DEL MÓDULO
# -----------------------------------------------------------------------------
TABLAS_CLAVE = (
    "ALUMNOS.DBF",
    "INSCRIPCION.DBF",
    "EXT.DBF",
    "PROG_CURSOS1.DBF",
)

TABLAS_EVIDENCIA_CURSO = (
    "EXT.DBF",
    "CALIF_EBC.DBF",
    "CALIF_LINEA.DBF",
    "CALIF_ROCO.DBF",
    "CALIF_T.DBF",
    "LISTAS.DBF",
    "LISTAS01.DBF",
    "PASO_LIST.DBF",
)

CAMPOS_CLAVE_CURSO = ("CLV_CURSO", "CLAVE_CURS", "CLV_CURS")


# -----------------------------------------------------------------------------
# NORMALIZACIÓN SEGURA DE VALORES Y TABLAS
# -----------------------------------------------------------------------------
def _vacio(valor: Any) -> bool:
    if valor is None:
        return True
    try:
        return bool(pd.isna(valor))
    except Exception:
        return False


def _texto(valor: Any) -> str:
    """Convierte números, fechas, bytes y texto sin producir '123.0'."""
    if _vacio(valor):
        return ""
    if isinstance(valor, bytes):
        try:
            return valor.decode("latin-1", errors="replace").strip()
        except Exception:
            return str(valor).strip()
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if math.isfinite(valor) and valor.is_integer():
            return str(int(valor))
        return str(valor).strip()
    return str(valor).replace("\x00", "").strip()


def _clave(valor: Any) -> str:
    """Normaliza claves numéricas/textuales sin alterar su contenido útil."""
    s = _texto(valor).strip()
    if not s:
        return ""
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".", 1)[0]
    return s.upper()


def _normalizar_curp(valor: Any) -> str:
    s = re.sub(r"\s+", "", _texto(valor)).upper()
    # No se descartan personas por CURP incompleta; una CURP no válida
    # simplemente no se usa como identificador fuerte.
    return s if len(s) == 18 else ""


def _nombre(row: Dict[str, Any]) -> str:
    paterno = _texto(row.get("A_PATERNO"))
    materno = _texto(row.get("A_MATERNO"))
    nombres = _texto(row.get("NOMBRE"))
    # En la ficha se presenta NOMBRES + APELLIDO PATERNO + APELLIDO MATERNO.
    completo = " ".join(x for x in (nombres, paterno, materno) if x).strip()
    if completo:
        return re.sub(r"\s+", " ", completo)
    return _texto(row.get("NOM_EST")) or "Nombre no disponible"


def _nombre_busqueda(valor: str) -> str:
    s = unicodedata.normalize("NFD", _texto(valor).upper())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]", "", s)


def _fecha(valor: Any) -> Optional[date]:
    if _vacio(valor):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = _texto(valor)
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except Exception:
            continue
    return None


def _fecha_mostrar(valor: Any) -> str:
    d = _fecha(valor)
    return d.strftime("%d/%m/%Y") if d else "No disponible"


def _valor(row: Dict[str, Any], *campos: str) -> Any:
    for campo in campos:
        key = campo.upper().strip()
        if key in row and not _vacio(row.get(key)) and _texto(row.get(key)) != "":
            return row.get(key)
    return ""


def _filas(tabla: Any) -> List[Dict[str, Any]]:
    """Admite la lista de diccionarios que entrega centro.sisae_bytes y DataFrame."""
    if tabla is None:
        return []
    if isinstance(tabla, pd.DataFrame):
        origen = tabla.to_dict(orient="records")
    elif isinstance(tabla, dict):
        # Por si el lector entrega un contenedor con la lista bajo una propiedad.
        for k in ("rows", "records", "data", "registros"):
            if k in tabla and isinstance(tabla[k], (list, tuple, pd.DataFrame)):
                return _filas(tabla[k])
        origen = [tabla]
    elif isinstance(tabla, (list, tuple)):
        origen = list(tabla)
    else:
        try:
            origen = list(tabla)
        except Exception:
            return []

    resultado = []
    for registro in origen:
        if isinstance(registro, dict):
            resultado.append({str(k).strip().upper(): v for k, v in registro.items()})
        elif hasattr(registro, "to_dict"):
            try:
                d = registro.to_dict()
                resultado.append({str(k).strip().upper(): v for k, v in d.items()})
            except Exception:
                continue
    return resultado


def _normalizar_tablas(tables: Any) -> Dict[str, List[Dict[str, Any]]]:
    if not isinstance(tables, dict):
        raise ValueError("centro.sisae_bytes no devolvió un diccionario de tablas.")

    normalizadas: Dict[str, List[Dict[str, Any]]] = {}
    for nombre, contenido in tables.items():
        nombre_limpio = str(nombre).replace("\\", "/").strip()
        nombre_limpio = PurePosixPath(nombre_limpio).name.strip().upper()
        if not nombre_limpio:
            continue
        normalizadas[nombre_limpio] = _filas(contenido)
    return normalizadas


def _tablas_opcionales(zip_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    """Lee ALUMNOS.DBF y EXT.DBF si existen. Son opcionales: sin ellas la auditoría sigue,
    pero la evidencia de alumnos y de EXT aparece como no localizada."""
    resultado: Dict[str, List[Dict[str, Any]]] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        nombres = {Path(n.strip()).name.upper(): n for n in z.namelist()}
        for nombre in ("ALUMNOS.DBF", "EXT.DBF", "LISTAS01.DBF", "PASO_LIST.DBF", "LISTAS.DBF"):
            if nombre in nombres:
                resultado[nombre] = _filas(C.dbf(z.read(nombres[nombre])))
    return resultado


def extraer_datos(zip_bytes: bytes) -> Dict[str, Any]:
    """Lee un ZIP SISAE sin modificarlo y devuelve sus tablas normalizadas."""
    if not zip_bytes:
        raise ValueError("El archivo ZIP está vacío.")
    try:
        tablas_originales = C.sisae_bytes(zip_bytes)
        tablas = _normalizar_tablas(tablas_originales)
        tablas.update(_tablas_opcionales(zip_bytes))
    except Exception as exc:
        raise RuntimeError(f"No fue posible leer el ZIP mediante centro.sisae_bytes: {exc}") from exc

    faltantes = [t for t in ("INSCRIPCION.DBF",) if t not in tablas]
    if faltantes:
        disponibles = ", ".join(sorted(tablas.keys())[:20]) or "ninguna"
        raise ValueError(
            "El ZIP no contiene la tabla necesaria INSCRIPCION.DBF. "
            f"Tablas detectadas: {disponibles}"
        )

    return {
        "tablas": tablas,
        "inscripciones": tablas.get("INSCRIPCION.DBF", []),
        "alumnos": tablas.get("ALUMNOS.DBF", []),
        "cursos": tablas.get("PROG_CURSOS1.DBF", []),
        "ext": tablas.get("EXT.DBF", []),
    }


# -----------------------------------------------------------------------------
# IDENTIFICACIÓN DE PERSONAS E INSCRIPCIONES
# -----------------------------------------------------------------------------
def _id_alumno(row: Dict[str, Any]) -> str:
    return _clave(_valor(row, "ID_ALUMNO", "ID", "NUM_CONTROL", "NO_CONTROL"))


def _curp(row: Dict[str, Any]) -> str:
    return _normalizar_curp(_valor(row, "CURP"))


def _curso(row: Dict[str, Any]) -> str:
    return _clave(_valor(row, *CAMPOS_CLAVE_CURSO))


def _periodo(row: Dict[str, Any]) -> str:
    return _clave(_valor(row, "PERIODO", "PERIOD"))


def _identidad(row: Dict[str, Any]) -> str:
    curp = _curp(row)
    if curp:
        return "CURP:" + curp
    alumno_id = _id_alumno(row)
    if alumno_id:
        return "ID:" + alumno_id
    # No se fusionan personas sin identificadores. Se mantienen por separado.
    return "SIN_ID:" + _clave(row.get("_RECNO") or id(row))


def _fecha_inscripcion(row: Dict[str, Any]) -> Optional[date]:
    return _fecha(_valor(row, "F_INSCRIP", "FECHA_INSCRIP", "F_INSCRIPCION"))


def _es_eliminado(row: Dict[str, Any]) -> Optional[bool]:
    for campo in ("ELIMINADO", "DELETED", "_DELETED", "_DELETED_PHYSICAL", "BORRADO"):
        if campo in row:
            valor = row.get(campo)
            if isinstance(valor, bool):
                return valor
            s = _texto(valor).upper()
            if s in {"1", "S", "SI", "TRUE", "T", "Y", "YES", "*", "X"}:
                return True
            if s in {"0", "N", "NO", "FALSE", "F", ""}:
                return False
    return None


def _normalizar_instructor(valor: Any) -> str:
    s = re.sub(r"^\s*\([^)]+\)\s*", "", _texto(valor)).strip()
    if not s:
        return "No disponible"
    # Se conserva el orden exacto que trae SISAE; solo se normaliza la capitalización.
    partes = s.split()
    minusculas = {"de", "del", "la", "las", "los", "y", "e", "da", "das", "do", "dos"}
    resultado = []
    for i, palabra in enumerate(partes):
        bajo = palabra.lower()
        if i > 0 and bajo in minusculas:
            resultado.append(bajo)
        else:
            # Mayúscula tras espacio, guion o apóstrofo (García-López, D'Arco)
            resultado.append(re.sub(r"(^|[-'’])(\w)", lambda m: m.group(1) + m.group(2).upper(), bajo))
    return " ".join(resultado)


def _buscar_curso(tablas: Dict[str, List[Dict[str, Any]]], clave: str) -> Dict[str, Any]:
    if not clave:
        return {}
    for tabla in ("PROG_CURSOS1.DBF", "EXT.DBF", "CALIF_EBC.DBF", "CALIF_LINEA.DBF", "CALIF_ROCO.DBF", "CALIF_T.DBF"):
        for row in tablas.get(tabla, []):
            if _curso(row) == clave:
                return row
    return {}


def _buscar_ext_persona_curso(
    tablas: Dict[str, List[Dict[str, Any]]], row_insc: Dict[str, Any]
) -> Dict[str, Any]:
    clave = _curso(row_insc)
    curp = _curp(row_insc)
    alumno_id = _id_alumno(row_insc)
    candidatos = []
    for row in tablas.get("EXT.DBF", []):
        if _curso(row) != clave:
            continue
        coincide = bool(curp and _curp(row) == curp) or bool(alumno_id and _id_alumno(row) == alumno_id)
        if coincide:
            candidatos.append(row)
    return candidatos[0] if candidatos else {}


def _horario_curso(info: Dict[str, Any]) -> str:
    # EXT y algunas tablas de evaluación guardan los extremos del horario.
    h1 = _texto(_valor(info, "HORARIO"))
    h2 = _texto(_valor(info, "HORARIO2"))
    dias = []
    for n in range(1, 4):
        dia = _texto(_valor(info, f"DIA{n}"))
        if dia and dia not in dias:
            dias.append(dia)
    if h1 and h2:
        tramo = f"{h1} a {h2}"
    elif h1:
        tramo = h1
    elif h2:
        tramo = h2
    else:
        tramos = []
        for n in range(1, 4):
            de = _texto(_valor(info, f"DIA{n}_DE"))
            hasta = _texto(_valor(info, f"DIA{n}_A"))
            if de or hasta:
                tramos.append(f"{de} a {hasta}".strip())
        tramo = "; ".join(tramos)
    dias_normalizados = []
    traducciones = {"miercoles": "miércoles", "sabado": "sábado"}
    for dia in dias:
        dias_normalizados.append(traducciones.get(dia.lower(), dia))
    if dias_normalizados and tramo:
        return f"{', '.join(dias_normalizados)}; {tramo}"
    if dias_normalizados:
        return ", ".join(dias_normalizados)
    return tramo or "No disponible"


def _taller(info: Dict[str, Any], tablas: Dict[str, List[Dict[str, Any]]]) -> str:
    directo = _texto(_valor(info, "TALLER", "NO_TALLER", "NUM_TALLER", "TALLER_AULA", "AULA", "NO_AULA"))
    if directo:
        return directo

    # SISAE relaciona la ubicación mediante CLV_AA1/2/3 de PROG_CURSOS1
    # con CLV_AAE de TEMPLAY_AULA; DESCRIP suele ser TALLER01/AULA01.
    claves_aula = {
        _clave(_valor(info, "CLV_AA1")),
        _clave(_valor(info, "CLV_AA2")),
        _clave(_valor(info, "CLV_AA3")),
    } - {""}
    if claves_aula:
        for aula in tablas.get("TEMPLAY_AULA.DBF", []):
            clave_aula = _clave(_valor(aula, "CLV_AAE"))
            if clave_aula and clave_aula in claves_aula:
                descripcion = _texto(_valor(aula, "DESCRIP"))
                numero = _texto(_valor(aula, "NUM_AULA"))
                if descripcion.upper().startswith("TALLER"):
                    return numero.zfill(2) if numero else descripcion.replace("TALLER", "").strip()
                if descripcion:
                    return descripcion
                return numero.zfill(2) if numero else "No disponible"
    return "No disponible"


def _enriquecer_inscripcion(
    row: Dict[str, Any],
    corte: Dict[str, Any],
) -> Dict[str, Any]:
    tablas = corte["tablas"]
    clave = _curso(row)
    programacion = _buscar_curso(tablas, clave)
    ext_persona = _buscar_ext_persona_curso(tablas, row)

    # La fila individual de EXT puede aportar horario/fechas/resultados; la
    # programación aporta el nombre e instructor del grupo.
    nombre_curso = (
        _texto(_valor(row, "NOM_CUR", "NOM_CURSO"))
        or _texto(_valor(programacion, "NOM_CURSO", "NOM_CUR", "DES_CURSO"))
        or _texto(_valor(ext_persona, "NOM_CURSO", "NOM_CUR"))
        or (f"Curso {clave}" if clave else "Curso no identificado")
    )
    instructor_raw = (
        _valor(ext_persona, "DOC_NOM", "INSTRUCTOR", "DOCENTE")
        or _valor(programacion, "DOC_NOM", "INSTRUCTOR", "DOCENTE")
    )

    inicio = (
        _valor(ext_persona, "F_INICIO", "FECHA_INICIO")
        or _valor(programacion, "F_INICIO", "FECHA_INICIO")
    )
    termino = (
        _valor(ext_persona, "F_TERMINO", "FECHA_TERMINO")
        or _valor(programacion, "F_TERMINO", "FECHA_TERMINO")
    )
    horas = (
        _valor(ext_persona, "HRS_CURSO", "HORAS", "DURACION")
        or _valor(programacion, "HRS_CURSO", "HORAS", "DURACION")
    )

    horario_info = dict(programacion)
    horario_info.update({k: v for k, v in ext_persona.items() if not _vacio(v)})

    return {
        "id_alumno": _id_alumno(row),
        "curp": _curp(row) or _texto(_valor(row, "CURP")),
        "nombre": _nombre(row),
        "identidad": _identidad(row),
        "periodo": _periodo(row),
        "clave_curso": clave,
        "nombre_curso": nombre_curso,
        "fecha_inscripcion": _fecha_mostrar(_fecha_inscripcion(row)),
        "instructor": _normalizar_instructor(instructor_raw),
        "inicio": _fecha_mostrar(inicio),
        "termino": _fecha_mostrar(termino),
        "horario": _horario_curso(horario_info),
        "duracion": (_texto(horas) + " horas") if _texto(horas) else "No disponible",
        "taller": _taller(horario_info, tablas),
        "estatus": _texto(_valor(row, "ESTATUS")) or "No disponible",
        "calificacion": _texto(_valor(row, "CALIFICACION", "RESULTADO")) or "No disponible",
        "eliminado": _es_eliminado(row),
        "registro": row,
    }


def _misma_persona(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    ca, cb = _curp(a), _curp(b)
    if ca and cb and ca == cb:
        return True
    ia, ib = _id_alumno(a), _id_alumno(b)
    if ia and ib and ia == ib:
        return True
    return False


def _misma_inscripcion(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return (
        _misma_persona(a, b)
        and bool(_curso(a))
        and _curso(a) == _curso(b)
        and _periodo(a) == _periodo(b)
    )


def _comparar_inscripciones(
    anteriores: List[Dict[str, Any]], actuales: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple[Dict[str, Any], Dict[str, Any], str]]]:
    """Empareja por CURP + curso + periodo; usa ID como respaldo.

    No utiliza el nombre como llave automática, para no unir personas distintas.
    Devuelve faltantes, nuevos y coincidencias (con tipo de coincidencia).
    """
    usados_actuales = set()
    coincidencias = []
    faltantes = []

    # Primera pasada: CURP + curso + periodo, aunque el ID_ALUMNO haya cambiado.
    for viejo in anteriores:
        encontrado = None
        for idx, nuevo in enumerate(actuales):
            if idx in usados_actuales:
                continue
            if (
                _curp(viejo)
                and _curp(viejo) == _curp(nuevo)
                and _curso(viejo) == _curso(nuevo)
                and _periodo(viejo) == _periodo(nuevo)
            ):
                encontrado = (idx, nuevo, "CURP + curso + periodo")
                break
        if encontrado:
            idx, nuevo, metodo = encontrado
            usados_actuales.add(idx)
            coincidencias.append((viejo, nuevo, metodo))

    # Segunda pasada: ID_ALUMNO + curso + periodo cuando CURP falta o fue corregida.
    pendientes = [v for v in anteriores if not any(v is x[0] for x in coincidencias)]
    for viejo in pendientes:
        encontrado = None
        for idx, nuevo in enumerate(actuales):
            if idx in usados_actuales:
                continue
            id_v, id_n = _id_alumno(viejo), _id_alumno(nuevo)
            if (
                id_v
                and id_v == id_n
                and _curso(viejo) == _curso(nuevo)
                and _periodo(viejo) == _periodo(nuevo)
            ):
                encontrado = (idx, nuevo, "ID + curso + periodo (revisar CURP si cambió)")
                break
        if encontrado:
            idx, nuevo, metodo = encontrado
            usados_actuales.add(idx)
            coincidencias.append((viejo, nuevo, metodo))
        else:
            faltantes.append(viejo)

    nuevos = [r for idx, r in enumerate(actuales) if idx not in usados_actuales]
    return faltantes, nuevos, coincidencias


# -----------------------------------------------------------------------------
# BÚSQUEDA TRANSVERSAL DE LA PERSONA EN EL SEGUNDO ZIP
# -----------------------------------------------------------------------------
def _filas_persona(
    filas: Iterable[Dict[str, Any]], objetivo: Dict[str, Any]
) -> List[Dict[str, Any]]:
    return [r for r in filas if _misma_persona(objetivo, r)]


def _filas_persona_curso(
    filas: Iterable[Dict[str, Any]], objetivo: Dict[str, Any], clave_curso: str
) -> List[Dict[str, Any]]:
    return [
        r for r in filas
        if _misma_persona(objetivo, r) and clave_curso and _curso(r) == clave_curso
    ]


def _resumen_registro(row: Dict[str, Any]) -> str:
    periodo = _periodo(row)
    curso = _texto(_valor(row, "NOM_CUR", "NOM_CURSO", "DES_CURSO"))
    clave = _curso(row)
    eliminado = _es_eliminado(row)
    partes = []
    if periodo:
        partes.append("periodo " + periodo)
    if curso:
        partes.append(curso)
    elif clave:
        partes.append("curso " + clave)
    if eliminado is True:
        partes.append("marcado eliminado")
    return " · ".join(partes) or "Registro encontrado"


def _evidencia_tablas(
    corte: Dict[str, Any], objetivo: Dict[str, Any], claves_originales: List[str]
) -> List[Tuple[str, str]]:
    tablas = corte["tablas"]
    evidencia: List[Tuple[str, str]] = []

    alumnos = _filas_persona(tablas.get("ALUMNOS.DBF", []), objetivo)
    if alumnos:
        estados = ["marcado eliminado" if _es_eliminado(r) is True else "sin marca de eliminación" for r in alumnos]
        evidencia.append(("ALUMNOS.DBF", f"Sigue existiendo ({', '.join(sorted(set(estados)))})"))
    else:
        evidencia.append(("ALUMNOS.DBF", "No localizado por CURP ni número de control"))

    insc = _filas_persona(tablas.get("INSCRIPCION.DBF", []), objetivo)
    insc_original = [
        r for r in insc
        if _curso(r) in set(claves_originales) and _periodo(r) == _periodo(objetivo)
    ]
    if insc:
        descripciones = sorted(set(_resumen_registro(r) for r in insc))
        texto = "Aparece: " + "; ".join(descripciones[:5])
        if claves_originales and not insc_original:
            texto += ". La inscripción original del mismo curso y periodo no está en esta tabla"
        evidencia.append(("INSCRIPCION.DBF", texto))
    else:
        evidencia.append(("INSCRIPCION.DBF", "No aparece en inscripciones del segundo corte"))

    ext = _filas_persona(tablas.get("EXT.DBF", []), objetivo)
    ext_original = [
        r for r in ext
        if _curso(r) in set(claves_originales) and _periodo(r) == _periodo(objetivo)
    ]
    if ext:
        descripciones = sorted(set(_resumen_registro(r) for r in ext))
        texto = "Aparece: " + "; ".join(descripciones[:5])
        if claves_originales and not ext_original:
            texto += ". No se encontró aquí un registro del curso original"
        evidencia.append(("EXT.DBF", texto))
    else:
        evidencia.append(("EXT.DBF", "No localizado"))

    # Las tablas auxiliares se reportan solo cuando contienen evidencia positiva
    # para el alumno y la clave del curso original; así se conserva la ficha compacta.
    for tabla in TABLAS_EVIDENCIA_CURSO:
        if tabla in {"EXT.DBF"} or tabla not in tablas:
            continue
        hits = []
        for clave in claves_originales:
            hits.extend(_filas_persona_curso(tablas.get(tabla, []), objetivo, clave))
        if hits:
            desc = sorted(set(_resumen_registro(r) for r in hits))
            evidencia.append((tabla, "Registro relacionado localizado: " + "; ".join(desc[:4])))

    return evidencia


def _inscripciones_actuales_persona(
    corte: Dict[str, Any], objetivo: Dict[str, Any]
) -> List[Dict[str, Any]]:
    filas = _filas_persona(corte["inscripciones"], objetivo)
    return [_enriquecer_inscripcion(r, corte) for r in filas]


def _estado_eliminacion(registros_originales: List[Dict[str, Any]], evidencia: List[Tuple[str, str]]) -> str:
    estados = [_es_eliminado(r) for r in registros_originales]
    if any(x is True for x in estados):
        return "El registro original tiene marca de eliminación en el corte anterior."
    texto_evidencia = " ".join(v.lower() for _, v in evidencia)
    if "marcado eliminado" in texto_evidencia or "eliminado" in texto_evidencia:
        return "Se encontró al menos una marca de eliminación en los registros relacionados; debe verificarse a qué registro corresponde."
    return (
        "No se encontró una marca explícita de eliminación para la inscripción original. "
        "La ausencia en INSCRIPCION.DBF no demuestra por sí sola quién la eliminó ni cuándo."
    )


# -----------------------------------------------------------------------------
# PRESENTACIÓN VISUAL DE LAS FICHAS
# -----------------------------------------------------------------------------
def _li(etiqueta: str, valor: Any) -> str:
    valor_txt = _texto(valor) or "No disponible"
    return f"<li><strong>{html.escape(etiqueta)}:</strong> {html.escape(valor_txt)}</li>"


def _ficha_html(
    persona: Dict[str, Any],
    inscripciones_anteriores: List[Dict[str, Any]],
    inscripciones_actuales: List[Dict[str, Any]],
    evidencia: List[Tuple[str, str]],
    corte_nuevo: Dict[str, Any],
) -> str:
    nombre = html.escape(_nombre(persona))
    numero = html.escape(_id_alumno(persona) or "No disponible")
    curp = html.escape(_curp(persona) or _texto(_valor(persona, "CURP")) or "No disponible")

    anteriores_html = []
    claves = []
    for item in inscripciones_anteriores:
        d = _enriquecer_inscripcion(item, corte_nuevo["_corte_anterior"])
        claves.append(d["clave_curso"])
        anteriores_html.append(
            "<ul>"
            + _li("Periodo", d["periodo"])
            + _li("Curso", d["nombre_curso"])
            + _li("Clave de curso", d["clave_curso"])
            + _li("Fecha de inscripción", d["fecha_inscripcion"])
            + _li("Instructor", d["instructor"])
            + _li("Inicio", d["inicio"])
            + _li("Término", d["termino"])
            + _li("Horario", d["horario"])
            + _li("Duración", d["duracion"])
            + _li("Taller", d["taller"])
            + "</ul>"
        )

    if inscripciones_actuales:
        badge_estado = '<span class="sisae-badge sisae-green">Localizado</span>'
        actuales_html = []
        for d in inscripciones_actuales:
            actuales_html.append(
                "<ul>"
                + _li("Periodo", d["periodo"])
                + _li("Curso", d["nombre_curso"])
                + _li("Clave de curso", d["clave_curso"])
                + _li("Fecha de inscripción", d["fecha_inscripcion"])
                + _li("Instructor", d["instructor"])
                + _li("Inicio", d["inicio"])
                + _li("Término", d["termino"])
                + _li("Horario", d["horario"])
                + _li("Duración", d["duracion"])
                + _li("Taller", d["taller"])
                + "</ul>"
            )
    else:
        # Puede existir en ALUMNOS.DBF aunque no tenga una inscripción activa.
        master = _filas_persona(corte_nuevo["alumnos"], persona)
        if master:
            badge_estado = '<span class="sisae-badge sisae-green">Localizado en padrón</span>'
            actuales_html = ['<p>El alumno sigue existiendo en ALUMNOS.DBF, pero no se encontró una inscripción activa en INSCRIPCION.DBF.</p>']
        else:
            badge_estado = '<span class="sisae-badge sisae-red">No localizado</span>'
            actuales_html = ['<p>No se localizó por CURP ni número de control en las inscripciones ni en el padrón del segundo corte.</p>']

    # Cada curso original se evalúa por separado; aparecer en otro curso no lo conserva.
    originales_status = []
    for anterior in inscripciones_anteriores:
        d = _enriquecer_inscripcion(anterior, corte_nuevo["_corte_anterior"])
        exacta = any(
            _misma_persona(anterior, actual["registro"])
            and _curso(anterior) == _curso(actual["registro"])
            and _periodo(anterior) == _periodo(actual["registro"])
            for actual in inscripciones_actuales
        )
        estado = "Conservada" if exacta else "No localizada en el mismo curso y periodo"
        color = "sisae-green" if exacta else "sisae-red"
        originales_status.append(
            f'<div class="sisae-status-line"><strong>{html.escape(d["nombre_curso"])}</strong> '
            f'<span class="sisae-badge {color}">{html.escape(estado)}</span></div>'
        )

    evidencia_rows = "".join(
        "<tr><td>" + html.escape(tabla) + "</td><td>" + html.escape(resultado) + "</td></tr>"
        for tabla, resultado in evidencia
    )
    evidencia_table = (
        '<table class="sisae-table"><thead><tr><th>Tabla</th><th>Resultado en el segundo corte</th></tr></thead>'
        f"<tbody>{evidencia_rows}</tbody></table>"
    )

    eliminacion = html.escape(_estado_eliminacion(inscripciones_anteriores, evidencia))

    return f"""
    <div class="sisae-card">
      <div class="sisae-name">{nombre}</div>
      <div class="sisae-muted">Número de control</div>
      <div class="sisae-control">{numero}</div>
      <div class="sisae-muted">CURP: {curp}</div>
      <hr class="sisae-rule">
      <div class="sisae-section-title">Dónde estaba en el primer corte</div>
      {''.join(anteriores_html)}
      <hr class="sisae-rule">
      <div class="sisae-title-row"><div class="sisae-section-title">Dónde aparece en el segundo corte</div>{badge_estado}</div>
      {''.join(actuales_html)}
      <hr class="sisae-rule">
      <div class="sisae-section-title">Estado de la inscripción original</div>
      {''.join(originales_status)}
      <hr class="sisae-rule">
      <div class="sisae-section-title">¿Fue eliminado?</div>
      {evidencia_table}
      <p class="sisae-diagnostico"><strong>Diagnóstico:</strong> {eliminacion}</p>
    </div>
    """


def _inyectar_estilos() -> None:
    st.markdown(
        """
        <style>
        .sisae-card {
            border: 1px solid rgba(var(--atrio-borde-rgb),.14); border-radius: 12px; background: var(--atrio-surface);
            padding: 16px 18px; margin: 10px 0 18px 0; color: var(--atrio-tinta);
            box-shadow: 0 1px 2px rgba(0,0,0,.035);
        }
        .sisae-name { font-size: 19px; font-weight: 750; letter-spacing: .1px; margin: 0 0 10px 0; }
        .sisae-muted { font-size: 11px; color: var(--atrio-tenue); margin-top: 2px; }
        .sisae-control { font-size: 18px; font-weight: 650; margin: 2px 0 4px 0; }
        .sisae-rule { border: 0; border-top: 1px solid rgba(var(--atrio-borde-rgb),.10); margin: 12px 0; }
        .sisae-section-title { font-size: 13px; font-weight: 750; margin: 3px 0 7px 0; }
        .sisae-card ul { margin: 3px 0 8px 0; padding-left: 20px; }
        .sisae-card li { font-size: 12px; line-height: 1.55; margin: 1px 0; }
        .sisae-title-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
        .sisae-badge { display: inline-block; border-radius: 20px; padding: 2px 8px; font-size: 9px; font-weight: 750; white-space: nowrap; }
        .sisae-green { color: var(--atrio-ok); background: var(--atrio-ok-bg); }
        .sisae-red { color: var(--atrio-error); background: var(--atrio-error-bg); }
        .sisae-yellow { color: var(--atrio-alerta); background: var(--atrio-alerta-bg); }
        .sisae-status-line { font-size: 12px; display: flex; justify-content: space-between; gap: 8px; align-items: center; margin: 5px 0; flex-wrap: wrap; }
        .sisae-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 5px; }
        .sisae-table th, .sisae-table td { border: 1px solid rgba(var(--atrio-borde-rgb),.14); padding: 6px 7px; text-align: left; vertical-align: top; }
        .sisae-table th { background: rgba(var(--atrio-borde-rgb),.05); font-weight: 700; }
        .sisae-diagnostico { font-size: 11px; color: var(--atrio-tenue); margin: 9px 0 0 0; line-height: 1.5; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _grupo_por_persona(faltantes: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grupos: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in faltantes:
        grupos[_identidad(row)].append(row)
    return grupos


def _persona_representativa(registros: List[Dict[str, Any]]) -> Dict[str, Any]:
    # La primera fila contiene los campos nominales y el identificador de referencia.
    return registros[0]


def _coincidencias_busqueda(
    texto_busqueda: str,
    corte_viejo: Dict[str, Any],
    corte_nuevo: Dict[str, Any],
) -> List[Dict[str, Any]]:
    q = _nombre_busqueda(texto_busqueda)
    if not q:
        return []
    candidatos = []
    for corte in (corte_viejo, corte_nuevo):
        for tabla in ("ALUMNOS.DBF", "INSCRIPCION.DBF"):
            for row in corte["tablas"].get(tabla, []):
                nombre = _nombre_busqueda(_nombre(row))
                identificadores = (_id_alumno(row), _curp(row))
                if q in nombre or any(q in x for x in identificadores if x):
                    candidatos.append(row)
    unicos = {}
    for r in candidatos:
        llave = _identidad(r)
        if llave not in unicos:
            unicos[llave] = r
    return list(unicos.values())


# -----------------------------------------------------------------------------
# ALMACENAMIENTO HISTÓRICO LOCAL (ZIP INMUTABLES + CATÁLOGO SQLITE)
# -----------------------------------------------------------------------------
MAX_ZIP_BYTES = 500 * 1024 * 1024  # límite preventivo: 500 MB por corte


def _directorio_historico() -> Path:
    """Carpeta persistente del módulo; admite ruta configurable por entorno."""
    configurada = os.environ.get("ATRIO_AUDITORIA_SISAE_DIR", "").strip()
    base = Path(configurada).expanduser() if configurada else Path(__file__).resolve().parent / "datos" / "DATOS_AUDITORIA_SISAE"
    base.mkdir(parents=True, exist_ok=True)
    (base / "CORTES_ORIGINALES").mkdir(parents=True, exist_ok=True)
    return base


@contextmanager
def _conexion_historica():
    """Abre y cierra cada conexión SQLite incluso si ocurre un error."""
    base = _directorio_historico()
    conn = sqlite3.connect(str(base / "historial_sisae.sqlite"), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _inicializar_historico() -> None:
    with _conexion_historica() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cortes (
                id TEXT PRIMARY KEY,
                periodo_corte TEXT NOT NULL,
                fecha_corte TEXT NOT NULL,
                version TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Pendiente de validar',
                nombre_visible TEXT NOT NULL,
                nombre_archivo TEXT NOT NULL,
                archivo_guardado TEXT NOT NULL,
                sha256 TEXT NOT NULL UNIQUE,
                bytes INTEGER NOT NULL,
                fecha_registro TEXT NOT NULL,
                notas TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                id TEXT PRIMARY KEY,
                corte_id TEXT NOT NULL,
                accion TEXT NOT NULL,
                fecha_evento TEXT NOT NULL,
                detalle TEXT DEFAULT '',
                FOREIGN KEY(corte_id) REFERENCES cortes(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comparaciones (
                id TEXT PRIMARY KEY,
                corte_origen_id TEXT NOT NULL,
                corte_destino_id TEXT NOT NULL,
                periodo_inscripcion TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'Individual',
                fecha_comparacion TEXT NOT NULL,
                resumen_json TEXT NOT NULL,
                FOREIGN KEY(corte_origen_id) REFERENCES cortes(id),
                FOREIGN KEY(corte_destino_id) REFERENCES cortes(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pendientes_auditoria (
                clave TEXT NOT NULL,
                identidad TEXT NOT NULL,
                atendido INTEGER NOT NULL DEFAULT 0,
                fecha TEXT NOT NULL,
                PRIMARY KEY(clave, identidad)
            )
        """)
        conn.commit()


def _obtener_cortes() -> List[Dict[str, Any]]:
    _inicializar_historico()
    with _conexion_historica() as conn:
        rows = conn.execute(
            "SELECT * FROM cortes ORDER BY fecha_corte, fecha_registro, periodo_corte"
        ).fetchall()
    return [dict(r) for r in rows]


def _obtener_corte(corte_id: str) -> Optional[Dict[str, Any]]:
    _inicializar_historico()
    with _conexion_historica() as conn:
        row = conn.execute("SELECT * FROM cortes WHERE id = ?", (corte_id,)).fetchone()
    return dict(row) if row else None


def _guardar_corte_historico(
    zip_bytes: bytes,
    periodo_corte: str,
    fecha_corte: date,
    version: str,
    nombre_visible: str,
    nombre_archivo: str,
    notas: str,
) -> Tuple[bool, str, str]:
    """Guarda ZIP exacto sin sobrescribir; devuelve (creado, id, mensaje)."""
    if not zip_bytes:
        raise ValueError("El ZIP está vacío.")
    if len(zip_bytes) > MAX_ZIP_BYTES:
        raise ValueError("El ZIP supera el límite preventivo de 500 MB.")
    if not zipfile.is_zipfile(io.BytesIO(zip_bytes)):
        raise ValueError("El archivo seleccionado no parece ser un ZIP válido.")

    # Validar que el lector SISAE pueda abrirlo antes de conservarlo.
    corte_leido = extraer_datos(zip_bytes)
    if not corte_leido.get("inscripciones"):
        raise ValueError("El ZIP se pudo abrir, pero INSCRIPCION.DBF no contiene registros.")

    digest = hashlib.sha256(zip_bytes).hexdigest()
    _inicializar_historico()
    with _conexion_historica() as conn:
        existente = conn.execute("SELECT id FROM cortes WHERE sha256 = ?", (digest,)).fetchone()
        if existente:
            return False, str(existente["id"]), "Este ZIP ya está registrado. No se creó un duplicado."

    corte_id = uuid.uuid4().hex
    archivo_guardado = f"{corte_id}.zip"
    carpeta = _directorio_historico() / "CORTES_ORIGINALES"
    destino = carpeta / archivo_guardado
    temporal = carpeta / f".{archivo_guardado}.tmp"
    try:
        temporal.write_bytes(zip_bytes)
        os.replace(temporal, destino)
        fecha_registro = datetime.now().isoformat(timespec="seconds")
        with _conexion_historica() as conn:
            conn.execute("""
                INSERT INTO cortes (
                    id, periodo_corte, fecha_corte, version, estado,
                    nombre_visible, nombre_archivo, archivo_guardado,
                    sha256, bytes, fecha_registro, notas
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                corte_id, str(periodo_corte), fecha_corte.isoformat(), version,
                "Pendiente de validar", nombre_visible.strip() or f"Periodo {periodo_corte}",
                nombre_archivo, archivo_guardado, digest, len(zip_bytes),
                fecha_registro, notas.strip()
            ))
            conn.execute(
                "INSERT INTO eventos (id, corte_id, accion, fecha_evento, detalle) VALUES (?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, corte_id, "Corte registrado", fecha_registro,
                 f"Versión: {version}. Periodo: {periodo_corte}. ZIP conservado sin modificaciones.")
            )
            conn.commit()
    except Exception:
        try:
            temporal.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            destino.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    return True, corte_id, "Corte guardado correctamente como archivo original inmutable."


def _cambiar_estado_corte(corte_id: str, nuevo_estado: str, detalle: str = "") -> None:
    if nuevo_estado not in {"Pendiente de validar", "Validado"}:
        raise ValueError("Estado de validación no reconocido.")
    ahora = datetime.now().isoformat(timespec="seconds")
    with _conexion_historica() as conn:
        conn.execute("UPDATE cortes SET estado = ? WHERE id = ?", (nuevo_estado, corte_id))
        conn.execute(
            "INSERT INTO eventos (id, corte_id, accion, fecha_evento, detalle) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, corte_id, f"Estado cambiado a: {nuevo_estado}", ahora, detalle)
        )
        conn.commit()


def _registrar_comparacion(
    origen_id: str, destino_id: str, periodo: str, tipo: str, resumen: Dict[str, Any]
) -> None:
    ahora = datetime.now().isoformat(timespec="seconds")
    with _conexion_historica() as conn:
        conn.execute("""
            INSERT INTO comparaciones (
                id, corte_origen_id, corte_destino_id, periodo_inscripcion,
                tipo, fecha_comparacion, resumen_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            uuid.uuid4().hex, origen_id, destino_id, str(periodo), tipo, ahora,
            json.dumps(resumen, ensure_ascii=False, default=str)
        ))
        conn.commit()


def _cargar_zip_guardado(corte: Dict[str, Any]) -> bytes:
    ruta = _directorio_historico() / "CORTES_ORIGINALES" / corte["archivo_guardado"]
    if not ruta.is_file():
        raise FileNotFoundError(
            f"No se encontró el ZIP guardado para {corte.get('nombre_visible', 'el corte')}. "
            "Comprueba que la carpeta DATOS_AUDITORIA_SISAE se haya conservado en el proyecto."
        )
    datos = ruta.read_bytes()
    digest = hashlib.sha256(datos).hexdigest()
    if digest != corte["sha256"]:
        raise ValueError("La huella SHA-256 no coincide. El ZIP guardado pudo modificarse o dañarse.")
    return datos


def _etiqueta_corte(corte: Dict[str, Any]) -> str:
    return (
        f"P{corte['periodo_corte']} · {corte['fecha_corte']} · "
        f"{corte['version']} · {corte['estado']} · {corte['nombre_visible']}"
    )


def _periodos_comunes(origen: Dict[str, Any], destino: Dict[str, Any]) -> List[str]:
    po = {_periodo(r) for r in origen.get("inscripciones", []) if _periodo(r)}
    pdest = {_periodo(r) for r in destino.get("inscripciones", []) if _periodo(r)}
    comunes = po & pdest
    return sorted(comunes, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))


def _clave_pendientes(origen_id: str, destino_id: str, periodo: str) -> str:
    return f"{origen_id}|{destino_id}|{periodo}"


def _atendidos(clave: str) -> set:
    _inicializar_historico()
    with _conexion_historica() as conn:
        filas = conn.execute(
            "SELECT identidad FROM pendientes_auditoria WHERE clave = ? AND atendido = 1", (clave,)
        ).fetchall()
    return {f["identidad"] for f in filas}


def _marcar_atendido(clave: str, identidad: str, valor: bool) -> None:
    _inicializar_historico()
    with _conexion_historica() as conn:
        conn.execute(
            """
            INSERT INTO pendientes_auditoria (clave, identidad, atendido, fecha)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(clave, identidad) DO UPDATE SET atendido = excluded.atendido, fecha = excluded.fecha
            """,
            (clave, identidad, 1 if valor else 0, datetime.now().isoformat(timespec="seconds")),
        )


def _bloque_revision(grupos: Dict[str, List[Dict[str, Any]]], clave_pend: str, periodo: str, tipo: str) -> None:
    """Checklist persistente por alumno y descarga en Excel del resultado."""
    atendidos = _atendidos(clave_pend)
    orden = sorted(grupos.items(), key=lambda item: _nombre(item[1][0]).upper())
    filas_pend = [{
        "Atendido": ident in atendidos,
        "Nombre": _nombre(registros[0]),
        "Número de control": _id_alumno(registros[0]),
        "CURP": _curp(registros[0]),
        "Inscripciones faltantes": len(registros),
        "Curso(s)": ", ".join(sorted({_texto(_valor(r, "NOM_CUR", "NOM_CURSO")) for r in registros if _texto(_valor(r, "NOM_CUR", "NOM_CURSO"))})),
    } for ident, registros in orden]
    identidades = [ident for ident, _ in orden]
    por_revisar = sum(1 for f in filas_pend if not f["Atendido"])

    st.markdown("##### Checklist de revisión")
    st.caption(f"Por revisar: {por_revisar} · Atendidos: {len(filas_pend) - por_revisar}. Marca cada alumno cuando lo hayas revisado en SISAE; el avance se guarda.")
    editado = st.data_editor(
        pd.DataFrame(filas_pend),
        column_config={"Atendido": st.column_config.CheckboxColumn("Atendido", help="Marca cuando ya lo revisaste en SISAE")},
        disabled=["Nombre", "Número de control", "CURP", "Inscripciones faltantes", "Curso(s)"],
        hide_index=True,
        use_container_width=True,
        key=f"aud_pend_editor_{tipo}_{clave_pend}",
    )
    for ident, nuevo in zip(identidades, editado["Atendido"].tolist()):
        if bool(nuevo) != (ident in atendidos):
            _marcar_atendido(clave_pend, ident, bool(nuevo))
            atendidos.add(ident) if nuevo else atendidos.discard(ident)

    exportacion = pd.DataFrame([{**f, "Atendido": "Sí" if f["Atendido"] else "No"} for f in filas_pend])
    buffer_xlsx = io.BytesIO()
    with pd.ExcelWriter(buffer_xlsx, engine="openpyxl") as escritor:
        exportacion.to_excel(escritor, index=False, sheet_name=f"Periodo {periodo}"[:31])
    st.download_button(
        "Descargar lista de revisión (Excel)",
        data=buffer_xlsx.getvalue(),
        file_name=f"revision_auditoria_periodo_{periodo}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"aud_xlsx_{tipo}_{clave_pend}",
    )


def _mes_inicio(valor: Any) -> str:
    """Convierte F_INICIO (AAAAMMDD) en AAAA-MM. Vacío si no es fecha."""
    f = _fecha(valor)
    return f.strftime("%Y-%m") if f else ""


def _listas_generadas(corte: Dict[str, Any], periodo: str) -> List[Dict[str, Any]]:
    """Resumen por curso de las listas de asistencia generadas (LISTAS01.DBF).

    Una lista está generada cuando existe al menos un alumno registrado en LISTAS01
    para la clave de curso y el periodo. El mes es el de F_INICIO de la lista.
    Compara contra las inscripciones del mismo curso y periodo en INSCRIPCION.DBF.
    """
    tablas = corte.get("tablas", {})
    listas = [r for r in tablas.get("LISTAS01.DBF", []) if _periodo(r) == str(periodo)]
    inscritos: Dict[str, set] = defaultdict(set)
    for r in corte.get("inscripciones", []):
        if _periodo(r) == str(periodo) and _curso(r):
            inscritos[_curso(r)].add(_identidad(r))

    agrupado: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in listas:
        clave = _curso(r)
        if not clave:
            continue
        mes = _mes_inicio(_valor(r, "F_INICIO")) or "Sin fecha"
        g = agrupado.setdefault((clave, mes), {
            "nombre_curso": _texto(_valor(r, "NOM_CURSO")),
            "alumnos": set(),
            "instructor": _normalizar_instructor(_valor(r, "DOC_NOM")),
        })
        g["alumnos"].add(_identidad(r))

    filas = []
    for (clave, mes), g in sorted(agrupado.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        inscritos_n = len(inscritos.get(clave, set()))
        generados_n = len(g["alumnos"])
        if inscritos_n == 0:
            estado = "Lista sin inscritos en el corte"
        elif generados_n < inscritos_n:
            estado = f"Incompleta ({generados_n} de {inscritos_n})"
        else:
            estado = "Generada"
        filas.append({
            "Mes de inicio": mes,
            "Clave de curso": clave,
            "Curso": g["nombre_curso"],
            "Instructor": g["instructor"],
            "Inscritos": inscritos_n,
            "En lista": generados_n,
            "Estado": estado,
        })

    con_lista = {clave for (clave, _mes) in agrupado}
    for clave, personas in sorted(inscritos.items()):
        if clave not in con_lista:
            filas.append({
                "Mes de inicio": "Sin lista",
                "Clave de curso": clave,
                "Curso": "",
                "Instructor": "",
                "Inscritos": len(personas),
                "En lista": 0,
                "Estado": "Sin lista generada",
            })
    return filas


def _ejecutar_comparacion_historica(
    origen_meta: Dict[str, Any],
    destino_meta: Dict[str, Any],
    origen: Dict[str, Any],
    destino: Dict[str, Any],
    periodo: str,
    aplicar_limite: bool,
    tipo: str = "Individual",
    mostrar_tarjetas: bool = True,
) -> Dict[str, Any]:
    if origen_meta["id"] == destino_meta["id"]:
        st.error("Selecciona dos cortes diferentes.")
        return {}

    anteriores = [r for r in origen["inscripciones"] if _periodo(r) == str(periodo)]
    actuales = [r for r in destino["inscripciones"] if _periodo(r) == str(periodo)]
    fechas_actuales = [_fecha_inscripcion(r) for r in actuales]
    fechas_actuales = [f for f in fechas_actuales if f is not None]
    fecha_limite = max(fechas_actuales) if fechas_actuales else None

    fuera_fecha: List[Dict[str, Any]] = []
    elegibles = list(anteriores)
    if aplicar_limite and fecha_limite:
        elegibles = [
            r for r in anteriores
            if _fecha_inscripcion(r) is None or _fecha_inscripcion(r) <= fecha_limite
        ]
        fuera_fecha = [
            r for r in anteriores
            if _fecha_inscripcion(r) is not None and _fecha_inscripcion(r) > fecha_limite
        ]

    faltantes, nuevos, coincidencias = _comparar_inscripciones(elegibles, actuales)
    grupos = _grupo_por_persona(faltantes)
    personas_afectadas = len(grupos)
    resumen = {
        "periodo": str(periodo),
        "inscripciones_origen": len(elegibles),
        "inscripciones_destino": len(actuales),
        "coincidencias": len(coincidencias),
        "inscripciones_faltantes": len(faltantes),
        "alumnos_afectados": personas_afectadas,
        "inscripciones_nuevas": len(nuevos),
        "fuera_limite_temporal": len(fuera_fecha),
        "alumnos_faltantes": [
            {
                "nombre": _nombre(registros[0]),
                "numero_control": _id_alumno(registros[0]),
                "curp": _curp(registros[0]),
                "inscripciones": len(registros),
            }
            for registros in grupos.values()
        ],
    }

    st.markdown(f"#### Periodo de inscripción {periodo}")
    st.caption(
        f"Origen: **{html.escape(origen_meta['nombre_visible'])}** → "
        f"Destino: **{html.escape(destino_meta['nombre_visible'])}**"
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Inscripciones de origen", len(elegibles))
    c2.metric("Inscripciones de destino", len(actuales))
    c3.metric("Inscripciones no localizadas", len(faltantes))
    c4.metric("Alumnos afectados", personas_afectadas)
    st.caption(
        f"Coincidencias: {len(coincidencias)} · Nuevas inscripciones: {len(nuevos)} · "
        f"Registros separados por fecha: {len(fuera_fecha)}. "
        "La coincidencia se calcula por inscripción, no solo por la existencia del alumno."
    )

    if grupos:
        _bloque_revision(grupos, _clave_pendientes(origen_meta["id"], destino_meta["id"], periodo), periodo, tipo)

    if fuera_fecha:
        with st.expander(f"Inscripciones posteriores al límite temporal ({len(fuera_fecha)})"):
            st.dataframe(pd.DataFrame([{
                "Nombre": _nombre(r),
                "Número de control": _id_alumno(r),
                "Curso": _texto(_valor(r, "NOM_CUR", "NOM_CURSO")),
                "Clave de curso": _curso(r),
                "Fecha de inscripción": _fecha_mostrar(_fecha_inscripcion(r)),
            } for r in fuera_fecha]), use_container_width=True, hide_index=True)

    filas_listas = _listas_generadas(destino, periodo)
    with st.expander(f"Listas de asistencia generadas · corte actual ({len(filas_listas)} registros)", expanded=False):
        if not filas_listas:
            st.info("El corte actual no trae LISTAS01.DBF. No hay listas que verificar.")
        else:
            st.dataframe(pd.DataFrame(filas_listas), use_container_width=True, hide_index=True)

    if mostrar_tarjetas:
        if not grupos:
            st.success("No se detectaron inscripciones originales faltantes con los criterios seleccionados.")
        else:
            st.markdown(
                f'<div style="display:inline-block;background:var(--atrio-ok-bg);color:var(--atrio-ok);border-radius:18px;'
                f'padding:4px 10px;font-size:11px;font-weight:800;margin:2px 0 10px 0;">'
                f'Identificados: {personas_afectadas} alumno(s)</div>',
                unsafe_allow_html=True,
            )
            destino_con_origen = dict(destino)
            destino_con_origen["_corte_anterior"] = origen
            for _, registros_originales in sorted(
                grupos.items(), key=lambda item: _nombre(item[1][0]).upper()
            ):
                persona = _persona_representativa(registros_originales)
                actuales_persona = _inscripciones_actuales_persona(destino, persona)
                claves_originales = sorted({_curso(r) for r in registros_originales if _curso(r)})
                evidencia = _evidencia_tablas(destino, persona, claves_originales)
                st.markdown(
                    _ficha_html(
                        persona, registros_originales, actuales_persona,
                        evidencia, destino_con_origen
                    ),
                    unsafe_allow_html=True,
                )

    return {
        "resumen": resumen,
        "origen_id": origen_meta["id"],
        "destino_id": destino_meta["id"],
        "periodo": str(periodo),
        "tipo": tipo,
    }


def _render_gestor_historico() -> None:
    """Interfaz para conservar cortes y compararlos en ciclos posteriores."""
    with st.expander("🗂️ Cortes históricos y comparación acumulada", expanded=False):
        st.caption(
            "Registra cada ZIP una sola vez. Los originales se conservan sin sobrescribirse; "
            "las correcciones se agregan como versiones nuevas."
        )
        try:
            _inicializar_historico()
            cortes = _obtener_cortes()
        except Exception as exc:
            st.error(f"No se pudo inicializar el almacenamiento histórico: {exc}")
            st.info(
                "Verifica que el directorio del proyecto tenga permisos de escritura. "
                "Puedes definir ATRIO_AUDITORIA_SISAE_DIR para usar una carpeta persistente."
            )
            return

        tab_registro, tab_comparar, tab_acumulada, tab_historial = st.tabs([
            "Registrar / administrar cortes",
            "Comparar dos cortes guardados",
            "Comparación acumulada",
            "Historial de auditorías",
        ])

        with tab_registro:
            st.markdown("##### Registrar un nuevo corte SISAE")
            with st.form("aud_hist_form_registrar", clear_on_submit=True):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    periodo_corte = st.selectbox(
                        "Periodo que estás cerrando",
                        options=["1", "2", "3", "4", "Otro"],
                        index=0,
                        key="aud_hist_periodo_registro",
                    )
                with col_b:
                    fecha_corte = st.date_input(
                        "Fecha del corte", value=date.today(), key="aud_hist_fecha_registro"
                    )
                with col_c:
                    version = st.selectbox(
                        "Versión del archivo",
                        options=["Original", "Corregido"],
                        key="aud_hist_version_registro",
                        help="Cada corrección se registra como un ZIP nuevo; nunca reemplaza el original.",
                    )
                nombre_visible = st.text_input(
                    "Nombre para identificar el corte",
                    placeholder="Ej. Cierre P2 corregido 31-12-2026",
                    key="aud_hist_nombre_registro",
                )
                archivo = st.file_uploader(
                    "Selecciona el ZIP de SISAE",
                    type=["zip"],
                    key="aud_hist_zip_registro",
                )
                notas = st.text_area(
                    "Notas (opcional)",
                    placeholder="Ej. Se corrigió la inscripción faltante y se verificó la matrícula.",
                    key="aud_hist_notas_registro",
                    height=70,
                )
                guardar = st.form_submit_button("Guardar corte histórico", use_container_width=True)

            if guardar:
                if archivo is None:
                    st.error("Selecciona un ZIP antes de guardar.")
                else:
                    try:
                        periodo_guardar = "0" if periodo_corte == "Otro" else periodo_corte
                        creado, corte_id, mensaje = _guardar_corte_historico(
                            archivo.getvalue(), periodo_guardar, fecha_corte, version,
                            nombre_visible or f"Periodo {periodo_corte} · {fecha_corte:%d/%m/%Y}",
                            archivo.name, notas
                        )
                        if creado:
                            st.success(mensaje)
                            st.info("El corte quedó como **Pendiente de validar**. Después de revisar sus diferencias podrás marcarlo como Validado.")
                        else:
                            st.warning(mensaje)
                    except Exception as exc:
                        st.error(f"No se guardó el corte: {exc}")
                cortes = _obtener_cortes()

            st.markdown("##### Cortes registrados")
            if not cortes:
                st.info("Todavía no hay cortes históricos guardados.")
            else:
                df_cortes = pd.DataFrame([{
                    "Periodo": f"P{c['periodo_corte']}" if c["periodo_corte"] != "0" else "Otro",
                    "Fecha de corte": c["fecha_corte"],
                    "Nombre": c["nombre_visible"],
                    "Versión": c["version"],
                    "Validación": c["estado"],
                    "Archivo": c["nombre_archivo"],
                    "Tamaño (MB)": round(c["bytes"] / (1024 * 1024), 2),
                } for c in cortes])
                st.dataframe(df_cortes, use_container_width=True, hide_index=True)

                opciones = {_etiqueta_corte(c): c["id"] for c in cortes}
                etiqueta_sel = st.selectbox(
                    "Administrar un corte",
                    options=list(opciones.keys()),
                    key="aud_hist_admin_seleccion",
                )
                corte_sel = _obtener_corte(opciones[etiqueta_sel])
                a1, a2, a3 = st.columns(3)
                with a1:
                    if corte_sel["estado"] != "Validado":
                        if st.button("Marcar como validado", key="aud_hist_validar", use_container_width=True):
                            _cambiar_estado_corte(corte_sel["id"], "Validado", "Validación confirmada desde el módulo de auditoría.")
                            st.success("Corte marcado como validado. El ZIP original permanece intacto.")
                            st.rerun()
                    else:
                        st.success("Corte validado")
                with a2:
                    if corte_sel["estado"] == "Validado":
                        if st.button("Reabrir revisión", key="aud_hist_reabrir", use_container_width=True):
                            _cambiar_estado_corte(corte_sel["id"], "Pendiente de validar", "Se reabrió la revisión del corte.")
                            st.rerun()
                with a3:
                    try:
                        datos_zip = _cargar_zip_guardado(corte_sel)
                        st.download_button(
                            "Descargar ZIP original",
                            data=datos_zip,
                            file_name=corte_sel["nombre_archivo"],
                            mime="application/zip",
                            key="aud_hist_descargar",
                            use_container_width=True,
                        )
                    except Exception as exc:
                        st.error(str(exc))

        # Refrescar cortes por si se registró uno en la pestaña anterior.
        cortes = _obtener_cortes()
        cortes_validos = [c for c in cortes if c["periodo_corte"] != "0"]

        with tab_comparar:
            st.markdown("##### Conciliar dos cortes históricos")
            if len(cortes) < 2:
                st.info("Registra al menos dos ZIP para habilitar la comparación histórica.")
            else:
                etiquetas = {_etiqueta_corte(c): c["id"] for c in cortes}
                col_o, col_d = st.columns(2)
                with col_o:
                    etiqueta_o = st.selectbox("Corte de origen", list(etiquetas.keys()), key="aud_hist_origen")
                with col_d:
                    etiqueta_d = st.selectbox("Corte de destino", list(etiquetas.keys()), index=len(etiquetas)-1, key="aud_hist_destino")
                meta_o = _obtener_corte(etiquetas[etiqueta_o])
                meta_d = _obtener_corte(etiquetas[etiqueta_d])
                if meta_o["id"] == meta_d["id"]:
                    st.warning("Elige dos cortes diferentes.")
                else:
                    try:
                        origen = extraer_datos(_cargar_zip_guardado(meta_o))
                        destino = extraer_datos(_cargar_zip_guardado(meta_d))
                        comunes = _periodos_comunes(origen, destino)
                        if not comunes:
                            st.warning("Los cortes seleccionados no comparten periodos de inscripción identificables.")
                        else:
                            sugerido = meta_o["periodo_corte"] if meta_o["periodo_corte"] in comunes else comunes[0]
                            periodo = st.selectbox(
                                "Periodo de inscripción que deseas comparar",
                                comunes,
                                index=comunes.index(sugerido),
                                format_func=lambda p: f"Periodo {p}",
                                key="aud_hist_periodo_individual",
                            )
                            limitar = st.checkbox(
                                "Separar altas posteriores a la última fecha de inscripción del periodo en el corte destino",
                                value=False,
                                key="aud_hist_limite_individual",
                                help="Por defecto se comparan todos los registros. Activa esta opción solo cuando quieras comparar una misma ventana de captura.",
                            )
                            resultado = _ejecutar_comparacion_historica(
                                meta_o, meta_d, origen, destino, periodo, limitar,
                                tipo="Individual", mostrar_tarjetas=True
                            )
                            if resultado and st.button("Guardar esta comparación en el historial", key="aud_hist_guardar_individual"):
                                _registrar_comparacion(
                                    meta_o["id"], meta_d["id"], periodo, "Individual", resultado["resumen"]
                                )
                                st.success("Comparación registrada en el historial.")
                    except Exception as exc:
                        st.error(f"No se pudo realizar la comparación: {exc}")

        with tab_acumulada:
            st.markdown("##### Comparar varios periodos contra un mismo corte actual")
            st.caption(
                "Ejemplo: selecciona el corte validado de P1 y el corte validado de P2 como referencias, "
                "y usa el ZIP de P3 como destino. El módulo comparará P1 contra P3 y P2 contra P3, "
                "cada uno usando su propio periodo de inscripción."
            )
            if len(cortes_validos) < 2:
                st.info("Para una comparación acumulada, registra y valida al menos dos cortes de referencia, además del corte actual.")
            else:
                etiquetas = {_etiqueta_corte(c): c["id"] for c in cortes}
                etiqueta_destino = st.selectbox(
                    "Corte actual / destino",
                    list(etiquetas.keys()),
                    index=len(etiquetas)-1,
                    key="aud_hist_acum_destino",
                )
                meta_destino = _obtener_corte(etiquetas[etiqueta_destino])
                candidatos = [c for c in cortes_validos if c["id"] != meta_destino["id"]]
                etiquetas_ref = {_etiqueta_corte(c): c["id"] for c in candidatos}
                seleccion_ref = st.multiselect(
                    "Cortes de referencia validados",
                    options=list(etiquetas_ref.keys()),
                    default=[],
                    key="aud_hist_acum_referencias",
                    help="Selecciona, por ejemplo, P1 validado y P2 validado para comprobar ambos contra P3.",
                )
                limitar_acum = st.checkbox(
                    "Aplicar límite temporal por periodo",
                    value=False,
                    key="aud_hist_acum_limite",
                    help="Si se activa, separa inscripciones anteriores posteriores a la fecha máxima encontrada en el mismo periodo del corte actual.",
                )
                ejecutar_acumulada = st.button(
                    "Ejecutar comparación acumulada",
                    key="aud_hist_ejecutar_acum",
                    use_container_width=True,
                )
                if ejecutar_acumulada:
                    if not seleccion_ref:
                        st.warning("Selecciona al menos un corte de referencia.")
                    else:
                        try:
                            destino = extraer_datos(_cargar_zip_guardado(meta_destino))
                            for etiqueta_ref in seleccion_ref:
                                meta_ref = _obtener_corte(etiquetas_ref[etiqueta_ref])
                                periodo_ref = meta_ref["periodo_corte"]
                                if periodo_ref == "0":
                                    st.warning(f"{etiqueta_ref}: no tiene un periodo de corte definido y se omite de la comparación acumulada.")
                                    continue
                                origen = extraer_datos(_cargar_zip_guardado(meta_ref))
                                comunes = _periodos_comunes(origen, destino)
                                if periodo_ref not in comunes:
                                    with st.expander(f"{etiqueta_ref} → {meta_destino['nombre_visible']}", expanded=True):
                                        st.warning(f"No se encontró el periodo de inscripción {periodo_ref} en ambos ZIP. No se comparó.")
                                    continue
                                with st.expander(f"P{periodo_ref}: {meta_ref['nombre_visible']} → {meta_destino['nombre_visible']}", expanded=True):
                                    resultado = _ejecutar_comparacion_historica(
                                        meta_ref, meta_destino, origen, destino, periodo_ref,
                                        limitar_acum, tipo="Acumulada", mostrar_tarjetas=True
                                    )
                                    if resultado and st.button(
                                        f"Guardar conciliación P{periodo_ref}",
                                        key=f"aud_hist_acum_guardar_{meta_ref['id']}_{meta_destino['id']}"
                                    ):
                                        _registrar_comparacion(
                                            meta_ref["id"], meta_destino["id"], periodo_ref,
                                            "Acumulada", resultado["resumen"]
                                        )
                                        st.success("Conciliación acumulada guardada.")
                        except Exception as exc:
                            st.error(f"No se pudo completar la comparación acumulada: {exc}")

        with tab_historial:
            st.markdown("##### Comparaciones y movimientos de validación registrados")
            with _conexion_historica() as conn:
                comparaciones = conn.execute(
                    "SELECT * FROM comparaciones ORDER BY fecha_comparacion DESC LIMIT 100"
                ).fetchall()
                eventos = conn.execute(
                    "SELECT e.*, c.nombre_visible FROM eventos e LEFT JOIN cortes c ON c.id=e.corte_id "
                    "ORDER BY e.fecha_evento DESC LIMIT 100"
                ).fetchall()
            if comparaciones:
                filas = []
                for comp in comparaciones:
                    origen_meta = _obtener_corte(comp["corte_origen_id"])
                    destino_meta = _obtener_corte(comp["corte_destino_id"])
                    resumen = json.loads(comp["resumen_json"] or "{}")
                    filas.append({
                        "Fecha": comp["fecha_comparacion"],
                        "Tipo": comp["tipo"],
                        "Origen": origen_meta["nombre_visible"] if origen_meta else "No disponible",
                        "Destino": destino_meta["nombre_visible"] if destino_meta else "No disponible",
                        "Periodo": comp["periodo_inscripcion"],
                        "Alumnos afectados": resumen.get("alumnos_afectados", 0),
                        "Inscripciones faltantes": resumen.get("inscripciones_faltantes", 0),
                    })
                st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
            else:
                st.info("Todavía no se han guardado comparaciones históricas.")
            if eventos:
                with st.expander("Registro de carga y validación de cortes"):
                    st.dataframe(pd.DataFrame([{
                        "Fecha": e["fecha_evento"],
                        "Corte": e["nombre_visible"] or e["corte_id"],
                        "Acción": e["accion"],
                        "Detalle": e["detalle"],
                    } for e in eventos]), use_container_width=True, hide_index=True)

        st.caption(
            "Almacenamiento local: DATOS_AUDITORIA_SISAE. Incluye ZIP originales, catálogo SQLite y auditorías. "
            "Respalda esta carpeta junto con ATRIO; no la coloques en una carpeta pública."
        )


# -----------------------------------------------------------------------------
# INTERFAZ PRINCIPAL DEL MÓDULO
# -----------------------------------------------------------------------------
def render_auditoria_sisae() -> None:
    _inyectar_estilos()
    st.markdown(
        """
        <div style="background:linear-gradient(109deg,var(--atrio-surface) 0%,rgba(212,175,55,.14) 60%,rgba(212,175,55,.30) 100%);border-radius:14px;padding:22px 25px;color:var(--atrio-titulo);margin-bottom:18px;">
          <div style="font-size:10px;font-weight:800;letter-spacing:1.5px;color:#D4AF37;margin-bottom:7px;">
            AUDITORÍA HISTÓRICA
          </div>
          <div style="font-family:Georgia,serif;font-size:29px;font-weight:700;line-height:1.15;">
            Buscador de Alumnos Reales
          </div>
          <div style="font-family:Georgia,serif;font-size:14px;margin-top:5px;">
            Comparación de inscripciones y búsqueda transversal en tablas SISAE.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Nueva administración histórica plegable: la pantalla de comparación directa
    # y las tarjetas aprobadas permanecen debajo sin cambios de diseño.
    _render_gestor_historico()

    col1, col2 = st.columns(2)
    with col1:
        zip_viejo = st.file_uploader(
            "1. Corte anterior (origen)", type=["zip"], key="aud_viejo"
        )
    with col2:
        zip_nuevo = st.file_uploader(
            "2. Corte actual (destino)", type=["zip"], key="aud_nuevo"
        )

    if not zip_viejo or not zip_nuevo:
        st.info("Carga los dos ZIP de SISAE para iniciar la conciliación.")
        return

    try:
        corte_viejo = extraer_datos(zip_viejo.getvalue())
        corte_nuevo = extraer_datos(zip_nuevo.getvalue())
    except Exception as exc:
        st.error(f"No fue posible analizar los ZIP: {exc}")
        return

    insc_v = corte_viejo["inscripciones"]
    insc_n = corte_nuevo["inscripciones"]
    if not insc_v:
        st.error("INSCRIPCION.DBF del corte anterior no contiene registros.")
        return

    periodos_v = sorted({p for p in (_periodo(r) for r in insc_v) if p}, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
    periodos_n = sorted({p for p in (_periodo(r) for r in insc_n) if p}, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
    periodos = periodos_v or periodos_n
    if not periodos:
        st.error("No se encontró el campo PERIODO en los registros de INSCRIPCION.DBF.")
        return

    pcol, info_col = st.columns([1, 2])
    with pcol:
        periodo = st.selectbox(
            "Periodo que deseas conciliar",
            options=periodos,
            index=0,
            format_func=lambda p: f"Periodo {p}",
            key="aud_periodo_comparar",
        )

    anteriores_periodo = [r for r in insc_v if _periodo(r) == periodo]
    actuales_periodo = [r for r in insc_n if _periodo(r) == periodo]

    fechas_actuales = [_fecha_inscripcion(r) for r in actuales_periodo]
    fechas_actuales = [f for f in fechas_actuales if f is not None]
    fecha_limite = max(fechas_actuales) if fechas_actuales else None

    with info_col:
        if fecha_limite:
            st.caption(
                f"En el corte actual, la última fecha de inscripción registrada para el periodo {periodo} "
                f"es **{fecha_limite.strftime('%d/%m/%Y')}**."
            )
        else:
            st.caption("No se detectaron fechas de inscripción suficientes para proponer un límite temporal.")

    aplicar_limite = False
    if fecha_limite:
        aplicar_limite = st.checkbox(
            "Comparar la misma cohorte temporal: excluir del corte anterior las altas posteriores a "
            f"{fecha_limite.strftime('%d/%m/%Y')} y mostrarlas aparte",
            value=True,
            key=f"aud_limite_{periodo}",
            help=(
                "Evita marcar como perdidos registros que fueron capturados después del último día "
                "de inscripción que aparece para ese mismo periodo en el corte actual. Los excluidos "
                "se contabilizan y se muestran por separado; no se eliminan del análisis."
            ),
        )

    if aplicar_limite and fecha_limite:
        elegibles_v = [
            r for r in anteriores_periodo
            if _fecha_inscripcion(r) is None or _fecha_inscripcion(r) <= fecha_limite
        ]
        fuera_fecha = [
            r for r in anteriores_periodo
            if _fecha_inscripcion(r) is not None and _fecha_inscripcion(r) > fecha_limite
        ]
    else:
        elegibles_v = list(anteriores_periodo)
        fuera_fecha = []

    faltantes, nuevos, coincidencias = _comparar_inscripciones(elegibles_v, actuales_periodo)
    grupos = _grupo_por_persona(faltantes)
    alumnos_faltantes = len(grupos)

    # Indicadores principales: separamos personas de inscripciones.
    st.markdown("### Resultado de la conciliación")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Inscripciones anteriores comparables", len(elegibles_v))
    m2.metric("Inscripciones del corte actual", len(actuales_periodo))
    m3.metric("Inscripciones originales no localizadas", len(faltantes))
    m4.metric("Alumnos afectados", alumnos_faltantes)

    st.caption(
        f"CURP válidas utilizadas como identificador principal; número de control como respaldo. "
        f"Coincidencias conservadas: {len(coincidencias)}. "
        f"Inscripciones nuevas del periodo en el corte actual: {len(nuevos)}."
    )

    filas_listas = _listas_generadas(corte_nuevo, periodo)
    with st.expander(
        f"Listas de asistencia generadas · corte actual · periodo {periodo} ({len(filas_listas)} registros)",
        expanded=False,
    ):
        if not filas_listas:
            st.info("El corte actual no trae LISTAS01.DBF. No hay listas que verificar.")
        else:
            st.dataframe(pd.DataFrame(filas_listas), use_container_width=True, hide_index=True)

    if grupos:
        clave_subida = "subida|" + hashlib.sha256(zip_viejo.getvalue()).hexdigest()[:16] + "|" + hashlib.sha256(zip_nuevo.getvalue()).hexdigest()[:16] + f"|{periodo}"
        _bloque_revision(grupos, clave_subida, periodo, "Subida")

    if fuera_fecha:
        with st.expander(
            f"Registros del corte anterior posteriores al límite temporal ({len(fuera_fecha)}); no se mezclaron con la cohorte comparable",
            expanded=False,
        ):
            st.warning(
                "Estos registros sí estaban en el ZIP anterior, pero tienen fecha posterior al último "
                "día de inscripción del mismo periodo detectado en el ZIP actual. Se separan para evitar "
                "falsos faltantes; puedes desactivar el límite temporal para incluirlos en la comparación."
            )
            df_fuera = pd.DataFrame(
                [{
                    "Nombre": _nombre(r),
                    "Número de control": _id_alumno(r),
                    "CURP": _curp(r) or _texto(_valor(r, "CURP")),
                    "Curso": _texto(_valor(r, "NOM_CUR", "NOM_CURSO")),
                    "Clave de curso": _curso(r),
                    "Fecha de inscripción": _fecha_mostrar(_fecha_inscripcion(r)),
                } for r in fuera_fecha]
            )
            st.dataframe(df_fuera, use_container_width=True, hide_index=True)

    st.markdown("### Buscar un alumno específico")
    busqueda = st.text_input(
        "Nombre, número de control o CURP",
        value="",
        placeholder="Ej. Sergio Sánchez o 20263003100526",
        key="aud_busqueda_alumno",
    )

    # Si se busca un alumno, se muestran sus fichas aunque no sea un faltante.
    if busqueda.strip():
        encontrados = _coincidencias_busqueda(busqueda, corte_viejo, corte_nuevo)
        if not encontrados:
            st.warning("No se encontró coincidencia por nombre, CURP ni número de control.")
        else:
            for persona in encontrados:
                persona_key = _identidad(persona)
                previas = [r for r in elegibles_v if _identidad(r) == persona_key]
                if not previas:
                    # Respaldo por ID si se corrigió la CURP entre las tablas.
                    previas = [r for r in elegibles_v if _id_alumno(r) and _id_alumno(r) == _id_alumno(persona)]
                actuales_persona_raw = _filas_persona(insc_n, persona)
                if not actuales_persona_raw and _id_alumno(persona):
                    actuales_persona_raw = [r for r in insc_n if _id_alumno(r) == _id_alumno(persona)]
                actuales_persona = [_enriquecer_inscripcion(r, corte_nuevo) for r in actuales_persona_raw]
                if previas:
                    originales = previas
                else:
                    # Si solo aparece en el corte actual, mostrar igualmente su ubicación.
                    originales = []
                if originales:
                    ev = _evidencia_tablas(corte_nuevo, persona, [_curso(r) for r in originales])
                    corte_nuevo_con_anterior = dict(corte_nuevo)
                    corte_nuevo_con_anterior["_corte_anterior"] = corte_viejo
                    st.markdown(
                        _ficha_html(persona, originales, actuales_persona, ev, corte_nuevo_con_anterior),
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(f"**{html.escape(_nombre(persona))}** · Número de control: `{html.escape(_id_alumno(persona) or 'No disponible')}`")
                    if actuales_persona:
                        st.success("Encontrado en el corte actual. No se localizó una inscripción comparable en el conjunto seleccionado del corte anterior.")
                        st.dataframe(pd.DataFrame([
                            {k: v for k, v in d.items() if k != "registro"}
                            for d in actuales_persona
                        ]), use_container_width=True, hide_index=True)
                    else:
                        st.info("La coincidencia aparece en el padrón o en una tabla auxiliar, pero no tiene inscripción visible en el corte actual.")

    st.markdown("---")
    st.markdown(f"### Alumnos con inscripciones faltantes en el periodo {periodo}")
    if not grupos:
        st.success("No se detectaron inscripciones originales faltantes con los criterios seleccionados.")
        if not aplicar_limite and fuera_fecha:
            st.caption("Los registros posteriores al límite temporal están incluidos en esta comparación.")
    else:
        st.markdown(
            f'<div style="display:inline-block;background:var(--atrio-ok-bg);color:var(--atrio-ok);border-radius:18px;'
            f'padding:4px 10px;font-size:11px;font-weight:800;margin:2px 0 10px 0;">'
            f'Identificados: {alumnos_faltantes} alumno(s)</div>',
            unsafe_allow_html=True,
        )

        corte_nuevo_con_anterior = dict(corte_nuevo)
        corte_nuevo_con_anterior["_corte_anterior"] = corte_viejo

        for identidad, registros_originales in sorted(
            grupos.items(), key=lambda item: _nombre(item[1][0]).upper()
        ):
            persona = _persona_representativa(registros_originales)
            actuales_persona = _inscripciones_actuales_persona(corte_nuevo, persona)
            claves_originales = sorted({_curso(r) for r in registros_originales if _curso(r)})
            evidencia = _evidencia_tablas(corte_nuevo, persona, claves_originales)
            tarjeta = _ficha_html(
                persona,
                registros_originales,
                actuales_persona,
                evidencia,
                corte_nuevo_con_anterior,
            )
            st.markdown(tarjeta, unsafe_allow_html=True)

    # Aviso de calidad: no se excluyen alumnos sin CURP; se reportan como identificados
    # por número de control o como registros que necesitan revisión.
    sin_curp_v = sum(1 for r in elegibles_v if not _curp(r))
    sin_curp_n = sum(1 for r in actuales_periodo if not _curp(r))
    if sin_curp_v or sin_curp_n:
        st.warning(
            f"Control de calidad: {sin_curp_v} inscripción(es) del corte anterior y "
            f"{sin_curp_n} del actual no tienen CURP de 18 caracteres. "
            "No se descartaron; se compararon por número de control cuando estuvo disponible."
        )

    st.caption(
        "Importante: una persona localizada en ALUMNOS.DBF o inscrita en otro curso no significa "
        "que su inscripción original se haya conservado. La ausencia de una fila tampoco permite "
        "atribuir quién la eliminó ni la fecha del movimiento si SISAE no exporta ese historial."
    )
