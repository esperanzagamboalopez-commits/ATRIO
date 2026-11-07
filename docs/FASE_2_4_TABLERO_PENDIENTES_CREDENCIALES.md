# Fase 2.4 · Tablero ejecutivo, seguimiento de procesos y credenciales

**Rama:** \`pruebas/fase2-funcional-aislada\`  
**Estado:** implementación preparada para validación local; no integrada en \`main\`.

## 1. Objetivo funcional

Cerrar la separación de responsabilidades entre las tres vistas:

- **Inicio:** bienvenida con reloj digital, calendario de consulta, panorama de capacitación y hasta tres prioridades inmediatas explicadas con su siguiente acción y destino.
- **Pendientes:** centro de trabajo con filtros de periodo, proceso, responsable y situación. Reúne obligaciones derivadas de fuentes reales y compromisos personales del calendario.
- **Mi Calendario:** agenda de reuniones, entregas, compromisos y actividades del Área de Capacitación, además de fechas objetivo y referencias de inicio/término de cursos.

Inicio ya no renderiza la maqueta HTML heredada ni la franja informativa PEA/MCE. Tampoco muestra el panel técnico «ATRIO · Vista previa de integración» ni una lista separada de próximas fechas importantes.

## 2. Inicio

\`tablero_inicio.py\` es la fuente de la vista ejecutiva:

1. Bienvenida dinámica con reloj digital de hora local que se actualiza cada segundo.
2. Calendario compacto de consulta: marcas de actividades, fechas objetivo, avisos e inicios/términos de cursos; no crea ni edita actividades desde Inicio.
3. Panorama con tarjetas diferenciadas para cursos programados, terminados por fecha, en curso, por iniciar e inscripciones del corte SISAE.
4. Tarjetas de avance por tipo con barra y conteos separados de terminados, en curso y por iniciar; el avance se calcula por término de curso y no por cierre de acreditaciones o constancias.
5. Hasta tres prioridades, con motivo, siguiente acción y acceso al módulo.

Los datos de alumnos y registros proceden del corte SISAE cargado. Cuando no hay un corte legible, se muestra «—» y no se inventa un cero.

## 3. Motor común de pendientes

\`motor_pendientes.py\` contiene cálculos deterministas sin escrituras. Inicio y Pendientes llaman a la misma función de carga y clasificación, evitando reglas distintas en cada pantalla.

| Proceso | Regla aplicada |
|---|---|
| Elaboración de PEA de Extensión | Objetivo: cinco días naturales antes del inicio. |
| Preparación de PEA de Repositorio | Descargar y adaptar el PEA de repositorio; no redactar uno desde cero. |
| Subir PEA al MCE | Se activa cuando el PEA está generado/revisado. Si la carga no está confirmada, la tarea queda en «Por verificar». No se inventa una fecha límite de MCE. |
| Alta de cursos Regulares en MCE | Seguimiento separado del PEA. «Sin verificar» queda como verificación, no atraso. |
| Listas de asistencia | Una tarea por grupo y cada mes en el que el curso esté activo. Fecha objetivo: primer martes-viernes del mes, excluyendo fechas de \`DIAS_SIN_CLASE.json\`. |
| Acreditaciones | Se acerca al término del curso y distingue los estados de elaboración, entrega al docente, devolución y captura de resultados. «Sin verificar» no se marca atrasado. |
| Credenciales | Fecha objetivo máxima: siete días naturales después del inicio. Requiere vínculo inequívoco con SISAE para contar alumnos. |
| Cursos ACM | Aviso preventivo por diez días, cuando ACM/Acciones Móviles está identificado en los campos de programación; es aviso, no vencimiento. |
| Mi Calendario | Reuniones, entregas y actividades personales activas se agregan al seguimiento sin duplicarlas en el calendario. |

La jornada personal para las listas es martes a viernes. Esta regla de trabajo no modifica plazos institucionales ni fechas oficiales.

### Estados y orden

- Bloqueado, vencido, pendiente, aviso, en espera y por verificar se distinguen.
- «Sin verificar» no se convierte en atraso confirmado.
- Las tareas que esperan respuesta quedan separadas de las que corresponden a la responsable.
- El orden prioriza primero los plazos oficiales vencidos o próximos confirmados; después los bloqueos; finalmente la prioridad de gestión y los avisos. Los registros sin verificar nunca se elevan como atrasos.
- Se conservan los identificadores de Control Escolar que utiliza \`hojas.snapshot\`, por lo que los estados de listas y credenciales coinciden con la misma tarjeta del grupo.

## 4. Mi Calendario y fechas objetivo automáticas

`calendario.py` conserva las actividades personales editables en sus tablas actuales. En Inicio, el calendario es una vista de consulta; para crear, editar o completar actividades se utiliza el módulo Mi Calendario. Recibe además las tareas generadas por el motor:

- Las fechas objetivo confirmadas se muestran con marca **L**.
- Los avisos o verificaciones se muestran con marca **V**.
- Los inicios/términos de cursos continúan con **C/T**.
- Las tareas de módulos se muestran como referencias de solo lectura, con la razón y un acceso al módulo.
- Las actividades de Mi Calendario no se vuelven a insertar como tareas editables ni aparecen dos veces.

Las fechas oficiales no se modifican. Los metadatos de recordatorios/repeticiones del calendario siguen sin enviar notificaciones ni generar ocurrencias automáticas.

## 5. Credenciales: PowerPoint y Excel de firmas

Se reutiliza \`credenciales.py\` y la ruta existente de Control Escolar:

1. Se selecciona un grupo vinculado inequívocamente con SISAE y todo su padrón.
2. Se genera el PowerPoint usando la plantilla institucional existente.
3. Al marcar el grupo como elaborado, ATRIO genera una relación Excel imprimible con curso, docente, fechas, número de control, nombre completo y espacio de firma.
4. El Excel se guarda en \`datos/salidas/RELACIONES_CREDENCIALES\` y permanece descargable desde Control Escolar.
5. El seguimiento continúa abierto hasta confirmar que la relación física está firmada y resguardada; entonces se registra «Entrega documentada».

El Excel no contiene CURP. El sistema exige seleccionar a todos los alumnos vinculados para marcar el grupo completo como elaborado; así no se cierra el grupo con una relación parcial.

**Dependencia por verificar:** el PowerPoint existente necesita \`FORMATO_CREDENCIALES.pptx\`. El código busca primero junto a \`credenciales.py\` y después en \`datos/recursos\`. El archivo binario no aparece versionado en el árbol de esta rama; la generación real del PowerPoint no puede considerarse validada hasta comprobar que la plantilla esté disponible en el entorno.

## 6. Archivos afectados

- Nuevos: \`motor_pendientes.py\`, \`tablero_inicio.py\`.
- Vistas/integración: \`app.py\`, \`interfaz.py\`, \`pendientes.py\`, \`calendario.py\`, \`laboratorio_orbita_streamlit.py\`.
- Control escolar/credenciales: \`hojas.py\`, \`hoja4.html\`, \`credenciales.py\`.
- Pruebas: \`tests/test_motor_pendientes.py\`, \`tests/test_tablero_inicio.py\`, \`tests/test_credenciales_excel.py\`, \`tests/test_calendario_inicio.py\`, \`tests/test_laboratorio_orbita_aislado.py\`.

No se cambió \`requirements.txt\`: ya declara Streamlit 1.66.1 y openpyxl 3.1.5.

## 7. Laboratorio y validación

\`laboratorio_orbita_streamlit.py\` ahora renderiza el tablero ejecutivo nuevo con cursos, cifras y tareas ficticias inyectadas. El calendario escribe únicamente en un SQLite temporal por sesión. El laboratorio no importa \`app.py\` ni \`centro.py\`, y no lee SISAE, Excel o expedientes reales.

Las pruebas añadidas cubren:
- Fechas y filtros martes-viernes, cinco días de PEA, siete días de credenciales, listas, acreditaciones, ACM, estados sin verificar y prioridades.
- Conteos de Inicio y correspondencia de IDs de Control Escolar.
- Calendario con fechas objetivo automáticas y separación de actividad personal.
- Excel imprimible, campos, firma, orientación, ajuste de página y ausencia de CURP.
- Aislamiento del laboratorio y conexión de Inicio/Pendientes al mismo motor.

**No se declara todavía que las pruebas hayan pasado ni que la interfaz se haya visto en navegador.** Deben ejecutarse en Codespaces después de actualizar la rama:

\`\`\`bash
cd /workspaces/ATRIO || exit 1
git pull --ff-only origin pruebas/fase2-funcional-aislada
python -m py_compile tablero_inicio.py motor_pendientes.py pendientes.py calendario.py credenciales.py hojas.py interfaz.py app.py laboratorio_orbita_streamlit.py tests/test_motor_pendientes.py tests/test_tablero_inicio.py tests/test_credenciales_excel.py tests/test_calendario_inicio.py tests/test_laboratorio_orbita_aislado.py
python -m pytest -q
\`\`\`

Vista previa:

\`\`\`bash
python -m streamlit run laboratorio_orbita_streamlit.py --server.address 0.0.0.0 --server.port 8502
\`\`\`

## 8. Reversión y límites

- Todos estos cambios permanecen en \`pruebas/fase2-funcional-aislada\`; \`main\` no se modifica.
- No se modificaron la programación Excel oficial, SISAE, la plantilla PEA ni la SQLite operativa por efecto de esta edición del código.
- Para revertir un ajuste individual, se restaura el archivo correspondiente desde su versión inmediatamente anterior en el historial Git de esta rama y se vuelve a ejecutar la suite.
- Para descartar toda la Fase 2 en un entorno local, se puede abandonar la rama de pruebas y volver a \`main\`; no se deben copiar estos archivos a \`main\` hasta concluir las pruebas y recibir autorización de integración.
- La conexión a datos reales de la aplicación seguirá protegida por el control de acceso existente. La validación visual debe hacerse primero en el laboratorio aislado.
