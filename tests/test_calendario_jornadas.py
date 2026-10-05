import contextlib
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import api_central as api


class CalendarioJornadasTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE presupuestos (id INTEGER PRIMARY KEY, cliente TEXT, num_presupuesto TEXT);
            CREATE TABLE trabajos_propios (
                id INTEGER PRIMARY KEY, tipo TEXT, cliente TEXT, obra TEXT, ubicacion TEXT, poblacion TEXT
            );
            CREATE TABLE faenas (id INTEGER PRIMARY KEY, cliente TEXT, obra TEXT, ubicacion TEXT, poblacion TEXT);
            CREATE TABLE remates (id INTEGER PRIMARY KEY);
            CREATE TABLE jornadas_faenas (faena_id INTEGER, fecha TEXT);
            CREATE TABLE citas_agenda (
                id INTEGER, fecha TEXT, hora TEXT, duracion_minutos INTEGER, tipo TEXT,
                cliente TEXT, ubicacion TEXT, poblacion TEXT, observaciones TEXT, estado TEXT
            );
            CREATE TABLE seguimientos_agenda (
                id INTEGER, fecha_llamada TEXT, fecha_recordatorio TEXT, hora TEXT,
                cliente TEXT, ubicacion TEXT, poblacion TEXT, motivo TEXT,
                observaciones TEXT, telefono TEXT, estado TEXT
            );
            CREATE TABLE calendario_silencios (fecha TEXT);
            INSERT INTO presupuestos VALUES (1, 'Cliente propio', 'P-1');
            INSERT INTO trabajos_propios VALUES (1, 'reparacion', 'Cliente reparación', 'Puerta', 'Calle 1', 'Jaca');
            INSERT INTO faenas VALUES (1, 'Tercero', 'Obra; A, B', 'Calle 2', 'Jaca');
            INSERT INTO jornadas_faenas VALUES (1, '2026-10-03');
            INSERT INTO citas_agenda VALUES (1, '2026-10-05', '09:00', 60, 'visita', 'Cita', '', '', '', 'Pendiente');
        """)

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        for cambio in (patch.object(api, "conexion", conexion), patch.object(api, "DATABASE_URL", None),
                       patch.object(api, "inicializar_base_datos")):
            cambio.start()
            self.addCleanup(cambio.stop)
        api.startup()
        self.datos = api.JornadaFaenaCreate(fecha=date(2026, 10, 4))

    def test_registra_y_lista_dias_propios_sin_crear_pagos(self):
        api.crear_jornada_propia("presupuesto", 1, self.datos, {})
        api.crear_jornada_propia("propio", 1, self.datos, {})
        dias = api.listar_jornadas_propias({})
        self.assertEqual({(d["origen"], d["origen_id"]) for d in dias}, {("presupuesto", 1), ("propio", 1)})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM pagos_ingresos").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM pagos_faenas").fetchone()[0], 0)

    def test_duplicado_409_y_destino_inexistente_404(self):
        api.crear_jornada_propia("presupuesto", 1, self.datos, {})
        for ident, esperado in ((1, 409), (999, 404)):
            with self.assertRaises(api.HTTPException) as error:
                api.crear_jornada_propia("presupuesto", ident, self.datos, {})
            self.assertEqual(error.exception.status_code, esperado)
        self.assertEqual(len(api.listar_jornadas_propias({})), 1)

    def test_calendarios_separados_fechas_reales_y_uid_estable(self):
        api.crear_jornada_propia("presupuesto", 1, self.datos, {})
        api.crear_jornada_propia("propio", 1, self.datos, {})
        propias = api.calendario_trabajos("propias", {}).body.decode()
        terceros = api.calendario_trabajos("terceros", {}).body.decode()
        self.assertEqual(propias.count("BEGIN:VEVENT"), 2)
        self.assertEqual(terceros.count("BEGIN:VEVENT"), 1)
        self.assertIn("DTSTART;VALUE=DATE:20261004", propias)
        self.assertIn("DTEND;VALUE=DATE:20261005", propias)
        self.assertIn("DTSTART;VALUE=DATE:20261003", terceros)
        self.assertIn("Obra\\; A\\, B", terceros)
        self.assertNotIn("Tercero", propias)
        self.assertNotIn("Cita", propias)
        self.assertNotIn("Cliente propio", terceros)
        uids = [l for l in propias.splitlines() if l.startswith("UID:")]
        self.assertEqual(len(set(uids)), 2)
        self.assertEqual(uids, [l for l in api.calendario_trabajos("propias", {}).body.decode().splitlines() if l.startswith("UID:")])

    def test_sin_dias_no_inventa_fecha_general(self):
        with self.assertRaises(api.HTTPException) as error:
            api.calendario_trabajos("propias", {})
        self.assertEqual(error.exception.status_code, 409)

    def test_lineas_largas_se_pliegan_sin_perder_acentos(self):
        texto = "SUMMARY:" + "á" * 100
        resultado = api.plegar_lineas_ics([texto, ""])
        self.assertTrue(all(len(l.encode("utf-8")) <= 75 for l in resultado.split("\r\n")))
        self.assertEqual(resultado.replace("\r\n ", "").rstrip("\r\n"), texto)

    def test_agenda_separada_conserva_citas_sin_trabajos(self):
        api.crear_jornada_propia("presupuesto", 1, self.datos, {})
        contenido = api.calendario_completo({}).body.decode()
        self.assertIn("UID:alucarpin-cita-1@", contenido)
        self.assertNotIn("UID:alucarpin-dia-", contenido)

    def test_calendario_individual_no_confunde_identificadores(self):
        api.crear_jornada_propia("presupuesto", 1, self.datos, {})
        obras = [{"origen": "presupuesto", "origen_id": 1}, {"origen": "faena", "origen_id": 1}]
        with patch.object(api, "listar_trabajos", return_value=obras):
            contenido = api.calendario_trabajo(1, "presupuesto", {}).body.decode()
            self.assertIn("alucarpin-dia-presupuesto-1-", contenido)
            self.assertNotIn("alucarpin-dia-faena-1-", contenido)

    def test_obras_con_dias_no_se_borran(self):
        api.crear_jornada_propia("presupuesto", 1, self.datos, {})
        api.crear_jornada_propia("propio", 1, self.datos, {})
        for borrar in (api.borrar_presupuesto, api.borrar_trabajo):
            with self.assertRaises(api.HTTPException) as error:
                borrar(1, {})
            self.assertEqual(error.exception.status_code, 409)

    def test_inicio_idempotente_preserva_dias(self):
        api.crear_jornada_propia("presupuesto", 1, self.datos, {})
        api.startup()
        self.assertEqual(len(api.listar_jornadas_propias({})), 1)

    def test_endpoints_requieren_administrador(self):
        for nombre in ("listar_jornadas_propias", "crear_jornada_propia", "calendario_trabajos"):
            ruta = next(r for r in api.app.routes if r.name == nombre)
            self.assertIn(api.administrador, [d.call for d in ruta.dependant.dependencies])


if __name__ == "__main__":
    unittest.main()
