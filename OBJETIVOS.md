# Hermes's Hoard — siguientes pasos

## Productos
- Avisos de stock del correo: aprender de las asignaciones a mano (guardar el par remitente→tienda o la palabra que faltaba) para que el siguiente correo igual se case solo.
- Avisos de stock del correo: leer también por la pasarela de correo del Hub cuando esté lista, con un interés propio que no pise el de las ofertas (hoy van por el lector de Faustus).
- Mostrar en Novedades una etiqueta «por correo» en los avisos con `data.source = mail_notice`, con el asunto del correo al pasar el ratón.

## Envíos
- Acción requerida: casar el aviso de aduanas con el correo del transportista que trae el enlace de pago y mostrar el importe cuando venga en el texto.
- Estimación: medir la precisión propia (fecha estimada el primer día frente a la entrega real) por transportista y origen y enseñarla en el detalle.

## Pruebas
- `legacy_tests/` conserva 12 pruebas de la época de repos separados (manifiesto, `docs/API.md`, versión 0.2.0, nombre del puente `tantalus-hoard` / `phileas-hoard`, `x-family.agenda` en la raíz) que fallan desde la fusión. Reescribirlas contra los manifiestos de `compatibility/` y el catálogo conjunto, o retirarlas a favor de `tests/`.
