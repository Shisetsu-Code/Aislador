# Validación de Aislador — 15 de octubre de 2026

Las capturas reales permanecen locales y excluidas de Git. Estas cifras sólo
miden reducción de contenido del HAR al archivo de eventos sanitizados; no miden
cobertura de apuestas ni éxito de los juegos.

| Proveedor | HAR original (bytes) | Eventos | Patrones | Eventos sanitizados (bytes) | Reducción |
| --- | ---: | ---: | ---: | ---: | ---: |
| nolimit_city | 12519086 | 84 | 31 | 677399 | 94.6 % |
| hacksaw | 27287701 | 37 | 22 | 487712 | 98.2 % |
| redtiger | 57100147 | 40 | 29 | 1657011 | 97.1 % |
| belatra | 68921282 | 320 | 57 | 1601129 | 97.7 % |
| 3oaks | 39365022 | 36 | 21 | 184346 | 99.5 % |
| yggdrasil | 6358300 | 65 | 38 | 931800 | 85.3 % |
| pragmatic | 7090121 | 56 | 22 | 161817 | 97.7 % |

Los patrones por revisar todavía incluyen variantes de campos y formatos no
incluidos en el vocabulario parcial. No se marcaron todos como conocidos sólo
para mejorar la cifra. `eventos.ndjson` conserva repeticiones; `novedades.ndjson`
agrupa hasta tres muestras con señales y valores nuevos acotados.

## Cifrados y capturas parciales

- Nolimit: los 78 mensajes de la captura revisada se descifraron, conservando
  conexiones separadas y señalando dónde faltaba init.
- Belatra: una captura con 295 peticiones cifradas y 295 respuestas se descifró
  completa; en otra se descifraron 141 peticiones y 137 respuestas. Las cuatro
  respuestas faltantes eran HTTP 0 con cuerpo vacío.
- Tres HAR de Belatra sin HTML/bootstrap conservaron sus 378, 234 y 100 sobres
  como pendientes: no se consultó el servidor para recuperar claves.
- 1Spin4Win: pruebas sintéticas contrastadas con el codec de Tester-Spin; no
  se atribuye validación real a un HAR ausente en la carpeta actual.

## Pruebas del programa

70 pruebas automatizadas aprobadas: normalización HAR, formularios/base64,
múltiples sesiones, mezcla parcial de representaciones WS, dominios de opciones,
errores no silenciables, credenciales conocidas, ventanas de contexto, codecs,
repetición de extracción sin sobrescritura y revisión explícita de patrones.

El paquete wheel se construyó sin descargar dependencias; su registro de perfiles
se carga fuera del árbol fuente. La ventana Tkinter se inicializó y cerró en una
prueba local. CI ejecuta la suite en Windows y Linux, Python 3.11 y 3.13.
