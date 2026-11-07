# Fase 2 · Especificación del laboratorio visual de ATRIO

## 1. Propósito

Preparar una vista de laboratorio independiente para revisar la identidad visual de ATRIO sin abrir la aplicación operativa, conectar recursos institucionales ni modificar la base SQLite.

La primera entrega será una galería estática/interactiva de temas con datos demostrativos. No importará `centro.py`, `app.py`, Excel, SISAE, expedientes, documentos PEA, claves ni archivos dentro de `datos/`.

## 2. Inventario del estado actual

Revisión del código en la rama de laboratorio:

- `tema.py` contiene Editorial Rosa, Editorial Premium, Japandi Minimalista, Cyber-Neon y Glass Executive.
- `tema.OPCIONES` expone solo Editorial Rosa, Editorial Premium y Japandi Minimalista.
- No están definidos los presets Editorial Oro ni Editorial Terracota.
- Glass Executive usa fondos oscuros y superficies como `#18181B`; el CSS de `interfaz.py` aplica varias superficies opacas y no incorpora desenfoque consistente en las tarjetas principales. Por eso todavía no representa el vidrio translúcido solicitado.
- `interfaz.py` centraliza buena parte del CSS de Streamlit; `inicio.html` define de forma independiente la composición y estilos de Inicio mediante variables CSS.
- El Inicio actual tiene saludo dinámico, calendario rosa, métricas y tarjetas de seguimiento. No tiene aún el degradado rosa de dos intensidades ni la franja negra con el título institucional solicitado.

Este inventario describe el código, no una evaluación visual en un navegador real. La galería permitirá revisar las propuestas visuales antes de intervenir la aplicación.

## 3. Dirección visual acordada

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

## 4. Muestra funcional que deberá incluir la galería

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

## 5. Reglas para el rediseño posterior

- Primero se comparan y aprueban los cuatro temas en la galería; después se implementan en la capa central de temas.
- `tema.py` debe ser la fuente única de tokens de color, superficies, bordes, sombras, tipografía y estados.
- `interfaz.py` debe aplicar esos tokens a Streamlit de forma consistente.
- `inicio.html` debe consumir los mismos tokens, sin mantener una paleta paralela difícil de controlar.
- Los nombres de módulos, rutas, claves de sesión, widgets, acciones y lógica académica no se cambian como parte del trabajo visual.
- La plantilla institucional del PEA permanece congelada: no se modifica su estructura, diseño, tipografía, tablas, controles ni distribución.
- No se modifican Inicio ni otros módulos operativos hasta aprobar primero la galería.
- Después de cada cambio visual se ejecutan las pruebas funcionales para detectar regresiones.

## 6. Archivos previstos

### Primera entrega: laboratorio independiente
- Nuevo `laboratorio_temas.py` o una página HTML autónoma servida en modo local.
- Este archivo no importará módulos de operación, ni leerá recursos o bases de datos.

### Entrega posterior, solo después de la aprobación visual
- `tema.py`: tokens y presets.
- `interfaz.py`: aplicación consistente de variables y componentes.
- `inicio.html`: composición de Inicio y consumo de variables compartidas.
- Pruebas visuales o verificaciones automatizadas de tokens, contraste básico y no regresión funcional.

## 7. Criterios de aceptación

- Los cuatro temas principales se distinguen claramente y conservan legibilidad.
- Glass Executive se percibe translúcido y con desenfoque real.
- Editorial Rosa incluye rosa polvo y degradados con profundidad, sin neón dominante.
- Editorial Oro utiliza negro, blanco cálido y champagne con moderación.
- Editorial Terracota mantiene calidez y contraste.
- Calendario, navegación, botones, tarjetas y tablas conservan jerarquía y coherencia.
- La galería puede ejecutarse sin conectar archivos institucionales.
- No se modifica `main`, la base SQLite, Excel, SISAE ni la plantilla PEA.
