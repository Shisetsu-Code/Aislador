# Perfiles de proveedores

`aislador/profiles.json` contiene schema 1 y los 24 proveedores del registro de Tester-Spin: 11 ejecutores y 13 catálogos. Fuente revisada: código local de `tester_spin/providers` y `tester_spin/catalog_sources.py`, el 15 de octubre de 2026. No se copiaron capturas, cookies ni claves.

Las listas son vocabulario parcial revisado, no un certificado de cobertura ni un catálogo de compras. Un evento de acción o forma conocida sigue íntegro en eventos; los campos nuevos se destacan. Dinero, apuestas, costes, premios, saldo y decisiones del jugador siguen visibles aunque su ruta sea conocida. `*` sólo representa elementos de una lista; nunca cualquier campo de un objeto.

Las expresiones se aplican al path URL, sin query. Son pistas de protocolo, no prueba de identidad por sí solas. Un host identifica una familia candidata; el esquema y endpoint concreto deben resolver conflictos. Las rutas vacías indican falta de evidencia estable, no ausencia de protocolo. Los hosts enumerados son dominios literales; cualquier coincidencia de subdominios debe respetar el límite de dominio, nunca substring.

| Proveedor | Estado | Evidencia de código | Límite real |
| --- | --- | --- | --- |
| Pragmatic Play | structured | pragmatic.py; pragmatic_endpoint.py | Formularios gameService; vocabulario parcial; pur/puri/purtr no certifican otra compra. |
| 1Spin4Win | structured | one_spin4win.py, _recv_protocol_json y D1 | A/u2 y JSON offline; init CSV sólo metadata pública; play conserva columnas numéricas posicionales sin inferir compras. CSV opaco se redacta. WS dinámico sin ruta inventada. |
| Belatra | belatra_codec | belatra.py, transporte game; aislador/codecs/belatra.py | AES offline opcional cuando el HAR contiene configuración sc necesaria. Sin clave/configuración suficiente, el sobre d permanece opaco y pendiente. No se extraen claves a las salidas. |
| BGaming | structured | bgaming/runtime.py | command, flow y variante legacy parciales. Endpoints derivados de bootstrap; Hyperhive puede quedar opaco. |
| KA Gaming | structured | ka_gaming/adapter.py y runtime.py | Sólo rutas RMP explícitas; no se declara aprendido el WS fish ni opciones dinámicas. |
| RubyPlay | structured | rubyplay/runtime.py | server_url viene del launcher; hosts de juego dinámicos no enumerados sin evidencia literal. init-session/demo y gameserver/demo tienen esquema propio. |
| Red Tiger | structured | redtiger/bootstrap.py y runtime.py | /platform/game/settings, spin y choice son evidencia principal; dominios dinámicos. Evolution, cmsevo y fansite no se adjudican a RedTiger. |
| 3 Oaks | structured | three_oaks/adapter.py y runtime.py | Goreel login/start/play y action.name; endpoint de configuración, sin regex amplia /demo/. |
| Yggdrasil | structured | yggdrasil/protocol.py y runtime.py | service fn=play y cmd=C explícitos; opciones anunciadas dinámicamente siguen sin aprender. |
| Hacksaw Gaming | structured | hacksaw/adapter.py y runtime.py | authenticate/bet en path; no se inventa discriminador del cuerpo. |
| Nolimit City | nolimit_codec | nolimit_city/runtime.py | RC4/LZW por conexión y clave bootstrap; falta de clave o captura tardía queda pendiente. Fases y campos parciales, nunca autorización de acciones. |
| Playtech | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Games Global | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Amusnet | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Play’n GO | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Greentube / Novomatic | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| NetEnt | catalog_only | catalog_sources.py | Sin protocolo aprendido; distinto de RedTiger. Evolution no es identidad de proveedor. |
| PG Soft | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Blueprint Gaming | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Relax Gaming | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Playson | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Wazdan | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| ELK Studios | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |
| Push Gaming | catalog_only | catalog_sources.py | Sólo identidad y hosts del catálogo. |

`structured` significa que existe estructura legible en el ejecutor, no que todos los juegos o variantes estén cubiertos. Las novedades de una variante no amplían silenciosamente el perfil. `catalog_only` deja vacíos endpoint_patterns, action_paths y todas las listas known; el catálogo no prueba comportamiento del juego.

La revisión usó únicamente código y contratos existentes. No se deducen compras del nombre de un juego, de una regex de comandos, del número de endpoints ni de un host compartido. Después se validó el motor con HAR locales de siete proveedores; los agregados y límites están en [VALIDACION.md](VALIDACION.md). Las capturas permanecen privadas.

La extensión `shared_host_endpoint_patterns` sólo se habilita en RedTiger para las tres rutas /platform/game indicadas; está vacía en los otros 23 perfiles. El motor debe limitar esta excepción a hosts compartidos explícitamente revisados (games.evolution.com/playin.com) y exigir coincidencia de ruta. El host compartido solo no atribuye proveedor.
