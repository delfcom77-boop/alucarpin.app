import contextlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import api_central as api
from diario_trabajo import crear_diario


class DiarioTrabajoTests(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        ruta = Path(self.carpeta.name) / "diario.db"

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
                CREATE TABLE faenas (id INTEGER PRIMARY KEY, cliente TEXT, obra TEXT, fecha TEXT,
                  ubicacion TEXT, poblacion TEXT, precio REAL, ayudantes TEXT, estado_revision TEXT);
                CREATE TABLE presupuestos (id INTEGER PRIMARY KEY, cliente TEXT, num_presupuesto TEXT,
                  fecha TEXT, bruto REAL, iva REAL, total_iva REAL, presupuesto_iva REAL,
                  efectivo REAL, estado TEXT, presupuesto_final REAL, estado_revision TEXT);
                CREATE TABLE trabajos_propios (id INTEGER PRIMARY KEY, tipo TEXT, fecha_inicio TEXT,
                  cliente TEXT, obra TEXT, ubicacion TEXT, poblacion TEXT, observaciones TEXT,
                  estado_revision TEXT, importe REAL DEFAULT 0, estado_cobro TEXT DEFAULT 'No cobrado');
                CREATE TABLE jornadas_faenas (id INTEGER PRIMARY KEY, faena_id INTEGER REFERENCES faenas,
                  fecha TEXT, UNIQUE(faena_id,fecha));
                CREATE TABLE jornadas_propias (id INTEGER PRIMARY KEY,
                  presupuesto_id INTEGER REFERENCES presupuestos, trabajo_id INTEGER REFERENCES trabajos_propios,
                  fecha TEXT, UNIQUE(presupuesto_id,fecha), UNIQUE(trabajo_id,fecha));
                CREATE TABLE pagos_faenas (id INTEGER PRIMARY KEY);
                CREATE TABLE pagos_ingresos (id INTEGER PRIMARY KEY);
            """)
        self.usuario = {"id": 1, "rol": "administrador"}

        def administrador():
            if self.usuario["rol"] != "administrador":
                raise HTTPException(403, "Solo administrador")
            return self.usuario

        app = FastAPI()
        app.include_router(crear_diario(conexion, administrador))
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def datos(self, tipo="faena", **cambios):
        return {
            "solicitud_id": str(uuid4()), "tipo": tipo, "fecha": "2026-10-01",
            "cliente": "Cliente", "obra": "Puerta", "ubicacion": "Calle 1",
            "poblacion": "Jaca", "observaciones": "Montaje", **cambios,
        }

    def guardar(self, datos):
        respuesta = self.client.post("/registro-dia", json=datos)
        self.assertEqual(respuesta.status_code, 201, respuesta.text)
        return respuesta.json()

    def test_tres_tipos_guardan_trabajo_dia_y_sello_sin_pagos(self):
        for tipo in ("faena", "presupuesto", "reparacion"):
            registro = self.guardar(self.datos(tipo))
            self.assertEqual(registro["tipo"], tipo)
            self.assertTrue(registro["creado_en"])
        dias = self.client.get("/mis-dias").json()
        self.assertEqual(len(dias), 3)
        self.assertEqual({d["tipo"] for d in dias}, {"faena", "presupuesto", "reparacion"})
        with self.conexion() as db:
            for tabla in ("pagos_faenas", "pagos_ingresos"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT precio FROM faenas").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT presupuesto_final FROM presupuestos").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT importe FROM trabajos_propios").fetchone()[0], 0)

    def test_otro_dia_reutiliza_cada_tipo_sin_crear_otra_obra(self):
        for tipo, tabla in (("faena", "faenas"), ("presupuesto", "presupuestos"), ("reparacion", "trabajos_propios")):
            registro = self.guardar(self.datos(tipo))
            self.guardar(self.datos(tipo, origen=registro["origen"], origen_id=registro["origen_id"], fecha="2026-10-02"))
            with self.conexion() as db:
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], 1)
        self.assertEqual(len(self.client.get("/mis-dias").json()), 6)

    def test_reintento_misma_solicitud_no_duplica(self):
        datos = self.datos()
        primero = self.guardar(datos)
        segundo = self.guardar(datos)
        self.assertEqual(primero, segundo)
        self.assertEqual(len(self.client.get("/mis-dias").json()), 1)
        self.assertEqual(self.client.post("/registro-dia", json={**datos, "obra": "Otra"}).status_code, 409)

    def test_dos_reintentos_simultaneos_no_duplican(self):
        datos = self.datos()
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            respuestas = list(ejecutor.map(lambda _: self.client.post("/registro-dia", json=datos), range(2)))
        self.assertEqual([r.status_code for r in respuestas], [201, 201])
        self.assertEqual(respuestas[0].json(), respuestas[1].json())
        with self.conexion() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM faenas").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jornadas_faenas").fetchone()[0], 1)

    def test_duplicado_misma_obra_y_fecha_409(self):
        registro = self.guardar(self.datos())
        respuesta = self.client.post("/registro-dia", json=self.datos(
            origen="faena", origen_id=registro["origen_id"]
        ))
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(len(self.client.get("/mis-dias").json()), 1)

    def test_transaccion_revierte_obra_y_jornada_si_falla_diario(self):
        with self.conexion() as db:
            db.execute("CREATE TRIGGER fallo BEFORE INSERT ON diario_trabajo BEGIN SELECT RAISE(ABORT,'prueba'); END")
        with self.assertLogs("diario_trabajo", level="ERROR"):
            respuesta = self.client.post("/registro-dia", json=self.datos())
        self.assertEqual(respuesta.status_code, 503)
        with self.conexion() as db:
            for tabla in ("faenas", "jornadas_faenas", "diario_trabajo"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], 0)

    def test_snapshot_conserva_ubicacion_y_obra_del_dia(self):
        registro = self.guardar(self.datos("presupuesto", obra="Obra exacta", ubicacion="Lugar exacto"))
        with self.conexion() as db:
            db.execute("UPDATE presupuestos SET cliente='Cliente editado' WHERE id=?", (registro["origen_id"],))
        dia = self.client.get("/mis-dias").json()[0]
        self.assertEqual((dia["cliente"], dia["obra"], dia["ubicacion"]), ("Cliente", "Obra exacta", "Lugar exacto"))

    def test_cliente_existente_no_se_suplanta_ni_modifica(self):
        registro = self.guardar(self.datos())
        segundo = self.guardar(self.datos(
            origen="faena", origen_id=registro["origen_id"], fecha="2026-10-02",
            cliente="Nombre distinto", ubicacion="Otro destino",
        ))
        self.assertEqual(segundo["cliente"], "Cliente")
        with self.conexion() as db:
            self.assertEqual(db.execute("SELECT ubicacion FROM faenas").fetchone()[0], "Calle 1")

    def test_presupuesto_existente_por_numero_no_se_duplica(self):
        self.guardar(self.datos("presupuesto", num_presupuesto="P-1"))
        respuesta = self.client.post("/registro-dia", json=self.datos("presupuesto", num_presupuesto="P-1"))
        self.assertEqual(respuesta.status_code, 409)

    def test_invalido_futuro_destino_inexistente_y_tipo_incompatible(self):
        for cambios in (
            {"cliente": "   "}, {"obra": " "},
            {"fecha": (date.today() + timedelta(days=1)).isoformat()},
            {"origen": "faena"}, {"origen": "presupuesto", "origen_id": 1},
        ):
            self.assertEqual(self.client.post("/registro-dia", json=self.datos(**cambios)).status_code, 422)
        self.assertEqual(self.client.post("/registro-dia", json=self.datos(origen="faena", origen_id=999)).status_code, 404)

    def test_legacy_dias_aparecen_sin_inventar_sello(self):
        registro = self.guardar(self.datos())
        with self.conexion() as db:
            db.execute("INSERT INTO jornadas_faenas(faena_id,fecha) VALUES (?,?)", (registro["origen_id"], "2026-09-30"))
        dias = self.client.get("/mis-dias").json()
        self.assertEqual(len(dias), 2)
        self.assertIsNone(dias[1]["creado_en"])

    def test_ayudantes_no_leen_ni_registran(self):
        self.usuario["rol"] = "ayudante"
        self.assertEqual(self.client.get("/mis-dias").status_code, 403)
        self.assertEqual(self.client.post("/registro-dia", json=self.datos()).status_code, 403)

    def test_rutas_reales_exigen_administrador(self):
        def denegar():
            raise HTTPException(403, "Prueba de permisos")

        api.app.dependency_overrides[api.administrador] = denegar
        try:
            cliente = TestClient(api.app)
            self.assertEqual(cliente.get("/mis-dias").status_code, 403)
            self.assertEqual(cliente.post("/registro-dia", json=self.datos()).status_code, 403)
        finally:
            api.app.dependency_overrides.pop(api.administrador)


if __name__ == "__main__":
    unittest.main()
