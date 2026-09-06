-- Ejecutar despues de supabase_schema.sql.
-- Migracion de los datos compatibles de empresa.db.

INSERT INTO ayudantes (id, nombre, activo)
VALUES (6, 'DESIRE', 1)
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre;

INSERT INTO fichajes_ayudantes
    (id, ayudante_id, fecha, tipo_destino, cliente, obra, ubicacion, poblacion,
     confirmado_ayudante, sincronizado)
VALUES
    (1, 6, '2026-09-03', 'faena', 'JACA', 'RYME', 'PLAZA ESPAÑA 1', 'BARCELONA', 1, 1),
    (2, 6, '2026-09-04', 'presupuesto', 'JACA', 'RYME', 'C/ GERANI', 'ESPARREGUERA', 1, 1),
    (3, 6, '2026-09-03', 'faena', 'JACA', 'RYME', 'PLAZA ESPAÑA 2', 'BARCELONA', 1, 1)
ON CONFLICT (id) DO UPDATE SET
    fecha = EXCLUDED.fecha,
    tipo_destino = EXCLUDED.tipo_destino,
    cliente = EXCLUDED.cliente,
    obra = EXCLUDED.obra,
    ubicacion = EXCLUDED.ubicacion,
    poblacion = EXCLUDED.poblacion,
    confirmado_ayudante = EXCLUDED.confirmado_ayudante,
    sincronizado = EXCLUDED.sincronizado;

INSERT INTO liquidaciones
    (id, ayudante_id, desde, hasta, precio_dia, importe_pagado, fecha_pago)
VALUES
    (1, 6, '2026-08-31', '2026-09-04', 50.0, 0.0, NULL),
    (6, 6, '2026-09-03', '2026-09-04', 50.0, 0.0, NULL)
ON CONFLICT (id) DO UPDATE SET
    ayudante_id = EXCLUDED.ayudante_id,
    desde = EXCLUDED.desde,
    hasta = EXCLUDED.hasta,
    precio_dia = EXCLUDED.precio_dia,
    importe_pagado = EXCLUDED.importe_pagado,
    fecha_pago = EXCLUDED.fecha_pago;

SELECT setval(
    pg_get_serial_sequence('fichajes_ayudantes', 'id'),
    COALESCE((SELECT MAX(id) FROM fichajes_ayudantes), 1),
    true
);

SELECT setval(
    pg_get_serial_sequence('liquidaciones', 'id'),
    COALESCE((SELECT MAX(id) FROM liquidaciones), 1),
    true
);
