import contextlib
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import api_central as api


class PagosDiariosTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE ayudantes (id INTEGER PRIMARY KEY, nombre TEXT);
            INSERT INTO ayudantes VALUES (1, 'DANI'), (2, 'DESIRE');
            CREATE TABLE fichajes_ayudantes (
                id INTEGER PRIMARY KEY, ayudante_id INTEGER, fecha TEXT, obra TEXT,
                faena_id_vinculada INTEGER, confirmado_ayudante INTEGER
            );
            INSERT INTO fichajes_ayudantes VALUES
                (1, 1, '2026-10-03', 'Obra A', 25, 1),
                (2, 1, '2026-10-03', 'Obra B', 26, 1),
                (3, 1, '2026-10-04', 'Obra A', 25, 1),
                (4, 2, '2026-10-03', 'Obra A', 25, 1);
            CREATE TABLE pagos_jornadas (
                fichaje_id INTEGER PRIMARY KEY, importe REAL, importe_pagado REAL,
                forma_pago TEXT, estado_pago TEXT, fecha_pago TEXT,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE liquidaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ayudante_id INTEGER,
                desde TEXT, hasta TEXT, precio_dia REAL, importe_pagado REAL,
                fecha_pago TEXT, creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        self.patches = [patch.object(api, "conexion", conexion), patch.object(api, "DATABASE_URL", None)]
        for cambio in self.patches:
            cambio.start()

    def tearDown(self):
        for cambio in reversed(self.patches):
            cambio.stop()
        self.db.close()

    def lista(self):
        return api.listar_jornadas_pago(1, date(2026, 10, 3), date(2026, 10, 4), {})

    def pago(self, fichaje=1, pagado=20):
        return api.actualizar_pago_jornada(
            fichaje, api.PagoJornadaUpdate(importe=50, importe_pagado=pagado), {},
        )

    def test_agrupa_por_fecha_incluye_sabado_domingo_y_todas_las_obras(self):
        lista = self.lista()
        self.assertEqual(len(lista), 2)
        self.assertEqual(lista[0]["fichajes_ids"], [1, 2])
        self.assertIn("Obra A", lista[0]["obra"])
        self.assertIn("Obra B", lista[0]["obra"])

    def test_guardar_desde_otro_fichaje_actualiza_un_solo_pago(self):
        self.pago()
        self.pago(2, 50)
        filas = self.db.execute("SELECT * FROM pagos_jornadas").fetchall()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["fichaje_id"], 1)
        self.assertEqual(filas[0]["importe_pagado"], 50)
        self.assertEqual(api.consultar_pago_jornada(2, {})["estado_pago"], "Pagado")

    def test_no_mezcla_ayudantes(self):
        self.pago()
        self.pago(4)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM pagos_jornadas").fetchone()[0], 2)

    def test_conserva_y_bloquea_dos_pagos_historicos(self):
        self.db.executescript("""
            INSERT INTO pagos_jornadas VALUES (1,50,50,'Efectivo','Pagado','2026-10-03',NULL);
            INSERT INTO pagos_jornadas VALUES (2,75,20,'Transferencia','Parcial','2026-10-03',NULL);
        """)
        anterior = [dict(f) for f in self.db.execute("SELECT * FROM pagos_jornadas")]
        grupo = self.lista()[0]
        self.assertTrue(grupo["revision"])
        self.assertEqual(len(grupo["pagos_existentes"]), 2)
        self.assertEqual(api.consultar_pago_jornada(1, {})["estado_pago"], "Revisar")
        with self.assertRaises(api.HTTPException) as error:
            self.pago()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(anterior, [dict(f) for f in self.db.execute("SELECT * FROM pagos_jornadas")])

    def test_conserva_y_bloquea_pago_legacy(self):
        self.db.executescript("""
            CREATE TABLE gastos_faenas_extras (
                id INTEGER, faena_id INTEGER, proveedor TEXT, fecha TEXT, categoria TEXT,
                importe REAL, importe_pagado REAL, pagado REAL, forma_pago TEXT, estado_pago TEXT
            );
            INSERT INTO gastos_faenas_extras VALUES
                (10,25,'DANI','2026-10-03','Ayudantes',50,25,0,'Efectivo','Parcial');
        """)
        self.assertEqual(self.lista()[0]["pago"]["importe_pagado"], 25)
        with self.assertRaises(api.HTTPException) as error:
            self.pago()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM pagos_jornadas").fetchone()[0], 0)

    def test_liquidacion_cuenta_fechas_y_no_fichajes_ni_solo_laborables(self):
        resultado = api.crear_liquidacion(api.PagoCreate(
            ayudante_id=1, desde=date(2026, 10, 3), hasta=date(2026, 10, 4),
            precio_dia=50, importe_pagado=25,
        ), {})
        self.assertEqual(resultado["dias"], 2)
        self.assertEqual(resultado["total"], 100)
        lista = api.listar_liquidaciones(usuario={})
        self.assertEqual(lista[0]["dias"], 2)
        self.assertEqual(lista[0]["pendiente"], 75)
        self.assertEqual(api.listar_fichajes(1, None, None, {"rol": "administrador"})[0]["pagado"], False)

    def test_pago_diario_marca_todos_los_fichajes_del_dia(self):
        self.pago(pagado=50)
        lista = api.listar_fichajes(1, None, None, {"rol": "administrador"})
        self.assertTrue(all(f["pagado"] for f in lista if f["fecha"] == "2026-10-03"))
        self.assertFalse(next(f["pagado"] for f in lista if f["fecha"] == "2026-10-04"))

    def test_rango_invertido_informa_error(self):
        with self.assertRaises(api.HTTPException) as error:
            api.listar_jornadas_pago(1, date(2026, 10, 4), date(2026, 10, 3), {})
        self.assertEqual(error.exception.status_code, 400)

    def test_pago_existente_conserva_fecha_y_valores_al_guardar_sin_cambios(self):
        self.db.executescript("""
            INSERT INTO pagos_jornadas VALUES (2,50,20,'Transferencia','Parcial','2020-01-01',NULL);
        """)
        api.actualizar_pago_jornada(1, api.PagoJornadaUpdate(
            importe=50, importe_pagado=20, forma_pago="Transferencia",
        ), {})
        pago = dict(self.db.execute("SELECT * FROM pagos_jornadas").fetchone())
        self.assertEqual(pago["fichaje_id"], 2)
        self.assertEqual(pago["fecha_pago"], "2020-01-01")
        self.assertEqual(pago["importe_pagado"], 20)
        self.assertEqual(pago["forma_pago"], "Transferencia")

    def test_gasto_compartido_no_se_duplica_y_varios_gastos_se_detectan(self):
        self.db.executescript("""
            UPDATE fichajes_ayudantes SET faena_id_vinculada=25 WHERE id=2;
            CREATE TABLE gastos_faenas_extras (
                id INTEGER, faena_id INTEGER, proveedor TEXT, fecha TEXT, categoria TEXT,
                importe REAL, importe_pagado REAL, pagado REAL, forma_pago TEXT, estado_pago TEXT
            );
            INSERT INTO gastos_faenas_extras VALUES
                (10,25,'DANI','2026-10-03','Ayudantes',50,50,0,'Efectivo','Pagado');
        """)
        grupo = self.lista()[0]
        self.assertFalse(grupo["revision"])
        self.assertEqual(len(grupo["pagos_existentes"]), 1)
        lista = api.listar_fichajes(1, None, None, {"rol": "administrador"})
        self.assertTrue(all(f["pagado"] for f in lista if f["fecha"] == "2026-10-03"))
        self.db.executescript("""
            INSERT INTO gastos_faenas_extras VALUES
                (11,25,'DANI','2026-10-03','Ayudantes',75,20,0,'Transferencia','Parcial');
        """)
        self.assertTrue(self.lista()[0]["revision"])
        self.assertIsNone(self.lista()[0]["pago"]["importe"])
        with self.assertRaises(api.HTTPException) as error:
            self.pago()
        self.assertEqual(error.exception.status_code, 409)

    def test_errores_de_esquema_no_parecen_dias_sin_pagar(self):
        self.db.executescript("CREATE TABLE gastos_faenas_extras (id INTEGER)")
        with self.assertRaises(sqlite3.OperationalError):
            self.lista()

    def test_liquidacion_rechaza_fechas_invertidas(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            api.PagoCreate(ayudante_id=1, desde=date(2026, 10, 4), hasta=date(2026, 10, 3), precio_dia=50)


class AlarmasTrabajoTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE seguimientos_agenda (id INTEGER, fecha_recordatorio TEXT, hora TEXT,
                cliente TEXT, ubicacion TEXT, poblacion TEXT, motivo TEXT, estado TEXT,
                telefono TEXT, observaciones TEXT, actualizado_en TEXT);
            CREATE TABLE citas_agenda (id INTEGER, fecha TEXT, hora TEXT, cliente TEXT,
                ubicacion TEXT, poblacion TEXT, observaciones TEXT, estado TEXT);
            CREATE TABLE trabajos_propios (id INTEGER PRIMARY KEY, fecha_inicio TEXT,
                cliente TEXT, ubicacion TEXT, poblacion TEXT, obra TEXT, estado_cobro TEXT);
            INSERT INTO trabajos_propios VALUES
                (1,'2020-01-01','Cliente','Calle','Jaca','Reparación','No cobrado'),
                (2,'2020-01-01','Otro','Calle','Jaca','Puerta','Cobrado');
            CREATE TABLE estados_ejecucion_trabajos (
                trabajo_id INTEGER PRIMARY KEY, estado TEXT, actualizado_en TEXT
            );
        """)

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        self.cambio = patch.object(api, "conexion", conexion)
        self.cambio.start()

    def tearDown(self):
        self.cambio.stop()
        self.db.close()

    def test_trabajos_antiguos_y_cobros_separados(self):
        alarmas = api.listar_alarmas({})
        self.assertEqual(len([a for a in alarmas if a["tipo"] == "trabajo"]), 2)
        self.assertEqual(len([a for a in alarmas if a["tipo"] == "cobro"]), 1)

    def test_terminar_no_cobra_y_reabrir_no_cambia_cobro(self):
        api.actualizar_ejecucion_trabajo(1, api.EstadoEjecucionUpdate(estado="Terminado"), {})
        alarmas = api.listar_alarmas({})
        self.assertEqual(next(a["estado"] for a in alarmas if a["tipo"] == "trabajo" and a["referencia_id"] == 1), "Archivado")
        self.assertTrue(any(a["tipo"] == "cobro" and a["referencia_id"] == 1 for a in alarmas))
        self.assertEqual(self.db.execute("SELECT estado_cobro FROM trabajos_propios WHERE id=1").fetchone()[0], "No cobrado")
        api.actualizar_ejecucion_trabajo(1, api.EstadoEjecucionUpdate(estado="Pendiente"), {})
        self.assertEqual(next(a["estado"] for a in api.listar_alarmas({}) if a["tipo"] == "trabajo" and a["referencia_id"] == 1), "Pendiente")

    def test_trabajo_inexistente(self):
        with self.assertRaises(api.HTTPException) as error:
            api.actualizar_ejecucion_trabajo(999, api.EstadoEjecucionUpdate(estado="Terminado"), {})
        self.assertEqual(error.exception.status_code, 404)

    def test_completar_nota_conserva_datos(self):
        self.db.executescript("""
            INSERT INTO seguimientos_agenda
                (id, estado, telefono, observaciones, fecha_recordatorio)
                VALUES (7, 'Pendiente', '600123123', 'Detalle conservado', '2026-10-05');
        """)
        api.actualizar_estado_seguimiento(7, api.SeguimientoEstadoUpdate(estado="Realizado"), {})
        nota = dict(self.db.execute("SELECT * FROM seguimientos_agenda WHERE id=7").fetchone())
        self.assertEqual(nota["estado"], "Realizado")
        self.assertEqual(nota["telefono"], "600123123")
        self.assertEqual(nota["observaciones"], "Detalle conservado")
        self.assertEqual(nota["fecha_recordatorio"], "2026-10-05")
