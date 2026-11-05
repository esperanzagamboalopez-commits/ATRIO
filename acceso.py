"""ATRIO · Acceso privado con contraseña (Fase 2).

La contraseña se lee de st.secrets['ATRIO_PASSWORD'] o de la variable de entorno
ATRIO_PASSWORD. Si no está configurada, la app se detiene: no existe contraseña por defecto.
"""
import hmac
import os

import streamlit as st

_SESION = 'atrio_acceso_ok'


def _contrasena_configurada():
    try:
        valor = st.secrets.get('ATRIO_PASSWORD', None)
    except Exception:
        valor = None
    if not valor:
        valor = os.getenv('ATRIO_PASSWORD', '')
    return str(valor or '')


def exigir():
    """Detiene la ejecución hasta que el visitante escriba la contraseña correcta."""
    esperada = _contrasena_configurada()
    if not esperada:
        st.error('Acceso no configurado. Define ATRIO_PASSWORD en st.secrets o como variable de entorno '
                 'y reinicia la aplicación.')
        st.stop()
    if st.session_state.get(_SESION):
        with st.sidebar:
            if st.button('Cerrar sesión', key='atrio_cerrar_sesion'):
                st.session_state.pop(_SESION, None)
                st.rerun()
        return
    st.markdown('<h2 style="font-family:\'Playfair Display\',Georgia,serif;color:#D4AF37;margin-bottom:0">ATRIO</h2>'
                '<p style="color:#6B6063">Acceso privado · CECATI 31</p>', unsafe_allow_html=True)
    with st.form('atrio_login'):
        intento = st.text_input('Contraseña', type='password')
        entrar = st.form_submit_button('Entrar')
    if entrar:
        if hmac.compare_digest(intento.encode('utf-8'), esperada.encode('utf-8')):
            st.session_state[_SESION] = True
            st.rerun()
        else:
            st.error('Contraseña incorrecta.')
    st.stop()
