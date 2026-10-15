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
- Nolimit City: RC4/LZW offline, con claves del propio HAR ligadas a la conexión.
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

No usa red, navegador, replay ni dinero. No sube capturas. Claves de descifrado
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
