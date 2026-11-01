import contextlib
import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
import psycopg

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from costes_ayudantes import consultar_costes, costes_destino, guardar_imputacion, inicializar_imputaciones
from imputaciones_api import crear_imputaciones


class ImputacionesAyudantesTests(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        ruta = Path(carpeta.name) / "costes.db"

        @contextlib.contextmanager
        def conexion():
            db = sqlite3.connect(ruta)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                with db:
                    yield db
            finally:
                db.close()

        self.conexion = conexion
        with conexion() as db:
            db.executescript("""
                CREATE TABLE ayudantes(id INTEGER PRIMARY KEY, nombre TEXT);
                INSERT INTO ayudantes VALUES(1,'Dani'),(2,'Desire');
                CREATE TABLE faenas(id INTEGER PRIMARY KEY, cliente TEXT, obra TEXT);
                INSERT INTO faenas VALUES(10,'Cliente','Obra A'),(20,'Otro','Obra B');
                CREATE TABLE presupuestos(id INTEGER PRIMARY KEY, cliente TEXT, num_presupuesto TEXT);
                INSERT INTO presupuestos VALUES(30,'Cliente','P30');
                CREATE TABLE trabajos_propios(id INTEGER PRIMARY KEY, tipo TEXT, cliente TEXT, obra TEXT);
                INSERT INTO trabajos_propios VALUES(40,'reparacion','Cliente','Puerta'),
                    (50,'alucarpin','Alucarpin','Oficina'),(51,'alucarpin','Alucarpin','Preparar');
                CREATE TABLE fichajes_ayudantes(id INTEGER PRIMARY KEY, ayudante_id INTEGER, fecha TEXT,
                    cliente TEXT, obra TEXT, ubicacion TEXT, faena_id_vinculada INTEGER, num_presupuesto TEXT);
                INSERT INTO fichajes_ayudantes VALUES
                    (1,1,'2026-10-01','Cliente','Obra A','',10,NULL),
                    (2,1,'2026-10-01','Otro','Obra B','',20,NULL),
                    (3,2,'2026-10-01','Cliente','Obra A','',10,NULL);
                CREATE TABLE pagos_jornadas(id INTEGER PRIMARY KEY, fichaje_id INTEGER,
                    importe REAL, importe_pagado REAL, forma_pago TEXT);
                CREATE TABLE gastos_faenas_extras(id INTEGER PRIMARY KEY, faena_id INTEGER,
                    categoria TEXT, concepto TEXT, proveedor TEXT, fecha TEXT, importe REAL, importe_pagado REAL);
                CREATE TABLE gastos_presupuestos(id INTEGER PRIMARY KEY, num_presupuesto TEXT,
                    categoria TEXT, proveedor TEXT, fecha TEXT, importe REAL, importe_pagado REAL);
            """)
            inicializar_imputaciones(db)
        self.rol = "administrador"

        def administrador():
            if self.rol != "administrador":
                raise HTTPException(403, "Solo administrador")
            return {}

        app = FastAPI()
        app.include_router(crear_imputaciones(conexion, administrador))
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def guardar(self, destino="alucarpin", ident=None, version=0, ayudante=1, fecha="2026-10-01"):
        return self.client.put(f"/costes-ayudantes/{ayudante}/{fecha}",
                              json={"destino": destino, "id": ident, "version": version})

    def costes(self):
        r = self.client.get("/costes-ayudantes?fecha=2026-10-01")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["costes"]

    def test_varios_sitios_y_actividades_no_multiplican_coste(self):
        costes = self.costes()
        self.assertEqual(len(costes), 2)
        self.assertEqual(sum(c["importe"] for c in costes), 100)
        self.assertEqual(len(costes[0]["lugares"]), 2)
        self.assertTrue(all(not c["registrado"] for c in costes))
        with self.conexion() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pagos_jornadas").fetchone()[0], 0)

    def test_general_y_obra_son_independientes_de_la_actividad_propia(self):
        self.assertEqual(self.guardar().status_code, 200)
        self.assertEqual(self.guardar("faena", 20, ayudante=2).status_code, 200)
        costes = self.costes()
        self.assertEqual(sum(c["importe"] for c in costes), 100)
        self.assertEqual(costes[0]["imputacion"]["destino"], "alucarpin")
        with self.conexion() as db:
            de_obra, _ = costes_destino(db, "faena", 20)
            self.assertEqual([c["ayudante_id"] for c in de_obra], [2])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM trabajos_propios").fetchone()[0], 3)

    def test_mover_destino_retira_el_coste_anterior_sin_crear_pago(self):
        self.assertEqual(self.guardar("faena", 10).status_code, 200)
        self.assertEqual(self.guardar("faena", 20, version=1).status_code, 200)
        with self.conexion() as db:
            self.assertEqual(costes_destino(db, "faena", 10)[0], [])
            self.assertEqual(len(costes_destino(db, "faena", 20)[0]), 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pagos_jornadas").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM imputaciones_ayudantes").fetchone()[0], 1)

    def test_pago_parcial_no_cambia_y_coste_global_es_identico(self):
        with self.conexion() as db:
            db.execute("INSERT INTO pagos_jornadas VALUES(1,2,80,30,'Transferencia')")
            antes = [(c["importe"], c["importe_pagado"], c["pendiente"]) for c in consultar_costes(db)[0]]
            pagos = tuple(db.execute("SELECT * FROM pagos_jornadas").fetchone())
        self.assertEqual(self.guardar("presupuesto", 30).status_code, 200)
        with self.conexion() as db:
            despues = [(c["importe"], c["importe_pagado"], c["pendiente"]) for c in consultar_costes(db)[0]]
            self.assertEqual(antes, despues)
            self.assertEqual(pagos, tuple(db.execute("SELECT * FROM pagos_jornadas").fetchone()))
        self.assertEqual(self.costes()[0]["estado_pago"], "Parcial")

    def test_historico_se_sustituye_una_vez_sin_borrarlo(self):
        with self.conexion() as db:
            db.execute("INSERT INTO gastos_faenas_extras VALUES(9,10,'Ayudantes','Jornada','Dani','2026-10-01',60,20)")
        self.assertEqual(self.guardar("faena", 20).status_code, 200)
        with self.conexion() as db:
            costes, usados = costes_destino(db, "faena", 20)
            self.assertEqual(costes[0]["importe"], 60)
            self.assertEqual(usados, {("faena", 9)})
            self.assertEqual(db.execute("SELECT COUNT(*) FROM gastos_faenas_extras").fetchone()[0], 1)
        self.assertEqual(sum(c["importe"] for c in self.costes()), 110)

    def test_pago_directo_prevalece_al_historico(self):
        with self.conexion() as db:
            db.execute("INSERT INTO gastos_faenas_extras VALUES(9,10,'Ayudantes','Jornada','Dani','2026-10-01',60,60)")
            db.execute("INSERT INTO pagos_jornadas VALUES(1,1,80,30,'Efectivo')")
        self.assertEqual(self.guardar("propio", 40).status_code, 200)
        coste = self.costes()[0]
        self.assertEqual((coste["importe"], coste["importe_pagado"]), (80, 30))

    def test_conflicto_y_reintento_idempotente(self):
        r = self.guardar("faena", 10)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.guardar("faena", 10).json()["version"], 1)
        self.assertEqual(self.guardar("faena", 20).status_code, 409)
        self.assertEqual(self.guardar(version=1).json()["version"], 2)
        self.assertEqual(self.guardar("faena", 10).status_code, 409)

    def test_no_imputa_pago_duplicado(self):
        with self.conexion() as db:
            db.execute("INSERT INTO pagos_jornadas VALUES(1,1,50,20,'Efectivo')")
            db.execute("INSERT INTO pagos_jornadas VALUES(2,2,50,20,'Efectivo')")
        self.assertTrue(self.costes()[0]["revision"])
        self.assertEqual(self.guardar().status_code, 409)

    def test_valida_dia_destino_y_version(self):
        for argumentos in (
            {"ayudante": 99}, {"fecha": "2026-09-30"},
            {"fecha": (date.today() + timedelta(days=1)).isoformat()},
            {"destino": "faena", "ident": 999}, {"destino": "faena"},
            {"ident": 10}, {"destino": "propio", "ident": 50}, {"version": 2},
        ):
            with self.subTest(argumentos=argumentos):
                self.assertEqual(self.guardar(**argumentos).status_code, 409)
        with self.conexion() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM imputaciones_ayudantes").fetchone()[0], 0)

    def test_acceso_solo_administrador(self):
        self.rol = "ayudante"
        self.assertEqual(self.guardar().status_code, 403)
        self.assertEqual(self.client.get("/costes-ayudantes?fecha=2026-10-01").status_code, 403)

    def test_no_ofrece_actividad_interna_como_obra(self):
        datos = self.client.get("/costes-ayudantes?fecha=2026-10-01").json()
        self.assertEqual([d["id"] for d in datos["destinos"] if d["destino"] == "propio"], [40])

    def test_transaccion_fallida_no_deja_asignacion(self):
        with self.assertRaisesRegex(RuntimeError, "Interrumpido"):
            with self.conexion() as db:
                guardar_imputacion(db, 1, date(2026, 10, 1), "faena", 10, 0)
                raise RuntimeError("Interrumpido")
        self.assertIsNone(self.costes()[0]["imputacion"])


@unittest.skipUnless(os.getenv("DATABASE_URL"), "Solo PostgreSQL temporal con rollback")
class ImputacionPostgresTests(unittest.TestCase):
    def test_guardado_reintento_y_cambio_en_tablas_temporales(self):
        class Remoto:
            def __init__(self, db):
                self.db = db

            def execute(self, sql, parametros=()):
                return self.db.execute(sql.replace("?", "%s"), parametros)

        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15) as pg:
            try:
                pg.execute("SET LOCAL search_path=pg_temp")
                pg.execute("SET LOCAL statement_timeout='15000'")
                pg.execute("""
                    CREATE TEMP TABLE ayudantes(id BIGINT PRIMARY KEY,nombre TEXT);
                    INSERT INTO ayudantes VALUES(1,'Prueba');
                    CREATE TEMP TABLE faenas(id BIGINT PRIMARY KEY);
                    INSERT INTO faenas VALUES(10),(20);
                    CREATE TEMP TABLE presupuestos(id BIGINT PRIMARY KEY);
                    CREATE TEMP TABLE trabajos_propios(id BIGINT PRIMARY KEY,tipo TEXT);
                    CREATE TEMP TABLE fichajes_ayudantes(id BIGINT PRIMARY KEY,ayudante_id BIGINT,fecha DATE);
                    INSERT INTO fichajes_ayudantes VALUES(1,1,'2026-10-01'),(2,1,'2026-10-01');
                    CREATE TEMP TABLE pagos_jornadas(fichaje_id BIGINT,importe DOUBLE PRECISION,importe_pagado DOUBLE PRECISION);
                    INSERT INTO pagos_jornadas VALUES(1,70,20);
                """)
                remoto = Remoto(pg)
                inicializar_imputaciones(remoto)
                inicializar_imputaciones(remoto)
                f = date(2026, 10, 1)
                guardar_imputacion(remoto, 1, f, "faena", 10, 0, True)
                self.assertEqual(guardar_imputacion(remoto, 1, f, "faena", 10, 0, True)["version"], 1)
                guardar_imputacion(remoto, 1, f, "faena", 20, 1, True)
                self.assertEqual(costes_destino(remoto, "faena", 10, True)[0], [])
                self.assertEqual(costes_destino(remoto, "faena", 20, True)[0][0]["importe"], 70)
                self.assertEqual(pg.execute("SELECT COUNT(*) FROM pagos_jornadas").fetchone()[0], 1)
            finally:
                pg.rollback()
