import contextlib
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import api_central as api


class CatalogoObrasTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE faenas (
                id INTEGER PRIMARY KEY, cliente TEXT, obra TEXT, ubicacion TEXT,
                poblacion TEXT, fecha TEXT, precio REAL, ayudantes TEXT,
                estado_revision TEXT
            );
            CREATE TABLE presupuestos (id INTEGER PRIMARY KEY, cliente TEXT, num_presupuesto TEXT);
            CREATE TABLE trabajos_propios (
                id INTEGER PRIMARY KEY, tipo TEXT, cliente TEXT, obra TEXT,
                ubicacion TEXT, poblacion TEXT
            );
            CREATE TABLE fichajes_ayudantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ayudante_id INTEGER, fecha TEXT,
                tipo_destino TEXT, cliente TEXT, obra TEXT, ubicacion TEXT, poblacion TEXT,
                num_presupuesto TEXT, faena_id_vinculada INTEGER, presupuesto_id INTEGER,
                trabajo_propio_id INTEGER, estado_revision TEXT, confirmado_ayudante INTEGER,
                sincronizado INTEGER, actualizado_en TEXT
            );
            CREATE TABLE pagos_jornadas (fichaje_id INTEGER, importe REAL, importe_pagado REAL);
            INSERT INTO faenas VALUES (25, 'Decoradora', 'Santjoanistes nº 4', 'Calle 4',
                'Barcelona', '2026-09-15', 400, 'Sí', 'Validado');
            INSERT INTO presupuestos VALUES (10, 'Alucarpin Samitier', 'P-10');
            INSERT INTO presupuestos VALUES (11, 'Alucarpin Samitier', NULL);
            INSERT INTO trabajos_propios VALUES (20, 'reparacion', 'Cliente reparación',
                'Puerta', 'Calle 2', 'Jaca');
        """)
        self.usuario = {"rol": "ayudante", "ayudante_id": 1}

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        self.patches = [
            patch.object(api, "conexion", conexion),
            patch.object(api, "DATABASE_URL", None),
        ]
        for cambio in self.patches:
            cambio.start()

    def tearDown(self):
        for cambio in reversed(self.patches):
            cambio.stop()
        self.db.close()

    def crear(self, referencia="faena:25", tipo="faena", usuario=None):
        return api.crear_fichaje(
            api.FichajeCreate(
                ayudante_id=1, fecha=date(2026, 10, 5), tipo_destino=tipo,
                cliente="Nombre inventado", obra="Obra inventada",
                ubicacion="Otra dirección", num_presupuesto="Número inventado",
                obra_catalogo=referencia,
            ),
            usuario or self.usuario,
        )

    def test_catalogo_disponible_al_ayudante_sin_importes(self):
        obras = api.listar_catalogo_obras(self.usuario)
        self.assertEqual(len(obras), 4)
        self.assertEqual({obra["referencia"] for obra in obras},
                         {"faena:25", "presupuesto:10", "presupuesto:11", "reparacion:20"})
        self.assertTrue(all("precio" not in obra for obra in obras))

    def test_crea_jornada_con_nombres_y_vinculo_canonicos_sin_duplicar_faena(self):
        fichaje = self.crear()
        self.assertEqual((fichaje["cliente"], fichaje["obra"], fichaje["ubicacion"]),
                         ("Decoradora", "Santjoanistes nº 4", "Calle 4"))
        self.assertEqual(fichaje["faena_id_vinculada"], 25)
        self.assertIsNone(fichaje["num_presupuesto"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM faenas").fetchone()[0], 1)

    def test_fichaje_manual_no_crea_ni_vincula_obras(self):
        for tipo in ("pendiente", "faena", "presupuesto", "reparacion"):
            with self.subTest(tipo=tipo):
                fichaje = self.crear(referencia=None, tipo=tipo)
                self.assertEqual(fichaje["cliente"], "Nombre inventado")
                self.assertEqual(fichaje["obra"], "Obra inventada")
                self.assertEqual(fichaje["tipo_destino"], tipo)
                self.assertEqual(fichaje["estado_revision"], "Pendiente de revisar")
                for campo in ("faena_id_vinculada", "presupuesto_id",
                              "trabajo_propio_id", "num_presupuesto"):
                    self.assertIsNone(fichaje[campo])
        for tabla, cantidad in (("faenas", 1), ("presupuestos", 2), ("trabajos_propios", 1)):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], cantidad)

    def test_rechaza_referencia_inexistente_y_tipo_incompatible(self):
        for referencia, tipo in [("faena:999", "faena"), ("reparacion:20", "faena")]:
            with self.subTest(referencia=referencia):
                with self.assertRaises(api.HTTPException) as error:
                    self.crear(referencia, tipo)
                self.assertEqual(error.exception.status_code, 400)

    def test_nombre_identico_a_faena_existente_no_vincula_automaticamente(self):
        fichaje = api.crear_fichaje(
            api.FichajeCreate(
                ayudante_id=1, fecha="2026-09-15", tipo_destino="faena",
                cliente="Decoradora", obra="Santjoanistes nº 4",
                ubicacion="Calle 4", poblacion="Barcelona",
            ),
            self.usuario,
        )
        self.assertIsNone(fichaje["faena_id_vinculada"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM faenas").fetchone()[0], 1)

    def test_presupuesto_existente_y_provisional_no_crean_otro(self):
        for referencia in ["presupuesto:10", "presupuesto:11"]:
            fichaje = self.crear(referencia, "presupuesto")
            self.assertEqual(fichaje["presupuesto_id"], int(referencia.split(":")[1]))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM presupuestos").fetchone()[0], 2)

    def test_reparacion_existente_no_se_duplica_y_tipo_se_resuelve(self):
        fichaje = self.crear("reparacion:20", "pendiente")
        self.assertEqual(fichaje["tipo_destino"], "reparacion")
        self.assertEqual(fichaje["trabajo_propio_id"], 20)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM trabajos_propios").fetchone()[0], 1)

    def test_no_permite_registrar_otro_ayudante(self):
        with self.assertRaises(api.HTTPException) as error:
            self.crear(usuario={"rol": "ayudante", "ayudante_id": 2})
        self.assertEqual(error.exception.status_code, 403)

    def test_edicion_cambia_vinculo_y_preserva_pago_fecha_y_ayudante(self):
        fichaje = self.crear()
        self.db.execute("INSERT INTO pagos_jornadas VALUES (?, 50, 50)", (fichaje["id"],))
        editado = api.modificar_fichaje(
            fichaje["id"],
            api.FichajeUpdate(obra_catalogo="reparacion:20", tipo_destino="reparacion"),
            self.usuario,
        )
        self.assertEqual(editado["trabajo_propio_id"], 20)
        self.assertIsNone(editado["faena_id_vinculada"])
        self.assertIsNone(editado["presupuesto_id"])
        self.assertEqual(editado["fecha"], fichaje["fecha"])
        self.assertEqual(editado["ayudante_id"], fichaje["ayudante_id"])
        self.assertEqual(self.db.execute("SELECT importe_pagado FROM pagos_jornadas").fetchone()[0], 50)

    def test_edicion_manual_de_fichaje_vinculado_requiere_administrador(self):
        fichaje = self.crear()
        with self.assertRaises(api.HTTPException) as error:
            api.modificar_fichaje(fichaje["id"], api.FichajeUpdate(cliente="Nuevo"), self.usuario)
        self.assertEqual(error.exception.status_code, 409)

    def test_edicion_manual_sin_vinculo_preserva_id_y_pago(self):
        fichaje = self.crear(referencia=None)
        self.db.execute("INSERT INTO pagos_jornadas VALUES (?, 50, 25)", (fichaje["id"],))
        editado = api.modificar_fichaje(
            fichaje["id"],
            api.FichajeUpdate(cliente=" Cliente nuevo ", obra=" Obra corregida ",
                              ubicacion=" Calle nueva ", tipo_destino="presupuesto"),
            self.usuario,
        )
        self.assertEqual(editado["id"], fichaje["id"])
        self.assertEqual(editado["cliente"], "Cliente nuevo")
        self.assertEqual(editado["obra"], "Obra corregida")
        self.assertEqual(editado["ubicacion"], "Calle nueva")
        self.assertIsNone(editado["presupuesto_id"])
        self.assertEqual(self.db.execute("SELECT importe_pagado FROM pagos_jornadas").fetchone()[0], 25)

    def test_administrador_vincula_fichaje_manual_a_cualquier_tipo(self):
        fichaje = self.crear(referencia=None)
        self.db.execute("INSERT INTO pagos_jornadas VALUES (?, 50, 25)", (fichaje["id"],))
        for referencia, campo in (("presupuesto:10", "presupuesto_id"),
                                   ("faena:25", "faena_id_vinculada"),
                                   ("reparacion:20", "trabajo_propio_id")):
            with self.subTest(referencia=referencia):
                editado = api.modificar_fichaje(
                    fichaje["id"], api.FichajeUpdate(obra_catalogo=referencia),
                    {"rol": "administrador"},
                )
                self.assertEqual(editado["id"], fichaje["id"])
                self.assertEqual(editado[campo], int(referencia.split(":")[1]))
                for otro in {"presupuesto_id", "faena_id_vinculada", "trabajo_propio_id"} - {campo}:
                    self.assertIsNone(editado[otro])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fichajes_ayudantes").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT importe_pagado FROM pagos_jornadas").fetchone()[0], 25)

    def test_administrador_desvincula_sin_borrar_dia_ni_pago(self):
        fichaje = self.crear("presupuesto:10", "presupuesto")
        self.db.execute("INSERT INTO pagos_jornadas VALUES (?, 50, 25)", (fichaje["id"],))
        editado = api.modificar_fichaje(
            fichaje["id"], api.FichajeUpdate(obra_catalogo=None),
            {"rol": "administrador"},
        )
        self.assertEqual(editado["id"], fichaje["id"])
        self.assertEqual(editado["cliente"], fichaje["cliente"])
        self.assertEqual(editado["estado_revision"], "Pendiente de revisar")
        for campo in ("presupuesto_id", "faena_id_vinculada", "trabajo_propio_id", "num_presupuesto"):
            self.assertIsNone(editado[campo])
        self.assertEqual(self.db.execute("SELECT importe_pagado FROM pagos_jornadas").fetchone()[0], 25)

    def test_edicion_solo_fecha_sigue_permitida(self):
        fichaje = self.crear()
        editado = api.modificar_fichaje(
            fichaje["id"], api.FichajeUpdate(fecha=date(2026, 10, 6)), self.usuario,
        )
        self.assertEqual(editado["fecha"], "2026-10-06")

    def test_datos_manuales_vacios_y_nulos_se_rechazan(self):
        for campo in ("cliente", "obra"):
            with self.subTest(campo=campo):
                with self.assertRaises(ValueError):
                    api.FichajeCreate(
                        ayudante_id=1, fecha="2026-10-13",
                        **{"cliente": "Cliente", "obra": "Obra", campo: "   "},
                    )
        for campo in ("fecha", "tipo_destino", "cliente", "obra", "ubicacion", "poblacion"):
            with self.subTest(campo=campo):
                with self.assertRaises(ValueError):
                    api.FichajeUpdate(**{campo: None})

    def test_vinculo_inexistente_no_cambia_datos_manuales(self):
        fichaje = self.crear(referencia=None)
        with self.assertRaises(api.HTTPException):
            api.modificar_fichaje(
                fichaje["id"], api.FichajeUpdate(cliente="Corregido", obra_catalogo="faena:999"),
                {"rol": "administrador"},
            )
        guardado = dict(self.db.execute("SELECT * FROM fichajes_ayudantes WHERE id=?", (fichaje["id"],)).fetchone())
        self.assertEqual(guardado, fichaje)

    def test_ayudante_no_puede_desvincular_ni_editar_registro_ajeno(self):
        fichaje = self.crear(referencia=None)
        for cambios, usuario in (
            (api.FichajeUpdate(obra_catalogo=None), self.usuario),
            (api.FichajeUpdate(cliente="Otro"), {"rol": "ayudante", "ayudante_id": 2}),
        ):
            with self.assertRaises(api.HTTPException) as error:
                api.modificar_fichaje(fichaje["id"], cambios, usuario)
            self.assertEqual(error.exception.status_code, 403)

    def test_edicion_con_referencia_ignora_nombres_y_numero_inventados(self):
        fichaje = self.crear()
        editado = api.modificar_fichaje(
            fichaje["id"],
            api.FichajeUpdate(
                obra_catalogo="presupuesto:10", tipo_destino="presupuesto",
                cliente="Inventado", obra="Inventada", num_presupuesto="No existe",
            ),
            self.usuario,
        )
        self.assertEqual(editado["cliente"], "Alucarpin Samitier")
        self.assertEqual(editado["obra"], "Presupuesto nº P-10")
        self.assertEqual(editado["num_presupuesto"], "P-10")
        self.assertIsNone(editado["faena_id_vinculada"])

    def test_presupuesto_a_faena_limpia_vinculos_anteriores(self):
        fichaje = self.crear("presupuesto:10", "presupuesto")
        editado = api.modificar_fichaje(
            fichaje["id"], api.FichajeUpdate(obra_catalogo="faena:25", tipo_destino="faena"),
            self.usuario,
        )
        self.assertIsNone(editado["presupuesto_id"])
        self.assertIsNone(editado["num_presupuesto"])
        self.assertEqual(editado["faena_id_vinculada"], 25)

    def test_edicion_solo_referencia_resuelve_nuevo_tipo(self):
        fichaje = self.crear()
        editado = api.modificar_fichaje(
            fichaje["id"], api.FichajeUpdate(obra_catalogo="reparacion:20"), self.usuario,
        )
        self.assertEqual(editado["tipo_destino"], "reparacion")

    def test_edicion_no_permite_otro_ayudante(self):
        fichaje = self.crear()
        with self.assertRaises(api.HTTPException) as error:
            api.modificar_fichaje(
                fichaje["id"], api.FichajeUpdate(obra_catalogo="faena:25"),
                {"rol": "ayudante", "ayudante_id": 2},
            )
        self.assertEqual(error.exception.status_code, 403)

    def test_administrador_puede_crear_faena_nueva(self):
        datos = api.FichajeCreate(
            ayudante_id=1, fecha=date(2026, 10, 5), tipo_destino="faena",
            cliente="Nuevo cliente", obra="Nueva obra",
        )
        fichaje = api.crear_fichaje(datos, {"rol": "administrador"})
        self.assertEqual(fichaje["cliente"], "Nuevo cliente")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM faenas").fetchone()[0], 2)
