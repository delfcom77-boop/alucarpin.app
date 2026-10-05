import unittest
from unittest.mock import patch

import api_central as api
from tests import test_pagos_diarios


class FichaObraTests(unittest.TestCase):
    setUp = test_pagos_diarios.PagosDiariosTests.setUp
    tearDown = test_pagos_diarios.PagosDiariosTests.tearDown

    def preparar(self):
        self.db.executescript("""
            ALTER TABLE fichajes_ayudantes ADD COLUMN presupuesto_id INTEGER;
            ALTER TABLE fichajes_ayudantes ADD COLUMN trabajo_propio_id INTEGER;
            CREATE TABLE jornadas_faenas (faena_id INTEGER, fecha TEXT);
            INSERT INTO jornadas_faenas VALUES (25,'2026-10-03');
            CREATE TABLE pagos_faenas (
                id INTEGER, faena_id INTEGER, fecha TEXT, importe_iva REAL,
                importe_b REAL, forma_pago TEXT, observaciones TEXT
            );
            INSERT INTO pagos_faenas VALUES (1,25,'2026-10-03',100,20,'Efectivo','Cobro');
            CREATE TABLE pagos_ingresos (
                id INTEGER, num_presupuesto TEXT, fecha TEXT, importe_iva REAL,
                importe_b REAL, forma_pago TEXT, observaciones TEXT
            );
            INSERT INTO pagos_ingresos VALUES (1,'P1','2026-10-03',200,30,'Efectivo','Cobro P1');
            INSERT INTO pagos_ingresos VALUES (2,'P2','2026-10-03',999,0,'Efectivo','Ajeno');
        """)

    def obra(self, origen="faena"):
        return {
            "origen": origen, "origen_id": 25, "num_presupuesto": "P1" if origen == "presupuesto" else None,
            "importe": 100, "estado_cobro": "No cobrado", "fecha_cobro": None, "forma_pago": "",
        }

    def consultar(self, origen="faena", gastos=None):
        with (
            patch.object(api, "listar_trabajos", return_value=[self.obra(origen)]),
            patch.object(api, "listar_gastos", return_value=gastos or []),
        ):
            return api.ficha_obra(origen, 25, {})

    def test_dias_distintos_y_pago_en_otra_obra_del_mismo_dia(self):
        self.preparar()
        test_pagos_diarios.PagosDiariosTests.pago(self, 2, 50)
        anterior = "\n".join(self.db.iterdump())
        ficha = self.consultar()
        self.assertEqual(ficha["resumen"]["dias_ayudantes"], 3)
        self.assertEqual(ficha["resumen"]["fechas_trabajadas"], 2)
        self.assertEqual(ficha["resumen"]["ayudantes"], 2)
        dia = next(j for j in ficha["jornadas_ayudantes"] if j["ayudante_id"] == 1 and j["fecha"] == "2026-10-03")
        self.assertEqual(dia["estado_pago"], "Pagado")
        self.assertIn("Obra B", dia["obras_del_dia"])
        self.assertEqual(ficha["resumen"]["cobros_registrados"], 120)
        self.assertEqual(ficha["resumen"]["dias_obra_registrados"], 1)
        self.assertEqual(anterior, "\n".join(self.db.iterdump()))

    def test_no_asigna_por_nombre_ni_duplica_fichajes(self):
        self.preparar()
        self.db.executescript("""
            UPDATE fichajes_ayudantes SET faena_id_vinculada=25 WHERE id=2;
            INSERT INTO fichajes_ayudantes (id,ayudante_id,fecha,obra,faena_id_vinculada)
                VALUES (9,1,'2026-10-05','Obra A',NULL);
        """)
        ficha = self.consultar()
        self.assertEqual(ficha["resumen"]["dias_ayudantes"], 3)
        self.assertTrue(all(j["fecha"] != "2026-10-05" for j in ficha["jornadas_ayudantes"]))

    def test_filtra_gastos_y_cobros_por_vinculo_presupuesto(self):
        self.preparar()
        self.db.execute("UPDATE fichajes_ayudantes SET presupuesto_id=25 WHERE id=1")
        self.db.commit()
        gastos = [
            {"num_presupuesto": "P1", "importe": 30, "importe_pagado": 10},
            {"num_presupuesto": "P2", "importe": 999, "importe_pagado": 999},
        ]
        ficha = self.consultar("presupuesto", gastos)
        self.assertEqual(ficha["resumen"]["gastos"], 30)
        self.assertEqual(ficha["resumen"]["gastos_pagados"], 10)
        self.assertEqual(ficha["resumen"]["cobros_registrados"], 230)
        self.assertEqual(ficha["resumen"]["dias_ayudantes"], 1)

    def test_gastos_de_faenas_distintas_no_se_mezclan(self):
        self.preparar()
        ficha = self.consultar(gastos=[
            {"faena_id": 25, "importe": 20, "importe_pagado": 10},
            {"faena_id": 26, "importe": 999, "importe_pagado": 999},
        ])
        self.assertEqual(ficha["resumen"]["gastos"], 20)
        self.assertEqual(ficha["resumen"]["gastos_pagados"], 10)
        self.assertEqual(len(ficha["gastos"]), 1)

    def test_presupuesto_sin_numero_no_recibe_cobros_ajenos(self):
        self.preparar()
        obra = self.obra("presupuesto")
        obra["num_presupuesto"] = None
        with (
            patch.object(api, "listar_trabajos", return_value=[obra]),
            patch.object(api, "listar_gastos", return_value=[]),
        ):
            ficha = api.ficha_obra("presupuesto", 25, {})
        self.assertEqual(ficha["cobros"], [])
        self.assertEqual(ficha["gastos"], [])

    def test_propio_cobrado_es_estado_no_movimiento_inventado(self):
        self.preparar()
        obra = self.obra("propio")
        obra["estado_cobro"] = "Cobrado"
        with patch.object(api, "listar_trabajos", return_value=[obra]):
            ficha = api.ficha_obra("propio", 25, {})
        self.assertEqual(ficha["gastos"], [])
        self.assertIsNone(ficha["cobros"][0]["id"])
        self.assertIn("sin movimiento", ficha["cobros"][0]["observaciones"])

    def test_id_inexistente_y_permiso(self):
        with patch.object(api, "listar_trabajos", return_value=[]):
            with self.assertRaises(api.HTTPException) as error:
                api.ficha_obra("faena", 999, {})
        self.assertEqual(error.exception.status_code, 404)
        ruta = next(r for r in api.app.routes if getattr(r, "path", None) == "/obras/{origen}/{obra_id}")
        self.assertEqual(ruta.dependant.dependencies[0].call, api.administrador)
