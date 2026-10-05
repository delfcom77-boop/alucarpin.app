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

### Dias trabajados de ayudantes por faena

En **Ayudantes -> Gastos registrados -> Dias trabajados por faena** puedes:

- Filtrar por tipo de trabajo: faenas a terceros, presupuestos Alucarpin, reparaciones o pendientes de vincular.
- Seleccionar un cliente, por ejemplo Mercedes o Alucarpin Samitier, y un ayudante.
- Buscar una obra y limitar el periodo con las fechas Desde y Hasta, ambas incluidas.
- Ver el total de dias y el desglose por ayudante, cliente, obra y ubicacion.
- Pulsar **Limpiar filtros de dias** para volver a ver todos los fichajes.

Los dias se calculan a partir de los fichajes, no de las compras ni de los importes pagados. Se incluyen los fines de semana registrados. Una misma fecha cuenta una vez por ayudante: dos ayudantes trabajando el mismo dia suman dos dias de trabajo. Si un ayudante tiene varios fichajes en una misma faena y fecha, ese dia no se duplica. Si trabaja en varias faenas el mismo dia, figura en cada faena, pero solo una vez en el total. Los filtros de compras y los del resumen de dias son independientes.

### Filtros del listado general de fichajes

En **Ayudantes -> Listado general de fichajes** estan disponibles los mismos filtros por tipo de trabajo, cliente, ayudante, obra y fechas. Ademas, puedes filtrar por estado de pago. El listado muestra el numero de fichajes visibles y el total de dias trabajados de esos registros, con el mismo criterio de recuento anterior.

El selector de ayudante se coordina con los botones de ayudantes de la parte superior, y el estado de pago con los botones Pagado, Parcial, Pendiente y Total jornadas. **Limpiar filtros de fichajes** restablece todos los filtros del listado. Estos filtros no cambian el resumen de Gastos registrados. Los botones Modificar, Validar y Borrar siguen disponibles en las filas filtradas.

### Organizacion de Ayudantes

La pantalla se divide en apartados: **Fichajes**, **Pagos**, **Liquidaciones**, **Gastos y dias**, **Faenas**, **Presupuestos**, **Ayudantes** y **Configuracion**. Solo se muestran las secciones del apartado seleccionado; cambiar de apartado conserva los filtros y los formularios sin guardar mientras no recargues la pagina.

Los botones superiores permiten seleccionar el ayudante activo, cuyo nombre se muestra debajo de los apartados. En **Ayudantes** aparecen tambien las acciones para modificar y borrar ayudantes. En **Configuracion** se gestionan los usuarios y las contrasenas. Los contadores de estado de pago abren **Fichajes** con el filtro correspondiente.

En el movil, los formularios y los botones se ajustan al ancho de la pantalla. Las tablas se desplazan horizontalmente dentro de su propio recuadro, sin desplazar toda la pagina. Tambien puedes enfocar una tabla con el teclado y desplazarla con las flechas. El formulario de edicion de fichajes solo aparece al seleccionar un registro; la pantalla se desplaza hasta el formulario. **Cancelar edicion** descarta ese borrador sin modificar el fichaje.

Esta reorganizacion no modifica los datos ni las reglas de pago y liquidacion.

### Catalogo de clientes y obras de la app

Solo el administrador puede crear clientes y obras nuevos. En **Ayudantes -> Faenas** se dan de alta las faenas con cliente y obra; en **Mi control** se crean las reparaciones, y en **Presupuestos** se crean los presupuestos. Los formularios administrativos sugieren clientes existentes y las obras de cada cliente. Escribir un nombre nuevo sigue estando permitido al administrador. Las sugerencias corrigen diferencias de mayusculas, espacios y acentos al salir del campo.

El ayudante selecciona el tipo de trabajo, un cliente y una obra del catalogo. La ubicacion y la poblacion se rellenan automaticamente. Si falta una obra, debe solicitar su alta al administrador. Un presupuesto se identifica por su numero (o por su identificador si es provisional). La opcion Todos los tipos permite buscar en todos los tipos; al seleccionar una obra, el dia se guarda con su tipo real y su vinculo.

Despues de que el administrador cree una obra, el ayudante puede pulsar **Actualizar clientes y obras** para verla sin salir de la pantalla.

Las jornadas nuevas se vinculan a la faena, reparacion o presupuesto existente, sin crear otra obra por cada fecha. El servidor impide que un ayudante introduzca nombres nuevos, incluso desde una version antigua de la app. Los fichajes antiguos no se renombran automaticamente: para editarlos, se selecciona la obra correcta del catalogo; el administrador puede seguir revisando los casos antiguos.

Esta mejora no modifica importes, pagos ni liquidaciones.

### Pagos diarios y liquidaciones

En **Pagos** aparece una fila por ayudante y fecha, con todas las obras realizadas ese dia. Se incluyen sabados y domingos; varios fichajes del mismo ayudante en una fecha no generan varias jornadas. El estado se calcula a partir del importe y lo realmente pagado; los pagos parciales reducen el pendiente.

Se paga cada dia trabajado contigo, independientemente de la obra, aunque se abonen todos los dias juntos al final de la semana. **El pago diario es la referencia**: si ese dia tiene ademas gastos asociados a obras, estos se conservan como desglose y no se suman como otro pago al ayudante ni generan una alerta de duplicado.

Los pagos ya registrados no se renumeran, suman ni borran. Solo si hay varios pagos diarios en una misma fecha aparece **Revision necesaria**, se muestran sus importes y el dia queda bloqueado para evitar sobrescribirlos. Esos dias quedan excluidos de los totales automaticos, que no representan el periodo completo hasta revisar los casos. Si no existe pago diario, se mantiene la consulta historica de Gastos: se modifica en **Gastos y dias**, sin crear otro pago desde Pagos.

Las liquidaciones cuentan las fechas distintas confirmadas por el ayudante, tambien en fin de semana. Las liquidaciones antiguas conservan sus importes pagados, pero sus dias, total y pendiente se recalculan con este criterio. Las liquidaciones y los pagos diarios siguen siendo registros independientes: no deben usarse para registrar dos veces el mismo pago.

### Trabajo terminado y cobro pendiente

En **Alarmas**, los trabajos propios registrados (incluidas reparaciones), las faenas y los presupuestos aceptados tienen recordatorios separados para **Trabajos por realizar** y **Cobros pendientes**, tambien cuando la fecha ya ha pasado. **Marcar terminado** solo cambia la ejecucion: no modifica el importe ni el cobro. Desde el historial archivado se puede **Reabrir trabajo**. Un trabajo cobrado sigue pendiente de ejecucion hasta marcarlo terminado.

**Revisar cobro en Mi control** abre la obra concreta, sin marcarla automaticamente como cobrada. **Ver todos los trabajos** elimina ese enfoque. Mi control muestra el cobro y la ejecucion por separado y permite terminar o reabrir la obra.

Los pendientes de faenas se calculan con su precio registrado menos sus pagos sincronizados (`pagos_faenas`). Para presupuestos aceptados se usa el importe final menos los cobros de su numero (`pagos_ingresos`). Un pago parcial reduce el aviso; un pago completo lo elimina, sin terminar la obra. Las obras de importe cero no generan un aviso monetario. No se convierten fechas antiguas en jornadas ni se inventan cobros.

Los presupuestos en estado Presupuesto o Rechazado no generan estos recordatorios. Los antiguos Completado se respetan como terminados y cobrados; su importe de cobros registrado no se modifica. Si desde la app se cambia el estado comercial de un presupuesto, su ejecucion previa se conserva. Completar una nota mantiene su telefono y observaciones.

### Panel resumen al entrar

El menu principal muestra al administrador un **Resumen de gestion** con accesos a trabajos por terminar, cobros pendientes, pagos de ayudantes y agenda. **Actualizar resumen** consulta de nuevo los registros; si falla, se muestra el error y se ocultan las cifras anteriores.

Los cobros pendientes utilizan los mismos datos que Alarmas y Mi control; terminar una obra no la cobra. Los casos sin importe se indican aparte. Los pagos de ayudantes cuentan fechas distintas por persona hasta hoy, incluidos fines de semana, y usan el pago diario como referencia. Solo se suma el pendiente de importes registrados: los dias sin registro y los casos para revisar se cuentan aparte, sin inventar deuda ni sumar las liquidaciones.

La agenda muestra notas y citas pendientes vencidas y las previstas hasta dentro de siete dias, ambos extremos incluidos. Se muestran los primeros ocho avisos, pero el contador incluye todos. Los enlaces de trabajos, cobros y avisos abren Alarmas con el tipo seleccionado. El panel no modifica registros ni genera pagos.

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
