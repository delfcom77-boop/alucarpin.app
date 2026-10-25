ALTER TABLE faenas ADD COLUMN IF NOT EXISTS importe_acordado
DOUBLE PRECISION CHECK (importe_acordado >= 0);
