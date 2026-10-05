(() => {
  const normalizar = valor => String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().replace(/\s+/g, ' ').toLocaleLowerCase('es');
  const tipoDe = fichaje => fichaje.tipo_destino || 'faena';
  const mostrarTipo = tipo => ({
    faena: 'Faena a 3º',
    presupuesto: 'Presupuesto Alucarpin',
    reparacion: 'Reparación',
    pendiente: 'Pendiente de vincular',
  }[tipo] || tipo);

  function filtrar(registros, filtros = {}) {
    if (filtros.desde && filtros.hasta && filtros.desde > filtros.hasta) {
      throw new Error('La fecha desde no puede ser posterior a la fecha hasta.');
    }
    return registros.filter(fichaje =>
      (!filtros.tipo || tipoDe(fichaje) === filtros.tipo)
      && (!filtros.cliente || normalizar(fichaje.cliente) === filtros.cliente)
      && (!filtros.ayudante || String(fichaje.ayudante_id) === filtros.ayudante)
      && (!filtros.obra || normalizar(fichaje.obra).includes(normalizar(filtros.obra)))
      && (!filtros.desde || fichaje.fecha >= filtros.desde)
      && (!filtros.hasta || fichaje.fecha <= filtros.hasta)
      && (!filtros.estado || fichaje.estadoPago === filtros.estado)
    );
  }

  function resumir(registros, filtros = {}) {
    const filtrados = filtrar(registros, filtros);
    const jornadas = new Set();
    const fechas = new Set();
    const grupos = new Map();
    filtrados.forEach(fichaje => {
      const tipo = tipoDe(fichaje);
      const clave = JSON.stringify([
        String(fichaje.ayudante_id), tipo, normalizar(fichaje.cliente),
        normalizar(fichaje.obra), normalizar(fichaje.ubicacion), normalizar(fichaje.poblacion),
      ]);
      if (!grupos.has(clave)) {
        grupos.set(clave, {
          ayudante: fichaje.nombreAyudante,
          tipo: mostrarTipo(tipo),
          cliente: fichaje.cliente || 'Sin cliente',
          obra: fichaje.obra || 'Sin obra',
          ubicacion: [fichaje.ubicacion, fichaje.poblacion].filter(Boolean).join(' · '),
          fechas: new Set(),
        });
      }
      grupos.get(clave).fechas.add(fichaje.fecha);
      jornadas.add(JSON.stringify([String(fichaje.ayudante_id), fichaje.fecha]));
      fechas.add(fichaje.fecha);
    });
    return {
      dias: jornadas.size,
      fechas: fechas.size,
      grupos: Array.from(grupos.values()).map(grupo => ({
        ayudante: grupo.ayudante,
        tipo: grupo.tipo,
        cliente: grupo.cliente,
        obra: grupo.obra,
        ubicacion: grupo.ubicacion,
        dias: grupo.fechas.size,
      })).sort((a, b) =>
        a.cliente.localeCompare(b.cliente, 'es')
        || a.obra.localeCompare(b.obra, 'es')
        || a.ayudante.localeCompare(b.ayudante, 'es')
      ),
    };
  }

  window.AlucarpinJornadas = { normalizar, mostrarTipo, filtrar, resumir };
})();
