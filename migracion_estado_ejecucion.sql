CREATE TABLE IF NOT EXISTS estados_ejecucion_trabajos (
    trabajo_id INTEGER PRIMARY KEY REFERENCES trabajos_propios(id) ON DELETE CASCADE,
    estado TEXT NOT NULL CHECK (estado IN ('Pendiente', 'Terminado')),
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS estados_ejecucion_faenas (
    faena_id BIGINT PRIMARY KEY REFERENCES faenas(id) ON DELETE CASCADE,
    estado TEXT NOT NULL CHECK (estado IN ('Pendiente', 'Terminado')),
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS estados_ejecucion_presupuestos (
    presupuesto_id BIGINT PRIMARY KEY REFERENCES presupuestos(id) ON DELETE CASCADE,
    estado TEXT NOT NULL CHECK (estado IN ('Pendiente', 'Terminado')),
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
