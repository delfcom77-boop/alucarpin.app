(() => {
  const token = localStorage.getItem('alucarpin_token');
  if (!token) { location.replace('/app/login.html'); return; }
  const parametros = new URLSearchParams(location.search);
  const origen = parametros.get('origen');
  const id = parametros.get('id');
  const mensaje = document.querySelector('#mensaje');
  const contenido = document.querySelector('#contenido');
  const imprimir = document.querySelector('#imprimir');
  const recargar = document.querySelector('#recargar');
  const euros = valor => valor == null ? 'No disponible' : Number(valor).toLocaleString('es-ES', { style: 'currency', currency: 'EUR' });
  const fecha = valor => valor ? String(valor).split('-').reverse().join('/') : 'Sin fecha';
  const texto = (selector, valor) => { document.querySelector(selector).textContent = valor; };
  function tabla(idTabla, filas) {
    const cuerpo = document.querySelector(`#${idTabla} tbody`);
    cuerpo.replaceChildren();
    for (const valores of filas) {
      const fila = document.createElement('tr');
      for (const valor of valores) {
        const celda = document.createElement('td');
        celda.textContent = valor ?? '';
        fila.appendChild(celda);
      }
      cuerpo.appendChild(fila);
    }
    document.querySelector(`[data-exportar="${idTabla}"]`).disabled = !filas.length;
    if (!filas.length) {
      const fila = document.createElement('tr');
      const celda = document.createElement('td');
      celda.colSpan = document.querySelectorAll(`#${idTabla} th`).length;
      celda.textContent = 'Sin registros vinculados.';
      fila.appendChild(celda); cuerpo.appendChild(fila);
    }
  }
  async function cargar() {
    contenido.hidden = true; imprimir.disabled = true; recargar.disabled = true;
    mensaje.className = ''; mensaje.textContent = 'Consultando ficha…';
    try {
      if (!['propio', 'faena', 'presupuesto'].includes(origen) || !/^[1-9]\d*$/.test(id || '')) throw new Error('La referencia de la obra no es válida.');
      const respuesta = await fetch(`/obras/${origen}/${id}`, {
        headers: { Authorization: `Bearer ${token}` }, cache: 'no-store', signal: AbortSignal.timeout(30000),
      });
      if (!respuesta.ok) throw new Error(`No se pudo consultar la ficha (HTTP ${respuesta.status}).`);
      const ficha = await respuesta.json();
      const obra = ficha.obra;
      texto('#titulo', `${obra.cliente} · ${obra.obra || 'Obra'}`);
      texto('#consulta', `Consulta del ${new Date().toLocaleString('es-ES')}. Referencia: ${origen} #${id}.`);
      const datos = document.querySelector('#datos'); datos.replaceChildren();
      for (const [nombre, valor] of Object.entries({
        Cliente: obra.cliente, Obra: obra.obra, Tipo: obra.tipo, Ubicación: obra.ubicacion,
        Población: obra.poblacion, Fecha: fecha(obra.fecha_inicio), Presupuesto: obra.num_presupuesto,
        Ejecución: obra.estado_ejecucion || 'Sin aceptar', Cobro: obra.estado_cobro,
        'Importe registrado': euros(obra.importe), Observaciones: obra.observaciones,
      })) {
        const dt = document.createElement('dt'); dt.textContent = nombre;
        const dd = document.createElement('dd'); dd.textContent = valor || 'Sin registrar';
        datos.append(dt, dd);
      }
      const r = ficha.resumen;
      texto('#resumen', `${r.dias_ayudantes} días de ayudantes en ${r.fechas_trabajadas} fechas, con ${r.ayudantes} ayudantes. ${r.dias_obra_registrados} días propios registrados.`);
      texto('#importe-resumen', `Gastos vinculados: ${euros(r.gastos)} · Gastos pagados: ${euros(r.gastos_pagados)} · Cobros registrados: ${euros(r.cobros_registrados)}.`);
      texto('#limitaciones', origen === 'propio'
        ? 'Las reparaciones no tienen un vínculo directo a gastos en el modelo actual. El cobro refleja el estado guardado en Mi control.'
        : origen === 'presupuesto'
          ? 'Los gastos y cobros se vinculan por número de presupuesto. Un estado histórico Completado puede indicar cobrado sin movimientos de cobro independientes; no se inventan esos movimientos.'
          : 'Los gastos y cobros se vinculan al identificador de la faena. Los días propios y los días de ayudantes son recuentos separados.');
      tabla('ayudantes', ficha.jornadas_ayudantes.map(j => [
        fecha(j.fecha), j.ayudante, j.revision ? 'Revisión necesaria' : j.sin_registro ? 'Sin pago registrado' : j.estado_pago,
        j.sin_registro ? 'Sin pago registrado' : euros(j.importe_dia),
        j.sin_registro ? 'Sin pago registrado' : euros(j.pagado_dia), j.obras_del_dia,
      ]));
      tabla('gastos', ficha.gastos.map(g => [fecha(g.fecha), g.proveedor, g.concepto, g.categoria, euros(g.importe), euros(g.importe_pagado), euros(g.pendiente)]));
      tabla('cobros', ficha.cobros.map(c => [fecha(c.fecha), euros(c.importe), c.forma_pago, c.observaciones]));
      const tiposRemate = { u: 'Bandeja / U', chapa: 'Chapa', angulo: 'Ángulo / L', tubo: 'Tubo', tubo_redondo: 'Tubo redondo' };
      const medidasRemate = r => {
        if (r.tipo === 'u') return `${r.medida_1} × ${r.medida_2} × ${r.medida_3} · Medidas ${r.posicion_medidas === 'exterior' ? 'exteriores' : 'interiores'}`;
        if (r.tipo === 'chapa' && r.modo_chapa === 'desnivel') return `Izq. ${r.medida_1} × Der. ${r.medida_2} · Recta ${r.orientacion_chapa}`;
        if (r.tipo === 'chapa' || r.tipo === 'tubo_redondo') return String(r.medida_1);
        return `${r.medida_1} × ${r.medida_2}`;
      };
      tabla('remates', ficha.remates.map(r => [
        r.pieza, r.lacado_color, tiposRemate[r.tipo],
        medidasRemate(r),
        r.largura, r.cantidad, r.observaciones,
      ]));
      texto('#dias-obra', ficha.dias_obra.length ? ficha.dias_obra.map(d => fecha(d.fecha)).join(', ') : 'Sin días propios vinculados.');
      mensaje.textContent = ''; contenido.hidden = false; imprimir.disabled = false;
    } catch (error) {
      mensaje.className = 'error'; mensaje.textContent = error.message;
    } finally { recargar.disabled = false; }
  }
  imprimir.onclick = () => window.print();
  recargar.onclick = cargar;
  document.querySelectorAll('[data-exportar]').forEach(boton => {
    boton.onclick = () => {
      try {
        const filas = AlucarpinExportar.tabla(document.querySelector(`#${boton.dataset.exportar}`), `obra-${origen}-${id}-${boton.dataset.exportar}.csv`);
        mensaje.className = ''; mensaje.textContent = `${filas} filas exportadas a CSV.`;
      } catch (error) { mensaje.className = 'error'; mensaje.textContent = error.message; }
    };
  });
  cargar();
})();
