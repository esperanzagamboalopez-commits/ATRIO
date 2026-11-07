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
