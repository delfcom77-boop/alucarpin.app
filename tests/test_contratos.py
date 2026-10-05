from pathlib import Path
import unittest
from unittest.mock import patch


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

    def test_conexion_no_cambia_a_sqlite_si_database_url_es_invalida(self):
        import importlib
        api = importlib.import_module("api_central")
        with (patch.object(api, "DATABASE_URL", "postgresql://bad"),
              patch.object(api, "ConexionPostgres", side_effect=api.psycopg.OperationalError("Prueba")),
              patch.object(api.sqlite3, "connect") as local,
              self.assertLogs(api.logger, level="ERROR")):
            with self.assertRaises(api.HTTPException) as error:
                api.conexion()
        self.assertEqual(error.exception.status_code, 503)
        local.assert_not_called()
