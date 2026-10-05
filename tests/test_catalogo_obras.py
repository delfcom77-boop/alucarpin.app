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

    def test_impide_nombres_nuevos_en_version_antigua(self):
        with self.assertRaises(api.HTTPException) as error:
            self.crear(referencia=None)
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fichajes_ayudantes").fetchone()[0], 0)

    def test_rechaza_referencia_inexistente_y_tipo_incompatible(self):
        for referencia, tipo in [("faena:999", "faena"), ("reparacion:20", "faena")]:
            with self.subTest(referencia=referencia):
                with self.assertRaises(api.HTTPException) as error:
                    self.crear(referencia, tipo)
                self.assertEqual(error.exception.status_code, 400)

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

    def test_edicion_impide_nombres_nuevos_sin_catalogo(self):
        fichaje = self.crear()
        with self.assertRaises(api.HTTPException) as error:
            api.modificar_fichaje(fichaje["id"], api.FichajeUpdate(cliente="Nuevo"), self.usuario)
        self.assertEqual(error.exception.status_code, 400)

    def test_edicion_solo_fecha_sigue_permitida(self):
        fichaje = self.crear()
        editado = api.modificar_fichaje(
            fichaje["id"], api.FichajeUpdate(fecha=date(2026, 10, 6)), self.usuario,
        )
        self.assertEqual(editado["fecha"], "2026-10-06")

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
