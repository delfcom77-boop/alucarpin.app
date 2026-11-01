import contextlib
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import api_central
import psycopg
from psycopg.rows import dict_row


ESQUEMA_CONVERSION = """
    CREATE TABLE citas_agenda (
        id INTEGER PRIMARY KEY, fecha TEXT, hora TEXT, tipo TEXT, cliente TEXT,
        ubicacion TEXT, poblacion TEXT, observaciones TEXT, estado TEXT,
        actualizado_en TEXT, convertida_en TIMESTAMP
    );
    CREATE TABLE faenas (
        id INTEGER PRIMARY KEY, cliente TEXT, obra TEXT, fecha TEXT,
        ubicacion TEXT, poblacion TEXT, precio REAL, ayudantes TEXT, estado_revision TEXT
    );
    CREATE TABLE presupuestos (
        id INTEGER PRIMARY KEY, cliente TEXT, num_presupuesto TEXT, fecha TEXT,
        bruto REAL, iva REAL, total_iva REAL, presupuesto_iva REAL, efectivo REAL,
        estado TEXT, presupuesto_final REAL, estado_revision TEXT
    );
    CREATE TABLE trabajos_propios (
        id INTEGER PRIMARY KEY, tipo TEXT, fecha_inicio TEXT, cliente TEXT, obra TEXT,
        ubicacion TEXT, poblacion TEXT, observaciones TEXT, importe REAL,
        estado_cobro TEXT, estado_revision TEXT
    );
    INSERT INTO citas_agenda (id,fecha,hora,tipo,cliente,estado)
    VALUES (1,'2026-11-01','09:00','faena','Prueba','Pendiente');
"""


class ConversionCitaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(ESQUEMA_CONVERSION)
        self.addCleanup(self.db.close)

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        self.enterContext(patch.object(api_central, "conexion", conexion))

    def convertir(self):
        return api_central.convertir_cita(1, {"rol": "administrador"})

    def test_tres_tipos_crean_un_solo_trabajo_incluso_tras_reabrir(self):
        for tipo, tabla, origen in (
            ("faena", "faenas", "faena"),
            ("presupuesto", "presupuestos", "presupuesto"),
            ("reparacion", "trabajos_propios", "propio"),
        ):
            with self.subTest(tipo=tipo):
                self.db.execute("UPDATE citas_agenda SET tipo=?, estado='Pendiente', convertida_en=NULL", (tipo,))
                self.db.commit()
                resultado = self.convertir()
                self.assertEqual(resultado["origen"], origen)
                self.assertEqual(resultado["origen_id"], resultado["trabajo"]["id"])
                cita = self.db.execute("SELECT * FROM citas_agenda").fetchone()
                self.assertEqual(cita["estado"], "Realizada")
                self.assertIsNotNone(cita["convertida_en"])
                for reabrir in (False, True):
                    if reabrir:
                        api_central.modificar_estado_cita(
                            1, api_central.CitaEstadoUpdate(estado="Pendiente"), {},
                        )
                    with self.assertRaises(api_central.HTTPException) as error:
                        self.convertir()
                    self.assertEqual(error.exception.status_code, 409)
                    self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], 1)

    def test_estados_no_pendientes_no_crean_trabajo(self):
        for estado in ("Cancelada", "Realizada", "Archivado"):
            with self.subTest(estado=estado):
                self.db.execute("UPDATE citas_agenda SET estado=?", (estado,))
                self.db.commit()
                with self.assertRaises(api_central.HTTPException) as error:
                    self.convertir()
                self.assertEqual(error.exception.status_code, 409)
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM faenas").fetchone()[0], 0)

    def test_inexistente_y_tipo_no_contable_no_guardan_marca(self):
        self.db.execute("UPDATE citas_agenda SET tipo='visita'")
        self.db.commit()
        with self.assertRaises(api_central.HTTPException) as error:
            self.convertir()
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(tuple(self.db.execute("SELECT estado,convertida_en FROM citas_agenda").fetchone()), ("Pendiente", None))
        self.db.execute("DELETE FROM citas_agenda")
        self.db.commit()
        with self.assertRaises(api_central.HTTPException) as error:
            self.convertir()
        self.assertEqual(error.exception.status_code, 404)

    def test_fallo_insercion_revierte_estado_y_marca(self):
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON faenas BEGIN SELECT RAISE(ABORT,'Fallo ficticio'); END")
        with self.assertRaises(api_central.HTTPException) as error:
            self.convertir()
        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(tuple(self.db.execute("SELECT estado,convertida_en FROM citas_agenda").fetchone()), ("Pendiente", None))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM faenas").fetchone()[0], 0)

    def test_peticiones_simultaneas_crean_un_solo_trabajo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "prueba.db"
            with contextlib.closing(sqlite3.connect(ruta)) as db:
                db.executescript(ESQUEMA_CONVERSION)

            @contextlib.contextmanager
            def conexion():
                with contextlib.closing(sqlite3.connect(ruta, timeout=10)) as db:
                    db.row_factory = sqlite3.Row
                    with db:
                        yield db

            def intentar(_):
                try:
                    self.convertir()
                    return 201
                except api_central.HTTPException as error:
                    return error.status_code

            with patch.object(api_central, "conexion", conexion), ThreadPoolExecutor(max_workers=2) as pool:
                estados = list(pool.map(intentar, range(2)))
            self.assertCountEqual(estados, [201, 409])
            with contextlib.closing(sqlite3.connect(ruta)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM faenas").fetchone()[0], 1)

    @unittest.skipUnless(os.getenv("DATABASE_URL"), "Requiere PostgreSQL; solo tablas temporales")
    def test_postgres_bloquea_repeticion_sin_tocar_tablas_reales(self):
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=15) as db:
            db.execute("SET LOCAL statement_timeout='15s'")
            esquema = ESQUEMA_CONVERSION.replace("CREATE TABLE", "CREATE TEMP TABLE").replace(
                "INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
            db.execute(esquema)
            adaptador = SimpleNamespace(execute=lambda sql, params=(): db.execute(sql.replace("?", "%s"), params))
            with patch.object(api_central, "conexion", return_value=contextlib.nullcontext(adaptador)):
                self.convertir()
                with self.assertRaises(api_central.HTTPException) as error:
                    self.convertir()
                self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM pg_temp.faenas").fetchone()["n"], 1)
            db.rollback()


class ActualizarEstadoCitaTests(unittest.TestCase):
    def test_cambia_solo_el_estado_de_la_cita(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE citas_agenda ("
            "id INTEGER PRIMARY KEY, fecha TEXT, hora TEXT, tipo TEXT, "
            "cliente TEXT, estado TEXT, actualizado_en TEXT)"
        )
        db.execute(
            "INSERT INTO citas_agenda "
            "(id, fecha, hora, tipo, cliente, estado) "
            "VALUES (1, '2026-10-04', '09:00:00', 'visita', 'Cliente', 'Pendiente')"
        )

        @contextlib.contextmanager
        def conexion_falsa():
            yield db

        try:
            with patch.object(api_central, "conexion", conexion_falsa):
                resultado = api_central.modificar_estado_cita(
                    1,
                    api_central.CitaEstadoUpdate(estado="Realizada"),
                    {"rol": "administrador"},
                )

            self.assertEqual(resultado["estado"], "Realizada")
            self.assertEqual(resultado["hora"], "09:00:00")
            self.assertEqual(resultado["cliente"], "Cliente")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
