window.AlucarpinPanel = (() => {
    const token = localStorage.getItem('alucarpin_token');
    if (!token) location.replace('/app/login.html');
    const apiFetch = (url, options = {}) => {
      const controller = new AbortController();
      const temporizador = setTimeout(() => controller.abort(), 10000);
      const metodo = (options.method || 'GET').toUpperCase();
      return fetch(url, { ...options, cache: metodo === 'GET' ? 'no-store' : options.cache, signal: controller.signal, headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` } })
        .finally(() => clearTimeout(temporizador));
    };

    function prepararTablas() {
    document.querySelectorAll('.lista-general').forEach(contenedor => {
      contenedor.tabIndex = 0;
      contenedor.setAttribute('role', 'region');
      contenedor.setAttribute('aria-label', `Tabla de ${contenedor.closest('section').querySelector('h2').textContent}. Desplaza horizontalmente para ver todas las columnas.`);
    });
    }
    function prepararExportaciones() {
    document.querySelectorAll('[data-exportar-listado]').forEach(boton => {
      const aviso = document.createElement('p');
      aviso.setAttribute('role', 'status'); aviso.setAttribute('aria-live', 'polite');
      boton.after(aviso);
      boton.onclick = () => {
        try {
          const filas = AlucarpinExportar.tabla(document.querySelector(`#${boton.dataset.exportarListado}`).closest('table'), `${boton.dataset.exportarListado}-filtrado.csv`);
          aviso.className = 'mensaje'; aviso.textContent = `${filas} filas exportadas con los filtros actuales.`;
        } catch (error) { aviso.className = 'mensaje error'; aviso.textContent = error.message; }
      };
    });
    }
    function accion(selectorAviso, operacion) {
      return async event => {
        event.preventDefault();
        const origen = event.currentTarget;
        const boton = origen.matches('form') ? origen.querySelector('[type="submit"]') : origen;
        if (boton.disabled) return;
        boton.disabled = true;
        try {
          await operacion(event);
        } catch (error) {
          const aviso = document.querySelector(selectorAviso);
          aviso.className = 'mensaje error';
          aviso.textContent = `${error.message}. Comprueba los datos antes de repetir la operación.`;
        } finally {
          boton.disabled = false;
        }
      };
    }
    return { apiFetch, prepararTablas, prepararExportaciones, accion };
})();
