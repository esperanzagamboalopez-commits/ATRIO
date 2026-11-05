# -*- coding: utf-8 -*-
"""Módulo para Adaptar PDFs Oficiales (Conserva formato)."""
import streamlit as st
import fitz  # PyMuPDF
import io
from datetime import datetime
from docx import Document

def adaptar_pdf(uploaded_file, reemplazos):
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    for page in doc:
        for viejo, nuevo in reemplazos.items():
            if not viejo or not nuevo: continue
            areas = page.search_for(viejo)
            for area in areas:
                page.add_redact_annot(area, fill=None)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        for viejo, nuevo in reemplazos.items():
            if not viejo or not nuevo: continue
            areas = page.search_for(viejo)
            for area in areas:
                fontsize = 10
                while fontsize > 5:
                    rc = page.insert_textbox(area, nuevo, fontsize=fontsize, fontname="helv", color=(0,0,0))
                    if rc >= 0: break
                    fontsize -= 0.5
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes

def generar_word_controlado(pdf_bytes, nombre_archivo):
    try:
        doc = Document()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = pdf_doc[0]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        pdf_doc.close()
        
        header = doc.sections[0].header
        run = header.paragraphs[0].add_run()
        run.add_picture(io.BytesIO(img_bytes), width=doc.sections[0].page_width)
        
        doc.add_paragraph("(Este es un documento de edición controlada. El diseño original está en el fondo y este texto es editable).")
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    except Exception:
        return None

def render_adaptar_pdf():
    st.markdown("""
    <div style="background: linear-gradient(109deg, #f5d8df 0%, #efafc9 45%, #ed78ab 100%); border-radius: 14px; padding: 24px 26px; color: #21191d; margin-bottom: 20px;">
        <div style="font-size:10px; font-weight:800; letter-spacing:1.5px; color:#87475f; margin-bottom:8px;">ADAPTACIÓN DOCUMENTAL</div>
        <h1 style="margin: 0; font-family: Georgia, serif; font-size: 32px;">Adaptar PDF Existente</h1>
        <p style="margin: 5px 0 0 0; font-family: Georgia, serif;">Sube un PEA oficial, actualiza sus datos y conserva su formato exacto.</p>
    </div>
    """, unsafe_allow_html=True)

    st.info("Sube el archivo PDF original. El sistema buscará los textos que le indiques, los borrará y escribirá los nuevos en la misma posición sin romper las tablas ni los logos.")

    uploaded_file = st.file_uploader("Selecciona el PDF oficial (ej. PEA histórico)", type=["pdf"])
    
    if uploaded_file is not None:
        st.success("PDF cargado correctamente.")
        
        st.markdown("### Datos Administrativos a Reemplazar")
        st.caption("Deja en blanco los campos que no deseas modificar.")
        
        c1, c2 = st.columns(2)
        with c1:
            viejo_cecati = st.text_input("CECATI anterior (ej. 114)", value="114")
            nuevo_cecati = st.text_input("Nuevo CECATI (ej. 31)", value="31")
            
            viejo_inicio = st.text_input("Fecha inicio anterior", value="09/01/2021")
            nuevo_inicio = st.text_input("Fecha inicio nueva", value="10/01/2026")
            
            viejo_docente = st.text_input("Nombre docente anterior", value="JULIO CESAR VAZQUEZ GARCIA")
            nuevo_docente = st.text_input("Nombre docente nuevo", value="NUEVO DOCENTE")
            
        with c2:
            viejo_fin = st.text_input("Fecha término anterior", value="13/03/2021")
            nuevo_fin = st.text_input("Fecha término nueva", value="14/03/2026")
            
            viejo_horario = st.text_input("Horario anterior", value="8:00 a 14:00 horas")
            nuevo_horario = st.text_input("Horario nuevo", value="17:00 a 22:00 horas")

        if st.button("✨ Adaptar PDF y Generar Word", type="primary", use_container_width=True):
            with st.spinner("Procesando documento..."):
                reemplazos = {
                    viejo_cecati: nuevo_cecati,
                    viejo_inicio: nuevo_inicio,
                    viejo_fin: nuevo_fin,
                    viejo_docente: nuevo_docente,
                    viejo_horario: nuevo_horario
                }
                reemplazos = {k: v for k, v in reemplazos.items() if k.strip() and v.strip()}
                
                try:
                    pdf_bytes = adaptar_pdf(uploaded_file, reemplazos)
                    st.success("✅ PDF adaptado con éxito.")
                    
                    col_pdf, col_word = st.columns(2)
                    with col_pdf:
                        st.download_button(
                            label="📄 Descargar PDF Adaptado",
                            data=pdf_bytes,
                            file_name=f"PEA_ADAPTADO_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    with col_word:
                        word_buffer = generar_word_controlado(pdf_bytes, uploaded_file.name)
                        if word_buffer:
                            st.download_button(
                                label="📝 Descargar Word de Edición",
                                data=word_buffer,
                                file_name=f"PEA_EDICION_{datetime.now().strftime('%Y%m%d')}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True
                            )
                        else:
                            st.caption("No se pudo generar el Word (revisa que python-docx esté instalado).")
                            
                except Exception as e:
                    st.error(f"Error al procesar el PDF: {e}")