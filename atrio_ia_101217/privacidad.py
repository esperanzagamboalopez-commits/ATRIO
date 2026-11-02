"""Límite de privacidad: sólo estructuras de métricas agregadas y tipadas pueden salir.

No se utiliza redacción por expresiones regulares como frontera de seguridad;
una expresión regular NO identifica de manera fiable todos los nombres propios.
"""
from typing import Any

_ALLOWED_METRICS = {'grupos_activos', 'pea_versiones', 'registros_historicos'}
_ALLOWED_UNITS = {'grupos', 'versiones_pea', 'expedientes'}
_ALLOWED_SOURCES = {
    'sqlite:groups', 'sqlite:artifacts+biblioteca_pea+pea_repo_actual_101213',
    'sqlite:pea_hist_101212'
}


def contexto_externo_seguro(*, indicador: str, valor: int, unidad: str, fuente: str) -> dict[str, Any]:
    """Lista blanca cerrada. No acepta nombres, texto de consulta, rutas ni registros."""
    if indicador not in _ALLOWED_METRICS or unidad not in _ALLOWED_UNITS or fuente not in _ALLOWED_SOURCES:
        raise ValueError('Contexto no permitido para un servicio externo.')
    if type(valor) is not int or not 0 <= valor <= 1_000_000:
        raise ValueError('Métrica externa inválida.')
    return {'indicador': indicador, 'valor': valor, 'unidad': unidad, 'fuente': fuente}


def para_mostrar_local(texto: str, acceso_autorizado: bool = False) -> str:
    """No hace desanonimización silenciosa. La autorización debe darla ATRIO."""
    if not isinstance(texto, str):
        raise TypeError('Se esperaba texto.')
    return texto


def prohibir_envio_raw(_: Any):
    """Impide usos accidentales de preguntas, historiales o resultados sin filtrar."""
    raise PermissionError('No enviar texto o registros sin un adaptador externo auditado.')
