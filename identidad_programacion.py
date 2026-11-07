"""Reglas conservadoras para conciliar grupos entre versiones de programación.

La identidad académica depende del nombre, tipo y especialidad.
El docente, las fechas, el horario y la duración son atributos modificables.
"""
from __future__ import annotations

import unicodedata

CAMPOS_COMPARABLES = (
    "hoja", "nombre", "tipo", "inicio", "fin", "duracion", "horario",
    "poblacion", "aula", "especialidad_programada",
)


def normalizar(value):
    """Normaliza acentos, mayúsculas y espacios sin alterar el texto original."""
    value = " ".join(str(value or "").split()).casefold()
    return "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )


def clave_identidad(group):
    """Clave académica: nombre + tipo + especialidad; excluye al docente."""
    return tuple(normalizar(group.get(field)) for field in (
        "nombre", "tipo", "especialidad_programada"
    ))


def cambios_entre(before, after):
    """Devuelve campos modificados, ignorando diferencias de formato."""
    changed = []
    for field in CAMPOS_COMPARABLES:
        a, b = before.get(field), after.get(field)
        if field in (
            "hoja", "nombre", "tipo", "horario", "aula",
            "especialidad_programada",
        ):
            different = normalizar(a) != normalizar(b)
        else:
            different = a != b
        if different:
            changed.append(field)
    return changed


def _payload(record):
    value = record.get("payload", record)
    if isinstance(value, str):
        import json
        value = json.loads(value)
    return dict(value or {})


def planificar_conciliacion(previous, incoming):
    """Propone vínculos sin adivinar cuando una identidad es ambigua.

    previous: registros con id, rowkey, fingerprint y payload.
    incoming: grupos normalizados leídos del Excel.

    Los grupos no incluidos se devuelven como pendientes de reprogramación.
    No se consideran eliminados ni se pierden sus vínculos o antecedentes.
    """
    old = []
    for record in previous:
        item = dict(record)
        item["_payload"] = _payload(record)
        old.append(item)

    used = set()
    vinculados, nuevos, no_incluidos, avisos = [], [], [], []

    for row in incoming:
        row = dict(row)
        rowkey = f"{row.get('hoja', '')}|{row.get('fila', '')}"
        identity = clave_identidad(row)
        available = [item for item in old if item.get("id") not in used]

        exact = [
            item for item in available
            if item.get("fingerprint") and
            item.get("fingerprint") == row.get("fingerprint")
        ]
        same_row_identity = [
            item for item in available
            if item.get("rowkey") == rowkey and
            clave_identidad(item["_payload"]) == identity
        ]
        same_identity = [
            item for item in available
            if clave_identidad(item["_payload"]) == identity
        ]

        candidate = None
        reason = None
        ambiguous = False
        if len(exact) == 1:
            candidate, reason = exact[0], "huella_exacta"
        elif len(exact) > 1:
            ambiguous, reason = True, "huella_duplicada"
        elif len(same_row_identity) == 1:
            candidate, reason = same_row_identity[0], "misma_fila_mismo_curso"
        elif len(same_row_identity) > 1:
            ambiguous, reason = True, "identidad_duplicada_en_fila"
        elif len(same_identity) == 1:
            candidate, reason = same_identity[0], "mismo_curso_fila_o_docente_cambiado"
        elif len(same_identity) > 1:
            ambiguous, reason = True, "varios_cursos_candidatos"

        if candidate is not None:
            uid = candidate.get("id")
            used.add(uid)
            before = candidate["_payload"]
            changes = cambios_entre(before, row)
            teacher_changed = normalizar(before.get("hoja")) != normalizar(row.get("hoja"))
            hours_changed = before.get("duracion") != row.get("duracion")
            if not changes:
                pea_action = "conservar"
            elif teacher_changed:
                pea_action = "reutilizar_base_y_revisar_docente_y_horas"
            elif hours_changed:
                pea_action = "reajustar_horas_y_revisar_contenido"
            else:
                pea_action = "actualizar_datos_variables"
            vinculados.append({
                "id": uid,
                "anterior": before,
                "actual": row,
                "motivo_vinculo": reason,
                "cambios": changes,
                "docente_cambio": teacher_changed,
                "horas_cambiaron": hours_changed,
                "accion_pea": pea_action,
                "requiere_pea_nuevo": False,
                "requiere_revision_manual": False,
            })
            continue

        # Un cambio de nombre nunca hereda el PEA del nombre anterior.
        possible_rename = [
            item for item in available
            if item.get("rowkey") == rowkey
            and normalizar(item["_payload"].get("tipo")) == normalizar(row.get("tipo"))
            and normalizar(item["_payload"].get("especialidad_programada")) == normalizar(row.get("especialidad_programada"))
            and normalizar(item["_payload"].get("nombre")) != normalizar(row.get("nombre"))
        ]
        rename_from = possible_rename[0].get("id") if len(possible_rename) == 1 else None
        item = {
            "actual": row,
            "motivo": (
                "coincidencia_ambigua" if ambiguous else
                "nombre_cambiado" if rename_from else "curso_nuevo"
            ),
            "posible_grupo_anterior": rename_from,
            "requiere_pea_nuevo": not ambiguous,
            "requiere_revision_manual": ambiguous,
            "accion_pea": (
                "resolver_identidad_antes_de_reutilizar" if ambiguous
                else "elaborar_pea_nuevo"
            ),
        }
        nuevos.append(item)
        if ambiguous:
            avisos.append(
                f"No se vinculó automáticamente '{row.get('nombre', '')}': "
                "hay más de un grupo candidato. Requiere revisión manual."
            )
        elif rename_from:
            avisos.append(
                f"El nombre de '{row.get('nombre', '')}' cambió o sustituyó al "
                "registro anterior. Se requiere un PEA nuevo; el anterior no se reutiliza."
            )
        else:
            avisos.append(
                f"Curso nuevo: '{row.get('nombre', '')}'. "
                "Requiere PEA nuevo cuando corresponda."
            )

    for item in old:
        if item.get("id") not in used:
            no_incluidos.append({
                "id": item.get("id"),
                "grupo": item["_payload"],
                "estado_propuesto": "pendiente_de_reprogramacion",
                "eliminar": False,
            })

    return {
        "vinculados": vinculados,
        "nuevos": nuevos,
        "no_incluidos": no_incluidos,
        "avisos": avisos,
        "resumen": {
            "recibidos": len(incoming),
            "vinculados": len(vinculados),
            "nuevos": len(nuevos),
            "no_incluidos": len(no_incluidos),
        },
    }



def grupo_incluido_en_actualizacion(group):
    """True si el grupo participa en la programación vigente de la jornada.

    Los registros anteriores a esta regla se consideran incluidos para mantener
    compatibilidad. Los pendientes y sustituidos quedan fuera de los procesos
    operativos, aunque sigan disponibles para consulta.
    """
    meta = group.get("_atrio") or {}
    state = normalizar(meta.get("estado_programacion"))
    if state.startswith("pendiente de reprogramacion"):
        return False
    if state.startswith("sustituido por cambio de nombre"):
        return False
    return meta.get("incluido_en_ultima_actualizacion", True) is not False


def grupos_operativos(groups):
    """Filtra grupos incluidos sin borrar ni mutar la colección original."""
    return [group for group in groups if grupo_incluido_en_actualizacion(group)]
