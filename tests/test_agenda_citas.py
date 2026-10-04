import contextlib
import sqlite3
import unittest
from unittest.mock import patch

import api_central


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
