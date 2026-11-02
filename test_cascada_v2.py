# -*- coding: utf-8 -*-
"""
Motor de reprogramacion con cascada SOLO en el mismo carril.
Carril = mismos dias + mismas horas exactas.
Otros carriles NO se tocan.
Horas extra = reposicion (advertencia, no bloqueo).
SEGURIDAD: solo lectura de atrio.sqlite3.
"""
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BASE = Path.home() / "PEAS" / "ATRIO_OPERATIVO_01"
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

def _parse_fecha(s):
    if isinstance(s, date):
        return s
    s = str(s).strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    try:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    except Exception:
        raise ValueError(f"Fecha invalida: {s}")

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
    """Devuelve bloques con dias, duracion y hora_inicio_min."""
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
    """Mismos dias + misma duracion + misma hora de inicio = mismo carril."""
    bloques = extraer_bloques_horario(horario_str)
    if not bloques:
        return None
    b = bloques[0]
    return (tuple(sorted(b["dias"])), round(b["duracion"], 2), b["hora_inicio_min"])

def _describir_carril(clave):
    if not clave:
        return "(sin horario)"
    dias, dur, h_min = clave
    h, m = h_min // 60, h_min % 60
    return f"dias={dias} | {int(dur)}h/dia | inicio={h:02d}:{m:02d}"

def simular_desde_inicio(fecha_inicio, bloques, limite=500):
    resultados, actual = [], fecha_inicio
    horas_acum, dias_acum = 0, 0
    while len(resultados) < limite:
        if actual > CIERRE_CICLO + timedelta(days=365):
            break
        if actual in FEST_SET:
            actual += timedelta(days=1)
            continue
        dia = actual.weekday()
        h = sum(b['duracion'] for b in bloques if dia in b['dias'])
        if h > 0:
            horas_acum += h
            dias_acum += 1
            resultados.append({'fecha': actual, 'horas_acum': horas_acum,
                                'dias_acum': dias_acum})
        actual += timedelta(days=1)
    return resultados

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

def calcular_fecha_desde_horas(fecha_inicio, horas_obj, bloques):
    if not bloques:
        return None, None, None
    sim = simular_desde_inicio(fecha_inicio, bloques)
    if not sim:
        return None, None, None
    primer = next((r for r in sim if r['horas_acum'] >= horas_obj), None)
    if primer is None:
        u = sim[-1]
        return u['fecha'], u['horas_acum'], u['dias_acum']
    return primer['fecha'], primer['horas_acum'], primer['dias_acum']

def siguiente_dia_del_bloque(desde, bloques):
    dias = set()
    for b in bloques:
        dias.update(b['dias'])
    d = desde
    for _ in range(400):
        if d.weekday() in dias and d not in FEST_SET:
            return d
        d += timedelta(days=1)
    return None

def aplicar_cambio_con_cascada(cursos, grupo_id, nueva_fin, estricto=False):
    """
    Aplica el cambio al curso dado y propaga SOLO en su mismo carril.
    Retorna dict con cambios aplicados, reposiciones y advertencias.
    """
    idx = {c["grupo_id"]: c for c in cursos}
    c0 = idx.get(grupo_id)
    if not c0:
        return {"error": "curso_no_encontrado", "grupo_id": grupo_id}

    clave = _clave_carril(c0["horario"])
    if not clave:
        return {"error": "sin_horario", "grupo_id": grupo_id}

    carril = [c for c in cursos if _clave_carril(c["horario"]) == clave]
    carril.sort(key=lambda c: c["fecha_inicio"])

    pos = next((i for i, c in enumerate(carril)
                if c["grupo_id"] == grupo_id), None)
    if pos is None:
        return {"error": "no_esta_en_carril", "grupo_id": grupo_id}

    afectados = carril[pos:]
    cambios, advertencias = [], []

    for i, c in enumerate(afectados):
        bloques = extraer_bloques_horario(c["horario"])
        if not bloques:
            return {"error": f"sin_horario en {c['grupo_id']}"}

        if i == 0:
            nuevo_inicio = c["fecha_inicio"]
            nuevo_fin = nueva_fin
            if nuevo_fin < nuevo_inicio:
                return {"error": "fin_antes_de_inicio",
                        "detalle": f"{nuevo_fin} < {nuevo_inicio}"}
        else:
            cursor = _parse_fecha(cambios[-1]["fin_nuevo"])
            base = cursor + timedelta(days=1)
            nuevo_inicio = siguiente_dia_del_bloque(base, bloques)
            if nuevo_inicio is None:
                return {"error": f"sin_dia_habil despues de {base}"}
            nuevo_fin, _, _ = calcular_fecha_desde_horas(
                nuevo_inicio, c["duracion_horas"], bloques)
            if nuevo_fin is None:
                return {"error": f"calculo_fallido en {c['grupo_id']}"}

        if nuevo_fin > CIERRE_CICLO:
            if estricto:
                return {"error": f"excede_ciclo en {c['grupo_id']}",
                        "detalle": f"{nuevo_fin} > {CIERRE_CICLO}"}
            dias_fuera = (nuevo_fin - CIERRE_CICLO).days
            if dias_fuera <= 2:
                sugerencia = "absorbible en penultimo curso (<=2 dias)"
            else:
                sugerencia = "comprimir penultimo curso para liberar dias"
            advertencias.append({
                "tipo": "fuera_de_ciclo",
                "grupo_id": c["grupo_id"],
                "curso": c["curso_nombre"],
                "fin_nuevo": str(nuevo_fin),
                "cierre": str(CIERRE_CICLO),
                "dias_fuera": dias_fuera,
                "sugerencia": sugerencia,
                "detalle": f"Termina {dias_fuera} dias despues del cierre",
            })

        horas_reales, dias_habiles = calcular_horas_entre(
            nuevo_inicio, nuevo_fin, bloques)
        requeridas = c["duracion_horas"]
        excede = round(horas_reales - requeridas, 1)
        es_reposicion = excede > 0

        if es_reposicion:
            advertencias.append({
                "tipo": "reposicion",
                "grupo_id": c["grupo_id"],
                "curso": c["curso_nombre"],
                "horas_requeridas": requeridas,
                "horas_reales": round(horas_reales, 1),
                "extra": excede,
                "detalle": (f"+{excede} h de reposicion "
                            f"({round(horas_reales,1)} vs {requeridas})"),
            })
        elif excede < 0:
            advertencias.append({
                "tipo": "horas_insuficientes",
                "grupo_id": c["grupo_id"],
                "curso": c["curso_nombre"],
                "horas_requeridas": requeridas,
                "horas_reales": round(horas_reales, 1),
                "falta": abs(excede),
                "detalle": (f"Faltan {abs(excede)} h "
                            f"({round(horas_reales,1)} vs {requeridas})"),
            })

        es_ext = 'EXTENSION' in str(c["tipo"]).upper()
        if es_ext and horas_reales > EXT_MAX:
            advertencias.append({
                "tipo": "excede_ext_max",
                "grupo_id": c["grupo_id"],
                "curso": c["curso_nombre"],
                "horas_reales": round(horas_reales, 1),
                "detalle": (f"Extension: {round(horas_reales,1)} h > "
                            f"{EXT_MAX} h. Aceptado como reposicion."),
            })

        cambios.append({
            "grupo_id": c["grupo_id"],
            "curso_nombre": c["curso_nombre"],
            "tipo": c["tipo"],
            "inicio_anterior": str(c["fecha_inicio"]),
            "fin_anterior": str(c["fecha_fin"]),
            "inicio_nuevo": str(nuevo_inicio),
            "fin_nuevo": str(nuevo_fin),
            "horas_requeridas": requeridas,
            "horas_reales": round(horas_reales, 1),
            "dias_habiles": dias_habiles,
            "excede_horas": excede,
            "es_reposicion": es_reposicion,
        })

    intactos = len(cursos) - len(cambios)
    return {
        "carril": _describir_carril(clave),
        "cambios": cambios,
        "advertencias": advertencias,
        "cursos_intactos": intactos,
        "cursos_afectados": len(cambios),
    }

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
        print("Docente sin cursos o no encontrado.")
        print("Docentes disponibles:")
        for d in sorted({c['docente'] for c in cursos}):
            print(f"   - {d}")
        return
    print(f"Total: {len(cs)} cursos")
    print()
    for i, c in enumerate(cs):
        clave = _clave_carril(c["horario"])
        carril_desc = _describir_carril(clave)
        print(f"  [{i:2d}] {c['fecha_inicio']} -> {c['fecha_fin']}  "
              f"{c['duracion_horas']:.0f}h  {c['curso_nombre'][:40]}")
        print(f"       {c['horario'][:75]}")
        print(f"       carril: {carril_desc}")

def cmd_aplicar(cursos, docente, idx, nueva_fin_str, estricto=False):
    cs = _cursos_de(cursos, docente)
    if not cs:
        print(f"Docente '{docente}' sin cursos.")
        return
    if idx < 0 or idx >= len(cs):
        print(f"Indice {idx} fuera de rango (0..{len(cs)-1})")
        return
    try:
        nueva_fin = _parse_fecha(nueva_fin_str)
    except ValueError as e:
        print(f"Error de fecha: {e}")
        return

    c0 = cs[idx]
    print("=" * 70)
    print("SIMULACION - solo lectura, nada se modifica")
    print("=" * 70)
    print(f"Docente:    {docente}")
    print(f"Curso:      [{idx}] {c0['curso_nombre']}")
    print(f"Carril:     {_describir_carril(_clave_carril(c0['horario']))}")
    print(f"Fin actual: {c0['fecha_fin']}")
    print(f"Fin nuevo:  {nueva_fin}")
    print()

    r = aplicar_cambio_con_cascada(cursos, c0["grupo_id"], nueva_fin, estricto=estricto)

    if "error" in r:
        print(f"ERROR: {r['error']}")
        if "detalle" in r:
            print(f"Detalle: {r['detalle']}")
        return

    print(f"Resultado: {r['cursos_afectados']} cursos movidos en el carril")
    print(f"           {r['cursos_intactos']} cursos intactos (otros carriles)")
    print()
    for c in r["cambios"]:
        etiqueta = "  (reposicion)" if c["es_reposicion"] else ""
        print(f"  - {c['curso_nombre'][:50]}{etiqueta}")
        print(f"    inicio: {c['inicio_anterior']} -> {c['inicio_nuevo']}")
        print(f"    fin:    {c['fin_anterior']} -> {c['fin_nuevo']}")
        print(f"    horas:  {c['horas_requeridas']} requeridas, "
              f"{c['horas_reales']} reales, {c['dias_habiles']} dias habiles")
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
    print("Para Excel de Programacion y SISAE: deben coincidir EXACTAMENTE.")
    print("Orden recomendado: actualizar Programacion -> SISAE -> publicar.")
    print("=" * 70)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "ultimo_resultado.json"
    dest.write_text(json.dumps({
        "docente": docente, "indice_curso": idx,
        "curso_0": c0["curso_nombre"],
        "fin_anterior": str(c0["fecha_fin"]),
        "fin_nuevo": str(nueva_fin),
        "resultado": r,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nResultado guardado en: {dest}")

if __name__ == "__main__":
    cursos = cargar_cursos()
    args = sys.argv[1:]

    if not args:
        print("=" * 70)
        print("DEMO AUTOMATICA")
        print("=" * 70)
        from collections import Counter
        cnt = Counter(c["docente"] for c in cursos)
        if not cnt:
            print("Sin cursos en la base.")
            sys.exit(0)
        docente = cnt.most_common(1)[0][0]
        cs = _cursos_de(cursos, docente)
        if len(cs) < 2:
            print(f"Docente '{docente}' con menos de 2 cursos.")
            sys.exit(0)
        idx = 0
        nueva = cs[0]["fecha_fin"] + timedelta(days=10)
        cmd_aplicar(cursos, docente, idx, nueva.isoformat())
    elif args[0] == "--listar" and len(args) >= 2:
        cmd_listar(cursos, args[1])
    elif len(args) == 4 and args[3] == "--estricto":
        docente, idx_s, fecha_s, _ = args
        try:
            idx = int(idx_s)
        except ValueError:
            print(f"Indice invalido: {idx_s}")
            sys.exit(1)
        cmd_aplicar(cursos, docente, idx, fecha_s, estricto=True)
    elif len(args) == 3:
        docente, idx_s, fecha_s = args
        try:
            idx = int(idx_s)
        except ValueError:
            print(f"Indice invalido: {idx_s}")
            sys.exit(1)
        cmd_aplicar(cursos, docente, idx, fecha_s)
    else:
        print("Uso:")
        print("  python3 test_cascada_v2.py")
        print("      -> demo automatica")
        print("  python3 test_cascada_v2.py --listar \"NOMBRE DOCENTE\"")
        print("      -> lista cursos del docente con indices")
        print("  python3 test_cascada_v2.py \"NOMBRE DOCENTE\" 0 2026-11-06")
        print("      -> aplica cascada al curso [0] hasta el 06/11/2026")
