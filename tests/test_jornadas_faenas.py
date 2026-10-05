import contextlib
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import api_central


class JornadasFaenasTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute(
            "CREATE TABLE faenas (id INTEGER PRIMARY KEY, cliente TEXT, obra TEXT)"
        )
        self.db.execute(
            "CREATE TABLE jornadas_faenas ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "faena_id INTEGER NOT NULL REFERENCES faenas(id) ON DELETE RESTRICT, "
            "fecha TEXT NOT NULL, UNIQUE (faena_id, fecha))"
        )
        self.db.execute(
            "INSERT INTO faenas (id, cliente, obra) VALUES (1, 'Cliente', 'Obra')"
        )

        @contextlib.contextmanager
        def conexion_falsa():
            yield self.db

        self.patch_conexion = patch.object(
            api_central, "conexion", conexion_falsa
        )
        self.patch_conexion.start()

    def tearDown(self):
        self.patch_conexion.stop()
        self.db.close()

    def test_registra_jornada_y_la_lista_con_datos_de_la_faena(self):
        resultado = api_central.crear_jornada_faena(
            1,
            api_central.JornadaFaenaCreate(fecha=date(2026, 10, 4)),
            {"rol": "administrador"},
        )
        lista = api_central.listar_jornadas_faenas(
            faena_id=1, usuario={"rol": "administrador"}
        )

        self.assertEqual(resultado["fecha"], "2026-10-04")
        self.assertEqual(lista, [{
            "id": resultado["id"],
            "faena_id": 1,
            "fecha": "2026-10-04",
            "cliente": "Cliente",
            "obra": "Obra",
        }])

    def test_impide_registrar_dos_veces_la_misma_fecha(self):
        datos = api_central.JornadaFaenaCreate(fecha=date(2026, 10, 4))
        api_central.crear_jornada_faena(1, datos, {"rol": "administrador"})

        with self.assertRaises(api_central.HTTPException) as error:
            api_central.crear_jornada_faena(1, datos, {"rol": "administrador"})

        self.assertEqual(error.exception.status_code, 409)

    def test_no_registra_jornada_para_una_faena_inexistente(self):
        with self.assertRaises(api_central.HTTPException) as error:
            api_central.crear_jornada_faena(
                999,
                api_central.JornadaFaenaCreate(fecha=date(2026, 10, 4)),
                {"rol": "administrador"},
            )

        self.assertEqual(error.exception.status_code, 404)

    def test_informa_si_falta_la_migracion_de_jornadas(self):
        self.db.execute("DROP TABLE jornadas_faenas")

        with self.assertRaises(api_central.HTTPException) as error:
            api_central.crear_jornada_faena(
                1,
                api_central.JornadaFaenaCreate(fecha=date(2026, 10, 4)),
                {"rol": "administrador"},
            )

        self.assertEqual(error.exception.status_code, 503)

    def test_no_borra_una_faena_que_tiene_jornadas(self):
        api_central.crear_jornada_faena(
            1,
            api_central.JornadaFaenaCreate(fecha=date(2026, 10, 4)),
            {"rol": "administrador"},
        )

        with self.assertRaises(api_central.HTTPException) as error:
            api_central.borrar_faena(1, {"rol": "administrador"})

        self.assertEqual(error.exception.status_code, 409)

    def test_inicio_sqlite_crea_la_tabla_de_jornadas(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "empresa.db"
            with patch.object(api_central, "DATABASE_URL", None):
                with patch.object(api_central, "DATABASE_PATH", ruta):
                    api_central.inicializar_base_datos()

            db = sqlite3.connect(ruta)
            try:
                tabla = db.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'jornadas_faenas'"
                ).fetchone()
                self.assertIsNotNone(tabla)
                columnas = {
                    fila[1]
                    for fila in db.execute("PRAGMA table_info(jornadas_faenas)")
                }
                self.assertIn("pago_faena_id", columnas)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
