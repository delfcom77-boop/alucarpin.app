import contextlib
import sqlite3
import unittest
from unittest.mock import patch

import api_central as api


class RematesVinculadosTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE faenas (id INTEGER PRIMARY KEY, cliente TEXT, obra TEXT, ubicacion TEXT, poblacion TEXT);
            CREATE TABLE presupuestos (id INTEGER PRIMARY KEY, cliente TEXT, num_presupuesto TEXT);
            CREATE TABLE trabajos_propios (id INTEGER PRIMARY KEY, tipo TEXT, cliente TEXT, obra TEXT, ubicacion TEXT, poblacion TEXT);
            CREATE TABLE remates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, origen TEXT, origen_id INTEGER,
                cliente TEXT, obra TEXT, pieza TEXT, lacado_color TEXT, tipo TEXT,
                modo_chapa TEXT, orientacion_chapa TEXT, posicion_medidas TEXT,
                medida_1 REAL, medida_2 REAL, medida_3 REAL, largura REAL, cantidad INTEGER,
                observaciones TEXT
            );
            INSERT INTO faenas VALUES (1,'Cliente','Obra','','');
            INSERT INTO faenas VALUES (2,'Cliente','Obra','','');
            INSERT INTO presupuestos VALUES (1,'Cliente','P-1');
            INSERT INTO trabajos_propios VALUES (1,'reparacion','Cliente','Obra','','');
            INSERT INTO remates VALUES (10,'tercero',0,'Cliente','Obra','Ventana','Blanco','u',
                'normal','abajo','exterior',10,20,30,2500,2,'Conservar');
        """)

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        for cambio in (patch.object(api, "conexion", conexion), patch.object(api, "DATABASE_URL", None),
                       patch.object(api, "inicializar_base_datos")):
            cambio.start()
            self.addCleanup(cambio.stop)
        api.startup()

    def crear(self, referencia, origen="propia"):
        return api.crear_remate(api.RemateCreate(
            origen=origen, obra_catalogo=referencia, cliente="Incorrecto", obra="Incorrecta",
            pieza="Puerta", lacado_color="Blanco", tipo="u", largura=2500,
            medida_1=10, medida_2=20, medida_3=30,
        ), {})

    def listar(self, **filtros):
        return api.listar_remates(origen=filtros.get("origen"), cliente=filtros.get("cliente"),
                                  obra=filtros.get("obra"), usuario={})

    def test_creacion_canonica_con_ids_coincidentes_y_nombres_iguales(self):
        for referencia in ("faena:1", "faena:2", "presupuesto:1", "reparacion:1"):
            self.crear(referencia, "tercero" if referencia.startswith("faena:") else "propia")
        vinculados = [r for r in self.listar() if r["obra_catalogo"]]
        self.assertEqual({r["obra_catalogo"] for r in vinculados},
                         {"faena:1", "faena:2", "presupuesto:1", "reparacion:1"})
        self.assertTrue(all(r["cliente"] == "Cliente" for r in vinculados))
        self.assertEqual(len(self.listar(origen="tercero")), 3)

    def test_historicos_no_se_vinculan_por_nombre_ni_origen_id(self):
        self.db.execute("UPDATE remates SET origen_id=1 WHERE id=10")
        self.db.commit()
        api.startup()
        self.assertIsNone(self.listar()[0]["obra_catalogo"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM remates_vinculos").fetchone()[0], 0)

    def test_vinculo_manual_preserva_todo_el_remate_y_puede_cambiarse(self):
        antes = dict(self.db.execute("SELECT * FROM remates WHERE id=10").fetchone())
        for referencia in ("faena:1", "presupuesto:1", "reparacion:1"):
            api.vincular_remate(10, api.RemateVinculacion(obra_catalogo=referencia), {})
            self.assertEqual(self.listar()[0]["obra_catalogo"], referencia)
            self.assertEqual(antes, dict(self.db.execute("SELECT * FROM remates WHERE id=10").fetchone()))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM remates_vinculos").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM pagos_ingresos").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM pagos_faenas").fetchone()[0], 0)

    def test_renombrado_se_refleja_y_filtra_por_nombre_actual(self):
        api.vincular_remate(10, api.RemateVinculacion(obra_catalogo="faena:1"), {})
        self.db.execute("UPDATE faenas SET cliente='Nuevo', obra='Renombrada' WHERE id=1")
        self.db.commit()
        self.assertEqual(len(self.listar(cliente="Nuevo", obra="Renombrada")), 1)
        self.assertEqual(self.listar(cliente="Cliente"), [])

    def test_rechaza_destinos_ausentes_y_tipo_incompatible_sin_guardar(self):
        for referencia, origen in ((None, "tercero"), ("faena:999", "tercero"),
                                   ("faena:1", "propia"), ("presupuesto:1", "tercero")):
            with self.subTest(referencia=referencia), self.assertRaises(api.HTTPException) as error:
                self.crear(referencia, origen)
            self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(len(self.listar()), 1)

    def test_vinculacion_invalida_no_cambia_vinculo_existente(self):
        api.vincular_remate(10, api.RemateVinculacion(obra_catalogo="faena:1"), {})
        for ident, referencia, estado in ((999, "faena:1", 404), (10, "faena:999", 400)):
            with self.assertRaises(api.HTTPException) as error:
                api.vincular_remate(ident, api.RemateVinculacion(obra_catalogo=referencia), {})
            self.assertEqual(error.exception.status_code, estado)
        self.assertEqual(self.listar()[0]["obra_catalogo"], "faena:1")

    def test_no_deja_remate_huerfano_si_falla_insertar_vinculo(self):
        with patch.object(api, "guardar_vinculo_remate", side_effect=sqlite3.IntegrityError("Prueba")):
            with self.assertRaises(sqlite3.IntegrityError):
                self.crear("faena:1", "tercero")
        self.assertEqual(len(self.listar()), 1)

    def test_no_se_borra_obra_con_remates_y_borrar_remate_libera_vinculo(self):
        for referencia, tabla in (("faena:1", "faenas"), ("presupuesto:1", "presupuestos"), ("reparacion:1", "trabajos_propios")):
            with self.subTest(referencia=referencia):
                api.vincular_remate(10, api.RemateVinculacion(obra_catalogo=referencia), {})
                with self.assertRaises(sqlite3.IntegrityError):
                    self.db.execute(f"DELETE FROM {tabla} WHERE id=1")
                borrar = {"faenas": api.borrar_faena, "presupuestos": api.borrar_presupuesto,
                          "trabajos_propios": api.borrar_trabajo}[tabla]
                with self.assertRaises(api.HTTPException) as error:
                    borrar(1, {})
                self.assertEqual(error.exception.status_code, 409)
        api.borrar_remate(10, {})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM remates_vinculos").fetchone()[0], 0)

    def test_rutas_exigen_administrador(self):
        for nombre in ("listar_remates", "crear_remate", "vincular_remate", "borrar_remate"):
            ruta = next(r for r in api.app.routes if r.name == nombre)
            self.assertIn(api.administrador, [d.call for d in ruta.dependant.dependencies])


if __name__ == "__main__":
    unittest.main()
