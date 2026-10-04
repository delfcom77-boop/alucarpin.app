CREATE TABLE IF NOT EXISTS jornadas_faenas (
    id BIGSERIAL PRIMARY KEY,
    faena_id BIGINT NOT NULL REFERENCES faenas(id) ON DELETE RESTRICT,
    fecha DATE NOT NULL,
    importe DOUBLE PRECISION NOT NULL DEFAULT 400,
    estado_cobro TEXT NOT NULL DEFAULT 'Pendiente'
        CHECK (estado_cobro IN ('Pendiente', 'Cobrado')),
    fecha_cobro DATE,
    forma_pago TEXT NOT NULL DEFAULT 'Efectivo',
    pago_faena_id BIGINT REFERENCES pagos_faenas(id) ON DELETE RESTRICT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (faena_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_jornadas_faenas_faena_fecha
    ON jornadas_faenas (faena_id, fecha);