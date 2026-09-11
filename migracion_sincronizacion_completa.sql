CREATE TABLE IF NOT EXISTS faenas (
    id BIGSERIAL PRIMARY KEY,
    cliente TEXT NOT NULL,
    obra TEXT,
    fecha DATE,
    ubicacion TEXT,
    poblacion TEXT,
    precio DOUBLE PRECISION DEFAULT 0,
    ayudantes TEXT
);

CREATE TABLE IF NOT EXISTS presupuestos (
    id BIGSERIAL PRIMARY KEY,
    cliente TEXT NOT NULL,
    num_presupuesto TEXT UNIQUE,
    fecha DATE,
    bruto DOUBLE PRECISION DEFAULT 0,
    iva DOUBLE PRECISION DEFAULT 0,
    total_iva DOUBLE PRECISION DEFAULT 0,
    presupuesto_iva DOUBLE PRECISION DEFAULT 0,
    efectivo DOUBLE PRECISION DEFAULT 0,
    estado TEXT,
    presupuesto_final DOUBLE PRECISION DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pagos_ingresos (
    id BIGSERIAL PRIMARY KEY,
    num_presupuesto TEXT NOT NULL,
    fecha DATE,
    importe_iva DOUBLE PRECISION DEFAULT 0,
    importe_b DOUBLE PRECISION DEFAULT 0,
    observaciones TEXT,
    forma_pago TEXT DEFAULT 'Transferencia'
);

CREATE TABLE IF NOT EXISTS pagos_faenas (
    id BIGSERIAL PRIMARY KEY,
    faena_id BIGINT NOT NULL REFERENCES faenas(id),
    fecha DATE,
    importe_iva DOUBLE PRECISION DEFAULT 0,
    importe_b DOUBLE PRECISION DEFAULT 0,
    observaciones TEXT,
    forma_pago TEXT DEFAULT 'Transferencia'
);

CREATE TABLE IF NOT EXISTS gastos_presupuestos (
    id BIGSERIAL PRIMARY KEY,
    num_presupuesto TEXT NOT NULL,
    concepto TEXT NOT NULL,
    proveedor TEXT,
    fecha DATE,
    importe DOUBLE PRECISION DEFAULT 0,
    bruto DOUBLE PRECISION DEFAULT 0,
    iva DOUBLE PRECISION DEFAULT 0,
    estado_pago TEXT,
    forma_pago TEXT,
    fecha_extra DATE,
    tipo_iva TEXT,
    importe_pagado DOUBLE PRECISION DEFAULT 0,
    resto_pago DOUBLE PRECISION DEFAULT 0,
    pagado DOUBLE PRECISION DEFAULT 0,
    numero_documento TEXT,
    categoria TEXT DEFAULT 'Extras'
);

CREATE TABLE IF NOT EXISTS gastos_faenas_extras (
    id BIGSERIAL PRIMARY KEY,
    faena_id BIGINT NOT NULL REFERENCES faenas(id),
    concepto TEXT NOT NULL,
    proveedor TEXT,
    fecha DATE,
    importe DOUBLE PRECISION DEFAULT 0,
    bruto DOUBLE PRECISION DEFAULT 0,
    iva DOUBLE PRECISION DEFAULT 0,
    estado_pago TEXT,
    forma_pago TEXT,
    fecha_extra DATE,
    tipo_iva TEXT,
    importe_pagado DOUBLE PRECISION DEFAULT 0,
    resto_pago DOUBLE PRECISION DEFAULT 0,
    pagado DOUBLE PRECISION DEFAULT 0,
    numero_documento TEXT,
    categoria TEXT DEFAULT 'Extras'
);

CREATE TABLE IF NOT EXISTS pagos_gastos (
    id BIGSERIAL PRIMARY KEY,
    gasto_id BIGINT NOT NULL,
    fecha DATE,
    importe_banco DOUBLE PRECISION DEFAULT 0,
    importe_efectivo DOUBLE PRECISION DEFAULT 0,
    observaciones TEXT,
    tipo_gasto TEXT DEFAULT 'presupuesto',
    importe DOUBLE PRECISION DEFAULT 0,
    forma_pago TEXT DEFAULT 'Transferencia'
);

ALTER TABLE fichajes_ayudantes
    ADD COLUMN IF NOT EXISTS num_presupuesto TEXT;
ALTER TABLE fichajes_ayudantes
    ADD COLUMN IF NOT EXISTS faena_id_vinculada BIGINT;
ALTER TABLE fichajes_ayudantes
    ADD COLUMN IF NOT EXISTS estado_procesamiento TEXT DEFAULT 'Pendiente';
ALTER TABLE fichajes_ayudantes
    ADD COLUMN IF NOT EXISTS gasto_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_faenas_fecha ON faenas (fecha);
CREATE INDEX IF NOT EXISTS idx_presupuestos_numero ON presupuestos (num_presupuesto);
CREATE INDEX IF NOT EXISTS idx_gastos_presupuesto ON gastos_presupuestos (num_presupuesto);
CREATE INDEX IF NOT EXISTS idx_gastos_faena ON gastos_faenas_extras (faena_id);

SELECT setval(pg_get_serial_sequence('faenas', 'id'), COALESCE((SELECT MAX(id) FROM faenas), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('presupuestos', 'id'), COALESCE((SELECT MAX(id) FROM presupuestos), 0) + 1, false);
