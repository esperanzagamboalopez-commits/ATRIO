# -*- coding: utf-8 -*-
"""Asistente flotante global (burbuja Glass Executive).

Se dibuja una sola vez desde app.py con render(). Usa el mismo motor local
que la página Asistente virtual (responder_local), sin enviar datos fuera.
"""
import sqlite3

import streamlit as st

import asistente_atrio_101214 as AI214
import centro as C


_CSS = """
<style>
/* Burbuja flotante */
div[class*="st-key-btn_flotante_asistente"] {
    position: fixed !important;
    bottom: 30px !important;
    right: 30px !important;
    z-index: 99999 !important;
    width: 65px !important;
    height: 65px !important;
}
div[class*="st-key-btn_flotante_asistente"] button {
    background: linear-gradient(135deg, #FF1493 0%, #D4AF37 100%) !important;
    color: #09090B !important;
    border-radius: 50% !important;
    width: 65px !important;
    height: 65px !important;
    box-shadow: 0 6px 22px rgba(255,20,147,.55) !important;
    border: 2px solid #D4AF37 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
    transition: all .3s cubic-bezier(.175,.885,.32,1.275) !important;
}
div[class*="st-key-btn_flotante_asistente"] button:hover {
    transform: scale(1.12) !important;
    box-shadow: 0 8px 26px rgba(255,20,147,.75) !important;
    border-color: #FF1493 !important;
}
div[class*="st-key-btn_flotante_asistente"] button p {
    font-size: 28px !important;
    margin: 0 !important;
    line-height: 1 !important;
}
/* Panel de conversación */
div[class*="st-key-mini_chat_container"] {
    position: fixed !important;
    bottom: 110px !important;
    right: 30px !important;
    width: 360px !important;
    max-height: 520px !important;
    z-index: 99998 !important;
    background: rgba(20,20,26,.96) !important;
    border: 1px solid rgba(212,175,55,.45) !important;
    border-radius: 16px !important;
    box-shadow: 0 12px 40px rgba(0,0,0,.55), 0 0 24px rgba(255,20,147,.18) !important;
    padding: 18px !important;
    overflow-y: auto !important;
    backdrop-filter: blur(16px);
}
div[class*="st-key-mini_chat_container"] h3 {
    font-family: 'Playfair Display', Georgia, serif !important;
    color: #F4F4F5 !important;
}
@media (max-width: 600px) {
    div[class*="st-key-mini_chat_container"] {
        right: 12px !important;
        left: 12px !important;
        width: auto !important;
    }
}
</style>
"""

_SIN_RESPUESTA = (
    "No encontré eso localmente. Abre el **Asistente virtual** completo en el menú lateral."
)


def render():
    """Dibuja la burbuja y, si está abierta, el panel de consulta rápida."""
    st.markdown(_CSS, unsafe_allow_html=True)

    if st.button(":material/chat:", key="btn_flotante_asistente", help="Asistente rápido"):
        st.session_state["show_mini_chat"] = not st.session_state.get("show_mini_chat", False)

    if not st.session_state.get("show_mini_chat"):
        return

    with st.container(key="mini_chat_container"):
        st.markdown("<h3 style='margin-top:0'>Asistente rápido</h3>", unsafe_allow_html=True)
        st.caption("Pregunta por tu agenda o programación, por ejemplo: ¿qué tengo el 15 de noviembre?")

        if "mini_chat_history" not in st.session_state:
            st.session_state["mini_chat_history"] = []

        for msg in st.session_state["mini_chat_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        with st.form("mini_chat_form", clear_on_submit=True):
            pregunta = st.text_input("Tu consulta", placeholder="Escribe aquí…")
            enviar = st.form_submit_button("Preguntar")

        if enviar and pregunta.strip():
            historial = st.session_state["mini_chat_history"]
            historial.append({"role": "user", "content": pregunta.strip()})
            try:
                respuesta, _fuente, estado = AI214.responder_local(
                    pregunta.strip(), C, st.session_state.get("ai215_context", {})
                )
                st.session_state["ai215_context"] = estado
            except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
                respuesta = f"No pude consultar la fuente local ({type(exc).__name__})."
            historial.append({"role": "assistant", "content": respuesta or _SIN_RESPUESTA})
            del historial[:-12]
            st.rerun()

        if st.button("Cerrar chat", key="close_mini", width="stretch"):
            st.session_state["show_mini_chat"] = False
            st.rerun()
