(() => {
  const normalizar = valor => String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().replace(/\s+/g, ' ').toLocaleLowerCase('es');
  async function cargar(apiFetch) {
    const respuesta = await apiFetch('/catalogo-obras', { cache: 'no-store' });
    if (!respuesta.ok) throw new Error('No se pudo cargar el catálogo de clientes y obras.');
    return respuesta.json();
  }

  function sugerencias({ cliente, obra, mensaje, apiFetch }) {
    const listaClientes = cliente.tagName === 'INPUT' ? document.createElement('datalist') : null;
    if (listaClientes) {
      listaClientes.id = `catalogo-${cliente.id}`;
      cliente.setAttribute('list', listaClientes.id);
      cliente.after(listaClientes);
    }
    const listaObras = obra ? document.createElement('datalist') : null;
    if (obra) {
      listaObras.id = `catalogo-${obra.id}`;
      obra.setAttribute('list', listaObras.id);
      obra.after(listaObras);
    }
    let registros = [];
    const pintar = () => {
      if (listaClientes) {
        listaClientes.replaceChildren();
        const clientes = new Map(registros.map(item => [normalizar(item.cliente), item.cliente]));
        clientes.forEach(nombre => listaClientes.appendChild(new Option(nombre, nombre)));
      }
      if (!obra) return;
      listaObras.replaceChildren();
      const nombres = new Map(registros.filter(item => normalizar(item.cliente) === normalizar(cliente.value))
        .map(item => [normalizar(item.obra), item.obra]));
      nombres.forEach(nombre => listaObras.appendChild(new Option(nombre, nombre)));
    };
    const actualizar = async () => {
      try {
        registros = await cargar(apiFetch);
        pintar();
      } catch (error) {
        mensaje.textContent = error.message;
        mensaje.className = 'mensaje error';
      }
    };
    cliente.addEventListener('input', pintar);
    cliente.addEventListener('change', pintar);
    cliente.addEventListener('focus', actualizar);
    cliente.addEventListener('blur', () => {
      if (listaClientes) {
        const existente = registros.find(item => normalizar(item.cliente) === normalizar(cliente.value));
        if (existente) cliente.value = existente.cliente;
      }
      pintar();
    });
    if (obra) {
      obra.addEventListener('focus', pintar);
      obra.addEventListener('blur', () => {
        const existente = registros.find(item => normalizar(item.cliente) === normalizar(cliente.value)
          && normalizar(item.obra) === normalizar(obra.value));
        if (existente) obra.value = existente.obra;
      });
    }
    actualizar();
  }
  window.AlucarpinCatalogo = { cargar, normalizar, sugerencias };
})();
