window.AlucarpinExportar = (() => {
  function celda(valor) {
    let texto = String(valor ?? '').replace(/\r?\n/g, ' ');
    if (/^[\s]*[=+\-@]/.test(texto) || /^[\t\r]/.test(texto)) texto = "'" + texto;
    return `"${texto.replace(/"/g, '""')}"`;
  }
  function csv(filas) {
    return '\ufeff' + filas.map(fila => fila.map(celda).join(';')).join('\r\n');
  }
  function descargar(nombre, filas) {
    const enlace = document.createElement('a');
    const url = URL.createObjectURL(new Blob([csv(filas)], { type: 'text/csv;charset=utf-8' }));
    enlace.href = url;
    enlace.download = nombre;
    enlace.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function tabla(tabla, nombre, omitirAcciones = true) {
    const cabeceras = Array.from(tabla.querySelectorAll('thead th'));
    const indices = cabeceras.map((_, i) => i).filter(i => !omitirAcciones || cabeceras[i].textContent.trim() !== 'Acciones');
    const filas = Array.from(tabla.querySelectorAll('tbody tr')).filter(fila =>
      !fila.hidden && !fila.closest('[hidden]') && fila.cells.length === cabeceras.length
    );
    if (!filas.length) throw new Error('No hay filas visibles para exportar.');
    const estadoPago = filas.some(fila => fila.dataset.exportEstado !== undefined);
    descargar(nombre, [
      [...indices.map(i => cabeceras[i].textContent.trim()), ...(estadoPago ? ['Estado de pago'] : [])],
      ...filas.map(fila => [...indices.map(i => fila.cells[i].textContent.trim()), ...(estadoPago ? [fila.dataset.exportEstado || ''] : [])]),
    ]);
    return filas.length;
  }
  return { csv, descargar, tabla };
})();
