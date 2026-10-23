# Hermes's Hoard

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
