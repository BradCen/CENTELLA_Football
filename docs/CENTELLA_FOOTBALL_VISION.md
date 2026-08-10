# CENTELLA Football — visión maestra recuperada

Este documento congela la visión de producto recuperada de las conversaciones de diseño de CENTELLA para evitar que el proyecto vuelva a reducirse a un menú de cuatro botones o a un simple reskin de Google Research Football.

## 1. Principio del producto

CENTELLA Football busca ser un simulador premium de fútbol que combine:

- control directo y balón con comportamiento independiente;
- profundidad táctica y administrativa;
- presentación moderna de televisión;
- rendimiento primero, con escalado interno preparado para CENTELLA SR;
- contenido editable y una comunidad de mods organizada;
- cero pay-to-win;
- una identidad propia de CENTELLA, no una copia visual o de assets de FIFA/PES.

FIFA, PES/eFootball y otros títulos se usan únicamente como **referencias observables de diseño y sensación**. El producto comercial no debe importar código, logos, fotografías, rostros, estadios, uniformes ni otros assets propietarios sin una licencia compatible.

## 2. ADN de gameplay

Objetivos de sensación:

1. El input humano tiene prioridad. Un botón no debe sentirse atrapado detrás de la cadencia de investigación del entorno.
2. La pelota se trata como objeto físico y no como accesorio pegado al jugador.
3. Pase y tiro deben depender de orientación, presión, impulso y habilidad; las asistencias corrigen poco y son configurables.
4. Defender exige posicionamiento, lectura y timing. La IA ayuda a conservar la estructura, no juega por el usuario.
5. Las transiciones entre animaciones deben ocultar la maquinaria: correr, frenar, girar, controlar, chutar, caer y levantarse no pueden sentirse como clips aislados.
6. La IA colectiva debe comprender espacio, coberturas, líneas, desmarques y contexto táctico; el entrenamiento por refuerzo es una capa posterior, no un sustituto de reglas básicas robustas.
7. El fútbol debe admitir personalidad y caos contextual: protestas, empujones, frustración, lujos, celebraciones y otros eventos se activan por estado, no aleatoriamente sin significado.

## 3. Presentación y UI/UX

La primera impresión debe sentirse como un videojuego premium actual:

- secuencia de arranque breve y cinematográfica;
- pantalla `press any button`;
- escenario de estadio como fondo vivo;
- navegación principal por pestañas;
- carrusel horizontal de modos con una selección dominante;
- transiciones cortas y decididas;
- mando como dispositivo de primera clase desde el primer frame;
- ayudas de botones que cambian según teclado / Xbox-like / PlayStation-like;
- interfaz totalmente escalable y con letterboxing correcto en relaciones de aspecto distintas;
- Jet Black, Obsidian, Pure White y Sapphire Blue como sistema maestro;
- Urbanist o equivalente del sistema para navegación, datos y cuerpo;
- ninguna dependencia obligatoria de imágenes remotas para que el menú funcione.

La UI puede estudiar jerarquía, ritmo, navegación, composición y claridad de juegos como FIFA 22 y PES 2019, pero no debe reproducir sus pantallas pixel por pixel ni reutilizar material protegido.

## 4. Modos de juego

### Patada Inicial

- 11v11 local;
- selección local/visitante;
- duración;
- dificultad;
- hora y clima;
- jugador único, co-op local y lados opuestos;
- random match;
- acceso directo a entrenamiento y penales.

### Liga y Copa

- liga independiente;
- eliminación directa;
- grupos + KO;
- ida/vuelta;
- formato suizo + KO;
- puntos y desempates configurables;
- reglas especiales guardadas como preset.

### Liga Máster 2.0

Tres papeles principales:

- **DT:** táctica, entrenamiento, preparación física/mental, alineación y recomendaciones de fichajes;
- **Presidente:** contratos, mercado, finanzas, infraestructura, estadio, patrocinio y relación institucional;
- **Control total:** ambos roles en una sola persona.

Debe existir una variante cooperativa DT + Presidente. La simulación final contempla calendario, mercado, scouting con incertidumbre, moral, cantera, infraestructura, reputación y eventos de vida deportiva.

Las ruedas de prensa y conversaciones con el vestuario son candidatas a IA Light, aislada del render y de la simulación por tiempo real.

### Modo Leyenda

- el usuario crea su futbolista;
- carrera, contratos, entrenamiento, reputación y relaciones;
- narrativa emergente en vez de una historia rígida única;
- conexión con Street/Futsal;
- capa cinematográfica para momentos importantes;
- en fases posteriores: selfie/face pipeline y experimentación con reconstrucción del entorno del usuario, siempre opcional y con privacidad explícita.

### Street / Futsal

No es simplemente 11v11 en una cancha pequeña.

- 5v5, 4v4 y 3v3;
- equipos mixtos cuando la regla lo permita;
- club persistente creado por usuarios;
- superficies: parquet, concreto, asfalto y tierra;
- perfiles propios de fricción, rebote y balón;
- reglas de barrio, juego continuo y porterías improvisadas como presets;
- progresión compatible con el jugador de Modo Leyenda;
- táctica e IA entrenables de forma independiente del 11v11.

### Show Football / Kings-style rules

El editor debe soportar formatos que permitan:

- 1v1 / 2v2 / 3v3 temporales;
- goles con valor variable;
- eventos o cartas de reglas;
- cambios dinámicos de formato.

Cualquier uso oficial de la marca Kings League, sus equipos o identidad requiere acuerdo/licencia. El juego base implementa un motor genérico de reglas especiales.

### Online

Objetivo de producto, no funcionalidad que deba fingirse antes de existir:

- Ranked 1v1;
- amistosos privados;
- Clubs;
- Street Clubs;
- Liga Máster co-op remota;
- copas de comunidad;
- spectator/broadcast.

La arquitectura de red debe tratarse como trabajo separado: transporte, sincronización/predicción, recuperación de estado, matchmaking, anti-cheat y telemetría.

## 5. Edición y comunidad

El juego debe conservar el espíritu editable que hizo longevos a los simuladores clásicos:

- editor de equipos;
- creador de jugadores;
- creador de competiciones;
- editor de reglas;
- laboratorio de jugadas preparadas;
- almacenamiento local legible/versionado;
- paquetes comunitarios con manifiesto, hashes y dependencias;
- Workshop de CENTELLA para contenido propio, CC0, compatible o debidamente licenciado.

Nunca asumir que un archivo encontrado en Internet es de libre uso. Cada paquete debe registrar procedencia y licencia.

## 6. Dirección visual

La prioridad no es simular poros, sudor o cada hebra de cabello. La prioridad es que **el frame completo parezca fútbol real** desde la cámara normal y sobreviva a primeros planos razonables.

Orden de inversión visual:

1. iluminación y exposición coherentes;
2. césped y terreno;
3. silueta/proporciones del futbolista;
4. caras fotográficas propias o licenciadas;
5. tela y caída de la equipación;
6. balón, botas, redes y porterías;
7. público y arquitectura del estadio;
8. clima, cámara, overlays y repetición;
9. microdetalle solo si su coste se justifica visualmente.

Se favorecen normal maps, roughness, baked detail y LOD agresivo sobre simulaciones caras que apenas son perceptibles en gameplay.

## 7. Arquitectura técnica

### Simulation Core

Gameplay Football / Google Research Football sirve como cimiento abierto de reglas, escenario y simulación. La capa CENTELLA no debe quedar acoplada a un único launcher Python.

### Product Shell

El shell maneja:

- arranque y menús;
- mando;
- perfiles;
- configuración;
- contenido del usuario;
- selección de modo;
- diagnóstico del runtime;
- lanzamiento del partido.

El shell debe poder abrir aunque el motor nativo esté roto.

### Native Match Runtime

Windows usa un runtime compatible separado para el módulo C++ de Gameplay Football. La beta detecta dependencias y evita lanzar un partido si el motor no importa realmente.

### CENTELLA SR

La resolución interna del partido es configurable. La integración final de SR debe vivir después del render target del partido, no mezclada con la IA de alto nivel.

### IA táctica / Google Colab

El entrenamiento masivo es una fase de ingeniería propia:

- baseline reproducible;
- reward functions documentadas;
- curriculum;
- evaluación contra bots congelados;
- pruebas 11v11 y futsal separadas;
- exportación del modelo solo después de superar métricas y tests de regresión.

No se promete una cifra fija de partidos ni una mejora automática por simplemente entrenar más tiempo.

### IA Light

Usos planeados:

- ruedas de prensa;
- vestuario/directiva;
- narrativa contextual;
- informes de asistente.

Debe ejecutarse de forma asíncrona respecto al loop de render y gameplay.

## 8. Monetización y ecosistema

- juego premium como base;
- cero estadísticas compradas para ganar;
- cosméticos/identidad como espacio de monetización;
- ropa CENTELLA física y virtual como integración opcional;
- Catatumbo como posible ecosistema de creadores;
- música externa (por ejemplo integración autorizada con un servicio) solo mediante APIs y términos oficiales;
- publicidad dinámica únicamente con acuerdos reales, controles de privacidad y sin degradar el partido.

## 9. Estado de la Beta Experience v2

### Funcional ahora en el shell

- splash / press-any-button;
- navegación por mando y teclado;
- viewport responsive;
- hub por pestañas y modos;
- configuración de Patada Inicial;
- co-op local como flujo de lanzamiento;
- selección de academias de entrenamiento;
- creación local de preset de Liga Máster;
- preset Street/Futsal;
- pantalla base de Modo Leyenda;
- editor local de identidad de equipos;
- creador de jugador;
- creador de competición;
- editor visual de jugadas preparadas;
- reasignación de botones persistente;
- vídeo/rendimiento;
- accesibilidad;
- estructura de Workshop;
- CENTELLA Lab para diagnosticar runtime y reparar instalación.

### Depende del runtime nativo

- entrar al partido 3D;
- entrenamiento jugable;
- co-op local dentro del motor.

### Próximas capas reales, no fingidas

- temporada completa de Liga Máster;
- simulación de mercado/scouting/finanzas;
- narrativa de Leyenda;
- física específica de Futsal;
- red online;
- IA Light conectada;
- RL entrenado y evaluado;
- render PBR/LOD moderno;
- estadio/jugadores originales de producción;
- CENTELLA SR integrado al frame final.

## 10. Regla de desarrollo

Una opción no debe aparecer como terminada solo porque existe una tarjeta de menú. Se considera funcional cuando posee:

1. estado persistente;
2. navegación completa;
3. acción real o simulación real;
4. manejo de error;
5. prueba automatizada o caso de test repetible.

La beta puede mostrar la visión completa, pero debe decir con precisión qué parte está conectada y qué parte todavía es una especificación.
