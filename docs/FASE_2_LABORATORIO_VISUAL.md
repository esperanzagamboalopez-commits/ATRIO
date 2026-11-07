# Fase 2 · Especificación del laboratorio visual de ATRIO

## 1. Propósito

Preparar una vista de laboratorio independiente para revisar la identidad visual de ATRIO sin abrir la aplicación operativa, conectar recursos institucionales ni modificar la base SQLite.

La primera entrega será una galería estática/interactiva de temas con datos demostrativos. No importará `centro.py`, `app.py`, Excel, SISAE, expedientes, documentos PEA, claves ni archivos dentro de `datos/`.

## 2. Inventario del estado actual

Revisión del código de `tema.py` en la rama de laboratorio:

- Presets existentes: Editorial Rosa, Editorial Premium, Japandi Minimalista, Cyber-Neon y Glass Executive.
- Antes de integrar Órbita, `tema.OPCIONES` exponía Editorial Rosa, Editorial Premium y Japandi Minimalista; los temas oscuros estaban definidos pero no aparecían en ese selector. En Fase 2.2 se incorpora ATRIO Órbita sin sustituir los temas anteriores.
- Editorial Oro y Editorial Terracota no existen todavía como presets de la aplicación: son propuestas nuevas del laboratorio.
- Glass Executive existente usa fondos oscuros y superficies como `#18181B`; no equivale al rediseño de vidrio translúcido.
- `interfaz.py` centraliza buena parte del CSS de Streamlit; `inicio.html` define de forma independiente la composición y estilos de Inicio mediante variables CSS.
- El Inicio actual tiene saludo dinámico, calendario rosa, métricas y tarjetas de seguimiento. No tiene aún el degradado rosa de dos intensidades ni la franja negra con el título institucional solicitado.

La galería ampliada permite comparar nueve variantes con una misma maqueta y datos ficticios:
1. Editorial Rosa · Renovado (propuesta).
2. Editorial Rosa · Anterior (paleta del preset actual).
3. Editorial Premium (preset actual).
4. Japandi Minimalista (preset actual).
5. Cyber-Neon (preset actual).
6. Glass Executive · Anterior (paleta oscura actual).
7. Glass Executive · Renovado (propuesta de vidrio translúcido).
8. Editorial Oro · Nuevo (propuesta).
9. Editorial Terracota · Nuevo (propuesta).

Las variantes “Anterior” reproducen los tokens principales de `tema.py` para facilitar la comparación; la maqueta no es una captura exacta de la interfaz Streamlit. Este inventario no afirma que la vista se haya probado visualmente en un navegador de la aplicación.

## 3. Nueva propuesta exclusiva: ATRIO Órbita

Se incorpora una dirección visual original concebida para el trabajo académico y administrativo de ATRIO, no como una variación de los temas rosados:

- Azul petróleo profundo y tinta azul para estructura, navegación y jerarquía.
- Verde mineral/teal como acento de acción y orientación.
- Lima mineral como señal secundaria de energía, avance y puntos importantes.
- Marfil mineral y papel cálido para lectura y descanso visual.
- Calendario en arena clara, separado del fondo general.
- Degradados controlados inspirados en capas cartográficas y trayectorias, sin repetir la estética editorial rosa/oro/terracota.

La propuesta busca transmitir precisión, continuidad, claridad y capacidad de gestión. La usuaria aprobó ATRIO Órbita como identidad visual para la integración controlada en la aplicación; esta aprobación no modifica la identidad institucional oficial del plantel.

## 4. Dirección visual acordada

Los cuatro temas principales que deben presentarse en la galería son:

### Editorial Rosa
- Rosa polvo con profundidad y contraste; evitar rosa fosforescente como acento dominante y tonos deslavados.
- Fondo marfil/hueso, superficies claras y acentos rosa elegantes.
- Negro carbón para títulos y contraste; oro champagne como detalle secundario.
- Degradados rosados sutiles, con mayor intensidad en los bordes o zonas de énfasis.
- Sensación editorial, femenina, segura y profesional.

### Editorial Oro
- Negro o carbón profundo, blanco cálido y oro champagne.
- Contraste alto, jerarquía tipográfica clara y acentos dorados controlados.
- Evitar fondos dorados extensos, brillos excesivos o texto dorado pequeño sobre blanco.

### Editorial Terracota
- Terracota cálida, arcilla, arena y marfil, con tinta oscura.
- Acentos profundos y legibles; no usar pasteles desaturados como texto o controles principales.
- Mantener una presentación editorial coherente con Rosa y Oro, pero con identidad propia.

### Glass Executive
- Vidrio realmente translúcido: paneles con transparencia, desenfoque de fondo, bordes sutiles y capas de profundidad.
- El fondo debe poder percibirse a través de los paneles; no basta con usar un tema oscuro y tarjetas sólidas.
- Mantener texto y controles con contraste alto.
- Evitar que transparencias reduzcan la legibilidad o conviertan la interfaz en una colección de rectángulos oscuros opacos.

Japandi Minimalista y Cyber-Neon pueden conservarse como temas secundarios para evaluación posterior; no sustituyen los cuatro temas principales solicitados.

## 5. Muestra funcional que deberá incluir la galería

Todas las vistas deben presentar la misma composición y los mismos datos ficticios para que la comparación sea justa:

- Marca ATRIO y navegación lateral de muestra.
- Encabezado de bienvenida.
- Franja oscura con el título `PEA y trámites en MCE`, texto blanco y acento oro.
- Calendario dentro de un panel rosa polvo (la variación de color debe adaptarse al tema, sin convertir el calendario en negro).
- Métricas compactas y un ejemplo de tabla/listado.
- Botones primario y secundario, pestañas, campos y estados de aviso.
- Iconos coherentes con cada tema y consistentes en estilo, grosor y tamaño.
- Adaptación para escritorio y pantalla estrecha.

La galería será demostrativa. Sus botones, campos y navegación no ejecutarán operaciones de ATRIO ni guardarán información.

## 6. Reglas de integración visual

- ATRIO Órbita ya fue aprobado en la galería; su integración se realiza primero en la rama aislada `pruebas/fase2-funcional-aislada` y no se fusiona automáticamente a `main`.
- `tema.py` debe ser la fuente única de tokens de color, superficies, bordes, sombras, tipografía y estados.
- `interfaz.py` debe aplicar esos tokens a Streamlit de forma consistente.
- `inicio.html` debe consumir los mismos tokens, sin mantener una paleta paralela difícil de controlar.
- Los nombres de módulos, rutas, claves de sesión, widgets, acciones y lógica académica no se cambian como parte del trabajo visual.
- La plantilla institucional del PEA permanece congelada: no se modifica su estructura, diseño, tipografía, tablas, controles ni distribución.
- Las modificaciones visuales de `Inicio` y `Ajustes` se limitan a consumir los tokens de tema; no se alteran flujos académicos ni operativos.
- Después de cada cambio visual se ejecutan las pruebas funcionales para detectar regresiones.

## 7. Personalización de paleta integrada

En la galería original, `Personalizar · Mi paleta` fue una prueba temporal. En la integración de Fase 2.2 se incorporan cuatro controles persistentes en `Ajustes`: fondo general, color principal, color secundario y calendario. Los cambios se previsualizan en vivo cuando ATRIO Órbita está activo. El botón `Guardar paleta y aplicar ATRIO Órbita` almacena los valores en la configuración existente (`settings`, clave `tema_paleta_personalizada`) mediante `C.set_setting`; no crea otra base de datos ni archivos. El botón de restablecimiento recupera la paleta base.

Los valores se validan como hexadecimal de seis dígitos. La tipografía, las superficies de lectura, la tinta y los estados semánticos permanecen controlados. La previsualización independiente descrita en la sección 8 no persiste cambios.

## 8. Archivos de integración y vista previa aislada

### Integración de tema
- `tema.py`: preset ATRIO Órbita, tokens de gradiente/calendario/franja principal y validación de paleta.
- `interfaz.py`: aplicación de variables compartidas a la interfaz Streamlit.
- `inicio.html`: consumo de tokens para el saludo, calendario y franja `PEA y trámites en MCE`.
- `app.py`: selector de tema y personalización persistente en Ajustes.
- `tests/test_tema_orbita.py`: pruebas de tokens, validación y separación entre temas.

### Vista previa independiente
- Inicio conserva la franja oscura `PEA y trámites en MCE` como título de identidad, sin el bloque `Lo que requiere tu atención`, texto de aviso demostrativo ni botón `Ver cursos para revisar`.
- El resumen informativo no se presenta como acción pendiente ni duplica el seguimiento que corresponde a sus módulos.
- `laboratorio_orbita_streamlit.py`: muestra el tema y la composición real de `inicio.html` con tres cursos ficticios.
- No importa `app.py` ni `centro.py`; no abre SQLite, Excel, SISAE, expedientes o documentos.
- Sus selectores de color son temporales y no guardan valores en la configuración del plantel.
- `tests/test_laboratorio_orbita_aislado.py`: verifica que la vista previa no incorpore conexiones con recursos operativos.

Para abrir solamente la vista previa, nunca `app.py`, se usa:

```bash
streamlit run laboratorio_orbita_streamlit.py --server.address 0.0.0.0 --server.port 8502
```

Se abrirá el puerto 8502 de Codespaces. Esta ejecución no equivale a iniciar ATRIO operativo ni autoriza conectar sus recursos institucionales.

## 9. Criterios de aceptación de identidad y separación

- Los temas principales y ATRIO Órbita se distinguen claramente y conservan legibilidad.
- Glass Executive se percibe translúcido y con desenfoque real.
- Editorial Rosa incluye rosa polvo y degradados con profundidad, sin neón dominante.
- Editorial Oro utiliza negro, blanco cálido y champagne con moderación.
- Editorial Terracota mantiene calidez y contraste.
- Calendario, navegación, botones, tarjetas y tablas conservan jerarquía y coherencia.
- La galería puede ejecutarse sin conectar archivos institucionales.
- No se modifica `main`, la base SQLite, Excel, SISAE ni la plantilla PEA.


## 10. Estado de la integración visual · 6 de noviembre de 2026

La identidad ATRIO Órbita está aprobada por la usuaria y su integración está preparada en la rama `pruebas/fase2-funcional-aislada`.

- Se incorpora como opción de tema; Editorial Rosa continúa como valor predeterminado y los temas anteriores no se eliminan.
- El Inicio consume los mismos tokens compartidos para el degradado de bienvenida, calendario en arena clara y franja oscura `PEA y trámites en MCE`. La franja es ahora un elemento de identidad sin panel informativo, aviso o botón simulado.
- Ajustes permite personalizar los cuatro colores aprobados y guardar la paleta en la configuración ya existente.
- La personalización no cambia tipografía, superficies de lectura, color de texto ni estados semánticos.
- No se han modificado `main`, Excel institucional, SISAE, documentos PEA, plantillas ni la base de datos del entorno operativo.
- La validación de ejecución y no regresión queda pendiente de realizar en Codespaces sobre esta rama; no se declara todavía una prueba visual de la aplicación Streamlit.

La reversión de esta integración en la rama de laboratorio consiste en revertir los commits de Fase 2.2 que afectan `tema.py`, `interfaz.py`, `inicio.html`, `app.py`, esta documentación y `tests/test_tema_orbita.py`. No se requiere tocar `main` ni eliminar datos.
