# -*- coding: utf-8 -*-
"""Reprogramación operativa: simulación, respaldo y aplicación coordinada Excel/SQLite."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import os
import re
import shutil
import tempfile

import streamlit as st
from openpyxl import load_workbook
import centro as C

DIAS_MAP = {
    "LUNES": 0, "MARTES": 1, "MIERCOLES": 2, "MIÉRCOLES": 2,
    "JUEVES": 3, "VIERNES": 4, "SABADO": 5, "SÁBADO": 5, "DOMINGO": 6,
}
FESTIVOS_DEFAULT = [date(2026, 11, 2), date(2026, 11, 16), date(2026, 12, 25), date(2027, 1, 1)]
CIERRE_CICLO = date(2027, 6, 30)


def _a_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        raw = str(value).strip()[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
    raise ValueError(f"Fecha no válida: {value!r}")


def _fmt_fecha(value):
    try:
        return _a_date(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "" if value is None else str(value)


def _nombre_dias(dias):
    nombres = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return ", ".join(nombres[d] for d in sorted(set(dias)))


def _obtener_festivos():
    ruta = C.ruta_dias_sin_clase()
    if ruta is None:
        st.warning(
            "No se encontró DIAS_SIN_CLASE.json. Se usa la lista de respaldo; "
            "revisa los días inhábiles antes de aplicar."
        )
        return FESTIVOS_DEFAULT
    try:
        valores = json.loads(ruta.read_text(encoding="utf-8-sig"))
        return [_a_date(x) for x in valores]
    except Exception as exc:
        st.error(f"No se pudo leer DIAS_SIN_CLASE.json: {exc}")
        return FESTIVOS_DEFAULT


def _parsear_dias(texto):
    if not isinstance(texto, str):
        return []
    texto = texto.upper().replace("MIÉRCOLES", "MIERCOLES").replace("SÁBADO", "SABADO")
    texto = re.sub(r"\s+", " ", texto)
    hallados = [num for dia, num in DIAS_MAP.items() if re.search(r"\b" + re.escape(dia) + r"\b", texto)]
    if len(hallados) >= 2:
        # "lunes a viernes" representa el rango completo; "lunes y miércoles", solo esos días.
        m = re.search(r"\b(LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO)\s+A\s+(LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO)\b", texto)
        if m:
            a, b = DIAS_MAP[m.group(1)], DIAS_MAP[m.group(2)]
            return list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
        return sorted(set(hallados))
    return sorted(set(hallados))


def _extraer_horario(horario_str):
    if not isinstance(horario_str, str):
        return []
    texto = horario_str.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    bloques = []
    for linea in texto.splitlines() or [texto]:
        linea = linea.strip()
        if not linea:
            continue
        matches = list(re.finditer(r"(\d{1,2}):(\d{2})\s*(?:A|[-–])\s*(\d{1,2}):(\d{2})", linea, re.I))
        for i, match in enumerate(matches):
            inicio = int(match.group(1)) * 60 + int(match.group(2))
            fin = int(match.group(3)) * 60 + int(match.group(4))
            dias = _parsear_dias(linea[:match.start()])
            if not dias and i:
                dias = _parsear_dias(linea[matches[i - 1].end():match.start()])
            if dias and fin > inicio:
                bloques.append({"dias": dias, "duracion": (fin - inicio) / 60, "hora_ini_min": inicio})
    return bloques


def _clave_carril(horario_str):
    bloques = _extraer_horario(horario_str)
    if not bloques:
        return None
    return tuple(sorted((tuple(sorted(b["dias"])), round(b["duracion"], 2), b["hora_ini_min"]) for b in bloques))


def _siguiente_dia_habil(desde, dias, festivos):
    actual = desde
    for _ in range(370):
        if actual.weekday() in dias and actual not in festivos:
            return actual
        actual += timedelta(days=1)
    return None


def _calcular_fecha_fin(inicio, horas_req, bloques, festivos):
    if inicio is None:
        return None, 0
    actual, acumuladas = inicio, 0.0
    limite = CIERRE_CICLO + timedelta(days=365)
    while actual <= limite:
        if actual not in festivos:
            acumuladas += sum(b["duracion"] for b in bloques if actual.weekday() in b["dias"])
            if acumuladas + 1e-9 >= float(horas_req):
                return actual, acumuladas
        actual += timedelta(days=1)
    return None, acumuladas


def _dif_habiles(inicio, fin, dias, festivos):
    actual, total = inicio, 0
    while actual <= fin:
        if actual.weekday() in dias and actual not in festivos:
            total += 1
        actual += timedelta(days=1)
    return total


def _grupo_incluido(g):
    meta = g.get("_atrio") or {}
    return meta.get("incluido_en_ultima_actualizacion", True) is not False and not str(
        meta.get("estado_programacion", "")
    ).startswith("Pendiente de reprogramación")


def _planificar_cascada(data, curso_id, nueva_fin, festivos):
    operativos = [g for g in data if _grupo_incluido(g)]
    seleccionado = next((g for g in operativos if g.get("id") == curso_id), None)
    if seleccionado is None:
        raise ValueError("El curso seleccionado no participa en la actualización actual.")
    clave = _clave_carril(seleccionado.get("horario", ""))
    if not clave:
        raise ValueError("El horario no permite identificar con seguridad el carril de reprogramación.")
    carril = [g for g in operativos if g.get("hoja") == seleccionado.get("hoja") and _clave_carril(g.get("horario", "")) == clave]
    carril.sort(key=lambda g: (_a_date(g["inicio"]), int(g.get("fila") or 0)))
    indice = next(i for i, g in enumerate(carril) if g["id"] == curso_id)
    afectados = carril[indice:]
    cambios, cursor_fin = [], nueva_fin
    for posicion, grupo in enumerate(afectados):
        bloques = _extraer_horario(grupo.get("horario", ""))
        if not bloques:
            raise ValueError(f"No se pudo interpretar el horario de {grupo.get('nombre', 'un curso')}; no se aplicó ningún cambio.")
        inicio_anterior, fin_anterior = _a_date(grupo["inicio"]), _a_date(grupo["fin"])
        if posicion == 0:
            nuevo_inicio = inicio_anterior
            nuevo_fin = nueva_fin
            if nuevo_fin < nuevo_inicio:
                raise ValueError("La nueva fecha de término no puede ser anterior al inicio del curso seleccionado.")
        else:
            dias = sorted({d for b in bloques for d in b["dias"]})
            nuevo_inicio = _siguiente_dia_habil(cursor_fin + timedelta(days=1), dias, festivos)
            nuevo_fin, _ = _calcular_fecha_fin(nuevo_inicio, grupo["duracion"], bloques, festivos)
            if nuevo_fin is None:
                raise ValueError(f"No fue posible calcular el término de {grupo.get('nombre')}. Revisa duración, horario y calendario.")
        cambios.append({
            "id": grupo["id"], "fingerprint": grupo.get("fingerprint"),
            "hoja": grupo["hoja"], "fila": int(grupo["fila"]),
            "curso": grupo["nombre"], "horas": float(grupo["duracion"]),
            "inicio_anterior": inicio_anterior.isoformat(), "fin_anterior": fin_anterior.isoformat(),
            "inicio_nuevo": nuevo_inicio.isoformat(), "fin_nuevo": nuevo_fin.isoformat(),
            "horario": grupo.get("horario", ""),
        })
        cursor_fin = nuevo_fin
    return cambios


def _actualizar_excel_y_db(cambios, excel_path=None):
    """Aplica los cambios coordinando respaldo, Excel y SQLite; restaura Excel si falla SQLite."""
    excel = Path(excel_path or (C.RES / "PROGRAMACION DE CURSOS.xlsx"))
    if not excel.is_file():
        raise FileNotFoundError(f"No se encontró la programación: {excel}")
    wb = load_workbook(excel)
    try:
        for cambio in cambios:
            hoja, fila = cambio["hoja"], int(cambio["fila"])
            if hoja not in wb.sheetnames or fila < 1 or fila > wb[hoja].max_row:
                raise ValueError(f"No se encontró la fila original del curso {cambio['curso']}.")
            ws = wb[hoja]
            # Esquema vigente de centro.parse_program: B nombre, E inicio, F término, G horas.
            ws.cell(fila, 2).value = cambio["curso"]
            ws.cell(fila, 5).value = _a_date(cambio["inicio_nuevo"])
            ws.cell(fila, 6).value = _a_date(cambio["fin_nuevo"])
            ws.cell(fila, 7).value = float(cambio["horas"])
    finally:
        pass

    excel.parent.mkdir(parents=True, exist_ok=True)
    C.ARCH.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = C.ARCH / f"PROGRAMACION_BACKUP_{marca}.xlsx"
    fd, temp_name = tempfile.mkstemp(prefix="PROGRAMACION_", suffix=".xlsx", dir=str(excel.parent))
    os.close(fd)
    temp = Path(temp_name)
    reemplazado = False
    try:
        wb.save(temp)
        wb.close()
        shutil.copy2(excel, backup)
        with C.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # Validar todos los grupos antes de modificar cualquiera.
            actuales = {}
            for cambio in cambios:
                row = conn.execute("SELECT payload,fingerprint,active FROM groups WHERE id=?", (cambio["id"],)).fetchone()
                if not row or not row["active"]:
                    raise ValueError(f"El curso {cambio['curso']} ya no está vigente. No se aplicó la reprogramación.")
                if cambio.get("fingerprint") and row["fingerprint"] != cambio["fingerprint"]:
                    raise ValueError(f"La programación de {cambio['curso']} cambió desde que se preparó la simulación. Vuelve a simular.")
                payload = json.loads(row["payload"])
                if not _grupo_incluido(payload):
                    raise ValueError(f"{cambio['curso']} quedó pendiente y no participa en esta jornada.")
                actuales[cambio["id"]] = payload
            os.replace(temp, excel)
            reemplazado = True
            try:
                for cambio in cambios:
                    payload = actuales[cambio["id"]]
                    payload["inicio"] = cambio["inicio_nuevo"]
                    payload["fin"] = cambio["fin_nuevo"]
                    nueva_huella = C.fingerprint(payload)
                    conn.execute(
                        "UPDATE groups SET fingerprint=?,payload=? WHERE id=?",
                        (nueva_huella, json.dumps(payload, ensure_ascii=False, default=str), cambio["id"]),
                    )
                    conn.execute(
                        "INSERT INTO events(at,group_id,action,payload) VALUES(?,?,?,?)",
                        (C.now(), cambio["id"], "Curso reprogramado", json.dumps({
                            "antes": {"inicio": cambio["inicio_anterior"], "fin": cambio["fin_anterior"]},
                            "despues": {"inicio": cambio["inicio_nuevo"], "fin": cambio["fin_nuevo"]},
                            "horas": cambio["horas"], "horario": cambio["horario"],
                            "excel": str(excel), "respaldo": str(backup),
                        }, ensure_ascii=False)),
                    )
                conn.execute(
                    "INSERT INTO events(at,group_id,action,payload) VALUES(?,?,?,?)",
                    (C.now(), None, "Reprogramación aplicada", json.dumps({
                        "grupos_actualizados": len(cambios), "respaldo": str(backup),
                        "archivo": str(excel), "regla": "Se conservaron group_id, estados y documentos existentes.",
                    }, ensure_ascii=False)),
                )
            except Exception:
                shutil.copy2(backup, excel)
                raise
        return backup, excel
    except Exception:
        if reemplazado and backup.exists():
            shutil.copy2(backup, excel)
        raise
    finally:
        try:
            wb.close()
        except Exception:
            pass
        temp.unlink(missing_ok=True)


def render_reprogramacion(data, today):
    st.markdown("""
    <div class="hero-pendientes" style="background:linear-gradient(109deg,rgba(255,20,147,.12),var(--atrio-surface) 55%,rgba(212,175,55,.16));border-radius:14px;padding:24px 26px;color:var(--atrio-titulo);border:1px solid rgba(212,175,55,.35);box-shadow:var(--atrio-sombra);margin-bottom:20px">
      <div style="font-size:10px;font-weight:800;letter-spacing:1.5px;color:#D4AF37;margin-bottom:8px">JEFATURA DE CAPACITACIÓN</div>
      <h1 style="margin:0;font-family:Georgia,serif;font-size:32px">Reprogramación</h1>
      <p style="margin:5px 0 0;font-family:Georgia,serif;color:var(--atrio-tinta)">Simulación y aplicación de cascada por docente y carril horario</p>
    </div>
    """, unsafe_allow_html=True)

    festivos = _obtener_festivos()
    operativos = [g for g in data if _grupo_incluido(g)]
    pendientes = [g for g in data if not _grupo_incluido(g)]
    if pendientes:
        st.info(f"{len(pendientes)} curso(s) pendiente(s) de reprogramación se conservan, pero no participan en esta jornada.")
    if not operativos:
        st.warning("No hay cursos incluidos en la actualización actual.")
        return

    docentes = sorted({g["hoja"] for g in operativos})
    docente = st.selectbox("Docente", docentes, key="reprog_docente")
    cursos = sorted([g for g in operativos if g["hoja"] == docente], key=lambda g: (_a_date(g["inicio"]), g.get("fila", 0)))
    curso = st.selectbox(
        "Curso desde el que inicia la cascada", cursos,
        format_func=lambda g: f"{g['nombre']} · {_fmt_fecha(g['inicio'])} a {_fmt_fecha(g['fin'])} · {g['horario']}",
        key="reprog_curso",
    )
    nueva_fin = st.date_input("Nueva fecha de término del curso seleccionado", value=_a_date(curso["fin"]), key="reprog_nueva_fin")
    if st.button("Simular reprogramación", type="primary", use_container_width=True):
        try:
            cambios = _planificar_cascada(data, curso["id"], nueva_fin, festivos)
            st.session_state["reprog_propuesta"] = cambios
            st.session_state["reprog_origen"] = curso["id"]
        except Exception as exc:
            st.session_state.pop("reprog_propuesta", None)
            st.error(str(exc))

    cambios = st.session_state.get("reprog_propuesta", [])
    if cambios:
        st.markdown("### Resultado de la simulación")
        st.caption(f"{len(cambios)} curso(s) incluidos en la cascada. Los grupos pendientes y otros carriles quedan intactos.")
        for cambio in cambios:
            with st.container(border=True):
                st.markdown(f"**{cambio['curso']}**")
                st.caption(f"{cambio['horas']:g} horas · {cambio['horario']}")
                st.write(f"Inicio: {_fmt_fecha(cambio['inicio_anterior'])} → **{_fmt_fecha(cambio['inicio_nuevo'])}**")
                st.write(f"Término: {_fmt_fecha(cambio['fin_anterior'])} → **{_fmt_fecha(cambio['fin_nuevo'])}**")
                if _a_date(cambio["fin_nuevo"]) > CIERRE_CICLO:
                    st.warning("El término calculado queda fuera del cierre de ciclo configurado.")
        st.warning("Al aplicar, se actualizarán el Excel vigente y SQLite. Se conservarán los identificadores, estados MCE, PEA y documentos; se generará un respaldo del Excel.")
        if st.button("Aplicar reprogramación y guardar", type="primary", use_container_width=True, key="reprog_aplicar"):
            try:
                backup, archivo = _actualizar_excel_y_db(cambios)
                st.session_state["reprog_excel"] = archivo.read_bytes()
                st.session_state["reprog_excel_nombre"] = archivo.name
                st.session_state.pop("reprog_propuesta", None)
                st.success(f"Reprogramación aplicada. Respaldo creado: {backup.name}")
                st.download_button(
                    "Descargar programación actualizada",
                    data=st.session_state["reprog_excel"],
                    file_name=st.session_state["reprog_excel_nombre"],
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
                st.rerun()
            except Exception as exc:
                st.error(f"No se aplicaron los cambios: {exc}")
    elif st.session_state.get("reprog_excel"):
        st.download_button(
            "Descargar programación actualizada",
            data=st.session_state["reprog_excel"],
            file_name=st.session_state.get("reprog_excel_nombre", "PROGRAMACION DE CURSOS.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
