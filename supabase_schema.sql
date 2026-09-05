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

ALTER TABLE ayudantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE fichajes_ayudantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE liquidaciones ENABLE ROW LEVEL SECURITY;