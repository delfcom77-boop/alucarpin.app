import contextlib
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import api_central as api
from cuentas_reparaciones import inicializar_cuentas, guardar_movimiento, filas
from resumen_economico import calcular_resumen
from tests.test_ficha_obra import FichaObraTests


class CuentasReparacionesTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE trabajos_propios(id INTEGER PRIMARY KEY, tipo TEXT, fecha_inicio TEXT,
                fecha_fin TEXT, cliente TEXT, obra TEXT, ubicacion TEXT, poblacion TEXT,
                observaciones TEXT, num_presupuesto TEXT, importe REAL, estado_cobro TEXT,
                forma_pago TEXT, fecha_cobro TEXT, estado_revision TEXT,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO trabajos_propios VALUES(1,'reparacion','2026-10-01',NULL,'Cliente','Ventana',
                'Calle','','',NULL,300,'No cobrado','',NULL,'Validado',NULL);
            CREATE TABLE faenas(id INTEGER, fecha TEXT, cliente TEXT, obra TEXT, ubicacion TEXT,
                poblacion TEXT, precio REAL, estado_revision TEXT);
            CREATE TABLE presupuestos(id INTEGER, fecha TEXT, cliente TEXT, num_presupuesto TEXT,
                presupuesto_final REAL, estado TEXT, estado_revision TEXT);
            CREATE TABLE estados_ejecucion_trabajos(trabajo_id INTEGER, estado TEXT);
            CREATE TABLE seguimientos_agenda(id INTEGER, fecha_recordatorio TEXT, hora TEXT,
                cliente TEXT, ubicacion TEXT, poblacion TEXT, motivo TEXT, estado TEXT);
            CREATE TABLE citas_agenda(id INTEGER, fecha TEXT, hora TEXT, cliente TEXT,
                ubicacion TEXT,poblacion TEXT,observaciones TEXT,estado TEXT);
        """)
        inicializar_cuentas(self.db)
        self.trabajo = filas(self.db, "SELECT * FROM trabajos_propios")[0]

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        for cambio in (patch.object(api, "conexion", conexion),
                       patch.object(api, "consultar_estados_obras", return_value=[])):
            cambio.start()
            self.addCleanup(cambio.stop)

    def ingresar(self, importe=100):
        return guardar_movimiento(self.db, self.trabajo, dict(
            clase="ingreso", fecha="2026-10-10", importe=importe, forma_pago="Transferencia"))

    def test_listado_y_alarmas_usan_cobro_parcial_real(self):
        self.ingresar()
        trabajo = api.listar_trabajos({})[0]
        self.assertEqual(trabajo["estado_cobro"], "Parcial")
        self.assertEqual(trabajo["pendiente_cobro"], 200)
        self.assertTrue(trabajo["cuenta_con_movimientos"])
        cobro = next(a for a in api.listar_alarmas({}) if a["tipo"] == "cobro")
        self.assertEqual(cobro["pendiente_cobro"], 200)

    def test_modificar_importe_no_borra_cobros_y_borrado_obra_se_bloquea(self):
        self.ingresar()
        datos = api.TrabajoUpdate(tipo="reparacion", fecha_inicio=date(2026, 10, 1),
                                  cliente="Cliente", obra="Ventana", importe=400, estado_cobro="Cobrado")
        api.modificar_trabajo(1, datos, {})
        self.assertEqual(api.listar_trabajos({})[0]["pendiente_cobro"], 300)
        with self.assertRaises(api.HTTPException) as error:
            api.borrar_trabajo(1, {})
        self.assertEqual(error.exception.status_code, 409)

    def test_modificar_historico_conserva_importe_cobrado_anterior(self):
        self.db.execute("UPDATE trabajos_propios SET estado_cobro='Cobrado',fecha_cobro='2026-10-01'")
        datos = api.TrabajoUpdate(tipo="reparacion", fecha_inicio=date(2026, 10, 1),
                                  cliente="Cliente", obra="Ventana", importe=400)
        api.modificar_trabajo(1, datos, {})
        trabajo = api.listar_trabajos({})[0]
        self.assertEqual(trabajo["cobrado"], 300)
        self.assertEqual(trabajo["pendiente_cobro"], 100)


class FichaReparacionTests(FichaObraTests):
    def test_ficha_reparacion_muestra_cobros_y_gastos_sin_sumar_estado(self):
        self.preparar()
        trabajo = dict(id=25, importe=300, estado_cobro="Cobrado", forma_pago="Efectivo", fecha_cobro=None)
        guardar_movimiento(self.db, trabajo, dict(
            clase="ingreso", fecha="2026-10-10", importe=20, forma_pago="Efectivo"))
        guardar_movimiento(self.db, trabajo, dict(
            clase="gasto", fecha="2026-10-10", importe=40, importe_pagado=15,
            concepto="Materiales", proveedor="Tienda", forma_pago="Transferencia"))
        obra = self.obra("propio")
        obra["estado_cobro"] = "Cobrado"
        obra["historico"] = False
        with patch.object(api, "listar_trabajos", return_value=[obra]), patch.object(api, "consultar_remates", return_value=[]):
            ficha = api.ficha_obra("propio", 25, {})
        self.assertEqual(ficha["resumen"]["cobros_registrados"], 320)
        self.assertEqual(ficha["resumen"]["gastos"], 40)
        self.assertEqual(ficha["resumen"]["gastos_pagados"], 15)
        self.assertEqual(ficha["gastos"][0]["pendiente"], 25)
