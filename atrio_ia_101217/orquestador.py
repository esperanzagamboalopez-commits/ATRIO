"""Punto futuro de integración con Gemini; en esta fase sólo enruta localmente.

No existe transferencia a la nube. El prompt se mantiene listo, pero no se envía.
"""
from .puente import responder_primero
from .prompts import SYSTEM_PROMPT


def responder(pregunta, contexto_atrio, memoria=None):
    return responder_primero(pregunta, contexto_atrio, memoria or {})


def estado():
    return {'modo':'local','solo_lectura':True,'gemini_activo':False,
            'documento_institucional_cargado':bool(SYSTEM_PROMPT)}
