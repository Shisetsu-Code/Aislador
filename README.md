# Aislador

Extractor offline de HAR para aislar protocolo, apuestas y novedades por proveedor.
Quita recursos visuales conocidos del informe principal, agrupa repeticiones y
conserva cada mensaje de juego con una referencia al HAR original.

## Abrir en Windows

Con Python 3.11 o posterior instalado, hacé doble clic en **Aislador.cmd**.
Elegí uno o varios HAR, el proveedor (o Automático) y una carpeta de resultados.
También se puede abrir con `python -m aislador gui`.

El núcleo funciona sin instalar paquetes. Para descifrar Belatra, si falta la
biblioteca de cifrado: `python -m pip install ".[belatra]"`.

## Usar desde una herramienta o consola

```powershell
python -m aislador extract "C:\Capturas\juego.har" --provider nolimit_city --out salidas --json
python -m aislador extract "C:\Capturas" --recursive --provider auto --out salidas --json
python -m aislador providers
```

La detección usa dominios y rutas de protocolo, no el nombre del archivo.
Evolution y Playin son plataformas compartidas: no bastan para decidir proveedor.
Si no hay evidencia suficiente se conserva `unknown`; se puede elegir el perfil.

## Qué genera

Cada captura crea una carpeta nueva; nunca sobrescribe el HAR ni una extracción anterior.

| Archivo | Contenido |
| --- | --- |
| `resumen.md` / `resumen.json` | Conteos, pendientes, proveedores y recursos retirados |
| `novedades.ndjson` | Patrones por revisar, campos nuevos, muestras, acciones y referencias |
| `eventos.ndjson` | Todas las transacciones de protocolo sanitizadas, incluidas las conocidas |
| `patrones.json` | Firmas agrupadas, frecuencia y hasta tres ejemplos |
| `contexto.json` | Inventario de imágenes, audio, fuentes, scripts y otros recursos, con hash y referencia |

Las decisiones, estados, precios, premios y saldos siguen en los eventos.
Los cambios de opciones y valores de selección participan en la firma; los
importes variables no crean por sí solos cientos de patrones iguales.
No se cuentan compras por endpoints, botones ni cantidad de mensajes.

## Recuperar contexto sin abrir todo el HAR

```powershell
python -m aislador event "salidas\captura-12345678" --ref ws:log:12
python -m aislador context "C:\Capturas\juego.har" --ref http:20 --find selectedIndex --radius 400
```

El segundo comando lee una ventana del recurso original, sanitiza antes de
recortar y no ejecuta JavaScript. Sus offsets corresponden al texto sanitizado.
`contexto.json` también incluye posiciones originales de llamadas conocidas en
scripts cuando el cuerpo fue capturado. El HAR original permite abrir el recurso
completo con otras herramientas si se necesita ingeniería inversa adicional.

## Qué está aprendido

Hay **24 perfiles** del registro de Tester-Spin: 11 con conocimiento de protocolo
y 13 de catálogo, cuyo protocolo todavía se conserva como no aprendido.
Cada uno tiene reglas independientes: [cobertura por proveedor](docs/PROVEEDORES.md).

- JSON y formularios HTTP; WebSocket de Firefox y HardFire; cuerpos base64.
- Nolimit City: RC4/LZW offline, con claves del propio HAR ligadas a la conexión; admite capturas de navegador y de Tester-Spin con metadatos `utf8`/`utf-8`.
- Belatra: AES offline opcional, con configuración y sesión capturadas.
- 1Spin4Win: envelope A/u2, CSV posicional y JSON; init sin identificadores privados.
- Imágenes, fuentes, atlas, Spine, traducciones, audio embebido y telemetría conocidos pasan al inventario de contexto.
- Mensajes opacos, claves ausentes, cuerpos incompletos y errores permanecen pendientes.

Un perfil no es un ejecutor ni un validador de rondas. **Conocido no significa OK**
y una captura no prueba la cantidad total de compras o elecciones del juego.

## Incorporar conocimiento revisado

Las firmas revisadas se guardan en una base local opcional. No se aprenden
silenciosamente ni se ocultan errores de servidor, mensajes opacos o falta de cuerpos.

```powershell
python -m aislador review "salidas\captura-12345678\patrones.json" --pattern FIRMA --note "Revisé la declaración y la transición" --knowledge conocimiento.local.json
python -m aislador extract "C:\Capturas\otro.har" --knowledge conocimiento.local.json --out salidas
```

Una opción, acción, fase o campo nuevo cambia la firma y reaparece para revisión.
Para añadir un proveedor se agrega un perfil en `aislador/profiles.json`; los
codecs nuevos viven en `aislador/codecs/`, sin modificar los demás proveedores.

## Privacidad y límites

El análisis `extract` no usa red, navegador, replay ni dinero. No sube capturas. Claves de descifrado
se usan sólo en memoria; las salidas redactan credenciales y alias conocidos.
Campos privados con nombres todavía desconocidos pueden requerir revisión antes
de compartir los informes. Los HAR y las bases locales están excluidos de Git.

Límites: 256 MiB por HAR y 8 MiB por cuerpo a interpretar. Un cuerpo binario
sin formato reconocido queda opaco con referencia al original. Si falta el
bootstrap de un cifrado no se consulta el servidor ni se inventa la clave.
Las capturas parciales y sesiones distintas se identifican sin certificar éxito.

## Desarrollo

```powershell
python -m unittest discover -s tests -v
python -m pip wheel . --no-build-isolation --no-deps --wheel-dir dist
```

Paquete instalable como `aislador-har`, comando `aislador`. La ventana requiere
Tkinter, incluido normalmente con Python en Windows.

Las primitivas conocidas se contrastaron con código del repositorio
[Tester-Spin](https://github.com/Shisetsu-Code/Tester-Spin). Aislador funciona
independientemente y no importa ni necesita instalar Tester-Spin.


## Aprendizaje aplicado a Tester-Spin

El flujo utilizado está documentado en [APRENDIZAJE.md](docs/APRENDIZAJE.md).
Se agrupan mensajes y bloqueos por familia; el cliente de la misma versión
aporta los enlaces de acciones y campos. Después se implementa una primitiva
compartida, se contrasta el corpus y se ejecutan demos nuevas representativas.
El extractor no convierte sus hallazgos en reglas ejecutables automáticamente.

## Playtech: aislamiento offline

El lector reconoce los sobres JSON `3:::` de Socket.IO 1.x en los endpoints
observados de GPAS y Playtech Horizon. Enlaza solicitudes y respuestas por
`correlationId`, conserva el tipo del mensaje y deja visibles configuraciones,
costes, opciones, elecciones, continuaciones, saldos y errores. Los controles
exactos de conexión y heartbeat pasan al inventario de contexto con su referencia.
Los mensajes malformados y tipos desconocidos siguen pendientes.

Los recursos `texts_<idioma>.jmm` y `dt_texts_<idioma>.jmm` del cliente oficial
pasan al contexto como traducciones; los `.default.jmm` y otras configuraciones
siguen en los eventos. Scripts, imágenes, atlas, fuentes y audio mantienen el
filtrado común existente, sin borrar el original. Los errores HTTP se conservan.

Este lector no equivale a un ejecutor aprendido: el perfil Playtech permanece
`catalog_only`. Las demos NGM con cálculo local requieren consultar el cliente
capturado; no se inventan apuestas de servidor ni se ejecutan scripts del HAR.
Los ámbitos `freespin`, tamaños de moneda y multiplicadores de coste no prueban
por sí solos compras o antebets. El análisis no envía apuestas ni consultas de red.

## Captura y aislamiento por lotes

`capture` abre demos nuevas en Chromium, graba respuestas HTTP con sus cuerpos
y mensajes WebSocket desde antes de navegar, guarda el HAR y ejecuta `extract`.
No necesita capturas manuales ni screenshots. Requiere el extra opcional:

```powershell
python -m pip install ".[capture]"
python -m playwright install chromium
python -m aislador capture "https://ejemplo.test/demo" --demo --provider auto --out .local/capturas
python -m aislador capture --demo --provider playtech --tester-spin-db "C:\Proyectos\Tester-Spin\data\tester-spin.sqlite3" --max-games 3 --seconds 12 --out .local/playtech
```

El segundo modo lee pendientes del catálogo en modo de sólo lectura, excluye
los OK y exclusiones manuales. Playtech usa el `symbol` oficial y reparte la
muestra entre NGM, GPAS y POP; son rutas de lanzamiento, no familias de mecánicas
ya demostradas. Otros proveedores abren la página pública registrada: un catálogo
o login que no abre la demo conserva esa limitación. No se promete ejecución
universal ni se adivinan controles. URLs explícitas permiten seleccionar demos
directas que el catálogo todavía no conoce.

`queue.private.json` conserva el progreso; repetir el mismo lote retoma pendientes
y reutiliza los HAR guardados si falló el análisis. `familias.json` agrupa firmas
entre capturas y mantiene hasta tres ejemplos con referencias para revisar una
primitiva compartida. HAR, cola e informes permanecen locales. Un mismo destino
admite un proceso de captura a la vez.

La captura abre sesiones independientes, sin reutilizar cookies o tokens de HAR,
y observa inicialización y tráfico espontáneo. No pulsa controles ni hace apuestas;
un bonus que exige jugar necesita el explorador/fuzzer correspondiente. Estos
informes son la entrada para analizar e implementar primitivas en Tester-Spin;
no modifican ejecutores ni convierten juegos en OK automáticamente.

## Entrega de observaciones a Tester-Spin

Al capturar con `--tester-spin-db`, los informes GPAS se guardan también junto
a los datos de Tester-Spin, sin modificar su base ni sus estados. Sólo se entrega
un informe cuando la inicialización identifica un único `gameCode` y coincide
con un único `symbol` del catálogo. `--handoff-data-root` permite elegir otra
carpeta de datos. Las configuraciones y rondas conservan la conexión y el código
de juego observado; la falta de identidad o de protocolo queda pendiente.

`protocol-evidence.json` es un contrato de observaciones, no código ejecutable:
el adaptador de Tester-Spin lee costes por ámbito y decisiones anidadas, mantiene
compras/antebets desconocidos y no convierte capturas históricas en rondas OK.
Los tipos de coste por sí solos no autorizan comandos. Los lanzadores NGM/POP
siguen requiriendo sus propios lectores y ejecutores.

La cola por catálogo aplica el límite después de omitir capturas terminadas:
cada lote avanza a candidatos nuevos. La carpeta se bloquea durante la operación
para impedir capturas duplicadas de dos procesos. El bloqueo se libera al salir
el proceso, incluso si se interrumpe.

## Capturas automáticas tras ERROR/PARCIAL

Tester-Spin puede iniciar `follow-failures` al guardar un resultado ERROR o
PARCIAL. El trabajador consulta la base en modo de sólo lectura, toma una
captura pasiva nueva por resultado y deja `revision.json` con los informes por
revisar. Un fallo posterior del mismo juego recibe otro HAR; reintentar sólo el
análisis reutiliza la captura de ese resultado. Los OK no disparan capturas.
Un resultado más reciente reemplaza solicitudes anteriores pendientes del juego.

```powershell
python -m aislador follow-failures --tester-spin-db "C:\Proyectos\Tester-Spin\data\tester-spin.sqlite3" --out .local/fallos --after-id 100 --seconds 12
```

`--after-id` fija el punto de inicio para no descargar el historial entero; la
cola conserva su cursor. `--once` procesa un lote y termina. El modo trabajador
mantiene vivos los reintentos pendientes (hasta tres intentos, separados por
cinco minutos) y finaliza tras quedar inactivo. Una captura sin protocolo útil
no equivale a cobertura ni produce reglas ejecutables. El análisis de primitivas
sigue siendo trabajo de revisión; no se instala código desde un HAR.
