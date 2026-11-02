import sqlite3
import unittest
from datetime import date

from resumen_economico import calcular_resumen


class ResumenJornadasTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE faenas(id INTEGER, cliente TEXT, obra TEXT, fecha TEXT,
                precio REAL, importe_acordado REAL);
            INSERT INTO faenas VALUES(1,'Cliente','Obra','2026-10-01',0,NULL);
            CREATE TABLE jornadas_faenas(id INTEGER,faena_id INTEGER,fecha TEXT,importe REAL);
            INSERT INTO jornadas_faenas VALUES(1,1,'2026-10-01',400);
            CREATE TABLE pagos_faenas(id INTEGER,faena_id INTEGER,fecha TEXT,
                importe_iva REAL,importe_b REAL,beneficiario TEXT);
            CREATE TABLE gastos_presupuestos(id INTEGER,num_presupuesto TEXT,fecha TEXT,
                importe REAL,importe_pagado REAL,pagado REAL,proveedor TEXT,concepto TEXT);
        """)

    def resumen(self):
        return calcular_resumen(self.db, date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 6))

    def test_jornadas_son_base_no_un_segundo_ingreso(self):
        self.assertEqual(self.resumen()["acumulado"]["cobros_pendientes"], 400)
        self.assertEqual(self.resumen()["periodo"]["cobros_recibidos"], 0)
        self.db.execute("INSERT INTO pagos_faenas VALUES(1,1,'2026-10-02',0,400,'')")
        resultado = self.resumen()
        self.assertEqual(resultado["acumulado"]["cobros_pendientes"], 0)
        self.assertEqual(resultado["periodo"]["cobros_recibidos"], 400)
        self.assertEqual(resultado["acumulado"]["cobros_sin_importe"], 0)

    def test_acordado_prevalece_y_cero_explicito_no_genera_aviso(self):
        self.db.execute("UPDATE faenas SET importe_acordado=700")
        self.assertEqual(self.resumen()["acumulado"]["cobros_pendientes"], 700)
        self.db.execute("UPDATE faenas SET importe_acordado=0")
        self.assertEqual(self.resumen()["acumulado"]["cobros_pendientes"], 0)
        self.assertEqual(self.resumen()["acumulado"]["cobros_sin_importe"], 0)

    def test_precio_sin_jornadas_y_jornada_futura(self):
        self.db.execute("UPDATE faenas SET precio=900")
        self.db.execute("INSERT INTO jornadas_faenas VALUES(2,1,'2026-10-07',800)")
        self.assertEqual(self.resumen()["acumulado"]["cobros_pendientes"], 400)
        self.db.execute("DELETE FROM jornadas_faenas")
        self.assertEqual(self.resumen()["acumulado"]["cobros_pendientes"], 900)

    def test_terceros_no_se_duplican(self):
        self.db.execute("INSERT INTO pagos_faenas VALUES(1,1,'2026-10-02',0,100,'Colaborador')")
        self.assertEqual(self.resumen()["acumulado"]["cobros_pendientes"], 300)
        self.assertEqual(self.resumen()["periodo"]["cobros_recibidos"], 0)

    def test_cobro_sin_fecha_salda_pero_no_inventa_periodo(self):
        self.db.execute("INSERT INTO pagos_faenas VALUES(1,1,NULL,0,400,'')")
        resultado = self.resumen()
        self.assertEqual(resultado["acumulado"]["cobros_pendientes"], 0)
        self.assertEqual(resultado["periodo"]["cobros_recibidos"], 0)
        self.assertTrue(any("cobro sin fecha" in a for a in resultado["avisos"]))

    def test_gasto_pagado_en_centimos_no_deja_residuo_iva(self):
        self.db.execute(
            "INSERT INTO gastos_presupuestos VALUES(1,'P1','2026-10-01',2335.6025,2335.60,2335.60,'Proveedor','Factura')")
        resultado = self.resumen()
        self.assertEqual(resultado["pagos"], [])
        self.assertEqual(resultado["periodo"]["pendiente_gastos"], 0)
        self.assertEqual(resultado["periodo"]["gastos_registrados"], 2335.60)

    def test_jornada_sin_fecha_es_visible(self):
        self.db.execute("UPDATE jornadas_faenas SET fecha=NULL")
        resultado = self.resumen()
        self.assertEqual(resultado["acumulado"]["cobros_pendientes"], 400)
        self.assertTrue(any("Jornada #1: sin fecha" in a for a in resultado["avisos"]))
