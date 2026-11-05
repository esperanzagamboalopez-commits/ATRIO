# ATRIO · CECATI 31

Aplicación Streamlit con SQLite para la operación del centro: programación, padrón docente,
SISAE, cortes y generación de PEA.

## Estructura de datos

- `datos/` — datos reales del centro. **No se sube al repositorio** (está en `.gitignore`).
  Contiene la base `atrio.sqlite3`, la carpeta `recursos/` con los archivos oficiales,
  y `salidas/` y `versiones/` generadas por la app.
- `datos_ejemplo/` — set de **datos ficticios** para probar la app sin archivos reales.
  Sí se sube al repositorio.

## Archivos que la app necesita en `datos/recursos/`

| Archivo | Para qué sirve |
|---|---|
| `PROGRAMACION DE CURSOS.xlsx` | Programación por docente (una hoja por docente, encabezado de especialidad, cursos desde la fila 15) |
| `Plantilla_Datos_Docentes_PEA_CECATI31.xlsx` | Padrón docente (hoja `DOCENTES`, columnas A–I, J opcional `ESPECIALIDAD DOCENTE`) |
| `SISAE.zip` | Exportación SISAE con `PROG_CURSOS1.DBF`, `INSCRIPCION.DBF` y `ESP.DBF` |
| `DIAS_SIN_CLASE.json` | Lista de fechas `AAAA-MM-DD` sin clase |
| `PEA_final en blanco.docx` | Plantilla institucional del PEA (se valida su estructura al cargarla) |

Si falta alguno, la app muestra un mensaje como
*"Falta el archivo X. Por favor, súbelo en Ajustes"*. Súbelos desde **Ajustes · Recursos**.

## Usar datos reales

1. Copia tus archivos oficiales a `datos/recursos/` con los nombres de la tabla.
   También puedes subirlos desde **Ajustes · Recursos**; la app guarda una copia de la versión anterior en `datos/versiones/`.
2. Inicia la app:
   ```bash
   python3 -m streamlit run app.py
   ```

## Volver al set de ejemplo

Úsalo para probar cambios sin tocar los datos del centro.

1. Haz respaldo de `datos/` antes de cualquier prueba:
   ```bash
   cp -r datos datos_respaldo_$(date +%Y%m%d_%H%M%S)
   ```
2. Copia los archivos de ejemplo sobre `datos/recursos/`:
   ```bash
   cp datos_ejemplo/* datos/recursos/
   ```
3. Para regresar a tus datos reales, restaura desde tu respaldo o vuelve a subir los archivos oficiales.

Nota: `datos_ejemplo/` no incluye `PEA_final en blanco.docx`. La plantilla institucional
debe venir del centro, porque la app valida su estructura exacta (28 tablas) antes de generar un PEA.

## Pruebas

`tests/test_operacion.py` usa `PEA_final en blanco.docx` de `datos/recursos/`, así que
necesita la plantilla institucional real. Con el set de ejemplo no corre completa.

## Reglas para el repositorio

- No subir nada de `datos/`, ni bases SQLite, ni Excel, ZIP o Word reales.
- Sí subir únicamente lo que esté en `datos_ejemplo/`, y solo con datos ficticios.

## Acceso con contraseña

La app pide contraseña antes de mostrar cualquier página. Configúrala en una de estas dos formas:

- `.streamlit/secrets.toml` (no se sube al repositorio):
  ```toml
  ATRIO_PASSWORD = "tu-contraseña"
  ```
- Variable de entorno: `ATRIO_PASSWORD=tu-contraseña`

Si no hay contraseña configurada, la app muestra un error y se detiene. Nunca se usa una contraseña por defecto.

## Variables de entorno

| Variable | Para qué | Valor por defecto |
|---|---|---|
| `ATRIO_PASSWORD` | Contraseña de acceso | — (obligatoria) |
| `ATRIO_DB_PATH` | Base de datos de Mi Calendario | `datos/atrio.sqlite3` |
| `ATRIO_AUDITORIA_SISAE_DIR` | Carpeta de auditoría SISAE | `datos/DATOS_AUDITORIA_SISAE` |

## Adaptar PDF

Solo acepta PEA oficiales de **17 páginas**. Sube el PDF, revisa la vista previa y luego:

- **Descargar PDF adaptado**: descarga el archivo.
- **Guardar en Históricos**: guarda el PDF en PEA históricos con estado `BORRADOR_REVISION_VISUAL`. No lo autoriza ni lo sube a MCE.

## Dependencias

Instala con `pip install -r requirements.txt`. `pymupdf` es necesario para Adaptar PDF.
