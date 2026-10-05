(async () => {
  const token = localStorage.getItem('alucarpin_token');
  if (!token) return;
  const panel = document.querySelector('#panel');
  const mensaje = document.querySelector('#mensaje-panel');
  const datos = document.querySelector('#datos-panel');
  const boton = document.querySelector('#actualizar');
  const texto = (id, valor) => { document.querySelector(`#${id}`).textContent = valor; };
  const euros = valor => Number(valor).toLocaleString('es-ES', { style: 'currency', currency: 'EUR' });
  const fecha = valor => String(valor).split('-').reverse().join('/');
  const obtener = async url => {
    const respuesta = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` }, cache: 'no-store',
      signal: AbortSignal.timeout(30000),
    });
    if (!respuesta.ok) throw new Error(`No se pudo consultar el resumen (HTTP ${respuesta.status}).`);
    return respuesta.json();
  };
  async function cargar() {
    boton.disabled = true;
    datos.hidden = true;
    mensaje.className = '';
    mensaje.textContent = 'Actualizando resumen…';
    try {
      const resumen = await obtener('/panel-resumen');
      texto('trabajos-pendientes', resumen.trabajos.pendientes);
      texto('trabajos-detalle', `${resumen.trabajos.vencidos} con fecha anterior a hoy. Terminar no significa cobrar.`);
      texto('cobros-importe', euros(resumen.cobros.importe_pendiente));
      texto('cobros-detalle', `${resumen.cobros.pendientes} recordatorios de cobro; ${resumen.cobros.sin_importe} sin importe. Según cobros registrados.`);
      const pagos = resumen.ayudantes;
      texto('pagos-importe', euros(pagos.importe_pendiente_registrado));
      texto('pagos-detalle', `${pagos.pagadas} días pagados, ${pagos.parciales} parciales, ${pagos.pendientes} pendientes. ${pagos.sin_registro} sin pago registrado y ${pagos.revision} para revisar, excluidos del importe.`);
      texto('agenda-total', resumen.agenda.total);
      texto('agenda-detalle', `${resumen.agenda.vencidos} vencidos. Hasta el ${fecha(resumen.agenda.hasta)}.`);
      const lista = document.querySelector('#avisos');
      lista.replaceChildren();
      for (const aviso of resumen.agenda.avisos) {
        const item = document.createElement('li');
        const enlace = document.createElement('a');
        enlace.href = `/app/alarmas.html?tipo=${encodeURIComponent(aviso.tipo)}`;
        enlace.textContent = `${aviso.vencido ? 'Vencido · ' : ''}${fecha(aviso.fecha)} ${aviso.hora || ''} · ${aviso.tipo === 'nota' ? 'Nota' : 'Cita'} · ${aviso.cliente || 'Sin cliente'} · ${aviso.detalle || 'Sin detalle'}`;
        item.appendChild(enlace);
        lista.appendChild(item);
      }
      if (!resumen.agenda.avisos.length) {
        const item = document.createElement('li');
        item.textContent = 'No hay notas ni citas pendientes en este periodo.';
        lista.appendChild(item);
      }
      texto('actualizado', `Datos consultados el ${fecha(resumen.fecha)} a las ${new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}.`);
      mensaje.textContent = resumen.agenda.total > 8 ? 'Se muestran los primeros 8 avisos; el total incluye todos.' : '';
      datos.hidden = false;
    } catch (error) {
      mensaje.textContent = `${error.message} Pulsa Actualizar resumen para reintentarlo.`;
      mensaje.className = 'error';
      texto('actualizado', 'Resumen no disponible; no se muestran cifras antiguas.');
    } finally {
      boton.disabled = false;
    }
  }
  try {
    const usuario = await obtener('/yo');
    if (usuario.rol !== 'administrador') {
      location.replace('/app/ayudante.html');
      return;
    }
    panel.hidden = false;
    boton.onclick = cargar;
    await cargar();
  } catch (error) {
    panel.hidden = false;
    mensaje.textContent = error.message;
    mensaje.className = 'error';
    boton.onclick = () => location.reload();
  }
})();
