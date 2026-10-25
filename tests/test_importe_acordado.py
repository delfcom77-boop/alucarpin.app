import contextlib
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import api_central as api
from importes_faenas import importe_acordado, inicializar_importes
from resumen_economico import calcular_resumen


class ImporteAcordadoTests(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        self.ruta = Path(self.carpeta.name) / "prueba.db"

        @contextlib.contextmanager
        def conexion():
            with contextlib.closing(sqlite3.connect(self.ruta)) as db:
                db.row_factory = sqlite3.Row
                with db:
                    yield db

        self.conexion = conexion
        for parche in (patch.object(api, "DATABASE_URL", ""),
                       patch.object(api, "DATABASE_PATH", self.ruta),
                       patch.object(api, "conexion", conexion)):
            parche.start()
            self.addCleanup(parche.stop)
        api.startup()
        with conexion() as db:
            db.execute(
                "INSERT INTO faenas (id,cliente,obra,fecha,precio,importe_acordado) "
                "VALUES (25,'Decoradora','Obra','2026-09-15',20651.5,18911.5)"
            )
            db.execute(
                "INSERT INTO jornadas_faenas (faena_id,fecha,importe) VALUES (25,'2026-10-13',400)"
            )
            for fecha, banco, efectivo in (
                ("2026-04-23", 8651.5, 0), ("2026-08-06", 0, 4000),
                ("2026-09-28", 0, 2000), ("2026-09-30", 0, 3000),
            ):
                db.execute(
                    "INSERT INTO pagos_faenas (faena_id,fecha,importe_iva,importe_b,forma_pago) "
                    "VALUES (25,?,?,?,?)",
                    (fecha, banco, efectivo, "Efectivo" if efectivo else "Transferencia"),
                )

    def test_listado_alarmas_y_resumen_no_confunden_total_con_dias(self):
        trabajo = next(t for t in api.listar_trabajos({}) if t["origen"] == "faena")
        self.assertEqual(trabajo["importe"], 18911.5)
        self.assertEqual(trabajo["pendiente_cobro"], 1260)
        with self.conexion() as db:
            estados = api.consultar_estados_obras(db)
            self.assertEqual(estados[0]["importe"], 18911.5)
            self.assertEqual(estados[0]["pendiente_cobro"], 1260)
            db.execute(
                "INSERT INTO pagos_faenas (faena_id,fecha,importe_iva,importe_b,forma_pago) "
                "VALUES (25,'2026-10-21',0,1260,'Efectivo')"
            )
        trabajo = next(t for t in api.listar_trabajos({}) if t["origen"] == "faena")
        self.assertEqual(trabajo["importe_cobrado"], 18911.5)
        self.assertEqual(trabajo["pendiente_cobro"], 0)
        self.assertFalse(any(a["tipo"] == "cobro" and a.get("origen") == "faena"
                             for a in api.listar_alarmas({})))
        with self.conexion() as db:
            resumen = calcular_resumen(db, date(2026, 1, 1), date(2026, 12, 31), date(2026, 10, 25))
            self.assertFalse(any(p["tipo"] == "faena" for p in resumen["cobros"]))
            self.assertEqual(db.execute("SELECT importe FROM jornadas_faenas").fetchone()[0], 400)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pagos_faenas").fetchone()[0], 5)
            inicializar_importes(db)
            inicializar_importes(db)

    def test_vacio_conserva_total_anterior_y_cero_es_total_explicito(self):
        with self.conexion() as db:
            db.execute("UPDATE faenas SET importe_acordado=NULL")
        self.assertEqual(api.listar_trabajos({})[0]["importe"], 20651.5)
        with self.conexion() as db:
            db.execute("UPDATE faenas SET importe_acordado=0")
        self.assertEqual(api.listar_trabajos({})[0]["importe"], 0)

    def test_validacion_total(self):
        self.assertIsNone(importe_acordado(""))
        self.assertEqual(importe_acordado("18911,50"), 18911.5)
        for texto in ("NaN", "inf", "-1", "1.001", "18.911,50", "1000000000"):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                importe_acordado(texto)
