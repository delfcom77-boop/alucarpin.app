import contextlib
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import api_central as api
from resumen_economico import calcular_resumen, periodo_actual


class ResumenEconomicoTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE faenas(id INTEGER, cliente TEXT, obra TEXT, fecha TEXT, precio REAL);
            INSERT INTO faenas VALUES(1,'Cliente','Obra antigua','2026-09-01',500);
            CREATE TABLE presupuestos(id INTEGER, cliente TEXT, num_presupuesto TEXT,
                fecha TEXT, presupuesto_final REAL, estado TEXT);
            INSERT INTO presupuestos VALUES
                (2,'Cliente','P2','2026-09-01',1000,'Aceptado'),
                (3,'Cliente','P3','2026-09-01',999,'Completado'),
                (4,'Cliente','P4','2026-09-01',999,'Pendiente');
            CREATE TABLE pagos_faenas(id INTEGER, faena_id INTEGER, fecha TEXT, importe_iva REAL, importe_b REAL);
            INSERT INTO pagos_faenas VALUES
                (1,1,'2026-09-30',100,0),(2,1,'2026-10-01',10,20),
                (3,1,'2026-10-06',20,0),(4,1,'2026-10-07',100,0),
                (5,1,NULL,50,0);
            CREATE TABLE pagos_ingresos(id INTEGER, num_presupuesto TEXT, fecha TEXT, importe_iva REAL, importe_b REAL);
            INSERT INTO pagos_ingresos VALUES(1,'P2','2026-09-01',200,0);
            CREATE TABLE trabajos_propios(id INTEGER, cliente TEXT, obra TEXT, fecha_inicio TEXT,
                importe REAL, estado_cobro TEXT, fecha_cobro TEXT, num_presupuesto TEXT);
            INSERT INTO trabajos_propios VALUES
                (1,'Cliente','Reparacion','2026-09-01',60,'No cobrado',NULL,NULL),
                (2,'Cliente','Reparacion cobrada','2026-09-01',40,'Cobrado','2026-10-06',NULL),
                (3,'Cliente','Presupuesto vinculado','2026-09-01',1000,'No cobrado',NULL,'P2');
            CREATE TABLE gastos_faenas_extras(id INTEGER, faena_id INTEGER, fecha TEXT, importe REAL,
                importe_pagado REAL, pagado REAL, proveedor TEXT, concepto TEXT, categoria TEXT);
            INSERT INTO gastos_faenas_extras VALUES
                (1,1,'2026-09-01',100,20,20,'Proveedor','Antiguo','Materiales'),
                (2,1,'2026-10-01',80,30,30,'Proveedor','Nuevo','Materiales'),
                (3,1,'2026-10-07',900,0,0,'Proveedor','Futuro','Materiales');
            CREATE TABLE gastos_presupuestos(id INTEGER, num_presupuesto TEXT, fecha TEXT, importe REAL,
                importe_pagado REAL, pagado REAL, proveedor TEXT, concepto TEXT, categoria TEXT);
            CREATE TABLE ayudantes(id INTEGER, nombre TEXT);
            INSERT INTO ayudantes VALUES(1,'Dani'),(2,'Desire');
            CREATE TABLE fichajes_ayudantes(id INTEGER, ayudante_id INTEGER, fecha TEXT, obra TEXT,
                faena_id_vinculada INTEGER, num_presupuesto TEXT);
            INSERT INTO fichajes_ayudantes VALUES
                (1,1,'2026-10-03','Obra A',1,NULL),(2,1,'2026-10-03','Obra B',2,NULL),
                (3,2,'2026-10-03','Obra A',1,NULL),(4,1,'2026-10-07','Futuro',1,NULL);
            CREATE TABLE pagos_jornadas(fichaje_id INTEGER, importe REAL, importe_pagado REAL);
            INSERT INTO pagos_jornadas VALUES(1,50,20);
        """)

    def tearDown(self):
        self.db.close()

    def resumen(self):
        return calcular_resumen(self.db, date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 6))

    def test_mes_actual_y_febrero_bisiesto(self):
        self.assertEqual(periodo_actual(date(2024, 2, 3)), (date(2024, 2, 1), date(2024, 2, 29)))

    def test_periodo_no_oculta_pendientes_anteriores_y_no_usa_futuro(self):
        resultado = self.resumen()
        self.assertEqual(resultado["periodo"], dict(
            cobros_recibidos=90, gastos_registrados=130, abonado_gastos=50,
            pendiente_gastos=80, jornadas_estimadas=1, coste_estimado=50))
        self.assertEqual(resultado["acumulado"]["cobros_pendientes"], 1160)
        self.assertEqual(resultado["acumulado"]["pagos_pendientes"], 160)
        self.assertEqual(resultado["acumulado"]["coste_estimado"], 50)
        self.assertTrue(any("cobro sin fecha" in aviso for aviso in resultado["avisos"]))
        septiembre = calcular_resumen(self.db, date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 6))
        self.assertEqual(septiembre["periodo"]["gastos_registrados"], 100)
        self.assertEqual(septiembre["acumulado"], resultado["acumulado"])

    def test_jornada_no_se_multiplica_y_historico_no_se_suma_otra_vez(self):
        self.db.execute("INSERT INTO gastos_faenas_extras VALUES(4,1,'2026-10-03',50,20,20,'Dani','Dia','Ayudantes')")
        self.assertEqual(self.resumen()["periodo"]["gastos_registrados"], 130)
        self.db.execute("DELETE FROM pagos_jornadas")
        self.assertEqual(self.resumen()["periodo"]["gastos_registrados"], 130)
        self.assertEqual(self.resumen()["periodo"]["abonado_gastos"], 50)
        self.db.execute("UPDATE gastos_faenas_extras SET importe_pagado=NULL WHERE id=4")
        self.assertEqual(self.resumen()["periodo"]["abonado_gastos"], 50)

    def test_historico_presupuesto_y_duplicados_excluidos(self):
        self.db.execute("UPDATE fichajes_ayudantes SET num_presupuesto='P2' WHERE id=3")
        self.db.execute("INSERT INTO gastos_presupuestos VALUES(1,'P2','2026-10-03',60,10,10,'Desire','Dia','Ayudantes')")
        self.assertEqual(self.resumen()["periodo"]["gastos_registrados"], 190)
        self.db.execute("INSERT INTO pagos_jornadas VALUES(2,50,20)")
        resultado = self.resumen()
        self.assertEqual(resultado["revision"], 1)
        self.assertEqual(resultado["periodo"]["gastos_registrados"], 140)
        self.assertEqual(resultado["acumulado"]["pagos_pendientes"], 180)

    def test_fechas_invalidas_y_sin_fecha_son_visibles(self):
        self.db.execute("UPDATE gastos_faenas_extras SET fecha='incorrecta' WHERE id=2")
        resultado = self.resumen()
        self.assertEqual(resultado["periodo"]["gastos_registrados"], 50)
        self.assertEqual(resultado["acumulado"]["pagos_pendientes"], 160)
        self.assertTrue(any("Fecha no valida" in aviso for aviso in resultado["avisos"]))

    def test_sin_escrituras_y_soporta_filas_dict_y_tupla(self):
        self.db.commit()
        cambios = self.db.total_changes
        esperado = self.resumen()
        self.db.row_factory = sqlite3.Row
        self.assertEqual(self.resumen(), esperado)
        self.assertEqual(self.db.total_changes, cambios)

    def test_error_base_e_importes_invalidos_no_da_cifras_falsas(self):
        self.db.execute("UPDATE gastos_faenas_extras SET importe='NaN' WHERE id=2")
        with self.assertRaisesRegex(ValueError, "no finito"):
            self.resumen()
        self.db.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            self.resumen()

    def test_endpoint_administrador_y_rango_invalido(self):
        ruta = next(r for r in api.app.routes if getattr(r, "path", None) == "/resumen-economico")
        self.assertEqual(ruta.dependant.dependencies[0].call, api.administrador)
        with self.assertRaises(api.HTTPException) as error:
            api.resumen_economico(date(2026, 10, 31), date(2026, 10, 1), {})
        self.assertEqual(error.exception.status_code, 400)

        @contextlib.contextmanager
        def conexion():
            yield self.db

        class Hoy(date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 6)
        with patch.object(api, "date", Hoy), patch.object(api, "conexion", conexion), patch.object(api, "DATABASE_URL", ""):
            self.assertEqual(api.resumen_economico(usuario={}), self.resumen())

    def test_postgres_descubre_tablas_con_filas_diccionario(self):
        self.db.row_factory = sqlite3.Row
        base = self.db

        class Postgres:
            def execute(self, sql):
                if "information_schema.tables" in sql:
                    sql = "SELECT name AS table_name FROM sqlite_master WHERE type='table'"
                return base.execute(sql)

        self.assertEqual(
            calcular_resumen(Postgres(), date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 6), True),
            self.resumen())
