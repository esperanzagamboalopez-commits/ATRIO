# -*- coding: utf-8 -*-
"""
Motor de reprogramacion MANUAL.
Solo mueve los cursos que el docente indica explicitamente.
Valida traslapes NUEVOS en el mismo carril y advierte.
SEGURIDAD: solo lectura de atrio.sqlite3.
USO:
  python3 test_manual.py "DOCENTE" 0=2026-11-06 7=2027-02-15
  python3 test_manual.py --listar "DOCENTE"
"""
import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "datos" / "atrio.sqlite3"
OUT_DIR = BASE / "datos" / "asistente_test"

FESTIVOS = [
    date(2026, 9, 16), date(2026, 11, 2), date(2026, 11, 16),
    date(2026, 12, 20), date(2026, 12, 21), date(2026, 12, 22),
    date(2026, 12, 23), date(2026, 12, 24), date(2026, 12, 25),
    date(2026, 12, 26), date(2026, 12, 27), date(2026, 12, 28),
    date(2026, 12, 29), date(2026, 12, 30), date(2026, 12, 31),
    date(2027, 1, 1), date(2027, 1, 2), date(2027, 1, 3),
    date(2027, 1, 4), date(2027, 1, 5),
    date(2027, 2, 1), date(2027, 3, 15),
    date(2027, 3, 21), date(2027, 3, 22), date(2027, 3, 23),
    date(2027, 3, 24), date(2027, 3, 25), date(2027, 3, 26),
    date(2027, 3, 27), date(2027, 3, 28), date(2027, 3, 29),
    date(2027, 3, 30), date(2027, 3, 31),
    date(2027, 4, 1), date(2027, 4, 2), date(2027, 4, 3),
    date(2027, 4, 4),
    date(2027, 5, 1), date(2027, 5, 5), date(2027, 5, 15),
]
FEST_SET = set(FESTIVOS)
CIERRE_CICLO = date(2027, 6, 30)
EXT_MAX = 60

DIAS_MAP = {
    'LUNES': 0, 'MARTES': 1, 'MIERCOLES': 2, 'MIÉRCOLES': 2,
    'JUEVES': 3, 'VIERNES': 4, 'SABADO': 5, 'SÁBADO': 5, 'DOMINGO': 6,
}

def parsear_dias(texto_dias):
    if not isinstance(texto_dias, str):
        return []
    texto = texto_dias.upper().strip()
    if ',' in texto:
        r = [DIAS_MAP[p.strip()] for p in texto.split(',') if p.strip() in DIAS_MAP]
        if r:
            return r
    m = re.search(r'(\w+)\s+A\s+(\w+)', texto)
    if m and m.group(1) in DIAS_MAP and m.group(2) in DIAS_MAP:
        return list(range(DIAS_MAP[m.group(1)], DIAS_MAP[m.group(2)] + 1))
    m = re.search(r'(\w+)\s+Y\s+(\w+)', texto)
    if m and m.group(1) in DIAS_MAP and m.group(2) in DIAS_MAP:
        return [DIAS_MAP[m.group(1)], DIAS_MAP[m.group(2)]]
    for dia, num in DIAS_MAP.items():
        if dia in texto:
            return [num]
    return []

def extraer_bloques_horario(horario_str):
    if not isinstance(horario_str, str):
        return []
    horario_str = horario_str.replace("<br>", "\n")
    bloques = []
    for linea in horario_str.split("\n"):
        linea = linea.strip()
        if not linea:
            continue
        matches = list(re.finditer(
            r'(\d{1,2}):(\d{2})\s*(?:A|-)\s*(\d{1,2}):(\d{2})',
            linea, re.IGNORECASE))
        for i, m in enumerate(matches):
            h_ini, m_ini = int(m.group(1)), int(m.group(2))
            h_fin, m_fin = int(m.group(3)), int(m.group(4))
            if i == 0:
                parte_dias = linea[:m.start()].strip()
            else:
                parte_dias = linea[matches[i - 1].end():m.start()].strip()
            parte_dias = parte_dias.strip(" .,;:")
            if not parte_dias:
                if bloques:
                    dias = bloques[-1]['dias']
                else:
                    continue
            else:
                dias = parsear_dias(parte_dias)
            if dias:
                dur = ((h_fin * 60 + m_fin) - (h_ini * 60 + m_ini)) / 60
                bloques.append({
                    'dias': dias,
                    'duracion': dur,
                    'hora_inicio_min': h_ini * 60 + m_ini,
                })
    return bloques

def _clave_carril(horario_str):
    # Usa TODOS los bloques del horario: un curso "Lun 16-19 y Vie 10-12" no debe
    # compartir carril con uno que solo tenga el primer bloque.
    bloques = extraer_bloques_horario(horario_str)
    if not bloques:
        return None
    return tuple(sorted(
        (tuple(sorted(b["dias"])), round(b["duracion"], 2), b["hora_inicio_min"])
        for b in bloques
    ))

def _describir_carril(clave):
    if not clave:
        return "(sin horario)"
    partes = []
    for dias, dur, h_min in clave:
        h, m = h_min // 60, h_min % 60
        partes.append(f"dias={dias} | {int(dur)}h/dia | inicio={h:02d}:{m:02d}")
    return " ; ".join(partes)

def calcular_horas_entre(inicio, fin, bloques):
    total_h, total_d = 0, 0
    actual = inicio
    while actual <= fin:
        if actual in FEST_SET:
            actual += timedelta(days=1)
            continue
        dia = actual.weekday()
        h = sum(b['duracion'] for b in bloques if dia in b['dias'])
        if h > 0:
            total_h += h
            total_d += 1
        actual += timedelta(days=1)
    return total_h, total_d

def cargar_cursos():
    if not DB.exists():
        print(f"ERROR: no existe {DB}")
        sys.exit(1)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, payload FROM groups WHERE active=1").fetchall()
    finally:
        con.close()
    cursos = []
    for r in rows:
        try:
            p = json.loads(r["payload"])
        except Exception:
            continue
        inicio = p.get("inicio") or p.get("start")
        fin = p.get("fin") or p.get("end")
        docente = p.get("hoja") or p.get("docente") or ""
        horario = p.get("horario") or ""
        dur = p.get("duracion") or p.get("horas") or 0
        tipo = p.get("tipo") or ""
        nombre = p.get("nombre") or p.get("curso") or ""
        if not (inicio and fin and docente and horario):
            continue
        try:
            cursos.append({
                "grupo_id": r["id"],
                "docente": docente,
                "curso_nombre": nombre,
                "tipo": tipo,
                "fecha_inicio": date.fromisoformat(str(inicio)[:10]),
                "fecha_fin": date.fromisoformat(str(fin)[:10]),
                "duracion_horas": float(dur),
                "horario": horario,
            })
        except Exception:
            continue
    return cursos

def _cursos_de(cursos, docente):
    return sorted(
        [c for c in cursos if c["docente"] == docente],
        key=lambda c: c["fecha_inicio"])

def cmd_listar(cursos, docente):
    print("=" * 70)
    print(f"CURSOS DE: {docente}")
    print("=" * 70)
    cs = _cursos_de(cursos, docente)
    if not cs:
        print("Docente no encontrado. Disponibles:")
        for d in sorted({c['docente'] for c in cursos}):
            print(f"   - {d}")
        return
    print(f"Total: {len(cs)} cursos")
    print()
    for i, c in enumerate(cs):
        clave = _clave_carril(c["horario"])
        print(f"  [{i:2d}] {c['fecha_inicio']} -> {c['fecha_fin']}  "
              f"{c['duracion_horas']:.0f}h  {c['curso_nombre'][:40]}")
        print(f"       {c['horario'][:75]}")
        print(f"       carril: {_describir_carril(clave)}")

def aplicar_manual(cursos, docente, cambios_dict):
    cs = _cursos_de(cursos, docente)
    if not cs:
        return {"error": f"Sin cursos para '{docente}'"}

    cambios = []
    for idx in sorted(cambios_dict):
        if idx < 0 or idx >= len(cs):
            return {"error": f"Indice [{idx}] fuera de rango (0..{len(cs)-1})"}
        c = cs[idx]
        nueva_fin = cambios_dict[idx]
        bloques = extraer_bloques_horario(c["horario"])
        if not bloques:
            return {"error": f"[{idx}] sin horario valido"}
        if nueva_fin < c["fecha_inicio"]:
            return {"error": f"[{idx}] fin {nueva_fin} < inicio {c['fecha_inicio']}"}

        horas, dias = calcular_horas_entre(c["fecha_inicio"], nueva_fin, bloques)
        req = c["duracion_horas"]
        cambios.append({
            "idx": idx,
            "grupo_id": c["grupo_id"],
            "curso": c["curso_nombre"],
            "tipo": c["tipo"],
            "carril": _clave_carril(c["horario"]),
            "inicio": c["fecha_inicio"],
            "fin_anterior": c["fecha_fin"],
            "fin_nuevo": nueva_fin,
            "horas_req": req,
            "horas_reales": round(horas, 1),
            "dias_habiles": dias,
            "excede": round(horas - req, 1),
        })

    # Traslapes NUEVOS en el mismo carril
    traslapes = []
    movidos_gid = {c["grupo_id"] for c in cambios}
    for cm in cambios:
        if not cm["carril"]:
            continue
        for otro in cs:
            if otro["grupo_id"] in movidos_gid:
                continue
            if _clave_carril(otro["horario"]) != cm["carril"]:
                continue
            antes = (otro["fecha_inicio"] <= cm["fin_anterior"]
                     and otro["fecha_fin"] >= cm["inicio"])
            ahora = (otro["fecha_inicio"] <= cm["fin_nuevo"]
                     and otro["fecha_fin"] >= cm["inicio"])
            if ahora and not antes:
                traslapes.append({
                    "curso_movido": cm["curso"],
                    "periodo_nuevo": f"{cm['inicio']} -> {cm['fin_nuevo']}",
                    "curso_afectado": otro["curso_nombre"],
                    "periodo_original": f"{otro['fecha_inicio']} -> {otro['fecha_fin']}",
                })

    advertencias = []
    for cm in cambios:
        if cm["excede"] > 0:
            advertencias.append({
                "tipo": "reposicion",
                "curso": cm["curso"],
                "detalle": f"+{cm['excede']}h ({cm['horas_reales']} vs {cm['horas_req']})",
            })
        elif cm["excede"] < 0:
            advertencias.append({
                "tipo": "horas_insuficientes",
                "curso": cm["curso"],
                "detalle": f"Faltan {abs(cm['excede'])}h ({cm['horas_reales']} vs {cm['horas_req']})",
            })
        if cm["fin_nuevo"] > CIERRE_CICLO:
            dias_fuera = (cm["fin_nuevo"] - CIERRE_CICLO).days
            advertencias.append({
                "tipo": "fuera_de_ciclo",
                "curso": cm["curso"],
                "detalle": f"{dias_fuera} dias despues del cierre ({CIERRE_CICLO})",
            })
        if 'EXTENSION' in str(cm["tipo"]).upper() and cm["horas_reales"] > EXT_MAX:
            advertencias.append({
                "tipo": "excede_ext_max",
                "curso": cm["curso"],
                "detalle": f"{cm['horas_reales']}h > {EXT_MAX}h (aceptado como reposicion)",
            })

    return {
        "cambios": cambios,
        "traslapes_nuevos": traslapes,
        "advertencias": advertencias,
        "cursos_intactos": len(cs) - len(cambios),
    }

def cmd_aplicar(cursos, docente, cambios_str):
    cambios_dict = {}
    for par in cambios_str:
        if "=" not in par:
            print(f"Formato invalido: {par} (usa idx=AAAA-MM-DD)")
            sys.exit(1)
        idx_s, fecha_s = par.split("=", 1)
        try:
            cambios_dict[int(idx_s)] = date.fromisoformat(fecha_s)
        except ValueError as e:
            print(f"Error en {par}: {e}")
            sys.exit(1)

    print("=" * 70)
    print("SIMULACION MANUAL - solo lectura, nada se modifica")
    print("=" * 70)
    print(f"Docente: {docente}")
    print(f"Cambios solicitados: {len(cambios_dict)}")
    print()

    r = aplicar_manual(cursos, docente, cambios_dict)
    if "error" in r:
        print(f"ERROR: {r['error']}")
        return

    print(f"Resultado: {len(r['cambios'])} cursos movidos, "
          f"{r['cursos_intactos']} intactos")
    print()
    for c in r["cambios"]:
        marca = "  (reposicion)" if c["excede"] > 0 else ""
        print(f"  [{c['idx']}] {c['curso'][:50]}{marca}")
        print(f"    inicio: {c['inicio']} (sin cambio)")
        print(f"    fin:    {c['fin_anterior']} -> {c['fin_nuevo']}")
        print(f"    horas:  {c['horas_req']} req, {c['horas_reales']} reales, "
              f"{c['dias_habiles']} dias habiles")
        print()

    if r["traslapes_nuevos"]:
        print(f"TRASLAPES NUEVOS EN EL MISMO CARRIL ({len(r['traslapes_nuevos'])}):")
        for t in r["traslapes_nuevos"]:
            print(f"  ! {t['curso_movido'][:45]}")
            print(f"    periodo nuevo:    {t['periodo_nuevo']}")
            print(f"    choca con:        {t['curso_afectado'][:45]}")
            print(f"    periodo original: {t['periodo_original']}")
            print(f"    -> Decide: mover tambien, o ajustar la fecha del movido.")
            print()

    if r["advertencias"]:
        print(f"ADVERTENCIAS ({len(r['advertencias'])}):")
        for a in r["advertencias"]:
            print(f"  ! [{a['tipo']}] {a['curso'][:45]}")
            print(f"    {a['detalle']}")
        print()

    print("=" * 70)
    print("IMPORTANTE")
    print("=" * 70)
    print("Estas fechas son para PUBLICIDAD y DIFUSION.")
    print("Para Excel de Programacion y SISAE: coincidir EXACTAMENTE.")
    print("=" * 70)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "ultimo_manual.json"
    dest.write_text(json.dumps({
        "docente": docente,
        "cambios_solicitados": {str(k): str(v) for k, v in cambios_dict.items()},
        "resultado": r,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nGuardado: {dest}")

if __name__ == "__main__":
    cursos = cargar_cursos()
    if len(sys.argv) < 2:
        print("Uso:")
        print('  python3 test_manual.py --listar "NOMBRE DOCENTE"')
        print('  python3 test_manual.py "NOMBRE DOCENTE" 0=2026-11-06 7=2027-02-15')
        sys.exit(1)
    if sys.argv[1] == "--listar" and len(sys.argv) >= 3:
        cmd_listar(cursos, sys.argv[2])
    else:
        cmd_aplicar(cursos, sys.argv[1], sys.argv[2:])
