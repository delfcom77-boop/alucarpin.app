import contextlib
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import api_central as api


class PresupuestoEdicionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE presupuestos (
                id INTEGER PRIMARY KEY, cliente TEXT, fecha TEXT,
                num_presupuesto TEXT, bruto REAL, iva REAL, total_iva REAL,
                presupuesto_iva REAL, efectivo REAL, presupuesto_final REAL,
                estado TEXT
            );
            CREATE TABLE estados_ejecucion_presupuestos (
                presupuesto_id INTEGER PRIMARY KEY, estado TEXT
            );
            INSERT INTO presupuestos VALUES (
                27, 'Cliente original', '2026-10-05', 'P-27',
                15962.21, 21, 3352.06, 19314.27, 120, 19434.27, 'Aceptado'
            );
        """)

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        cambio = patch.object(api, "conexion", conexion)
        cambio.start()
        self.addCleanup(cambio.stop)

    def test_editar_cliente_fecha_estado_conserva_todos_los_importes(self):
        resultado = api.modificar_presupuesto(
            27, api.PresupuestoUpdate(
                cliente="Cliente cambiado", fecha=date(2026, 10, 6), estado="Completado",
            ), {},
        )
        self.assertEqual(resultado["cliente"], "Cliente cambiado")
        self.assertEqual(resultado["fecha"], "2026-10-06")
        self.assertEqual(resultado["estado"], "Completado")
        self.assertEqual(
            [resultado[k] for k in ("bruto", "iva", "total_iva", "presupuesto_iva", "efectivo", "presupuesto_final")],
            [15962.21, 21, 3352.06, 19314.27, 120, 19434.27],
        )
        self.assertEqual(resultado["num_presupuesto"], "P-27")
        self.assertEqual(self.db.execute(
            "SELECT estado FROM estados_ejecucion_presupuestos WHERE presupuesto_id = 27"
        ).fetchone()["estado"], "Pendiente")

    def test_total_explicito_cero_conserva_desglose_y_estado(self):
        resultado = api.modificar_presupuesto(
            27, api.PresupuestoUpdate(presupuesto_final=0), {},
        )
        self.assertEqual(resultado["presupuesto_final"], 0)
        self.assertEqual(
            [resultado[k] for k in ("bruto", "iva", "total_iva", "presupuesto_iva", "efectivo")],
            [15962.21, 21, 3352.06, 19314.27, 120],
        )
        self.assertEqual(resultado["estado"], "Aceptado")


if __name__ == "__main__":
    unittest.main()
