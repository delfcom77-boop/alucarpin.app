CREATE TABLE IF NOT EXISTS ayudantes (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    usuario TEXT NOT NULL UNIQUE,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL,
    ayudante_id INTEGER UNIQUE REFERENCES ayudantes(id),
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fichajes_ayudantes (
    id BIGSERIAL PRIMARY KEY,
    ayudante_id INTEGER NOT NULL REFERENCES ayudantes(id),
    fecha DATE NOT NULL,
    tipo_destino TEXT NOT NULL DEFAULT 'faena',
    cliente TEXT NOT NULL DEFAULT '',
    obra TEXT NOT NULL,
    ubicacion TEXT NOT NULL DEFAULT '',
    poblacion TEXT NOT NULL DEFAULT '',
    num_presupuesto TEXT,
    confirmado_ayudante INTEGER NOT NULL DEFAULT 1,
    sincronizado INTEGER NOT NULL DEFAULT 0,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ayudante_id, fecha, cliente, obra, ubicacion, poblacion)
);

CREATE TABLE IF NOT EXISTS liquidaciones (
    id BIGSERIAL PRIMARY KEY,
    ayudante_id INTEGER NOT NULL REFERENCES ayudantes(id),
    desde DATE NOT NULL,
    hasta DATE NOT NULL,
    precio_dia DOUBLE PRECISION NOT NULL,
    importe_pagado DOUBLE PRECISION NOT NULL DEFAULT 0,
    fecha_pago DATE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fichajes_ayudante_fecha
    ON fichajes_ayudantes (ayudante_id, fecha);

CREATE INDEX IF NOT EXISTS idx_liquidaciones_ayudante
    ON liquidaciones (ayudante_id);

CREATE TABLE IF NOT EXISTS trabajos_propios (
    id BIGSERIAL PRIMARY KEY,
    tipo TEXT NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    cliente TEXT NOT NULL,
    obra TEXT NOT NULL,
    ubicacion TEXT NOT NULL DEFAULT '',
    poblacion TEXT NOT NULL DEFAULT '',
    observaciones TEXT NOT NULL DEFAULT '',
    num_presupuesto TEXT,
    importe DOUBLE PRECISION NOT NULL DEFAULT 0,
    estado_cobro TEXT NOT NULL DEFAULT 'No cobrado',
    forma_pago TEXT NOT NULL DEFAULT '',
    fecha_cobro DATE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trabajos_propios_fecha
    ON trabajos_propios (fecha_inicio);

CREATE TABLE IF NOT EXISTS citas_agenda (
    id BIGSERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    hora TEXT NOT NULL,
    duracion_minutos INTEGER NOT NULL DEFAULT 60,
    tipo TEXT NOT NULL DEFAULT 'visita',
    cliente TEXT NOT NULL DEFAULT '',
    ubicacion TEXT NOT NULL DEFAULT '',
    poblacion TEXT NOT NULL DEFAULT '',
    telefono TEXT NOT NULL DEFAULT '',
    observaciones TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'Pendiente',
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_citas_agenda_fecha_hora
    ON citas_agenda (fecha, hora);

CREATE TABLE IF NOT EXISTS seguimientos_agenda (
    id BIGSERIAL PRIMARY KEY,
    fecha_llamada DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_recordatorio DATE NOT NULL,
    hora TEXT NOT NULL,
    cliente TEXT NOT NULL DEFAULT '',
    telefono TEXT NOT NULL DEFAULT '',
    motivo TEXT NOT NULL,
    observaciones TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'Pendiente',
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_seguimientos_agenda_estado_fecha
    ON seguimientos_agenda (estado, fecha_recordatorio, hora);

ALTER TABLE seguimientos_agenda
    ADD COLUMN IF NOT EXISTS fecha_llamada DATE;

UPDATE seguimientos_agenda
SET fecha_llamada = fecha_recordatorio
WHERE fecha_llamada IS NULL;

ALTER TABLE seguimientos_agenda
    ALTER COLUMN fecha_llamada SET DEFAULT CURRENT_DATE;

ALTER TABLE seguimientos_agenda
    ALTER COLUMN fecha_llamada SET NOT NULL;

ALTER TABLE fichajes_ayudantes
    ADD COLUMN IF NOT EXISTS num_presupuesto TEXT;

ALTER TABLE ayudantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE fichajes_ayudantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE liquidaciones ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION alucarpin_rellenar_fechas()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.creado_en IS NULL THEN
        NEW.creado_en := CURRENT_TIMESTAMP;
    END IF;
    IF NEW.actualizado_en IS NULL THEN
        NEW.actualizado_en := CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_trabajos_propios_fechas ON trabajos_propios;
CREATE TRIGGER trg_trabajos_propios_fechas
BEFORE INSERT OR UPDATE ON trabajos_propios
FOR EACH ROW EXECUTE FUNCTION alucarpin_rellenar_fechas();

DROP TRIGGER IF EXISTS trg_citas_agenda_fechas ON citas_agenda;
CREATE TRIGGER trg_citas_agenda_fechas
BEFORE INSERT OR UPDATE ON citas_agenda
FOR EACH ROW EXECUTE FUNCTION alucarpin_rellenar_fechas();

DROP TRIGGER IF EXISTS trg_seguimientos_agenda_fechas ON seguimientos_agenda;
CREATE TRIGGER trg_seguimientos_agenda_fechas
BEFORE INSERT OR UPDATE ON seguimientos_agenda
FOR EACH ROW EXECUTE FUNCTION alucarpin_rellenar_fechas();

UPDATE trabajos_propios
SET creado_en = COALESCE(creado_en, CURRENT_TIMESTAMP),
    actualizado_en = COALESCE(actualizado_en, CURRENT_TIMESTAMP)
WHERE creado_en IS NULL OR actualizado_en IS NULL;

UPDATE citas_agenda
SET creado_en = COALESCE(creado_en, CURRENT_TIMESTAMP),
    actualizado_en = COALESCE(actualizado_en, CURRENT_TIMESTAMP)
WHERE creado_en IS NULL OR actualizado_en IS NULL;

UPDATE seguimientos_agenda
SET creado_en = COALESCE(creado_en, CURRENT_TIMESTAMP),
    actualizado_en = COALESCE(actualizado_en, CURRENT_TIMESTAMP)
WHERE creado_en IS NULL OR actualizado_en IS NULL;