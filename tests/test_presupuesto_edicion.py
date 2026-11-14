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
        cambio_url = patch.object(api, "DATABASE_URL", None)
        cambio_url.start()
        self.addCleanup(cambio_url.stop)

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

    def test_crear_presupuesto_rechaza_numero_duplicado_aunque_tenga_espacios(self):
        with self.assertRaises(api.HTTPException) as error:
            api.crear_presupuesto(api.PresupuestoCreate(cliente="Otro cliente", num_presupuesto=" P-27 "), {})
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM presupuestos").fetchone()["n"], 1)

    def test_crear_presupuesto_numero_distinto_se_crea_sin_problema(self):
        resultado = api.crear_presupuesto(api.PresupuestoCreate(cliente="Otro cliente", num_presupuesto="P-28"), {})
        self.assertEqual(resultado["num_presupuesto"], "P-28")
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM presupuestos").fetchone()["n"], 2)

    def test_modificar_presupuesto_rechaza_renombrar_a_numero_de_otro(self):
        api.crear_presupuesto(api.PresupuestoCreate(cliente="Otro cliente", num_presupuesto="P-28"), {})
        with self.assertRaises(api.HTTPException) as error:
            api.modificar_presupuesto(27, api.PresupuestoUpdate(num_presupuesto="P-28"), {})
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            self.db.execute("SELECT num_presupuesto FROM presupuestos WHERE id = 27").fetchone()["num_presupuesto"],
            "P-27",
        )

    def test_modificar_presupuesto_conserva_su_propio_numero(self):
        resultado = api.modificar_presupuesto(27, api.PresupuestoUpdate(num_presupuesto=" P-27 "), {})
        self.assertEqual(resultado["num_presupuesto"], "P-27")


if __name__ == "__main__":
    unittest.main()
