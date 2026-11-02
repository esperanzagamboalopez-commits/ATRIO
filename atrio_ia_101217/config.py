"""Los valores de entorno se consultan en tiempo de ejecución."""
import os
from . import VERSION_ASISTENTE

ASSISTANT_VERSION = VERSION_ASISTENTE

def atrio_version():
    return os.getenv('ATRIO_VERSION', 'no determinada')

MODO_LECTURA = True
MODO_ESCRITURA = False
BUSQUEDA_WEB = False
PRIVACIDAD_ESTRICTA = True
# No es un interruptor automático: ninguna función local efectúa envíos externos.
GEMINI_EXTERNO_HABILITADO = False
