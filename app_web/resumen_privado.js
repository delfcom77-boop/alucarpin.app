(() => {
  const login = localStorage.getItem('alucarpin_token');
  if (!login) { location.replace('/app/login.html'); return; }
  const acceso = document.querySelector('#acceso');
  const formulario = document.querySelector('#formulario-acceso');
  const configuracion = document.querySelector('#formulario-clave');
  const mensaje = document.querySelector('#mensaje-acceso');
  const bloquear = document.querySelector('#bloquear-resumen');
  const reintentar = document.querySelector('#reintentar-acceso');
  let privado = null;
  let temporizador;
  let configurado = false;
  let generacion = 0;
  const aviso = error => { mensaje.textContent = error.message; mensaje.className = 'error'; };
  async function peticion(url, opciones = {}, clave = privado) {
    const respuesta = await fetch(url, {
      ...opciones, cache: 'no-store', signal: AbortSignal.timeout(30000),
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${login}`,
        ...(clave ? { 'X-Resumen-Token': clave } : {}) },
    });
    if (!respuesta.ok) {
      const resultado = await respuesta.json();
      const error = new Error(typeof resultado.detail === 'string' ? resultado.detail : `No se pudo realizar la operación (HTTP ${respuesta.status}).`);
      error.status = respuesta.status;
      throw error;
    }
    return respuesta.json();
  }
  function mostrarAcceso() {
    acceso.hidden = false;
    formulario.hidden = !configurado;
    configuracion.hidden = configurado;
    document.querySelector('#titulo-acceso').textContent = configurado ? 'Desbloquear resumen' : 'Crear contraseña privada';
    document.querySelector('#instrucciones-acceso').textContent = configurado
      ? 'Introduce tu contraseña privada para consultar las cifras.'
      : 'Confirma tu contraseña de administrador y crea otra distinta. Guárdala en un lugar seguro; no puede consultarse después.';
    document.querySelector('#clave-anterior-campo').hidden = !configurado;
    document.querySelector('#clave-anterior').required = configurado;
    document.querySelector('#cancelar-clave').hidden = !configurado;
  }
  function cerrar() {
    generacion++;
    const anterior = privado;
    privado = null;
    clearTimeout(temporizador);
    formulario.reset();
    configuracion.reset();
    mostrarAcceso();
    bloquear.hidden = true;
    document.dispatchEvent(new Event('resumen-bloqueado'));
    if (anterior) peticion('/resumen-privado/cerrar', { method: 'POST', keepalive: true }, anterior)
      .catch(error => { aviso(new Error(`Bloqueado en esta pantalla. No se pudo cerrar el acceso en el servidor: ${error.message}`)); });
  }
  window.AlucarpinPrivado = {
    cerrar,
    async obtener(url) {
      const actual = privado;
      if (!actual) throw new Error('El resumen está bloqueado.');
      try {
        const resultado = await peticion(url);
        if (actual !== privado || document.hidden) throw new Error('El resumen está bloqueado.');
        return resultado;
      } catch (error) {
        if (actual === privado && [401, 403].includes(error.status)) cerrar();
        throw error;
      }
    },
    abierto: () => Boolean(privado),
  };
  async function estado() {
    reintentar.hidden = true;
    try {
      const resultado = await peticion('/resumen-privado/estado');
      configurado = resultado.configurado;
      mostrarAcceso();
    } catch (error) {
      aviso(error);
      reintentar.hidden = false;
    }
  }
  formulario.addEventListener('submit', async event => {
    event.preventDefault();
    const boton = formulario.querySelector('button[type="submit"]');
    const actual = generacion;
    boton.disabled = true;
    mensaje.textContent = 'Comprobando contraseña…';
    try {
      const resultado = await peticion('/resumen-privado/abrir', {
        method: 'POST', body: JSON.stringify({ password: document.querySelector('#clave-privada').value }),
      });
      formulario.reset();
      if (actual !== generacion || document.hidden) {
        await peticion('/resumen-privado/cerrar', { method: 'POST' }, resultado.token);
        return;
      }
      privado = resultado.token;
      acceso.hidden = true;
      bloquear.hidden = false;
      mensaje.textContent = '';
      temporizador = setTimeout(cerrar, resultado.duracion_segundos * 1000);
      document.dispatchEvent(new Event('resumen-desbloqueado'));
    } catch (error) { aviso(error); }
    finally { boton.disabled = false; }
  });
  configuracion.addEventListener('submit', async event => {
    event.preventDefault();
    const nueva = document.querySelector('#clave-nueva').value;
    if (nueva !== document.querySelector('#clave-confirmar').value) {
      aviso(new Error('Las nuevas contraseñas no coinciden.'));
      return;
    }
    const boton = configuracion.querySelector('button[type="submit"]');
    boton.disabled = true;
    try {
      await peticion('/resumen-privado/configuracion', { method: 'PUT', body: JSON.stringify({
        password_admin: document.querySelector('#clave-admin').value,
        password_nueva: nueva,
        password_actual: configurado ? document.querySelector('#clave-anterior').value : null,
      }) });
      configuracion.reset();
      configurado = true;
      mostrarAcceso();
      mensaje.className = '';
      mensaje.textContent = 'Contraseña privada guardada. Introdúcela para abrir el resumen.';
    } catch (error) { aviso(error); }
    finally { boton.disabled = false; }
  });
  document.querySelector('#cambiar-clave').onclick = () => {
    formulario.reset();
    formulario.hidden = true;
    configuracion.hidden = false;
  };
  document.querySelector('#cancelar-clave').onclick = () => { configuracion.reset(); mostrarAcceso(); };
  bloquear.onclick = cerrar;
  reintentar.onclick = estado;
  document.addEventListener('visibilitychange', () => { if (document.hidden) cerrar(); });
  window.addEventListener('pagehide', cerrar);
  window.addEventListener('pageshow', event => { if (event.persisted) cerrar(); });
  window.addEventListener('storage', event => { if (event.key === 'alucarpin_token') cerrar(); });
  estado();
})();
