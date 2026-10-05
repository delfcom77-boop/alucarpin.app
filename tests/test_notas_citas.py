import contextlib
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import api_central as api


class NotasCitasTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE seguimientos_agenda (
                id INTEGER PRIMARY KEY, cliente TEXT, telefono TEXT, motivo TEXT,
                observaciones TEXT, estado TEXT, actualizado_en TEXT
            );
            INSERT INTO seguimientos_agenda VALUES
                (1, 'Cliente', '600111222', 'Medir', 'Llamar antes', 'Pendiente', NULL);
            CREATE TABLE citas_agenda (
                id INTEGER PRIMARY KEY, fecha TEXT, hora TEXT, tipo TEXT,
                cliente TEXT, ubicacion TEXT, poblacion TEXT, telefono TEXT,
                observaciones TEXT, estado TEXT
            );
        """)

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        for cambio in (patch.object(api, "conexion", conexion), patch.object(api, "DATABASE_URL", None)):
            cambio.start()
            self.addCleanup(cambio.stop)
        self.datos = api.CitaCreate(
            fecha=date(2026, 10, 7), hora="09:30", cliente="Cliente",
            telefono="600111222", observaciones="Medir | Llamar antes",
        )

    def test_archivar_y_realizar_conservan_datos_de_nota(self):
        for estado in ("Realizado", "Archivado"):
            api.actualizar_estado_seguimiento(1, api.SeguimientoEstadoUpdate(estado=estado), {})
            nota = dict(self.db.execute("SELECT * FROM seguimientos_agenda").fetchone())
            self.assertEqual(nota["estado"], estado)
            self.assertEqual(nota["telefono"], "600111222")
            self.assertEqual(nota["motivo"], "Medir")
            self.assertEqual(nota["observaciones"], "Llamar antes")

    def test_conversion_crea_cita_y_archiva_sin_modificar_nota(self):
        cita = api.convertir_seguimiento_en_cita(1, self.datos, {})
        self.assertEqual(cita["fecha"], "2026-10-07")
        self.assertEqual(cita["telefono"], "600111222")
        self.assertEqual(cita["observaciones"], "Medir | Llamar antes")
        nota = dict(self.db.execute("SELECT * FROM seguimientos_agenda").fetchone())
        self.assertEqual(nota["estado"], "Archivado")
        self.assertEqual(nota["telefono"], "600111222")
        self.assertEqual(nota["observaciones"], "Llamar antes")

    def test_segundo_intento_no_crea_cita_duplicada(self):
        api.convertir_seguimiento_en_cita(1, self.datos, {})
        with self.assertRaises(api.HTTPException) as error:
            api.convertir_seguimiento_en_cita(1, self.datos, {})
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM citas_agenda").fetchone()[0], 1)

    def test_nota_inexistente_no_crea_cita(self):
        with self.assertRaises(api.HTTPException) as error:
            api.convertir_seguimiento_en_cita(999, self.datos, {})
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM citas_agenda").fetchone()[0], 0)

    def test_fallo_de_insercion_revierte_archivo(self):
        self.db.execute("""
            CREATE TRIGGER fallo_cita BEFORE INSERT ON citas_agenda
            BEGIN SELECT RAISE(ABORT, 'Fallo de prueba'); END
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            api.convertir_seguimiento_en_cita(1, self.datos, {})
        self.assertEqual(self.db.execute("SELECT estado FROM seguimientos_agenda").fetchone()[0], "Pendiente")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM citas_agenda").fetchone()[0], 0)

    def test_creacion_ordinaria_y_rama_returning(self):
        cita = api.crear_cita(self.datos, {})
        self.assertEqual(cita["id"], 1)
        self.assertEqual(self.db.execute("SELECT estado FROM seguimientos_agenda").fetchone()[0], "Pendiente")
        with patch.object(api, "DATABASE_URL", "prueba-returning"):
            cita = api.convertir_seguimiento_en_cita(1, self.datos, {})
        self.assertEqual(cita["id"], 2)

    def test_conversion_requiere_administrador(self):
        ruta = next(r for r in api.app.routes if r.path == "/seguimientos/{seguimiento_id}/cita")
        self.assertIn(api.administrador, [d.call for d in ruta.dependant.dependencies])


if __name__ == "__main__":
    unittest.main()
