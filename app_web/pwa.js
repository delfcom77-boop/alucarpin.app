(() => {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/app/sw.js'));
  }

  let instalacionPendiente;
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    instalacionPendiente = event;
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.textContent = 'Instalar aplicación';
    boton.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:10;border:0;border-radius:8px;padding:12px 16px;background:#d45d3f;color:#fff;font:600 16px Segoe UI,sans-serif;box-shadow:0 4px 12px #0003;cursor:pointer';
    boton.addEventListener('click', async () => {
      boton.remove();
      instalacionPendiente.prompt();
      await instalacionPendiente.userChoice;
      instalacionPendiente = null;
    });
    document.body.appendChild(boton);
  });
})();
