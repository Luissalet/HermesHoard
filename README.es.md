# Hermes's Hoard

**Productos → objetivo → Cómo descargar → Mi ventana abierta (Brave/Chrome/Edge)** vigila una página que ya tienes abierta en un navegador Chromium de este PC, para tiendas que responden a los navegadores automáticos con una verificación. En cada comprobación Hermes busca la ventana cuya pestaña activa muestra la dirección del objetivo, pulsa el botón Recargar de esa misma ventana mediante Windows UI Automation, la desliza hasta el final y vuelta arriba para que carguen las listas perezosas y lee el texto; la ventana no pasa al frente ni recibe teclas ni clics. Cada fila de producto de una lista (nombre, precio y texto del botón, como «Añadir», «Agotado temporalmente» o «Próximamente») se sigue por separado: sus propios avisos de reposición, apertura de venta, reserva y precio, y su propio «se acabó», así que dos productos que vuelven uno detrás de otro dan dos avisos. Estas comprobaciones tienen su propio carril en el planificador y mantienen su intervalo (5 minutos o más) aunque otros objetivos tengan cola. Si la ventana está cerrada, muestra otra página o pide una verificación humana, Hermes envía un único aviso de prioridad alta (también por correo) y sigue intentándolo al mismo ritmo; nunca responde a la verificación. En la API/MCP el modo es `open_window` en `target_add` / `target_update`. Necesita Windows y el paquete `uiautomation` (incluido en `requirements.txt`).

Cada lectura de ventana abierta se comprueba dos veces más. **Comprobación del modelo:** el modelo configurado (por defecto la ruta de Prometheus) lee el mismo texto y devuelve cada fila con su estado y las palabras que lo prueban; las filas en las que coincide quedan corroboradas, una fila comprable que solo ve el modelo queda pendiente y se vuelve a leer al minuto (un aviso necesita dos lecturas seguidas), y si discrepa se mantiene la lectura por reglas. **Mirada de Faustus:** si Faustus está en marcha, Hermes le pide (en segundo plano, una mirada por objetivo a la vez) que lea la misma pestaña con su extensión de sesión de navegador, la deslice y abra fichas de producto en pestañas de fondo cuando una fila no esté clara; su veredicto se guarda y se combina en la siguiente comprobación, y si difiere de Hermes esa comprobación se adelanta. Faustus nunca pulsa un botón de compra ni responde a una verificación. Ajustes: `faustus_eye.enabled` (`1`/`0`) y `faustus_eye.url` (por defecto `http://127.0.0.1:7000`).

Los avisos de compra caducan cuando acaba la oferta. Un aviso de reposición, reserva o precio sale de **Productos → Novedades** en cuanto la página de la tienda o el radar de agregadores lo ven agotado, o cuando ninguna página lo confirma durante horas. El historial lo conserva marcado **Agotado** o **Sin confirmar**, con la hora. Si el aviso ya se había enviado, sale un breve «se acabó» por los mismos canales. Sale una sola vez por aviso, dentro de los dos días siguientes y solo cuando la oferta acaba de terminar. Limpiar avisos antiguos no envía nada. La opción del vigilante **Avisar también cuando se agota algo que ya avisó** (`policies.notify_ended_alerts`, activada por defecto) lo desactiva. Una oferta que solo había caducado y vuelve a aparecer el mismo día recupera su aviso sin generar otro.

Las invitaciones de Amazon que reaparecen tras caducar o discrepar las vistas del agregador no generan otra alerta de reserva. El panel muestra una reserva actual por URL de Amazon y el historial conserva todos los avisos. El radar prefiere fotos de la tienda, con caché diaria y hasta seis consultas por ciclo. `radar_run(watcher_id, refresh_urls)` actualiza las fotos de productos conocidos; `retailer_details` corrige imagen HTTPS y formato verificados expresamente, conservándolos frente al agregador. Estas operaciones dirigidas no comprueban stock ni envían avisos.

**Productos → Novedades / Historial / avisos de un producto** permiten **Marcar visto** un aviso individual. Sólo cambia su marca local `seen`: conserva estado, precio, historial, otros avisos pendientes y la última visita global. El aviso sigue disponible en Historial al quitar **Sólo no vistos**. Se conservan **Marcar todo visto**, Descartar y Reenviar. Usa `events_mark_seen(event_ids:[ID])` nativo API/MCP115 sin comprobar fuentes ni enviar notificaciones; los errores conservan filtros y permiten reintentar.

En **Viajes → Fusionar con otro viaje**, IDs, fechas, destino, cantidades nativas
de reservas/gastos y monedas distinguen ambos viajes, incluso con títulos iguales.
La misma confirmación existente reúne reservas y gastos, remapea personas,
pagadores y repartos según el motor, concatena notas guardadas y elimina el otro
viaje. No añade conversión de divisas ni deshacer. El recibo del viaje conservado
permanece hasta Cerrar, aunque falle la recarga; las notas de la ficha pendientes
siguen separadas y sin guardar. La página retira de sus opciones el ID cuya unión
se confirmó. Motor y `trip_update(merge_from, confirm)` API/MCP115 siguen iguales.

En **Viajes → Editar tramo** se pueden anotar Puerta de vuelo, Coche de tren y
Clase de transporte. Coche y Asiento tienen campos distintos. El editor carga los
valores guardados; vaciar un campo borra su valor nativo. Guardar envía sólo campos
editados por `segment_add/update` API/MCP existentes, conservando el comportamiento
actual de error, reintento y borrador posterior. Son datos locales: no consultan
información de embarque en directo ni cambian la reserva del transportista.
Los demás campos, exportación de calendario y acciones de viaje siguen disponibles.

En **Productos → Segunda mano**, **Marcar como retirado** establece el estado local `gone` del anuncio. Sale de los activos y sigue accesible en el filtro **Retirados** del vigilante; **Guardar** lo devuelve a Guardados. Usa `listing_set` existente por API/MCP sin consultar ni cambiar el anuncio en la plataforma ni pausar el vigilante. Sólo cambia el estado: conserva identidad, precios cero/desconocidos, fechas guardadas, contenido e historial de precios. No se infiere una fecha de retirada.

En **Viajes → Plan**, selecciona algunas reservas y pulsa **Separar** para revisar cuáles se trasladan y dar nombre opcional al nuevo viaje. Vacío conserva el nombre automático nativo. El resultado muestra los IDs, fechas y cantidades devueltos del original y del nuevo, con **Abrir viaje creado** explícito; no navega automáticamente. Las reservas conservan su identidad y sus correos asociados. Los participantes y gastos registrados, incluidos los de reservas trasladadas, permanecen en el viaje original. Cancelar no escribe; un error conserva nombre y selección. Usa `trip_update(split_segments, split_title)` existente por API/MCP, sin consultar proveedores o correo.

En **Viajes → Gastos → Participantes**, **Cambiar nombre** modifica la persona seleccionada mediante el mapa `rename` de `trip_people`, ya disponible por API/MCP y dirigido al ID visible de la persona. Antes de guardar se muestran el viaje y la persona. Los homónimos siguen siendo personas distintas; se conservan el ID, la marca «soy yo», la posición, los gastos, quién pagó y los repartos. Cancelar o fallar conserva el borrador, y una edición posterior durante el guardado sigue pendiente tras refrescar. Sólo guardar escribe el nombre local nativo; no cambia ningún perfil de una cuenta externa.

La ficha de cada vigilante de disponibilidad ofrece **Marcar comprado**, con referencia local de compra opcional. El registro manual detiene las comprobaciones programadas, conserva productos e historial y muestra fecha/referencia registradas sin verificar una compra externa. El interruptor **Activado** existente permite volver a vigilar y retira la marca de compra. La UI usa `watcher_mark_bought` y `watcher_update` de API/MCP; abrir o cancelar no modifica el vigilante, y cancelar o fallar el guardado conserva el borrador de la referencia.

<img src="app-icon.png" width="96" alt="Hermes icon">

Productos, ofertas, seguimiento de envíos y viajes en un único proceso. Absorbe **Tantalus y Phileas**, conservando sus funciones, herramientas e historiales.

La ficha de un envío ofrece **Unir registro duplicado** para dos registros locales del mismo paquete. La ficha abierta conserva su identidad; elige el otro registro y revisa ambas identidades y los siete campos que pueden rellenarse si están vacíos. Los valores existentes tienen prioridad. `shipment_merge` nativo API/MCP traslada correos asociados, eventos no duplicados y notificaciones registradas, elimina el registro seleccionado y recalcula en silencio la estimación local de entrega. No concatena notas, nombres ni los demás campos; la confirmación habitual explica la eliminación y que no hay deshacer. Abrir/cancelar sólo lee, y los errores de búsqueda o guardado conservan la selección y las ediciones sin guardar. No se consulta transportista/correo ni se modifica un pedido externo.

En **Envíos → Consultar número** puedes consultar puntualmente un seguimiento sin añadirlo a la biblioteca ni programar comprobaciones. Muestra la respuesta nativa del transportista: estado, fuente, estimación y hasta 40 eventos; diferencia envío no encontrado, falta de fuente y error. Consulta sólo al pulsar **Consultar**, mediante `track_number` existente en API/MCP. Usa las fuentes configuradas, que pueden realizar peticiones externas y consumir su cuota; no lee correo ni guarda el envío. Cambiar número o transportista retira el resultado anterior, y cerrar o fallar conserva el borrador.

[English](README.md) · [Inventario de herramientas](provenance/CAPABILITIES.md) · [Procedencia del código](provenance/sources.json)

## Funciones independientes

**Los dos módulos están desactivados en la primera apertura.** Abrir Hermes o consultar el catálogo MCP no inicia navegadores, búsquedas, lectura de correo, comprobaciones ni modelos. Activa lo que quieras usar; la elección se recuerda entre sesiones. «Desactivar todas» detiene los módulos sin borrar su historial.

- **Productos y ofertas:** stock, precios, preventas, lanzamientos, descubrimiento, segunda mano y puntuación de resultados, vigilantes de webs/noticias, ofertas por correo, radar, navegadores, avisos, programación e historial.
- **Envíos y viajes:** importación y lectura de correos, identificación de paquetes, transportistas, seguimiento y llegada estimada, panel de entregas, incidencias, avisos, viajes y trayectos, recordatorios de facturación/salida, correo de viajes, presupuestos, monedas y husos horarios.

Las interfaces completas están en `/products/` y `/shipments/`, con el tema común de los Hoards, el icono de Hermes y Faustus. Los ajustes propios de cada función siguen dentro de su módulo.

## Arranque y datos

Python 3.11 o posterior. Ejecuta `Start.cmd` o sigue los comandos de [README.md](README.md#run). Abre `http://127.0.0.1:5221`; no se abre una ventana automáticamente. También puede iniciarse expresamente desde Hoard Hub.

Con ambos módulos apagados:

```powershell
.venv\Scripts\python.exe scripts\adopt_data.py --parent "C:\ruta\a\las Hoards"
```

Solo se escribe `data/modules.json`. Las bases de datos, marcas de correo leído, cachés, perfiles de navegador, evidencias, ajustes y tokens siguen **en las carpetas originales**. Los secretos `.env` se leen desde allí al activar el módulo. No se copian, mueven ni borran esos datos; conserva sus carpetas. Sin adopción se usan carpetas nuevas.

Desactivar espera a que termine el trabajo en curso antes de mostrar el módulo apagado, manteniendo disponible el panel.

## Herramientas y compatibilidad

**115 herramientas MCP:** 113 funciones nativas y dos controles de módulos. Siete nombres coincidían entre Tantalus y Phileas; en el catálogo conjunto llevan el prefijo `products_` o `shipments_`. Cada API nativa conserva los nombres originales. El [inventario completo](provenance/CAPABILITIES.md) muestra las correspondencias.

En **Envíos**, «Calendario de entregas» permite revisar un periodo y descargar un ICS con entregas estimadas y fechas límite de recogida registradas. Las entregas llevan estado provisional y los plazos de recogida, confirmado; todos son eventos de día completo que no bloquean la agenda. Se cuentan envíos sin fecha y fechas fuera del periodo, excluyendo finalizados, archivados e históricos. Es una instantánea descargada, sin actualización automática. La herramienta `shipments_ics` ofrece fechas, ICS completo y enlace de descarga por API/MCP; `GET /shipments/api/shipments/ics?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` descarga el archivo. Por defecto abarca desde hoy hasta dentro de 90 días. El listado existente admite hasta 2.000 envíos activos y avisa al alcanzar esa cifra. No se consulta correo, transportistas ni modelos, ni se modifican envíos.

El puente `mcp_server.py` descubre las herramientas sin arrancar Hermes. Las llamadas a módulos apagados devuelven `module_disabled`. Las identidades antiguas pueden permanecer en el Hub como entradas de compatibilidad **sin lanzador**, apuntando a Hermes; conservan correo, tokens, referencias y llamadas internas sin ejecutar servidores antiguos.

Los modelos de texto usan Sparks, según la configuración global de la familia. Ningún modelo se carga con sus módulos apagados. La configuración, compilación y pruebas se detallan en [README.md](README.md).


## Datos propios y compatibilidad

Los datos nativos pueden trasladarse a `data/native/<módulo>/data`, con configuración privada junto a cada módulo. La ficción de Writer utiliza su perfil de escritorio `writers-hoard/fiction/data`. Traslada árboles completos, incluidos WAL/SHM de SQLite, medios, modelos descargados y sesiones del navegador; actualiza las rutas absolutas guardadas antes de activar el módulo. Los manifiestos de `compatibility/<id>/faustus-plugin.json` conservan identidades, nombres de herramientas y tokens sin necesitar el repositorio retirado. Añade el directorio `compatibility` de cada producto a las raíces del Hub antes de la raíz general. El catálogo y los puentes compatibles nunca arrancan aplicaciones. Todos los módulos permanecen apagados durante el traslado.

Las instrucciones anteriores de adopción in-place describen una importación opcional. Una vez comprobados el traslado y las rutas, ya no es necesario conservar las carpetas de los productos antiguos.
