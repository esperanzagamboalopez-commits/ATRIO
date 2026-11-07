# Fase 1 · Identidad y conservación de grupos

## Alcance de esta entrega aislada

Esta rama incorpora una primera capa de conciliación para que la actualización de programación no confunda cambios operativos con cambios de identidad académica.

### Reglas implementadas

- La identidad académica se reconoce por nombre normalizado, tipo de curso y especialidad.
- El docente, fechas, horario, duración, aula y población se tratan como atributos modificables.
- Si cambia el docente y la coincidencia de curso es única, se conserva el identificador del grupo y sus vínculos con estado, documentos y trabajos PEA.
- Si cambia el nombre, se crea un grupo con identidad nueva y se marca que requiere PEA nuevo. El grupo anterior permanece almacenado como antecedente y se registra el vínculo entre ambos.
- Si hay más de un grupo candidato, no se elige arbitrariamente: se crea una entrada pendiente de revisión de identidad.
- Los grupos no incluidos en una actualización no se eliminan ni se desactivan automáticamente. Permanecen en ATRIO con estado «Pendiente de reprogramación».
- La duración diferente se marca para revisar el reajuste de horas del PEA.
- Los cambios se registran en eventos para conservar trazabilidad.

### Caso de cascada parcial

Si diez cursos están en una secuencia y la reprogramación solo alcanza ocho, los otros dos quedan conservados como pendientes de reprogramación. Mantienen sus fechas y atributos anteriores hasta que se programe un cambio posterior.

### Archivos modificados

- `centro.py`: sustituye la conciliación basada únicamente en huella/fila por la nueva estrategia y conserva grupos no incluidos.
- `identidad_programacion.py`: nuevo motor puro de comparación de identidad.
- `tests/test_identidad_programacion.py`: seis pruebas unitarias sin dependencia de datos reales.

### No incluido todavía

- Interfaz para resolver coincidencias ambiguas.
- Presentación de los estados nuevos en Programación, Inicio y Pendientes.
- Integración visual de la acción de reajuste de horas dentro de Preparar PEA/Repositorio.
- Actualización del módulo local de Reprogramación: el archivo de la rama principal consultada es una versión de simulación que no coincide con el código local que la usuaria confirmó que guarda Excel y SQLite. No se debe sustituir hasta conciliar ambas versiones.
- Cambios de temas, colores, iconos, menú o navegación.

### Pruebas

Las seis pruebas unitarias cubren cambio de docente, cambio de nombre, horas distintas, curso nuevo, candidatos ambiguos y una cascada de ocho cursos de diez. Deben ejecutarse en el entorno de pruebas del repositorio antes de integrar.

### Reversión

Esta entrega está en la rama `implementacion/identidad-grupos-pea-fase1`. Para revertirla, basta con no integrar esa rama; `main` permanece intacta.


## Compatibilidad de antecedentes en consultas

La consulta de documentos generados ahora recupera también la ficha del grupo inactivo que los originó. Esto permite identificar curso y docente anteriores en la biblioteca y en los detalles del asistente, sin reactivar el grupo ni transferir sus documentos al grupo nuevo.

Prueba añadida: `tests/test_antecedentes_consulta.py`, con base SQLite temporal y datos ficticios. Comprueba la identificación del antecedente en ambas consultas.


## PEA anterior después de una reprogramación

Cuando el grupo conserva su identidad, pero cambian atributos de programación, los artefactos cuya huella no coincide con la vigente se presentan como versiones anteriores. Preparar PEA ofrece acceso directo a Revisor para comparar y reajustar el Word, conservando el original. Las versiones anteriores no se muestran como PEA vigente ni se reutilizan automáticamente.

Prueba adicional: el selector de biblioteca marca la huella anterior y Preparar PEA recupera esos artefactos por group_id para enviarlos a revisión.


## Separación entre grupos operativos y pendientes conservados

La conciliación distingue la conservación del registro de su participación en la actualización actual:

- **Vigente/incluido:** participa en alertas, Inicio, Centro de Pendientes y selección para preparar PEA.
- **Pendiente de reprogramación:** permanece activo y consultable; puede volver a seleccionarse en Reprogramación, pero queda fuera de alertas y tareas de la jornada actual.
- **Identidad pendiente de revisión:** permanece conservada y consultable, pero queda fuera de los grupos operativos y no puede generar PEA hasta resolver manualmente la coincidencia.
- **Sustituido por cambio de nombre:** permanece como antecedente histórico y no participa en los procesos operativos.

En `identidad_programacion.py`, `grupo_incluido_en_actualizacion()` aplica esta regla y `grupos_operativos()` filtra sin mutar ni borrar la colección original. En `centro.py`, `groups()` conserva su comportamiento de devolver todos los grupos activos, para que Programación, Reprogramación y las consultas no pierdan acceso a los pendientes. `operational_groups()` ofrece la vista filtrada.

En `app.py`, Inicio, alertas, búsqueda que abre Preparar PEA, Centro de Pendientes y selección para generar PEA reciben solo grupos operativos. Programación, Reprogramación y las consultas generales conservan el conjunto completo. Los registros antiguos sin metadatos se consideran incluidos para mantener compatibilidad.

Pruebas específicas: `tests/test_grupos_operativos.py` cubre pendientes, vigentes, sustituidos, compatibilidad histórica y no mutación de los registros originales.


## Protección de generación frente a cambios de programación

Los trabajos de PEA en cola conservan una instantánea de los datos seleccionados, pero esa instantánea no se considera autorización para generar indefinidamente. Antes de encolar y al iniciar la generación, ATRIO comprueba que el grupo siga activo, incluido en la actualización actual y con la misma huella de programación. Al finalizar el documento, vuelve a validar dentro de una transacción SQLite `BEGIN IMMEDIATE` antes de registrar el artefacto y actualizar el estado. Si la programación cambió durante la generación, el documento provisional se descarta y no se registra como PEA vigente.

Cambios en `centro.py` y `trabajos.py`; pruebas en `tests/test_generacion_vigente.py`. Esta protección no sustituye la conciliación pendiente del módulo real de Reprogramación, que debe hacerse por separado antes de ejecutar una prueba integrada.

## Reprogramación operativa con persistencia

El módulo \`reprogramacion.py\` dejó de ser un simulador manual. La pantalla calcula la cascada por docente y carril horario, excluyendo grupos pendientes de reprogramación que no participan en la actualización actual. Los grupos excluidos se conservan en la base y no se modifican.

Al aplicar una simulación:

- Se valida que cada \`group_id\`, huella y fila del Excel sigan correspondiendo a los datos usados en la simulación.
- Se crea un respaldo \`datos/versiones/PROGRAMACION_BACKUP_*.xlsx\`.
- Se actualiza el Excel vigente con el esquema que lee \`centro.parse_program\`: B nombre, E inicio, F término y G duración.
- Se actualiza el payload y la huella del mismo grupo en SQLite; no se crea una identidad nueva.
- Se registran eventos de reprogramación. No se alteran estados MCE, artefactos PEA ni documentos históricos.
- Si falla la actualización de SQLite después de sustituir el Excel, se restaura el respaldo.

Pruebas aisladas: \`python -B -m unittest discover -s tests -p "test_reprogramacion_operativa.py" -v\`.
