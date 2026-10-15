# Del HAR a una primitiva comprobada

Aislador se usa offline. Tester-Spin ejecuta pruebas demo nuevas por separado;
no se reutilizan las sesiones de los HAR.

1. Extraer las capturas pendientes por proveedor y agrupar firmas de
   `patrones.json`. Usar `novedades.ndjson` para priorizar; conservar
   `eventos.ndjson` para no perder el contexto conocido que explica una ronda.
2. Emparejar peticiones y respuestas por conexión e identificador. Una captura
   sin inicialización o con respuestas ausentes conserva esa limitación.
3. Contrastar el campo o acción con el cliente de esa misma versión cuando el HAR
   no declara su semántica. Leer código no equivale a ejecutar JavaScript.
4. Crear una prueba reducida sin credenciales, demostrar el fallo e implementar
   la regla en el proveedor de Tester-Spin. No agregar nombres de juegos como
   condiciones ni inferir compras por cantidad de mensajes.
5. Probar negativos: precio o destino contradictorio, opciones no declaradas,
   callbacks condicionados, campos monetarios ambiguos y saldo que no concilia.
6. Comparar el corpus y ejecutar una muestra por familia. Los pasos históricos
   aceptados no cuentan como juegos OK. El ejecutor sigue exigiendo cobertura,
   cierre, saldo conciliado y retorno al giro normal.

## Primer uso sobre Nolimit City

Las capturas de Tester-Spin declaran `encoding: utf8` aun cuando el contenido
transmitido sigue siendo texto RC4 o LZW. Esa etiqueta describe el transporte,
no convierte el contenido en JSON ni significa base64. El codec acepta `utf8`
y `utf-8`, conserva la trama textual y aplica el descifrado correspondiente.
Se incluye una prueba de ambos sentidos de la conexión.

El análisis permitió detectar variantes de mapas de fases, versiones oficiales
con sufijos, campos de premio elegidos por el cliente y retornos de giros extra.
Las reglas y resultados ejecutables se mantienen en
[Tester-Spin](https://github.com/Shisetsu-Code/Tester-Spin/blob/main/docs/NOLIMIT_PRIMITIVES.md).
Aislador no importa Tester-Spin ni exige instalarlo.

Los HAR originales, fuentes completas, claves e informes privados permanecen
locales. Sólo se publican fixtures reducidas y resultados agregados revisados.
