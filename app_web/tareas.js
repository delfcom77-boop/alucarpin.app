'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const token = localStorage.getItem('alucarpin_token');
  if (!token) { location.replace('/app/login.html'); return; }
  const campos = ['titulo', 'tipo', 'cliente', 'obra', 'notas', 'fecha_prevista', 'prioridad', 'estado'];
  let tareas = [];
  let trabajos = [];
  let editada = null;
  let solicitud = null;
  let ocupado = false;
  const normalizar = texto => texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');
  const hoy = () => {
    const fecha = new Date();
    return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, '0')}-${String(fecha.getDate()).padStart(2, '0')}`;
  };
  const fechaTexto = texto => texto ? texto.split('-').reverse().join('/') : 'Sin fecha';
  const selloTexto = texto => texto ? new Date(texto).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '—';
  function mensaje(texto, error = false, editor = false) {
    const destino = $(editor ? 'mensaje-editor' : 'mensaje');
    destino.textContent = texto;
    destino.className = error ? 'error' : 'exito';
  }
  async function api(url, opciones = {}) {
    const respuesta = await fetch(url, {
      ...opciones, cache: 'no-store',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    });
    if (respuesta.status === 401) {
      location.assign('/app/login.html');
      throw new Error('La sesión ha caducado. Vuelve a entrar.');
    }
    if (!respuesta.ok) {
      const datos = await respuesta.json().catch(() => null);
      const detalle = datos?.detail;
      throw new Error(typeof detalle === 'string' ? detalle : `No se pudo completar la operación (HTTP ${respuesta.status}). Revisa los datos o actualiza el listado.`);
    }
    return respuesta.json();
  }
  function bloquear(valor) {
    ocupado = valor;
    document.querySelectorAll('button, #editor input, #editor select, #editor textarea').forEach(elemento => { elemento.disabled = valor; });
  }
  function renderizar() {
    const consulta = normalizar($('buscar').value.trim());
    const filtro = $('filtro').value;
    const tipo = $('filtro-tipo').value;
    const prioridad = $('filtro-prioridad').value;
    const dia = hoy();
    const visibles = tareas.filter(t => {
      if (filtro === 'Pendientes' && t.estado === 'Hecha') return false;
      if (filtro === 'Hechas' && t.estado !== 'Hecha') return false;
      if (filtro === 'Hoy' && (t.estado === 'Hecha' || t.fecha_prevista !== dia)) return false;
      if (filtro === 'Atrasadas' && (t.estado === 'Hecha' || !t.fecha_prevista || t.fecha_prevista >= dia)) return false;
      return (!tipo || t.tipo === tipo) && (!prioridad || t.prioridad === prioridad)
        && (!consulta || normalizar([t.titulo, t.cliente, t.obra, t.notas].join(' ')).includes(consulta));
    });
    $('contador').textContent = `${visibles.length} de ${tareas.length} tareas · ${tareas.filter(t => t.estado === 'Pendiente').length} pendientes`;
    $('lista').replaceChildren();
    for (const tarea of visibles) {
      const fila = document.createElement('tr');
      const atrasada = tarea.estado !== 'Hecha' && tarea.fecha_prevista && tarea.fecha_prevista < dia;
      fila.className = tarea.estado === 'Hecha' ? 'hecha' : atrasada ? 'atrasada' : 'pendiente';
      for (const texto of [
        tarea.estado === 'Hecha' ? 'Hecha' : atrasada ? 'Atrasada' : 'Pendiente',
        tarea.titulo, tarea.tipo, [tarea.cliente, tarea.obra].filter(Boolean).join(' · '),
        tarea.prioridad, fechaTexto(tarea.fecha_prevista), selloTexto(tarea.creado_en), selloTexto(tarea.hecha_en)
      ]) {
        const celda = document.createElement('td');
        celda.textContent = texto;
        celda.title = texto;
        fila.append(celda);
      }
      const acciones = document.createElement('td');
      acciones.className = 'acciones-fila';
      for (const [texto, accion] of [['Ver / editar', () => abrir(tarea)], [tarea.estado === 'Hecha' ? 'Reabrir' : 'Hecha', () => cambiarEstado(tarea)]]) {
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.textContent = texto;
        boton.disabled = ocupado;
        boton.addEventListener('click', accion);
        acciones.append(boton);
      }
      fila.append(acciones);
      $('lista').append(fila);
    }
    if (!visibles.length) {
      const fila = $('lista').insertRow();
      const celda = fila.insertCell();
      celda.colSpan = 9;
      celda.textContent = 'No hay tareas con estos filtros.';
    }
  }
  function abrir(tarea = null) {
    editada = tarea;
    solicitud = tarea ? null : crypto.randomUUID();
    $('formulario').reset();
    for (const campo of campos) {
      $(campo).value = tarea ? tarea[campo] : ({ tipo: 'Otro', prioridad: 'Normal', estado: 'Pendiente' }[campo] || '');
    }
    $('titulo-editor').textContent = tarea ? 'Detalle de tarea' : 'Nueva tarea';
    $('fechas').textContent = tarea ? `Creada: ${selloTexto(tarea.creado_en)} · Hecha: ${selloTexto(tarea.hecha_en)}` : 'La fecha de creación y de finalización se guardan automáticamente.';
    mensaje('', false, true);
    $('editor').showModal();
    $('titulo').focus();
  }
  async function cargar() {
    tareas = await api('/tareas');
    renderizar();
  }
  async function cambiarEstado(tarea) {
    if (ocupado) return;
    if (tarea.estado === 'Hecha' && !confirm('¿Volver a pendiente? Se quitará la fecha de finalización actual.')) return;
    bloquear(true);
    try {
      const datos = Object.fromEntries(campos.map(c => [c, tarea[c]]));
      datos.estado = tarea.estado === 'Hecha' ? 'Pendiente' : 'Hecha';
      await api(`/tareas/${tarea.id}`, { method: 'PUT', body: JSON.stringify({ ...datos, version: tarea.version }) });
      await cargar();
      mensaje(datos.estado === 'Hecha' ? 'Tarea hecha. Día y hora registrados automáticamente.' : 'Tarea reabierta.');
    } catch (error) { mensaje(error.message, true); }
    finally { bloquear(false); }
  }
  $('formulario').addEventListener('submit', async evento => {
    evento.preventDefault();
    if (ocupado) return;
    const datos = Object.fromEntries(campos.map(c => [c, $(c).value]));
    if (!datos.titulo.trim()) { mensaje('Escribe lo que tienes que hacer.', true, true); return; }
    if (editada?.estado === 'Hecha' && datos.estado === 'Pendiente' && !confirm('¿Reabrir y quitar la fecha de finalización actual?')) return;
    bloquear(true);
    let guardada = false;
    try {
      await api(editada ? `/tareas/${editada.id}` : '/tareas', {
        method: editada ? 'PUT' : 'POST',
        body: JSON.stringify({ ...datos, ...(editada ? { version: editada.version } : { id: solicitud }) })
      });
      guardada = true;
      $('editor').close();
      await cargar();
      mensaje('Tarea guardada en la app. El programa la recibirá al sincronizar Tareas.');
    } catch (error) {
      mensaje(guardada ? `Tarea guardada, pero no se pudo actualizar el listado: ${error.message}` : error.message, true, !guardada);
    } finally { bloquear(false); }
  });
  $('cancelar').onclick = () => $('editor').close();
  $('editor').addEventListener('cancel', evento => { if (ocupado) evento.preventDefault(); });
  $('nueva').onclick = () => abrir();
  $('actualizar').onclick = async () => {
    bloquear(true);
    try { await cargar(); mensaje('Listado actualizado.'); }
    catch (error) { mensaje(error.message, true); }
    finally { bloquear(false); }
  };
  for (const id of ['filtro', 'filtro-tipo', 'filtro-prioridad', 'buscar']) $(id).addEventListener('input', renderizar);
  $('trabajo').addEventListener('change', () => {
    if ($('trabajo').value === '') return;
    const trabajo = trabajos[Number($('trabajo').value)];
    $('cliente').value = trabajo.cliente || '';
    $('obra').value = trabajo.obra || (trabajo.num_presupuesto ? `Presupuesto ${trabajo.num_presupuesto}` : '');
  });
  cargar().catch(error => {
    $('lista').replaceChildren();
    mensaje(error.message, true);
  });
  api('/trabajos').then(datos => {
    trabajos = datos;
    trabajos.forEach((trabajo, indice) => {
      const opcion = document.createElement('option');
      opcion.value = indice;
      opcion.textContent = [trabajo.tipo, trabajo.cliente, trabajo.obra || trabajo.num_presupuesto].filter(Boolean).join(' · ');
      $('trabajo').append(opcion);
    });
  }).catch(error => { $('mensaje-catalogo').textContent = `No se pudo cargar el catálogo: ${error.message} Puedes escribir cliente y obra.`; });
  setInterval(renderizar, 60000);
})();
