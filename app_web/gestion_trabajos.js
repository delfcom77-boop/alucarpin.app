(() => {
    const api = '';
    const apiFetch = AlucarpinPanel.apiFetch;
    const mostrarFecha = fecha => String(fecha || '').split('-').reverse().join('/');
    const filtroGastos = document.querySelector('#filtro-gastos');
    const filtroEstadoGastos = document.querySelector('#filtro-estado-gastos');
    const mensajeGastos = document.querySelector('#mensaje-gastos');
    const formularioGasto = document.querySelector('#formulario-gasto');
    const gastoTipo = document.querySelector('#gasto-tipo');
    const gastoDestino = document.querySelector('#gasto-destino');
    const mensajeAltaGasto = document.querySelector('#mensaje-alta-gasto');
    let cargaGastos = 0;
    async function cargarGastos() {
      const carga = ++cargaGastos;
      const tipo = filtroGastos.value ? `?tipo=${encodeURIComponent(filtroGastos.value)}` : '';
      const respuesta = await apiFetch(`${api}/gastos${tipo}`);
      if (!respuesta.ok) throw new Error('No se pudieron cargar los gastos.');
      const lista = await respuesta.json();
      if (carga !== cargaGastos) return;
      const estado = filtroEstadoGastos.value;
      const filtrada = lista.filter(gasto => !estado || gasto.estado_pago === estado);
      const revisiones = filtrada.filter(gasto => gasto.revision);
      const calculables = filtrada.filter(gasto => !gasto.revision);
      const sumar = campo => calculables.reduce((total, gasto) => total + Number(gasto[campo] || 0), 0).toFixed(2);
      document.querySelector('#totales-gastos').textContent = `Gastos visibles: ${sumar('importe')} € · Pagado: ${sumar('importe_pagado')} € · Pendiente: ${sumar('pendiente')} €${revisiones.length ? ` · ${revisiones.length} jornadas requieren revisión y están excluidas: los totales no representan todo el periodo.` : ''}`;
      const cuerpo = document.querySelector('#lista-gastos');
      cuerpo.textContent = '';
      if (!filtrada.length) {
        cuerpo.innerHTML = '<tr><td colspan="9">No hay gastos con estos filtros.</td></tr>';
        return;
      }
      filtrada.forEach(gasto => {
        const fila = document.createElement('tr');
        fila.className = gasto.estado_pago === 'Pagado' ? 'pagado' : gasto.estado_pago === 'Parcial' ? 'parcial' : 'pendiente';
        if (gasto.tipo === 'jornada' && (!gasto.gasto_historico || gasto.imputacion)) {
          const dinero = valor => gasto.revision ? 'Revisar' : `${Number(valor || 0).toFixed(2)} €`;
          ['Jornada de ayudante', mostrarFecha(gasto.fecha), gasto.proveedor,
            gasto.concepto, dinero(gasto.importe), dinero(gasto.importe_pagado),
            dinero(gasto.pendiente), gasto.estado_pago].forEach(texto => {
            const celda = document.createElement('td');
            celda.textContent = texto;
            fila.appendChild(celda);
          });
          const acciones = document.createElement('td');
          const boton = document.createElement('a');
          boton.textContent = 'Ver en Pagos';
          const parametros = new URLSearchParams({ ayudante: gasto.ayudante_id, desde: gasto.fecha, hasta: gasto.fecha });
          boton.href = `/app/administrador.html?${parametros}#pagos`;
          acciones.appendChild(boton);
          const destino = document.createElement('a');
          destino.href = `/app/mi_control.html?costes_fecha=${encodeURIComponent(gasto.fecha)}#costes-dia`;
          destino.textContent = 'Destino en Mi control';
          acciones.appendChild(destino);
          fila.appendChild(acciones);
          cuerpo.appendChild(fila);
          return;
        }
        const tipoTexto = gasto.tipo === 'jornada' ? 'Jornada (gasto histórico)' : gasto.tipo === 'presupuesto' ? 'Presupuesto' : 'Faena';
        if (gasto.gasto_historico) gasto = gasto.gasto_historico;
        fila.innerHTML = `<td>${tipoTexto}</td><td>${mostrarFecha(gasto.fecha)}</td><td>${gasto.proveedor || ''}</td><td>${gasto.concepto || ''}</td><td>${Number(gasto.importe || 0).toFixed(2)} €</td><td>${Number(gasto.importe_pagado || 0).toFixed(2)} €</td><td>${Number(gasto.pendiente || 0).toFixed(2)} €</td><td>${gasto.estado_pago || 'No pagado'}</td><td class="acciones"><button type="button" class="historial-gasto">Historial</button><button type="button" class="pagar-gasto">Registrar pago</button><button type="button" class="editar-gasto">Editar</button><button type="button" class="borrar">Borrar</button></td>`;
        fila.querySelector('.historial-gasto').onclick = AlucarpinPanel.accion('#mensaje-gastos', async () => {
          const respuesta = await apiFetch(`/gastos/${gasto.tipo}/${gasto.id}/pagos`);
          if (!respuesta.ok) { mensajeGastos.textContent = 'No se pudo cargar el historial.'; mensajeGastos.className = 'mensaje error'; return; }
          const pagos = await respuesta.json();
          mensajeGastos.textContent = pagos.length
            ? pagos.map(pago => `${mostrarFecha(pago.fecha)}: ${Number(pago.importe || 0).toFixed(2)} € (${pago.forma_pago})`).join(' | ')
            : 'Este gasto todavía no tiene pagos registrados.';
          mensajeGastos.className = 'mensaje';
        });
        fila.querySelector('.pagar-gasto').onclick = AlucarpinPanel.accion('#mensaje-gastos', async () => {
          const importeTexto = prompt('Importe del pago:', Number(gasto.pendiente || 0).toFixed(2));
          if (importeTexto === null || Number(importeTexto) <= 0) return;
          const forma = prompt('Forma de pago:', gasto.forma_pago || 'Efectivo');
          if (forma === null || !forma.trim()) return;
          const pago = await apiFetch(`/gastos/${gasto.tipo}/${gasto.id}/pagos`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ importe: Number(importeTexto), forma_pago: forma.trim(), fecha: new Date().toISOString().slice(0, 10), observaciones: '' }) });
          if (!pago.ok) { mensajeGastos.textContent = 'No se pudo registrar el pago.'; mensajeGastos.className = 'mensaje error'; return; }
          await cargarGastos();
        });
        fila.querySelector('.editar-gasto').onclick = AlucarpinPanel.accion('#mensaje-gastos', async () => {
          const concepto = prompt('Concepto del gasto:', gasto.concepto || '');
          if (concepto === null || !concepto.trim()) return;
          const importeTexto = prompt('Importe del gasto:', gasto.importe || 0);
          if (importeTexto === null || Number.isNaN(Number(importeTexto))) return;
          const estado = prompt('Estado (No pagado, Parcial o Pagado):', gasto.estado_pago || 'No pagado');
          if (estado === null) return;
          const datos = {
            tipo: gasto.tipo,
            concepto: concepto.trim(),
            proveedor: gasto.proveedor || '',
            fecha: gasto.fecha || null,
            importe: Number(importeTexto),
            bruto: Number(importeTexto),
            iva: 0,
            estado_pago: estado,
            forma_pago: gasto.forma_pago || '',
            categoria: gasto.categoria || 'Extras',
            numero_documento: '',
          };
          if (gasto.tipo === 'faena') datos.faena_id = gasto.faena_id;
          else datos.num_presupuesto = gasto.num_presupuesto;
          const cambio = await apiFetch(`/gastos/${gasto.tipo}/${gasto.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) });
          if (!cambio.ok) { mensajeGastos.textContent = 'No se pudo modificar el gasto.'; mensajeGastos.className = 'mensaje error'; return; }
          await cargarGastos();
        });
        fila.querySelector('.borrar').onclick = AlucarpinPanel.accion('#mensaje-gastos', async () => {
          if (!confirm(`¿Borrar el gasto de ${gasto.proveedor || 'este proveedor'}?`)) return;
          const borrado = await apiFetch(`/gastos/${gasto.tipo}/${gasto.id}`, { method: 'DELETE' });
          if (!borrado.ok) { mensajeGastos.textContent = 'No se pudo borrar el gasto.'; mensajeGastos.className = 'mensaje error'; return; }
          await cargarGastos();
        });
        cuerpo.appendChild(fila);
      });
    }

    let cargaDestinos = 0;
    let tipoDestinos = '';
    async function cargarDestinosGasto() {
      const carga = ++cargaDestinos;
      const tipo = gastoTipo.value;
      const seleccionado = tipoDestinos === tipo ? gastoDestino.value : '';
      gastoDestino.disabled = true;
      const presupuesto = gastoTipo.value === 'presupuesto';
      const respuesta = await apiFetch(presupuesto ? '/presupuestos' : '/faenas');
      if (!respuesta.ok) throw new Error('No se pudieron cargar los destinos de gastos.');
      const lista = await respuesta.json();
      if (carga !== cargaDestinos) return;
      gastoDestino.textContent = '';
      lista.forEach(item => {
        const opcion = document.createElement('option');
        opcion.value = presupuesto ? item.num_presupuesto : item.id;
        opcion.textContent = presupuesto
          ? `Nº ${item.num_presupuesto} | ${item.cliente}`
          : `#${item.id} | ${item.cliente} | ${item.obra}`;
        gastoDestino.appendChild(opcion);
      });
      if (!lista.length) gastoDestino.innerHTML = '<option value="">No hay destinos disponibles</option>';
      if ([...gastoDestino.options].some(opcion => opcion.value === seleccionado)) gastoDestino.value = seleccionado;
      tipoDestinos = tipo;
      gastoDestino.disabled = !lista.length;
    }

    gastoTipo.addEventListener('change', () => cargarDestinosGasto().catch(error => {
      mensajeAltaGasto.textContent = error.message;
      mensajeAltaGasto.className = 'mensaje error';
    }));
    formularioGasto.addEventListener('submit', AlucarpinPanel.accion('#mensaje-alta-gasto', async event => {
      event.preventDefault();
      if (gastoDestino.disabled || !gastoDestino.value) throw new Error('Selecciona un destino disponible para el gasto');
      const tipo = gastoTipo.value;
      const importe = Number(document.querySelector('#gasto-importe').value || 0);
      const datos = {
        tipo,
        concepto: document.querySelector('#gasto-concepto').value,
        proveedor: document.querySelector('#gasto-proveedor').value,
        fecha: document.querySelector('#gasto-fecha').value || null,
        importe,
        bruto: importe,
        iva: 0,
        estado_pago: document.querySelector('#gasto-estado').value,
        forma_pago: document.querySelector('#gasto-forma').value,
        categoria: 'Extras',
        numero_documento: '',
      };
      if (tipo === 'faena') datos.faena_id = Number(gastoDestino.value);
      else datos.num_presupuesto = gastoDestino.value;
      const respuesta = await apiFetch('/gastos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) });
      const resultado = await respuesta.json();
      if (!respuesta.ok) { mensajeAltaGasto.textContent = resultado.detail || 'No se pudo guardar el gasto.'; mensajeAltaGasto.className = 'mensaje error'; return; }
      mensajeAltaGasto.textContent = 'Gasto guardado correctamente.';
      mensajeAltaGasto.className = 'mensaje exito';
      formularioGasto.reset();
      await cargarGastos();
      await cargarDestinosGasto();
    }));

    [filtroGastos, filtroEstadoGastos].forEach(item => item.addEventListener('change', () => cargarGastos().catch(error => {
      mensajeGastos.textContent = error.message;
      mensajeGastos.className = 'mensaje error';
    })));
    // === CRUD FAENAS ===
    async function cargarFaenasLista() {
      const respuesta = await apiFetch('/faenas');
      if (!respuesta.ok) throw new Error('No se pudieron cargar las faenas.');
      const lista = await respuesta.json();
      const cuerpo = document.querySelector('#lista-faenas');
      cuerpo.textContent = '';
      if (!lista.length) { cuerpo.innerHTML = '<tr><td colspan="8">No hay faenas registradas.</td></tr>'; return; }
      lista.forEach(faena => {
        const fila = document.createElement('tr');
        fila.innerHTML = `<td>${faena.cliente}</td><td>${faena.obra || '-'}</td><td>${faena.fecha || '-'}</td><td>${faena.ubicacion || '-'}</td><td>${faena.poblacion || '-'}</td><td>${Number(faena.precio || 0).toFixed(2)} €</td><td>${faena.ayudantes || '-'}</td><td class="acciones"><button type="button" class="editar-faena">Editar</button><button type="button" class="borrar-faena">Borrar</button></td>`;
        fila.querySelector('.editar-faena').onclick = () => {
          document.querySelector('#faena-id').value = faena.id;
          document.querySelector('#faena-cliente').value = faena.cliente;
          document.querySelector('#faena-obra').value = faena.obra || '';
          document.querySelector('#faena-fecha').value = faena.fecha || '';
          document.querySelector('#faena-ubicacion').value = faena.ubicacion || '';
          document.querySelector('#faena-poblacion').value = faena.poblacion || '';
          document.querySelector('#faena-precio').value = faena.precio || 0;
          document.querySelector('#faena-ayudantes').value = faena.ayudantes || '';
          document.querySelector('#btn-faena-submit').textContent = 'Actualizar faena';
          document.querySelector('#btn-faena-cancelar').hidden = false;
          window.scrollTo(0, document.querySelector('#formulario-faena').offsetTop - 100);
        };
        fila.querySelector('.borrar-faena').onclick = AlucarpinPanel.accion('#mensaje-faena', async () => {
          if (!confirm(`¿Borrar la faena de ${faena.cliente}?`)) return;
          const borrada = await apiFetch(`/faenas/${faena.id}`, { method: 'DELETE' });
          if (!borrada.ok) { document.querySelector('#mensaje-faena').textContent = 'No se pudo borrar la faena.'; document.querySelector('#mensaje-faena').className = 'mensaje error'; return; }
          await cargarFaenasLista();
          document.querySelector('#mensaje-faena').textContent = 'Faena borrada correctamente.';
          document.querySelector('#mensaje-faena').className = 'mensaje exito';
        });
        cuerpo.appendChild(fila);
      });
      filtrarTabla('#filtro-faenas', '#lista-faenas');
    }
    const detalleErrorApi = async (respuesta, mensajePredeterminado) => {
      const cuerpo = await respuesta.json().catch(() => null);
      if (Array.isArray(cuerpo?.detail)) return cuerpo.detail.map(error => error.msg).join('; ');
      return cuerpo?.detail || mensajePredeterminado;
    };
    const filtrarTabla = (selectorFiltro, selectorCuerpo) => {
      const texto = document.querySelector(selectorFiltro).value.trim().toLocaleLowerCase();
      document.querySelectorAll(`${selectorCuerpo} tr`).forEach(fila => {
        fila.hidden = Boolean(texto) && !fila.textContent.toLocaleLowerCase().includes(texto);
      });
    };
    const exportarTablaCsv = (selectorTabla, nombreArchivo) => {
      AlucarpinExportar.tabla(document.querySelector(selectorTabla).closest('table'), nombreArchivo);
    };
    document.querySelector('#filtro-faenas').addEventListener('input', () => filtrarTabla('#filtro-faenas', '#lista-faenas'));
    document.querySelector('#filtro-presupuestos').addEventListener('input', () => filtrarTabla('#filtro-presupuestos', '#lista-presupuestos'));
    document.querySelector('#exportar-faenas').onclick = AlucarpinPanel.accion('#mensaje-faena', async () => exportarTablaCsv('#lista-faenas', 'faenas.csv'));
    document.querySelector('#exportar-presupuestos').onclick = AlucarpinPanel.accion('#mensaje-presupuesto', async () => exportarTablaCsv('#lista-presupuestos', 'presupuestos.csv'));

    const reiniciarFormularioFaena = () => {
      document.querySelector('#formulario-faena').reset();
      document.querySelector('#faena-id').value = '';
      document.querySelector('#btn-faena-submit').textContent = 'Crear faena';
      document.querySelector('#btn-faena-cancelar').hidden = true;
      document.querySelector('#mensaje-faena').textContent = '';
    };
    document.querySelector('#btn-faena-cancelar').onclick = reiniciarFormularioFaena;

    document.querySelector('#formulario-faena').addEventListener('submit', AlucarpinPanel.accion('#mensaje-faena', async event => {
      event.preventDefault();
      const id = document.querySelector('#faena-id').value;
      const datos = {
        cliente: document.querySelector('#faena-cliente').value.trim(),
        obra: document.querySelector('#faena-obra').value || null,
        fecha: document.querySelector('#faena-fecha').value || null,
        ubicacion: document.querySelector('#faena-ubicacion').value || null,
        poblacion: document.querySelector('#faena-poblacion').value || null,
        precio: Number(document.querySelector('#faena-precio').value || 0),
        ayudantes: document.querySelector('#faena-ayudantes').value || null,
      };
      const msgFaena = document.querySelector('#mensaje-faena');
      if (!datos.cliente) {
        msgFaena.textContent = 'El cliente es obligatorio.';
        msgFaena.className = 'mensaje error';
        return;
      }
      msgFaena.textContent = 'Guardando...';
      const metodo = id ? 'PATCH' : 'POST';
      const url = id ? `/faenas/${id}` : '/faenas';
      const respuesta = await apiFetch(url, { method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) });
      if (!respuesta.ok) {
        msgFaena.textContent = await detalleErrorApi(respuesta, 'No se pudo guardar la faena.');
        msgFaena.className = 'mensaje error';
        return;
      }
      reiniciarFormularioFaena();
      await cargarFaenasLista();
      msgFaena.textContent = id ? 'Faena actualizada correctamente.' : 'Faena creada correctamente.';
      msgFaena.className = 'mensaje exito';
    }));

    // === CRUD PRESUPUESTOS ===
    async function cargarPresupuestosLista() {
      const respuesta = await apiFetch('/presupuestos');
      if (!respuesta.ok) throw new Error('No se pudieron cargar los presupuestos.');
      const lista = await respuesta.json();
      const cuerpo = document.querySelector('#lista-presupuestos');
      cuerpo.textContent = '';
      if (!lista.length) { cuerpo.innerHTML = '<tr><td colspan="8">No hay presupuestos registrados.</td></tr>'; return; }
      lista.forEach(presupuesto => {
        const fila = document.createElement('tr');
        const total = Number(presupuesto.presupuesto_final || 0);
        fila.innerHTML = `<td>${presupuesto.cliente}</td><td>${presupuesto.num_presupuesto || '-'}</td><td>${presupuesto.fecha || '-'}</td><td>${Number(presupuesto.bruto || 0).toFixed(2)} €</td><td>${Number(presupuesto.iva || 0).toFixed(2)} €</td><td>${presupuesto.estado || '-'}</td><td>${total.toFixed(2)} €</td><td class="acciones"><button type="button" class="editar-presupuesto">Editar</button><button type="button" class="borrar-presupuesto">Borrar</button></td>`;
        fila.querySelector('.editar-presupuesto').onclick = () => {
          document.querySelector('#presupuesto-id').value = presupuesto.id;
          document.querySelector('#presupuesto-cliente').value = presupuesto.cliente;
          document.querySelector('#presupuesto-num').value = presupuesto.num_presupuesto || '';
          document.querySelector('#presupuesto-fecha').value = presupuesto.fecha || '';
          document.querySelector('#presupuesto-bruto').value = presupuesto.bruto || 0;
          document.querySelector('#presupuesto-iva').value = presupuesto.iva || 0;
          document.querySelector('#presupuesto-total-iva').value = presupuesto.total_iva || 0;
          document.querySelector('#presupuesto-presupuesto-iva').value = presupuesto.presupuesto_iva || 0;
          document.querySelector('#presupuesto-efectivo').value = presupuesto.efectivo || 0;
          document.querySelector('#presupuesto-estado').value = presupuesto.estado || 'Presupuesto';
          document.querySelector('#presupuesto-final').value = presupuesto.presupuesto_final || 0;
          document.querySelector('#btn-presupuesto-submit').textContent = 'Actualizar presupuesto';
          document.querySelector('#btn-presupuesto-cancelar').hidden = false;
          window.scrollTo(0, document.querySelector('#formulario-presupuesto').offsetTop - 100);
        };
        fila.querySelector('.borrar-presupuesto').onclick = AlucarpinPanel.accion('#mensaje-presupuesto', async () => {
          if (!confirm(`¿Borrar el presupuesto ${presupuesto.num_presupuesto} de ${presupuesto.cliente}?`)) return;
          const borrado = await apiFetch(`/presupuestos/${presupuesto.id}`, { method: 'DELETE' });
          if (!borrado.ok) { document.querySelector('#mensaje-presupuesto').textContent = 'No se pudo borrar el presupuesto.'; document.querySelector('#mensaje-presupuesto').className = 'mensaje error'; return; }
          await cargarPresupuestosLista();
          document.querySelector('#mensaje-presupuesto').textContent = 'Presupuesto borrado correctamente.';
          document.querySelector('#mensaje-presupuesto').className = 'mensaje exito';
        });
        cuerpo.appendChild(fila);
      });
      filtrarTabla('#filtro-presupuestos', '#lista-presupuestos');
    }
    const reiniciarFormularioPresupuesto = () => {
      document.querySelector('#formulario-presupuesto').reset();
      document.querySelector('#presupuesto-id').value = '';
      document.querySelector('#btn-presupuesto-submit').textContent = 'Crear presupuesto';
      document.querySelector('#btn-presupuesto-cancelar').hidden = true;
      document.querySelector('#mensaje-presupuesto').textContent = '';
    };
    document.querySelector('#btn-presupuesto-cancelar').onclick = reiniciarFormularioPresupuesto;

    document.querySelector('#formulario-presupuesto').addEventListener('submit', AlucarpinPanel.accion('#mensaje-presupuesto', async event => {
      event.preventDefault();
      const id = document.querySelector('#presupuesto-id').value;
      const datos = {
        cliente: document.querySelector('#presupuesto-cliente').value.trim(),
        num_presupuesto: document.querySelector('#presupuesto-num').value || null,
        fecha: document.querySelector('#presupuesto-fecha').value || null,
        bruto: Number(document.querySelector('#presupuesto-bruto').value || 0),
        iva: Number(document.querySelector('#presupuesto-iva').value || 0),
        total_iva: Number(document.querySelector('#presupuesto-total-iva').value || 0),
        presupuesto_iva: Number(document.querySelector('#presupuesto-presupuesto-iva').value || 0),
        efectivo: Number(document.querySelector('#presupuesto-efectivo').value || 0),
        estado: document.querySelector('#presupuesto-estado').value,
        presupuesto_final: Number(document.querySelector('#presupuesto-final').value || 0),
      };
      const msgPresupuesto = document.querySelector('#mensaje-presupuesto');
      if (!datos.cliente) {
        msgPresupuesto.textContent = 'El cliente es obligatorio.';
        msgPresupuesto.className = 'mensaje error';
        return;
      }
      msgPresupuesto.textContent = 'Guardando...';
      const metodo = id ? 'PATCH' : 'POST';
      const url = id ? `/presupuestos/${id}` : '/presupuestos';
      const respuesta = await apiFetch(url, { method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) });
      if (!respuesta.ok) {
        msgPresupuesto.textContent = await detalleErrorApi(respuesta, 'No se pudo guardar el presupuesto.');
        msgPresupuesto.className = 'mensaje error';
        return;
      }
      reiniciarFormularioPresupuesto();
      await cargarPresupuestosLista();
      msgPresupuesto.textContent = id ? 'Presupuesto actualizado correctamente.' : 'Presupuesto creado correctamente.';
      msgPresupuesto.className = 'mensaje exito';
    }));

    [
      ['#faena-cliente', '#faena-obra', '#mensaje-faena'],
      ['#presupuesto-cliente', null, '#mensaje-presupuesto'],
    ].forEach(([cliente, obra, mensaje]) => AlucarpinCatalogo.sugerencias({
      cliente: document.querySelector(cliente),
      obra: obra ? document.querySelector(obra) : null,
      mensaje: document.querySelector(mensaje),
      apiFetch,
    }));
    AlucarpinPanel.prepararTablas();
    AlucarpinPanel.prepararExportaciones();
    let anterior = '';
    async function mostrarGestion() {
      const apartado = location.hash.slice(1);
      const gestion = ['faenas', 'presupuestos', 'gastos'].includes(apartado);
      document.querySelector('#control-personal').hidden = gestion;
      document.querySelector('#gestion-paneles').hidden = !gestion;
      document.querySelectorAll('[data-gestion]').forEach(seccion => {
        seccion.hidden = seccion.dataset.gestion !== apartado;
      });
      document.querySelectorAll('.gestion-atajos a').forEach(enlace => {
        if (enlace.hash === (gestion ? location.hash : '#trabajos')) enlace.setAttribute('aria-current', 'page');
        else enlace.removeAttribute('aria-current');
      });
      const refrescarTrabajos = !gestion && anterior;
      anterior = gestion ? apartado : '';
      const aviso = document.querySelector('#mensaje-gestion');
      aviso.textContent = '';
      try {
        if (apartado === 'faenas') await cargarFaenasLista();
        else if (apartado === 'presupuestos') await cargarPresupuestosLista();
        else if (apartado === 'gastos') await Promise.all([cargarGastos(), cargarDestinosGasto()]);
        else if (refrescarTrabajos) await cargarTrabajos();
      } catch (error) {
        aviso.className = 'mensaje error';
        aviso.textContent = `No se pudo actualizar el apartado: ${error.message}. Selecciónalo de nuevo para reintentar.`;
      }
    }
    window.addEventListener('hashchange', mostrarGestion);
    document.querySelectorAll('.gestion-atajos a').forEach(enlace => {
      enlace.addEventListener('click', () => { if (location.hash === enlace.hash) mostrarGestion(); });
    });
    mostrarGestion();

})();
