# -*- coding: utf-8 -*-
"""Radar de Pendientes de ATRIO (Solo lectura, sin duplicar estados)."""
import json
from datetime import datetime
import centro as C

def obtener_alertas_excluidas():
    """Lee la lista de alertas que el usuario decidió silenciar (histórico)."""
    return C.setting('pendientes_excluidos', [])

def calcular_pendientes(data, C, today):
    pendientes = []
    deadline_dias = int(C.setting('deadline_days', 11))
    excluidos = obtener_alertas_excluidas()

    for g in data:
        s = C.status(g['id'])
        dias_para_inicio = 999
        dias_para_fin = 999
        
        try:
            inicio_date = datetime.strptime(str(g['inicio'])[:10], '%Y-%m-%d').date()
            fin_date = datetime.strptime(str(g['fin'])[:10], '%Y-%m-%d').date()
            dias_para_inicio = (inicio_date - today).days
            dias_para_fin = (fin_date - today).days
        except Exception:
            pass

        def crear_ficha(tarea_id, cat, accion, fecha_limite, dias, prioridad, enlace):
            # Si está excluido (silenciado), no lo mostramos
            f_id = f"{g['id']}_{tarea_id}"
            if f_id in excluidos:
                return None

            estado = "Pendiente"
            if dias < 0: estado = "Vencido"
            elif dias <= deadline_dias: estado = "Por vencer"
            
            return {
                "id": f_id, "grupo_id": g['id'], "curso": g['nombre'],
                "docente": g['hoja'], "tipo": g['tipo'], "categoria": cat,
                "accion": accion, "fecha_limite": str(fecha_limite),
                "dias": dias, "estado": estado, "prioridad": prioridad, "enlace": enlace
            }

        # 1. PREPARAR PEA (Si el estado real dice 'Sin PEA')
        if s['doc'] == 'Sin PEA':
            f = crear_ficha("PEA", "Preparar PEA", "Elaborar y confirmar PEA", g['inicio'], dias_para_inicio, "Alta", "Preparar PEA")
            if f: pendientes.append(f)

        # 2. SEGUIMIENTO Y MCE (Si el estado real dice que falta o está observado)
        if s['mce'] == 'Observado':
            f = crear_ficha("MCE_OBS", "Seguimiento y MCE", "Corregir observaciones en MCE", g['inicio'], dias_para_inicio, "Alta", "Seguimiento y MCE")
            if f: pendientes.append(f)
        elif s['mce'] == 'No subido' and g['tipo'] != 'Regular':
            f = crear_ficha("MCE_SUBIR", "Seguimiento y MCE", "Subir PEA al MCE", g['inicio'], dias_para_inicio, "Media", "Seguimiento y MCE")
            if f: pendientes.append(f)

        # 3. CIERRE DE GRUPO (Solo avisa que el curso terminó, invita a revisar Control escolar)
        if dias_para_fin < 0:
            f = crear_ficha("CIERRE", "Control escolar / Constancias", "Verificar cierre, credenciales y constancias del grupo", g['fin'], dias_para_fin, "Media", "Control escolar")
            if f: pendientes.append(f)

    pendientes.sort(key=lambda x: x['dias'])
    return pendientes

def excluir_alerta(pendiente_id):
    """Silencia una alerta (útil para históricos que ya no quieres ver)."""
    excluidos = obtener_alertas_excluidas()
    if pendiente_id not in excluidos:
        excluidos.append(pendiente_id)
        C.set_setting('pendientes_excluidos', excluidos)

def restaurar_alerta(pendiente_id):
    """Quita el silencio de una alerta."""
    excluidos = obtener_alertas_excluidas()
    if pendiente_id in excluidos:
        excluidos.remove(pendiente_id)
        C.set_setting('pendientes_excluidos', excluidos)
