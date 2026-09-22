import os
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def leer(nombre):
    return (ROOT / nombre).read_text(encoding="utf-8")


class ContratosTests(unittest.TestCase):
    def test_schema_incluye_pagos_y_revision(self):
        schema = leer("supabase_schema.sql")
        self.assertIn("CREATE TABLE IF NOT EXISTS pagos_jornadas", schema)
        self.assertIn("ADD COLUMN IF NOT EXISTS estado_revision", schema)
        self.assertIn("ADD COLUMN IF NOT EXISTS presupuesto_id", schema)
        self.assertIn("ADD COLUMN IF NOT EXISTS trabajo_propio_id", schema)


    def test_api_crea_y_valida_los_tres_tipos(self):
        api = leer("api_central.py")
        self.assertIn('Literal["pendiente", "faena", "presupuesto", "reparacion"]', api)
        self.assertIn('@app.patch("/fichajes/{fichaje_id}/validacion")', api)
        self.assertIn('estado_revision = "Pendiente de revisar"', api)


    def test_documentacion_menciona_pago_independiente(self):
        readme = leer("README.md")
        self.assertIn("pagos_jornadas", readme)
        self.assertIn("Pendiente de revisar", readme)

    def test_conexion_fallback_a_sqlite_si_database_url_es_invalida(self):
        import importlib
        api = importlib.import_module("api_central")
        valor_anterior = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://bad"
        try:
            with api.conexion() as db:
                fila = db.execute("SELECT 1 AS ok").fetchone()
                self.assertEqual(fila["ok"], 1)
        finally:
            if valor_anterior is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = valor_anterior
