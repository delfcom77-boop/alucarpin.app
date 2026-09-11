# Manual de usuario de AlucarpinSamitier

## 1. Las dos herramientas

El sistema tiene dos formas de trabajo:

- **Aplicacion web**: permite trabajar desde el navegador y gestionar datos centralizados.
- **Programa de escritorio**: permite trabajar desde Windows con las tablas de clientes, faenas, presupuestos, contabilidad y agenda.

Los datos centrales se guardan en Supabase. El programa de escritorio usa tambien una base local SQLite llamada `empresa.db`.

Flujo de datos:

```text
Web -> Supabase -> Programa de escritorio
Programa de escritorio -> Supabase -> Web
```

## 2. Aplicacion web

### Acceso

1. Abre `https://alucarpin-app.onrender.com`.
2. Inicia sesion con tu usuario y contrasena.
3. Entra en el panel correspondiente.

Render puede tardar unos segundos en despertar si llevaba tiempo sin usarse. Esto es normal.

### Gestion de faenas

En **Gestion de Faenas** puedes:

- Crear una faena rellenando cliente, obra, fecha, ubicacion, poblacion, precio y ayudantes.
- Pulsar **Editar** para cargar una faena en el formulario.
- Pulsar **Cancelar edicion** para volver al formulario vacio sin guardar cambios.
- Pulsar **Borrar** para eliminar una faena despues de confirmar.
- Buscar por cliente, obra, ubicacion o poblacion.
- Pulsar **Exportar CSV** para descargar las filas visibles.

El cliente es obligatorio y no puede estar compuesto solo por espacios.

### Gestion de presupuestos

En **Gestion de Presupuestos** puedes:

- Crear presupuestos con cliente, numero, fecha, importes, estado y total.
- Editar un presupuesto.
- Cancelar una edicion.
- Borrar un presupuesto despues de confirmar.
- Buscar por cliente o numero de presupuesto.
- Exportar a CSV los resultados visibles.

Los CSV incluyen encabezados, usan separador `;` y no incluyen los botones de acciones, por lo que se pueden abrir con Excel.

### Otras funciones web

Desde el panel de administracion tambien se gestionan:

- Ayudantes.
- Fichajes.
- Pagos.
- Gastos.
- Liquidaciones.
- Usuarios y contrasenas.

Antes de borrar datos, comprueba siempre el cliente, la fecha y la obra mostrados en la confirmacion.

## 3. Programa de escritorio

### Abrir el programa

Usa siempre esta copia actualizada:

`C:\Users\AlucarpinSamitier\Desktop\EmpresaPython\dist\AlucarpinSamitier.exe`

No abras copias antiguas ni accesos directos que apunten a otra carpeta.

### Recibir datos de la web

El boton **ACTUALIZAR DATOS DE LA APP** descarga datos desde Supabase al programa.

Tambien se realiza una recepcion automatica al iniciar el programa. La recepcion automatica no envia datos locales.

El resultado esperado puede mostrar:

- Ayudantes: 2.
- Fichajes: 6.
- Liquidaciones: 1.
- Faenas: 5.
- Presupuestos: 2.

Despues de recibir datos, abre **CENTRO DE CONTROL** para revisar las tablas.

### Enviar cambios del programa

El boton **ENVIAR DATOS LOCALES A LA APP** sube a Supabase los cambios hechos en el programa de escritorio.

Usalo solamente cuando quieras publicar cambios locales en la web. Este envio es manual para evitar sobrescrituras accidentales.

### Centro de control

Desde **CENTRO DE CONTROL** puedes revisar:

- Faenas.
- Presupuestos.
- Fichajes.
- Gastos.
- Pagos y liquidaciones.

Tras una recepcion, si alguna ventana estaba abierta, sus tablas se actualizan.

## 4. Flujo diario recomendado

### Si trabajas desde la web

1. Entra en la web.
2. Crea o edita faenas y presupuestos.
3. Abre el programa de escritorio.
4. Pulsa **ACTUALIZAR DATOS DE LA APP** si necesitas tener esos cambios en el programa.
5. Revisa los datos en **CENTRO DE CONTROL**.

### Si trabajas desde el programa

1. Abre el programa.
2. Deja que haga la recepcion inicial o pulsa **ACTUALIZAR DATOS DE LA APP**.
3. Haz tus cambios locales.
4. Pulsa **ENVIAR DATOS LOCALES A LA APP**.
5. Comprueba los cambios en la web.

## 5. Botones importantes

| Boton | Accion |
|---|---|
| **ACTUALIZAR DATOS DE LA APP** | Recibe datos de Supabase en el programa |
| **ENVIAR DATOS LOCALES A LA APP** | Envia cambios del programa a Supabase |
| **Editar** | Carga un registro para modificarlo |
| **Cancelar edicion** | Abandona la edicion sin guardar |
| **Borrar** | Elimina un registro despues de confirmar |
| **Exportar CSV** | Descarga las filas visibles de una tabla web |

## 6. Errores habituales

### La web parece no responder

Espera unos segundos. Render puede estar despertando el servicio. Despues recarga la pagina.

### No aparecen cambios en el programa

1. Comprueba que has pulsado **ACTUALIZAR DATOS DE LA APP**.
2. Espera a que termine el mensaje de sincronizacion.
3. Abre o actualiza **CENTRO DE CONTROL**.
4. Comprueba que estas usando el `.exe` de la carpeta `dist`.

### No aparecen cambios de escritorio en la web

1. Comprueba que el cambio se guardo localmente.
2. Pulsa **ENVIAR DATOS LOCALES A LA APP**.
3. Recarga la web con `Ctrl + F5` si ves datos antiguos.

### No se debe pulsar el boton equivocado

- Para descargar datos: **ACTUALIZAR DATOS DE LA APP**.
- Para subir datos: **ENVIAR DATOS LOCALES A LA APP**.

### El programa muestra una version antigua

Cierra todas las copias abiertas y abre:

`C:\Users\AlucarpinSamitier\Desktop\EmpresaPython\dist\AlucarpinSamitier.exe`

## 7. Recomendaciones de seguridad

- No compartas contrasenas.
- No borres manualmente `empresa.db`.
- No pulses el envio local si solo querias recibir datos.
- Antes de borrar una faena o presupuesto, revisa la confirmacion.
- Si hay cambios simultaneos en web y escritorio, sincroniza primero y trabaja despues en un solo lugar.
- Mantén una copia de seguridad de los datos importantes.

## 8. Comprobacion rapida del sistema

El sistema esta funcionando correctamente cuando:

- La web muestra faenas y presupuestos.
- El programa recibe datos sin errores.
- Las cantidades de la web y del programa coinciden.
- Los cambios enviados desde el programa aparecen en la web.
- Las exportaciones CSV se abren correctamente en Excel.
