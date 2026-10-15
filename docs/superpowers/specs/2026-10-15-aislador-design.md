# Aislador: extractor HAR por proveedor

Objetivo: reducir el material de análisis de Tester-Spin eliminando ruido visual
y separando protocolo conocido de novedades, sin borrar la evidencia original.
No ejecuta apuestas, no navega, no certifica OK y no modifica los HAR.

Python 3.11+, núcleo sin dependencias, interfaz CLI y ventana local para elegir
archivos. Perfiles independientes para todos los proveedores del registro de
Tester-Spin; perfiles de catálogo sin protocolo aprendido quedan explícitos.
Nolimit incluye RC4/LZW offline ligado a cada conexión. Otros formatos JSON,
formularios y WebSocket se conservan; opacos permanecen pendientes.

Salidas por captura: resumen.json, resumen.md, eventos.ndjson (protocolo íntegro
sanitizado), novedades.ndjson, patrones.json y contexto.json. Cada evento tiene
referencia estable al original, proveedor, dirección, transporte, petición y
respuesta o mensaje, firma de forma y clasificación con motivo. Los eventos
repetidos siguen completos en eventos, pero el informe agrupa ejemplos.

El filtro sólo retira recursos visuales/telemetría conocidos del informe de
protocolo. JavaScript/config relevante se inventaría con hash y referencias;
se puede extraer por referencia para ingeniería inversa, con ventana de texto.
Las novedades incluyen acciones/fases desconocidas, campos nuevos y errores.
Nunca inferir compras desde número de endpoints o acciones ni del host Evolution.

Todas las credenciales, cookies, encabezados de autorización e identificadores
de sesión se redactan antes de escribir salidas. Claves de descifrado sólo en
memoria. Sin red, replay, ejecución JS o subida automática de capturas privadas.
La publicación contiene código, documentación y pruebas sintéticas, sin HAR reales.

Interfaz codec: decode_frames(document, frames) -> mapping[ref] de dict con
`data` (objeto JSON decodificado o None), `issue` (código estable o None),
`codec` (nombre). Frames normalizados: ref(str), url(str privado), connection(str
privado), direction(sent|received), payload(str), encoding(str|None), late_attach(bool).
Referencias HTTP `http:0`, WS `ws:entry:0:frame:0` o `ws:log:0`.

Los perfiles son datos versionados. La estructura JSON usa key, name, hosts,
endpoint_patterns, action_paths, known_actions, known_phases, known_fields,
protocol_status y notes. Un host o acción conocida no basta para ocultar una
respuesta: siempre se preserva y campos desconocidos se señalan. Una base de
patrones local opcional reconoce firmas revisadas, sin aprender silenciosamente
ni convertir una captura en autoridad de opciones.
