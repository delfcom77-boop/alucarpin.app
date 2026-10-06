(() => {
  const panel = document.querySelector('#economia');
  const datos = document.querySelector('#economia-datos');
  const mensaje = document.querySelector('#economia-mensaje');
  const desde = document.querySelector('#economia-desde');
  const hasta = document.querySelector('#economia-hasta');
  const boton = document.querySelector('#economia-consultar');
  const mes = document.querySelector('#economia-mes');
  const euros = valor => Number(valor).toLocaleString('es-ES', {style: 'currency', currency: 'EUR'});
  const local = dia => `${dia.getFullYear()}-${String(dia.getMonth() + 1).padStart(2, '0')}-${String(dia.getDate()).padStart(2, '0')}`;
  function mesActual() {
    const hoy = new Date();
    desde.value = local(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
    hasta.value = local(new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0));
  }
  function texto(id, valor) { document.querySelector(`#${id}`).textContent = valor; }
  function lista(id, filas, propiedad) {
    const destino = document.querySelector(`#${id}`);
    destino.replaceChildren();
    for (const fila of filas.slice(0, 20)) {
      const item = document.createElement('li');
      item.textContent = `${fila.fecha || 'Sin fecha'} · ${fila[propiedad]} · ${fila.concepto} · ${euros(fila.pendiente)}${fila.estimado ? ' (estimado, sin registro)' : ''}`;
      destino.appendChild(item);
    }
    const nota = document.createElement('li');
    nota.textContent = !filas.length ? 'No hay pendientes.' : `${filas.length} registros. Se muestran los primeros 20, por fecha más antigua; el total incluye todos.`;
    destino.appendChild(nota);
  }
  async function cargar() {
    datos.hidden = true;
    mensaje.textContent = 'Consultando resumen económico…';
    mensaje.className = '';
    boton.disabled = true;
    mes.disabled = true;
    desde.disabled = true;
    hasta.disabled = true;
    try {
      if (!desde.value || !hasta.value || desde.value > hasta.value) {
        throw new Error('Introduce un rango de fechas válido.');
      }
      const respuesta = await fetch(`/resumen-economico?${new URLSearchParams({desde: desde.value, hasta: hasta.value})}`, {
        headers: {Authorization: `Bearer ${localStorage.getItem('alucarpin_token')}`},
        cache: 'no-store', signal: AbortSignal.timeout(30000),
      });
      if (!respuesta.ok) throw new Error(`No se pudo consultar el resumen (HTTP ${respuesta.status}).`);
      const resumen = await respuesta.json();
      const p = resumen.periodo;
      const a = resumen.acumulado;
      texto('economia-cobrado', euros(p.cobros_recibidos));
      texto('economia-gastos', euros(p.gastos_registrados));
      texto('economia-abonado', euros(p.abonado_gastos));
      texto('economia-pendiente-periodo', euros(p.pendiente_gastos));
      texto('economia-estimado', `${p.jornadas_estimadas} jornadas sin registro: ${euros(p.coste_estimado)} estimados, aparte del gasto registrado.`);
      texto('economia-cobros-pendientes', euros(a.cobros_pendientes));
      texto('economia-pagos-pendientes', euros(a.pagos_pendientes));
      texto('economia-pendientes-estimados', `${a.jornadas_estimadas} jornadas sin registro: ${euros(a.coste_estimado)} estimados aparte. Pendientes hasta ${resumen.fecha}, incluidos meses anteriores.`);
      texto('economia-revision', `${resumen.revision} jornadas con pagos duplicados, excluidas de importes; ${a.cobros_sin_importe} trabajos sin importe de cobro.`);
      lista('economia-lista-cobros', resumen.cobros, 'cliente');
      lista('economia-lista-pagos', resumen.pagos, 'proveedor');
      const avisos = document.querySelector('#economia-avisos');
      avisos.replaceChildren();
      for (const aviso of resumen.avisos) {
        const item = document.createElement('li');
        item.textContent = aviso;
        avisos.appendChild(item);
      }
      texto('economia-actualizado', `Fuente: app central. Consultado a las ${new Date().toLocaleTimeString('es-ES')}.`);
      mensaje.textContent = resumen.avisos.length ? 'Resumen con datos que requieren revisión; consulta los avisos.' : '';
      datos.hidden = false;
    } catch (error) {
      mensaje.className = 'error';
      mensaje.textContent = `${error.message} No se muestran cifras antiguas.`;
    } finally {
      boton.disabled = false;
      mes.disabled = false;
      desde.disabled = false;
      hasta.disabled = false;
    }
  }
  mesActual();
  boton.onclick = cargar;
  mes.onclick = () => { mesActual(); cargar(); };
  function mostrar() {
    if (!document.querySelector('#panel').hidden && panel.hidden) {
      panel.hidden = false;
      cargar();
    }
  }
  new MutationObserver(mostrar).observe(document.querySelector('#panel'), {attributes: true, attributeFilter: ['hidden']});
  mostrar();
})();
