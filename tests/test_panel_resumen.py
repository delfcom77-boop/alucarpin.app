from datetime import date
import unittest
from unittest.mock import patch

import api_central as api
from tests import test_pagos_diarios


class FechaPanel(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 5)


class PanelResumenTests(unittest.TestCase):
    setUp = test_pagos_diarios.PagosDiariosTests.setUp
    tearDown = test_pagos_diarios.PagosDiariosTests.tearDown
    def resumen(self, alarmas=None):
        with (
            patch.object(api, "date", FechaPanel),
            patch.object(api, "listar_alarmas", return_value=alarmas or []),
        ):
            return api.panel_resumen({})

    def test_panel_no_asigna_importe_a_dias_sin_registro(self):
        resumen = self.resumen()
        self.assertEqual(resumen["ayudantes"]["jornadas"], 3)
        self.assertEqual(resumen["ayudantes"]["sin_registro"], 3)
        self.assertEqual(resumen["ayudantes"]["importe_pendiente_registrado"], 0)

    def test_panel_usa_pago_diario_y_no_suma_liquidacion_ni_gastos(self):
        self.db.executescript("""
            INSERT INTO pagos_jornadas VALUES (1,50,20,'Efectivo','Parcial','2026-10-03',NULL);
            INSERT INTO pagos_jornadas VALUES (4,50,50,'Efectivo','Pagado','2026-10-03',NULL);
            INSERT INTO liquidaciones
                (ayudante_id,desde,hasta,precio_dia,importe_pagado)
                VALUES (1,'2026-10-01','2026-10-05',50,500);
            CREATE TABLE gastos_faenas_extras (
                id INTEGER, faena_id INTEGER, proveedor TEXT, fecha TEXT, categoria TEXT,
                importe REAL, importe_pagado REAL, pagado REAL, forma_pago TEXT, estado_pago TEXT
            );
            INSERT INTO gastos_faenas_extras VALUES
                (10,25,'DANI','2026-10-03','Ayudantes',50,0,0,'Efectivo','No pagado');
        """)
        resumen = self.resumen()["ayudantes"]
        self.assertEqual(resumen["parciales"], 1)
        self.assertEqual(resumen["pagadas"], 1)
        self.assertEqual(resumen["sin_registro"], 1)
        self.assertEqual(resumen["revision"], 0)
        self.assertEqual(resumen["importe_pendiente_registrado"], 30)

    def test_panel_excluye_futuro_y_dias_con_conflicto_del_importe(self):
        self.db.executescript("""
            INSERT INTO pagos_jornadas VALUES (1,50,10,'Efectivo','Parcial',NULL,NULL);
            INSERT INTO pagos_jornadas VALUES (2,50,0,'Efectivo','No pagado',NULL,NULL);
            INSERT INTO fichajes_ayudantes VALUES (9,1,'2026-10-06','Obra',NULL,1);
        """)
        resumen = self.resumen()["ayudantes"]
        self.assertEqual(resumen["jornadas"], 3)
        self.assertEqual(resumen["revision"], 1)
        self.assertEqual(resumen["importe_pendiente_registrado"], 0)

    def test_panel_cobros_y_ejecucion_independientes(self):
        alarmas = [
            {"tipo": "trabajo", "estado": "Pendiente", "fecha": "2026-10-04"},
            {"tipo": "trabajo", "estado": "Pendiente", "fecha": None},
            {"tipo": "trabajo", "estado": "Archivado", "fecha": "2026-10-01"},
            {"tipo": "cobro", "referencia_id": 1, "origen": "faena", "pendiente_cobro": 70},
            {"tipo": "cobro", "referencia_id": 2, "origen": "propio", "pendiente_cobro": 50},
            {"tipo": "cobro", "referencia_id": 3, "origen": "propio", "pendiente_cobro": 0},
        ]
        resumen = self.resumen(alarmas)
        self.assertEqual(resumen["trabajos"], {"pendientes": 2, "vencidos": 1})
        self.assertEqual(resumen["cobros"], {"pendientes": 3, "importe_pendiente": 120, "sin_importe": 1})

    def test_agenda_incluye_vencidos_y_siete_dias_sin_archivados(self):
        alarmas = [
            {"tipo": "nota", "referencia_id": 1, "estado": "Pendiente", "fecha": "2026-10-04", "hora": "09:00"},
            {"tipo": "cita", "referencia_id": 2, "estado": "Pendiente", "fecha": "2026-10-12", "hora": "10:00"},
            {"tipo": "nota", "referencia_id": 3, "estado": "Pendiente", "fecha": "2026-10-13"},
            {"tipo": "cita", "referencia_id": 4, "estado": "Archivado", "fecha": "2026-10-05"},
            {"tipo": "nota", "referencia_id": 5, "estado": "Pendiente", "fecha": None},
        ]
        resumen = self.resumen(alarmas)["agenda"]
        self.assertEqual(resumen["total"], 2)
        self.assertEqual(resumen["vencidos"], 1)
        self.assertEqual([a["referencia_id"] for a in resumen["avisos"]], [1, 2])
        self.assertEqual(resumen["hasta"], "2026-10-12")

    def test_agenda_limita_detalle_pero_no_recuento(self):
        alarmas = [
            {"tipo": "nota", "referencia_id": i, "estado": "Pendiente", "fecha": "2026-10-05"}
            for i in range(12)
        ]
        agenda = self.resumen(alarmas)["agenda"]
        self.assertEqual(agenda["total"], 12)
        self.assertEqual(len(agenda["avisos"]), 8)

    def test_error_no_devuelve_resumen_vacio(self):
        with patch.object(api, "listar_alarmas", side_effect=RuntimeError("Fallo de base de datos")):
            with self.assertRaises(RuntimeError):
                api.panel_resumen({})

    def test_endpoint_requiere_administrador(self):
        ruta = next(r for r in api.app.routes if getattr(r, "path", None) == "/panel-resumen")
        self.assertEqual(ruta.dependant.dependencies[0].call, api.administrador)
        with self.assertRaises(api.HTTPException) as error:
            api.administrador({"rol": "ayudante"})
        self.assertEqual(error.exception.status_code, 403)
