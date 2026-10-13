(() => {
  const destino = document.querySelector('[data-diario]');
  if (!destino) return;
  const token = localStorage.getItem('alucarpin_token');
  const nombres = {faena: 'Faena a terceros', presupuesto: 'Presupuesto', reparacion: 'Reparación'};
  destino.innerHTML = `
    <h2>Mis días trabajados</h2>
    <p>Solo tus días registrados, no los fichajes de ayudantes ni fechas previstas. Pulsa un día para ver dónde trabajaste.</p>
    <div class="diario-leyenda"><span class="dia-tipo faena">3º · Faenas a terceros</span><span class="dia-tipo presupuesto">P · Presupuestos</span><span class="dia-tipo reparacion">R · Reparaciones</span></div>
    <div class="fila">
      <label>Mes <input id="diario-mes" type="month" required></label>
      <label>Tipo <select id="diario-tipo"><option value="">Todos</option><option value="faena">Faenas a terceros</option><option value="presupuesto">Presupuestos</option><option value="reparacion">Reparaciones</option></select></label>
      <label>Buscar cliente, obra o ubicación <input id="diario-buscar" type="search"></label>
    </div>
    <div class="acciones"><button type="button" id="diario-anterior">Mes anterior</button><button type="button" id="diario-hoy">Mes actual</button><button type="button" id="diario-siguiente">Mes siguiente</button><button type="button" id="diario-todos">Ver todo el mes</button><button type="button" id="diario-actualizar">Actualizar días</button></div>
    <p id="diario-mensaje" role="status" aria-live="polite"></p>
    <div class="diario-calendario" id="diario-calendario" aria-label="Calendario de mis días trabajados"></div>
    <h3 id="diario-titulo-lista">Días del mes</h3>
    <div id="diario-lista"></div>`;
  const mes = destino.querySelector('#diario-mes');
  const tipo = destino.querySelector('#diario-tipo');
  const buscar = destino.querySelector('#diario-buscar');
  const mensaje = destino.querySelector('#diario-mensaje');
  const calendario = destino.querySelector('#diario-calendario');
  const lista = destino.querySelector('#diario-lista');
  let dias = [];
  let seleccionado = null;
  let cargado = false;
  let consulta = 0;
  const hoy = () => {
    const fecha = new Date();
    return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, '0')}`;
  };
  mes.value = hoy();
  const normalizar = texto => String(texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  const fechaBonita = fecha => fecha.split('-').reverse().join('/');
  function pintar() {
    calendario.replaceChildren();
    lista.replaceChildren();
    if (!/^\d{4}-\d{2}$/.test(mes.value)) {
      mensaje.textContent = 'Selecciona un mes válido.';
      return;
    }
    const registros = dias.filter(d => d.fecha.startsWith(mes.value)
      && (!tipo.value || d.tipo === tipo.value)
      && normalizar([d.cliente, d.obra, d.ubicacion, d.poblacion].join(' ')).includes(normalizar(buscar.value.trim())));
    for (const nombre of ['L', 'M', 'X', 'J', 'V', 'S', 'D']) {
      const etiqueta = document.createElement('span');
      etiqueta.textContent = nombre;
      etiqueta.className = 'diario-cabecera';
      calendario.appendChild(etiqueta);
    }
    const [ano, numeroMes] = mes.value.split('-').map(Number);
    const inicio = new Date(ano, numeroMes - 1, 1);
    const numeroDias = new Date(ano, numeroMes, 0).getDate();
    for (let i = 0; i < (inicio.getDay() + 6) % 7; i++) calendario.appendChild(document.createElement('span'));
    for (let numero = 1; numero <= numeroDias; numero++) {
      const fecha = `${mes.value}-${String(numero).padStart(2, '0')}`;
      const eventos = registros.filter(d => d.fecha === fecha);
      const boton = document.createElement('button');
      boton.type = 'button';
      boton.className = 'diario-dia';
      boton.dataset.fecha = fecha;
      boton.textContent = numero;
      boton.setAttribute('aria-pressed', String(seleccionado === fecha));
      boton.setAttribute('aria-label', `${fechaBonita(fecha)}: ${eventos.length ? eventos.map(d => `${nombres[d.tipo]}: ${d.cliente}, ${d.obra}`).join('; ') : 'Sin días registrados'}`);
      for (const categoria of [...new Set(eventos.map(d => d.tipo))]) {
        const marca = document.createElement('span');
        marca.className = `dia-tipo ${categoria}`;
        marca.textContent = {faena: '3º', presupuesto: 'P', reparacion: 'R'}[categoria];
        marca.title = nombres[categoria];
        boton.appendChild(marca);
      }
      boton.onclick = () => { seleccionado = fecha; pintar(); };
      calendario.appendChild(boton);
    }
    const visibles = registros.filter(d => !seleccionado || d.fecha === seleccionado);
    destino.querySelector('#diario-titulo-lista').textContent = seleccionado
      ? `Dónde trabajé el ${fechaBonita(seleccionado)}` : 'Días del mes';
    if (!visibles.length) lista.textContent = cargado ? 'No hay días registrados para esta selección.' : 'Los días todavía no se han podido consultar.';
    for (const dia of visibles) {
      const tarjeta = document.createElement('article');
      tarjeta.className = `diario-registro ${dia.tipo}`;
      const etiqueta = document.createElement('span');
      etiqueta.className = `dia-tipo ${dia.tipo}`;
      etiqueta.textContent = nombres[dia.tipo];
      const titulo = document.createElement('h4');
      titulo.textContent = `${fechaBonita(dia.fecha)} · ${dia.cliente} · ${dia.obra || 'Sin nombre de obra'}`;
      const ubicacion = document.createElement('p');
      ubicacion.textContent = [dia.ubicacion, dia.poblacion].filter(Boolean).join(' · ') || 'Ubicación no indicada';
      const nota = document.createElement('p');
      nota.textContent = dia.observaciones || '';
      const sello = document.createElement('small');
      sello.textContent = dia.creado_en ? `Registrado: ${dia.creado_en}` : 'Registro anterior sin sello de fecha de alta.';
      const ficha = document.createElement('a');
      ficha.textContent = 'Ver trabajo';
      ficha.href = `/app/obra.html?origen=${encodeURIComponent(dia.origen)}&id=${dia.origen_id}`;
      tarjeta.append(etiqueta, titulo, ubicacion, nota, sello, document.createElement('br'), ficha);
      lista.appendChild(tarjeta);
    }
    if (cargado) {
      mensaje.className = '';
      mensaje.textContent = `${registros.length} registros en ${new Set(registros.map(d => d.fecha)).size} días distintos. Un día puede tener más de un trabajo.`;
    }
  }
  async function actualizar() {
    const actual = ++consulta;
    cargado = false;
    dias = [];
    pintar();
    mensaje.textContent = 'Consultando tus días…';
    try {
      const respuesta = await fetch('/mis-dias', {
        cache: 'no-store', signal: AbortSignal.timeout(30000),
        headers: {Authorization: `Bearer ${token}`},
      });
      if (!respuesta.ok) {
        const resultado = await respuesta.json();
        throw new Error(typeof resultado.detail === 'string' ? resultado.detail : `No se pudieron consultar tus días (HTTP ${respuesta.status}).`);
      }
      const resultado = await respuesta.json();
      if (actual !== consulta) return;
      dias = resultado;
      cargado = true;
      pintar();
    } catch (error) {
      if (actual !== consulta) return;
      mensaje.className = 'error';
      mensaje.textContent = error.message;
      throw error;
    }
  }
  mes.onchange = () => { seleccionado = null; pintar(); };
  tipo.onchange = pintar;
  buscar.oninput = pintar;
  const moverMes = delta => {
    if (!mes.value) mes.value = hoy();
    const [ano, numero] = mes.value.split('-').map(Number);
    const fecha = new Date(ano, numero - 1 + delta, 1);
    mes.value = `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, '0')}`;
    seleccionado = null;
    pintar();
  };
  destino.querySelector('#diario-anterior').onclick = () => moverMes(-1);
  destino.querySelector('#diario-siguiente').onclick = () => moverMes(1);
  destino.querySelector('#diario-hoy').onclick = () => { mes.value = hoy(); seleccionado = null; pintar(); };
  destino.querySelector('#diario-todos').onclick = () => { seleccionado = null; pintar(); };
  const consultar = () => actualizar().catch(() => { /* El error ya se muestra en el calendario. */ });
  destino.querySelector('#diario-actualizar').onclick = consultar;
  window.AlucarpinDiario = {
    actualizar,
    mostrarFecha(fecha) {
      mes.value = fecha.slice(0, 7);
      seleccionado = fecha;
      tipo.value = '';
      buscar.value = '';
      pintar();
    },
  };
  consultar();
})();
