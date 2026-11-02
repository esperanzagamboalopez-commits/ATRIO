"""ATRIO · Preferencias de orden del menú. No modifica nombres, destinos ni datos académicos.

La selección es una preferencia local dentro de la tabla de ajustes existente de ATRIO.
"""
import streamlit as st

CLAVE='orden_menu'
BORRADOR='atrio_orden_menu_borrador_10124'

def orden_actual(paginas,guardado):
    """Normaliza preferencias: conserva cada módulo exactamente una vez.

    Si hay módulos nuevos en futuras versiones, se agregan al final, sin desaparecer.
    """
    disponibles=list(paginas)
    if not isinstance(guardado,list):
        return disponibles
    resultado=[]
    for pagina in guardado:
        if isinstance(pagina,str) and pagina in disponibles and pagina not in resultado:
            resultado.append(pagina)
    resultado.extend(pagina for pagina in disponibles if pagina not in resultado)
    return resultado

def panel_ajustes(paginas,centro):
    """Solo aparece en Ajustes; no añade widgets al menú lateral."""
    st.subheader('Organización del menú')
    with st.expander('Reordenar apartados del menú lateral',expanded=False):
        st.caption('Sube o baja cada apartado con las flechas. El menú no cambiará hasta pulsar Guardar orden. Se conservan los mismos módulos, iconos y funciones.')
        guardado=orden_actual(paginas,centro.setting(CLAVE,[]))
        if BORRADOR not in st.session_state or not isinstance(st.session_state[BORRADOR],list) or set(st.session_state[BORRADOR])!=set(paginas) or len(st.session_state[BORRADOR])!=len(paginas):
            st.session_state[BORRADOR]=list(guardado)
        borrador=st.session_state[BORRADOR]
        for indice,pagina in enumerate(borrador):
            fila,subir,bajar=st.columns([8,1,1],gap='small')
            with fila:
                st.markdown('**'+str(indice+1)+'. '+pagina+'**')
            with subir:
                if st.button('↑',key='atrio_orden_subir_'+str(indice),disabled=indice==0,help='Subir '+pagina,use_container_width=True):
                    otro=list(borrador)
                    otro[indice-1],otro[indice]=otro[indice],otro[indice-1]
                    st.session_state[BORRADOR]=otro
                    st.rerun()
            with bajar:
                if st.button('↓',key='atrio_orden_bajar_'+str(indice),disabled=indice==len(borrador)-1,help='Bajar '+pagina,use_container_width=True):
                    otro=list(borrador)
                    otro[indice],otro[indice+1]=otro[indice+1],otro[indice]
                    st.session_state[BORRADOR]=otro
                    st.rerun()
        izquierda,derecha=st.columns(2,gap='small')
        with izquierda:
            if st.button('Guardar orden',type='primary',key='atrio_orden_guardar',disabled=borrador==guardado,use_container_width=True):
                centro.set_setting(CLAVE,list(borrador))
                st.rerun()
        with derecha:
            if st.button('Restaurar orden original',key='atrio_orden_restaurar',disabled=guardado==list(paginas) and borrador==list(paginas),use_container_width=True):
                centro.set_setting(CLAVE,list(paginas))
                st.session_state[BORRADOR]=list(paginas)
                st.rerun()
        if borrador!=guardado:
            st.caption('Tienes cambios sin guardar. Puedes seguir ordenando o pulsar Guardar orden.')
        else:
            st.caption('El orden que ves coincide con el guardado.')
    st.divider()
