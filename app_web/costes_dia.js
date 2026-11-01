'use strict';
(() => {
  const zona = document.querySelector('#costes-dia');
  if (!zona) return;
  const fecha = zona.querySelector('#costes-fecha');
  const lista = zona.querySelector('tbody');
  const mensaje = zona.querySelector('[role="status"]');
  const resumen = zona.querySelector('#costes-resumen');
  const lugares = zona.querySelector('#costes-actividades');
  const actualizar = zona.querySelector('button');
  const token = localStorage.getItem('alucarpin_token');
  let consulta = 0;
  const euros = n => n == null ? 'Revisar' : Number(n).toLocaleString('es-ES', {style: 'currency', currency: 'EUR'});
  const clave = d => `${d.destino}:${d.id || ''}`;
  async function api(url, opciones = {}) {
    const r = await fetch(url, {...opciones, cache: 'no-store', signal: AbortSignal.timeout(30000),
      headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'}});
    const datos = await r.json();
    if (!r.ok) throw new Error(typeof datos.detail === 'string' ? datos.detail : `Error HTTP ${r.status}. Actualiza y revisa el registro.`);
    return datos;
  }
  async function cargar() {
    const id = ++consulta;
    actualizar.disabled = true;
    mensaje.textContent = 'Consultando gastos del día…';
    lista.replaceChildren();
    resumen.textContent = '';
    lugares.textContent = '';
    try {
      const [datos, dias] = await Promise.all([api(`/costes-ayudantes?fecha=${encodeURIComponent(fecha.value)}`), api('/mis-dias')]);
      if (id !== consulta) return;
      lugares.textContent = 'Mi actividad: ' + (dias.filter(d => d.fecha === fecha.value).map(d => `${d.cliente} · ${d.obra}`).join(' | ') || 'Sin actividad propia registrada. Puedes imputar el gasto aunque tú no hayas estado en esa obra.');
      let gasto = 0, pagado = 0, pendiente = 0, revision = 0, estimadas = 0;
      for (const coste of datos.costes) {
        if (coste.revision) revision++;
        else { gasto += coste.importe; pagado += coste.importe_pagado; pendiente += coste.pendiente; estimadas += !coste.registrado; }
        const fila = document.createElement('tr');
        const textos = [coste.proveedor, coste.lugares.join(' | '), euros(coste.importe),
          coste.revision ? 'Revisar pagos duplicados' : `${coste.estado_pago} · Pagado ${euros(coste.importe_pagado)} · Pendiente ${euros(coste.pendiente)}${!coste.registrado ? ' · Estimación; sin pago registrado' : ''}`];
        for (const t of textos) { const td = document.createElement('td'); td.textContent = t; fila.append(td); }
        const acciones = document.createElement('td');
        const select = document.createElement('select');
        select.setAttribute('aria-label', `Destino del gasto de ${coste.proveedor}`);
        select.add(new Option('Sin imputar · elegir destino', ''));
        for (const destino of datos.destinos) select.add(new Option(destino.nombre, clave(destino)));
        if (coste.imputacion) {
          const i = coste.imputacion;
          select.value = clave({destino: i.destino, id: i.faena_id || i.presupuesto_id || i.trabajo_id});
        }
        const guardar = document.createElement('button');
        guardar.type = 'button';
        guardar.textContent = 'Guardar destino';
        guardar.onclick = async () => {
          const destino = datos.destinos.find(d => clave(d) === select.value);
          if (!destino) { mensaje.textContent = 'Selecciona Alucarpin o una obra para imputar el gasto.'; return; }
          guardar.disabled = true;
          select.disabled = true;
          let confirmado = false;
          try {
            await api(`/costes-ayudantes/${coste.ayudante_id}/${fecha.value}`, {
              method: 'PUT', body: JSON.stringify({destino: destino.destino, id: destino.id, version: coste.version}),
            });
            confirmado = true;
            if (await cargar()) mensaje.textContent = 'Destino guardado. Es el mismo gasto del día: no se ha creado otro gasto ni cambiado el pago.';
            else mensaje.textContent = `Destino guardado, pero no se pudo actualizar: ${mensaje.textContent}`;
          } catch (error) {
            mensaje.textContent = `${confirmado ? 'Destino guardado, pero no se pudo actualizar: ' : 'Destino no confirmado; actualiza y revisa antes de reintentar: '}${error.message}`;
          } finally { guardar.disabled = false; select.disabled = false; }
        };
        if (coste.revision) { guardar.disabled = true; select.disabled = true; }
        acciones.append(select, guardar);
        fila.append(acciones);
        lista.append(fila);
      }
      resumen.textContent = `Gasto de ayudantes: ${euros(gasto)} · Pagado: ${euros(pagado)} · Pendiente: ${euros(pendiente)} · Resultado sin ingresos: ${euros(-gasto)}.${estimadas ? ` Incluye ${estimadas} jornada(s) estimada(s).` : ''}${revision ? ` ${revision} jornada(s) para revisar, excluidas; total incompleto.` : ''}`;
      mensaje.textContent = datos.costes.length ? 'Un gasto por ayudante y fecha. Los sitios no multiplican el gasto.' : 'No hay jornadas de ayudantes registradas en esta fecha.';
      return true;
    } catch (error) {
      if (id === consulta) mensaje.textContent = error.message;
      return false;
    } finally { if (id === consulta) actualizar.disabled = false; }
  }
  const hoy = new Date();
  hoy.setMinutes(hoy.getMinutes() - hoy.getTimezoneOffset());
  const fechaEnlace = new URLSearchParams(location.search).get('costes_fecha');
  fecha.value = /^\d{4}-\d{2}-\d{2}$/.test(fechaEnlace || '') ? fechaEnlace : hoy.toISOString().slice(0, 10);
  fecha.onchange = cargar;
  actualizar.onclick = cargar;
  cargar();
})();
