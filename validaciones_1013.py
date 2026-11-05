# -*- coding: utf-8 -*-
"""Módulo de validaciones preventivas para ATRIO."""

def validar_datos_grupos(grupos):
    """Revisa los datos en memoria (del Excel) buscando errores lógicos."""
    errores = []
    
    for g in grupos:
        grupo_id = g.get('id', 'Desconocido')
        nombre = g.get('nombre', 'Sin nombre')
        
        # Validación 1: Fechas invertidas
        if g.get('inicio') and g.get('fin'):
            if g['inicio'] > g['fin']:
                errores.append({
                    'tipo': 'Fechas invertidas',
                    'grupo': nombre,
                    'detalle': f"Empieza {g['inicio']} pero termina {g['fin']}"
                })
        
        # Validación 2: Duración en 0 o negativa
        if g.get('duracion', 0) <= 0:
            errores.append({
                'tipo': 'Duración inválida',
                'grupo': nombre,
                'detalle': f"El curso tiene {g.get('duracion', 0)} horas registradas."
            })
            
        # Validación 3: Curso sin horario
        if not g.get('horario') or str(g.get('horario')).strip() == "":
             errores.append({
                'tipo': 'Sin horario',
                'grupo': nombre,
                'detalle': "El curso no tiene días/horas asignados."
            })
            
    return errores
