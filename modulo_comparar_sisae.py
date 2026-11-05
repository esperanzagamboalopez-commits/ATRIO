# -*- coding: utf-8 -*-
"""Auditoría Definitiva: Diferencias por Grupo (Curso) y Alumnos Faltantes."""
import streamlit as st
import centro as C
import pandas as pd

def extraer_alumnos_por_grupo(zip_bytes):
    """Agrupa a los alumnos por su CLAVE_CURSO (Grupo)."""
    try:
        tables = C.sisae_bytes(zip_bytes)
        insc = tables.get('INSCRIPCION.DBF', [])
        prog = tables.get('PROG_CURSOS1.DBF', [])
        
        cursos_dict = {p['CLAVE_CURS']: p['NOM_CURSO'].strip() for p in prog}
        datos = {}
        
        for r in insc:
            # Ya no filtramos por periodo, solo por grupo (curso)
            clave_curso = r.get('CLV_CURSO', '').strip()
            id_alumno = r.get('ID_ALUMNO', '').strip()
            
            if not clave_curso or not id_alumno: continue
            
            if clave_curso not in datos:
                datos[clave_curso] = {}
                
            nombre = f"{r.get('A_PATERNO', '').strip()} {r.get('A_MATERNO', '').strip()} {r.get('NOMBRE', '').strip()}"
            datos[clave_curso][id_alumno] = nombre
            
        return datos, cursos_dict
    except Exception:
        return None, None

def render_comparar_sisae():
    st.markdown("""
    <div style="background: linear-gradient(109deg, #f5d8df 0%, #efafc9 45%, #ed78ab 100%); border-radius: 14px; padding: 24px 26px; color: #21191d; margin-bottom: 20px;">
        <div style="font-size:10px; font-weight:800; letter-spacing:1.5px; color:#87475f; margin-bottom:8px;">AUDITORÍA POR GRUPO</div>
        <h1 style="margin: 0; font-family: Georgia, serif; font-size: 32px;">Alumnos Faltantes por Curso</h1>
        <p style="margin: 5px 0 0 0; font-family: Georgia, serif;">Identifica exactamente qué grupo perdió alumnos y quiénes fueron.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        archivo_viejo = st.file_uploader("1. Sube el ZIP Antiguo (El que enviaste)", type=["zip"], key="zip_viejo")
    with col2:
        archivo_nuevo = st.file_uploader("2. Sube el ZIP Nuevo (El actual)", type=["zip"], key="zip_nuevo")

    if archivo_viejo and archivo_nuevo:
        datos_viejos, nombres_cursos = extraer_alumnos_por_grupo(archivo_viejo.getvalue())
        datos_nuevos, _ = extraer_alumnos_por_grupo(archivo_nuevo.getvalue())

        if not datos_viejos or not datos_nuevos:
            st.error("No se pudieron leer los archivos.")
            return

        if st.button("🔍 Comparar Alumnos por Grupo", type="primary", use_container_width=True):
            
            total_faltantes_global = 0
            
            st.markdown("### 📋 Grupos con Alumnos Faltantes")
            st.caption("Aquí solo se muestran los grupos que tenían más alumnos antes y ahora tienen menos. ¡Busca al tuyo aquí!")
            
            # Iterar sobre todos los cursos que existían en el archivo viejo
            for curso_key in sorted(datos_viejos.keys()):
                alu_viejo = datos_viejos.get(curso_key, {})
                alu_nuevo = datos_nuevos.get(curso_key, {})
                
                set_v = set(alu_viejo.keys())
                set_n = set(alu_nuevo.keys())
                
                faltantes = set_v - set_n
                
                if faltantes:
                    total_faltantes_global += len(faltantes)
                    nombre_curso = nombres_cursos.get(curso_key, curso_key)
                    
                    # Creamos un acordeón para cada grupo afectado
                    with st.expander(f"⚠️ **{nombre_curso}** (Clave: {curso_key}) - Faltan {len(faltantes)} alumnos", expanded=False):
                        st.write(f"Este grupo tenía **{len(set_v)}** alumnos en el archivo original y ahora tiene **{len(set_n)}**.")
                        st.write("Estos son los alumnos que ya no aparecen en este grupo:")
                        
                        lista_faltantes = []
                        for f in faltantes:
                            lista_faltantes.append({
                                "ID del Alumno": f,
                                "Nombre Completo": alu_viejo[f]
                            })
                        st.dataframe(pd.DataFrame(lista_faltantes), use_container_width=True, hide_index=True)
            
            if total_faltantes_global == 0:
                st.success("✅ ¡Todo perfecto! Ningún grupo perdió alumnos.")
            else:
                st.info(f"💡 Se encontraron un total de {total_faltantes_global} alumnos faltantes distribuidos en los grupos de arriba.")