'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const token = localStorage.getItem('alucarpin_token');
  if (!token) { location.replace('/app/login.html'); return; }
  let usuario, materiales = [], editado, seleccionado, tipoMovimiento, siguiente;
  let ocupado = false, pendiente = null, clavePendiente, listo = false;
  let carpetas = [], carpetaActual = null;
  let gestionCarpeta = null;
  const nombreCarpeta = id => carpetas.find(c => c.id === id)?.nombre || 'Sin carpeta';
  const nombreMaterial = m => m.carpeta_id ? `${nombreCarpeta(m.carpeta_id)} / ${m.nombre}` : m.nombre;
  const normalizar = texto => texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');
  const numero = texto => Number(texto).toLocaleString('es-ES', { maximumFractionDigits: 3 });
  const fecha = texto => new Date(texto).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' });
  function mensaje(texto, error = false) {
    $('mensaje').textContent = texto;
    $('mensaje').className = error ? 'error' : '';
  }
  async function api(url, opciones = {}) {
    const respuesta = await fetch(url, {
      ...opciones, cache: 'no-store',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    });
    if (!respuesta.ok) {
      const datos = await respuesta.json().catch(() => null);
      const detalle = datos?.detail;
      const error = new Error(typeof detalle === 'string' ? detalle : `No se pudo completar la operación (HTTP ${respuesta.status}). Revisa las cantidades y actualiza el listado.`);
      error.estado = respuesta.status;
      if (respuesta.status === 401) location.assign('/app/login.html');
      throw error;
    }
    return respuesta.json();
  }
  function bloquear(valor) {
    ocupado = valor;
    document.querySelectorAll('button, dialog input, dialog select, #historial-material').forEach(e => { e.disabled = valor; });
    if (!valor && editado) $('unidad').disabled = true;
    $('pendiente').hidden = !pendiente;
  }
  function guardarPendiente(valor) {
    // Persistir antes de enviar permite reintentar tras una respuesta perdida.
    if (valor) localStorage.setItem(clavePendiente, JSON.stringify(valor));
    else localStorage.removeItem(clavePendiente);
    pendiente = valor;
    $('pendiente').hidden = !valor;
  }
  function celda(fila, texto) {
    const td = document.createElement('td');
    td.textContent = texto;
    td.title = texto;
    fila.append(td);
    return td;
  }
  function pintar() {
    const consulta = normalizar($('buscar').value.trim()), filtro = $('filtro').value;
    $('carpetas').replaceChildren();
    const grupos = [...carpetas];
    if (materiales.some(m => !m.carpeta_id)) grupos.push({ id: '', nombre: 'Sin carpeta · materiales anteriores' });
    if (!grupos.some(c => c.id === carpetaActual)) carpetaActual = grupos[0]?.id ?? null;
    for (const carpeta of grupos) {
      const variantes = materiales.filter(m => (m.carpeta_id || '') === carpeta.id);
      const coincidencias = variantes.filter(m =>
        (filtro === 'inactivos' ? !m.activo : m.activo)
        && (filtro !== 'reponer' || m.situacion !== 'Hay')
        && (filtro !== 'agotados' || m.situacion === 'Agotado')
        && normalizar(nombreMaterial(m)).includes(consulta));
      const boton = document.createElement('button');
      boton.textContent = `${carpeta.nombre} · ${coincidencias.length} variantes`;
      boton.id = 'pestana-' + (carpeta.id || 'sin-carpeta');
      boton.setAttribute('role', 'tab');
      boton.setAttribute('aria-selected', String(carpetaActual === carpeta.id));
      boton.setAttribute('aria-controls', 'panel-carpeta');
      boton.tabIndex = carpetaActual === carpeta.id ? 0 : -1;
      boton.disabled = ocupado;
      boton.onclick = () => {
        carpetaActual = carpeta.id; $('historial-material').value = ''; pintar();
        $(boton.id)?.focus(); refrescarHistorial();
      };
      boton.onkeydown = evento => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(evento.key)) return;
        evento.preventDefault();
        const indice = grupos.findIndex(c => c.id === carpeta.id);
        const siguiente = evento.key === 'Home' ? 0 : evento.key === 'End' ? grupos.length - 1
          : (indice + (evento.key === 'ArrowRight' ? 1 : -1) + grupos.length) % grupos.length;
        $('pestana-' + (grupos[siguiente].id || 'sin-carpeta')).click();
      };
      $('carpetas').append(boton);
    }
    if (!grupos.length) $('carpetas').textContent = 'Todavía no hay carpetas. Pulsa «Nuevo material» para crear la primera.';
    $('titulo-carpeta').textContent = carpetaActual === null ? 'Selecciona una carpeta' : nombreCarpeta(carpetaActual);
    $('anadir-variante').hidden = !carpetaActual;
    $('renombrar-carpeta').hidden = !carpetaActual || usuario.rol !== 'administrador';
    $('borrar-carpeta').hidden = !carpetaActual || usuario.rol !== 'administrador';
    if (carpetaActual !== null) $('panel-carpeta').setAttribute('aria-labelledby', 'pestana-' + (carpetaActual || 'sin-carpeta'));
    else $('panel-carpeta').setAttribute('aria-labelledby', 'titulo-carpeta');
    const visibles = materiales.filter(m =>
      carpetaActual !== null && (m.carpeta_id || '') === carpetaActual
      && (filtro === 'inactivos' ? !m.activo : m.activo)
      && (filtro !== 'reponer' || m.situacion !== 'Hay')
      && (filtro !== 'agotados' || m.situacion === 'Agotado')
      && normalizar(nombreMaterial(m)).includes(consulta)
    );
    $('materiales').replaceChildren();
    $('contador').textContent = `${visibles.length} materiales · ${materiales.filter(m => m.activo && m.situacion !== 'Hay').length} por reponer o agotados`;
    for (const material of visibles) {
      const fila = document.createElement('tr');
      fila.className = !material.activo ? 'inactivo' : material.situacion === 'Agotado' ? 'agotado' : material.situacion === 'Hay' ? 'hay' : 'reponer';
      for (const texto of [material.nombre, numero(material.cantidad), material.unidad,
        material.minimo === null ? '—' : numero(material.minimo), material.activo ? material.situacion : 'Desactivado']) celda(fila, texto);
      const acciones = celda(fila, '');
      acciones.className = 'acciones-fila';
      const botones = material.activo ? [
        ['Sacar', () => abrirMovimiento(material, 'salida')],
        ['Añadir', () => abrirMovimiento(material, 'entrada')],
        ['Corregir cantidad', () => abrirMovimiento(material, 'recuento')]
      ] : [];
      if (usuario.rol === 'administrador') botones.push(['Editar', () => abrirMaterial(material)]);
      for (const [texto, accion] of botones) {
        const boton = document.createElement('button');
        boton.textContent = texto;
        boton.disabled = ocupado;
        boton.onclick = accion;
        acciones.append(boton);
      }
      $('materiales').append(fila);
    }
    if (!visibles.length) {
      const fila = $('materiales').insertRow();
      const td = fila.insertCell();
      td.colSpan = 6;
      td.textContent = carpetaActual === null ? 'Abre una carpeta para ver sus variantes.' : 'No hay variantes con este filtro. Usa «Añadir variante» dentro de una carpeta.';
    }
  }
  async function cargarMateriales() {
    carpetas = await api('/almacen/carpetas');
    materiales = await api('/almacen/materiales');
    const elegido = $('historial-material').value;
    $('historial-material').replaceChildren(new Option('Todos los materiales', ''));
    materiales.forEach(m => $('historial-material').add(new Option(nombreMaterial(m) + (m.activo ? '' : ' (desactivado)'), m.id)));
    $('historial-material').value = elegido;
    pintar();
  }
  async function cargarHistorial(ampliar = false) {
    const parametros = new URLSearchParams({ limite: '50' });
    if ($('historial-material').value) parametros.set('material_id', $('historial-material').value);
    else if (carpetaActual) parametros.set('carpeta_id', carpetaActual);
    if (ampliar && siguiente) parametros.set('antes', siguiente);
    const datos = await api('/almacen/movimientos?' + parametros);
    if (!ampliar) $('movimientos').replaceChildren();
    for (const m of datos.movimientos) {
      const fila = document.createElement('tr');
      let texto;
      if (m.tipo === 'recuento') texto = `Recuento de material: ${m.nombre}, de ${numero(m.stock_anterior)} a ${numero(m.stock_resultante)} ${m.unidad}`;
      else texto = `${{ salida: 'Salida de material', entrada: 'Entrada de material', inicial: 'Stock inicial' }[m.tipo]}: ${numero(m.cantidad)} ${m.unidad} de ${m.nombre}`;
      for (const valor of [fecha(m.creado_en), texto, `${numero(m.stock_resultante)} ${m.unidad}`, m.motivo || '—']) celda(fila, valor);
      $('movimientos').append(fila);
    }
    siguiente = datos.siguiente;
    $('mas').hidden = !siguiente;
    if (!$('movimientos').children.length) {
      const fila = $('movimientos').insertRow();
      const td = fila.insertCell();
      td.colSpan = 4;
      td.textContent = 'Todavía no hay movimientos.';
    }
  }
  async function actualizar() {
    await cargarMateriales();
    await cargarHistorial();
  }
  function disponible() {
    if (pendiente) {
      mensaje('Primero reintenta la operación pendiente para evitar duplicados.', true);
      return false;
    }
    return !ocupado;
  }
  function abrirMaterial(material = null) {
    if (!disponible()) return;
    editado = material;
    $('form-material').reset();
    $('titulo-editor').textContent = material ? 'Editar variante' : 'Añadir variante';
    $('carpeta-variante').replaceChildren();
    if (material && !material.carpeta_id) $('carpeta-variante').add(new Option('Sin carpeta', ''));
    carpetas.forEach(c => $('carpeta-variante').add(new Option(c.nombre, c.id)));
    $('carpeta-variante').value = material ? material.carpeta_id || '' : carpetaActual;
    $('carpeta-variante').required = !material;
    $('nombre').value = material?.nombre || '';
    $('unidad').value = material?.unidad || 'unidades';
    $('unidad').disabled = Boolean(material);
    $('minimo').value = material?.minimo ?? '';
    $('activo').value = material?.activo === false ? '0' : '1';
    $('campo-activo').hidden = !material;
    $('campo-inicial').hidden = Boolean(material);
    $('cantidad-inicial').required = !material;
    $('error-material').textContent = '';
    $('editor').showModal();
  }
  function abrirMovimiento(material, tipo) {
    if (!disponible()) return;
    seleccionado = material;
    tipoMovimiento = tipo;
    $('form-movimiento').reset();
    const texto = { salida: 'Sacar material', entrada: 'Añadir material', recuento: 'Corregir cantidad' }[tipo];
    $('titulo-operacion').textContent = texto;
    $('confirmar-movimiento').textContent = texto;
    $('detalle-material').textContent = `${nombreMaterial(material)} · Hay ${numero(material.cantidad)} ${material.unidad}`;
    $('campo-motivo').hidden = tipo !== 'recuento';
    $('motivo').required = tipo === 'recuento';
    $('cantidad').min = tipo === 'recuento' ? '0' : '0.001';
    $('ayuda-movimiento').textContent = tipo === 'recuento'
      ? 'Escribe la cantidad real que has contado, no la diferencia. Se guardará el motivo.'
      : tipo === 'salida' ? 'La cantidad se descontará del stock. No hace falta indicar obra ni destino.' : 'La cantidad se sumará al stock.';
    $('error-movimiento').textContent = '';
    $('operacion').showModal();
    $('cantidad').focus();
  }
  async function enviarPendiente() {
    if (!pendiente || ocupado) return;
    bloquear(true);
    let confirmada = false;
    const borrando = pendiente.metodo === 'DELETE';
    try {
      const resultado = await api(pendiente.url, { method: pendiente.metodo, body: JSON.stringify(pendiente.datos) });
      if (pendiente.url === '/almacen/carpetas') carpetaActual = resultado.id;
      confirmada = true;
      guardarPendiente(null);
      $('editor').close();
      $('operacion').close();
      $('editor-carpeta').close();
      $('gestionar-carpeta').close();
      await actualizar();
      mensaje(borrando ? 'Carpeta eliminada definitivamente con sus variantes, stock e historial.' : 'Operación guardada. Stock actualizado.');
    } catch (error) {
      // Un rechazo de validacion/conflicto confirma que esta solicitud no se aplico.
      if ([403, 404, 409, 422].includes(error.estado)) guardarPendiente(null);
      const texto = confirmada ? `Operación guardada, pero no se pudo refrescar el listado: ${error.message}` : error.message;
      mensaje(texto, true);
      $('error-material').textContent = texto;
      $('error-movimiento').textContent = texto;
      $('error-carpeta').textContent = texto;
      $('error-gestionar').textContent = texto;
    } finally { bloquear(false); }
  }
  function preparar(url, metodo, datos) {
    if (!disponible()) return;
    try {
      guardarPendiente({ url, metodo, datos });
    } catch (error) {
      mensaje('El navegador no permite guardar la referencia de la operación. No se ha enviado nada. Revisa el almacenamiento del navegador.', true);
      return;
    }
    enviarPendiente();
  }
  $('form-material').onsubmit = evento => {
    evento.preventDefault();
    const datos = {
      nombre: $('nombre').value.trim(), unidad: $('unidad').value,
      minimo: $('minimo').value === '' ? null : $('minimo').value,
      carpeta_id: $('carpeta-variante').value || null
    };
    if (!datos.nombre) { $('error-material').textContent = 'Escribe el nombre del material.'; return; }
    if (editado) {
      datos.version = editado.version;
      datos.activo = $('activo').value === '1';
      preparar('/almacen/materiales/' + editado.id, 'PUT', datos);
    } else {
      datos.id = crypto.randomUUID();
      datos.cantidad = $('cantidad-inicial').value;
      preparar('/almacen/materiales', 'POST', datos);
    }
  };
  $('form-movimiento').onsubmit = evento => {
    evento.preventDefault();
    const datos = { id: crypto.randomUUID(), tipo: tipoMovimiento, cantidad: $('cantidad').value };
    if (tipoMovimiento === 'recuento') {
      datos.version = seleccionado.version;
      datos.motivo = $('motivo').value.trim();
      if (!datos.motivo) { $('error-movimiento').textContent = 'Escribe el motivo del recuento.'; return; }
    }
    preparar(`/almacen/materiales/${seleccionado.id}/movimientos`, 'POST', datos);
  };
  $('nuevo').onclick = () => {
    if (!disponible()) return;
    $('form-carpeta').reset();
    $('error-carpeta').textContent = '';
    $('editor-carpeta').showModal();
  };
  $('form-carpeta').onsubmit = evento => {
    evento.preventDefault();
    const nombre = $('nombre-carpeta').value.trim();
    if (!nombre) { $('error-carpeta').textContent = 'Escribe el nombre de la carpeta.'; return; }
    preparar('/almacen/carpetas', 'POST', { id: crypto.randomUUID(), nombre });
  };
  $('anadir-variante').onclick = () => abrirMaterial();
  function gestionarCarpeta(borrar) {
    if (!disponible() || !carpetaActual) return;
    gestionCarpeta = { ...carpetas.find(c => c.id === carpetaActual), borrar };
    $('titulo-gestionar').textContent = borrar ? 'Eliminar carpeta completa' : 'Cambiar nombre de carpeta';
    $('aviso-gestionar').textContent = borrar
      ? `Se eliminará definitivamente «${gestionCarpeta.nombre}», con TODAS sus variantes, cantidades e historial, aunque tenga stock. No se puede deshacer. Escribe su nombre exacto para confirmar.`
      : `Nuevo nombre para «${gestionCarpeta.nombre}». Sus cantidades e historial no se modificarán.`;
    $('valor-gestionar').value = borrar ? '' : gestionCarpeta.nombre;
    $('confirmar-gestionar').textContent = borrar ? 'Eliminar definitivamente' : 'Guardar nombre';
    $('confirmar-gestionar').className = borrar ? 'peligro' : '';
    $('error-gestionar').textContent = '';
    $('gestionar-carpeta').showModal();
    $('valor-gestionar').focus();
  }
  $('renombrar-carpeta').onclick = () => gestionarCarpeta(false);
  $('borrar-carpeta').onclick = () => gestionarCarpeta(true);
  $('form-gestionar').onsubmit = evento => {
    evento.preventDefault();
    const valor = $('valor-gestionar').value;
    if (gestionCarpeta.borrar && valor !== gestionCarpeta.nombre) {
      $('error-gestionar').textContent = 'El nombre no coincide. Escribe el nombre exacto para borrar la carpeta.';
      return;
    }
    if (!valor.trim()) { $('error-gestionar').textContent = 'Escribe el nombre.'; return; }
    preparar('/almacen/carpetas/' + gestionCarpeta.id, gestionCarpeta.borrar ? 'DELETE' : 'PUT',
      gestionCarpeta.borrar ? { confirmar_nombre: valor } : { nombre: valor.trim(), nombre_anterior: gestionCarpeta.nombre });
  };
  async function refrescarHistorial() {
    try { await cargarHistorial(); }
    catch (error) { mensaje(error.message, true); }
  }
  $('reintentar').onclick = enviarPendiente;
  $('actualizar').onclick = async () => {
    if (!listo) { await iniciar(); return; }
    bloquear(true);
    try { await actualizar(); mensaje(pendiente ? 'Listado actualizado. Queda una operación pendiente de confirmar.' : 'Stock actualizado.'); }
    catch (error) { mensaje(error.message, true); }
    finally { bloquear(false); }
  };
  $('historial-material').onchange = async () => {
    bloquear(true);
    try { await cargarHistorial(); }
    catch (error) { mensaje(error.message, true); }
    finally { bloquear(false); }
  };
  $('mas').onclick = async () => {
    bloquear(true);
    try { await cargarHistorial(true); }
    catch (error) { mensaje(error.message, true); }
    finally { bloquear(false); }
  };
  $('buscar').oninput = pintar;
  $('filtro').onchange = pintar;
  document.querySelectorAll('[data-cerrar]').forEach(b => { b.onclick = () => $(b.dataset.cerrar).close(); });
  document.querySelectorAll('dialog').forEach(d => d.addEventListener('cancel', e => { if (ocupado) e.preventDefault(); }));
  async function iniciar() {
    bloquear(true);
    try {
      usuario = await api('/yo');
      if (!['administrador', 'ayudante'].includes(usuario.rol)) throw new Error('No tienes acceso al almacén.');
      $('volver').href = usuario.rol === 'administrador' ? '/app/inicio.html' : '/app/inicio_ayudante.html';
      $('filtro').querySelector('[value="inactivos"]').hidden = usuario.rol !== 'administrador';
      clavePendiente = 'alucarpin_almacen_pendiente_' + usuario.id;
      const guardada = localStorage.getItem(clavePendiente);
      if (guardada) {
        pendiente = JSON.parse(guardada);
        if (!(pendiente.url?.startsWith('/almacen/materiales') || pendiente.url?.startsWith('/almacen/carpetas')) || !['POST', 'PUT', 'DELETE'].includes(pendiente.metodo) || !pendiente.datos) {
          throw new Error('La referencia de operación pendiente no es válida. No se enviará automáticamente; requiere revisión.');
        }
      }
      await actualizar();
      listo = true;
      mensaje(pendiente ? 'Hay una operación pendiente de confirmar. Pulsa Reintentar.' : 'Stock actualizado.');
      bloquear(false);
    } catch (error) {
      mensaje(error.message, true);
      $('actualizar').disabled = false;
    }
  }
  iniciar();
})();
