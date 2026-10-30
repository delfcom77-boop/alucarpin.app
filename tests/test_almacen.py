import os
import shlex
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from almacen import crear_almacen


class AlmacenTests(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        self.addCleanup(self.directorio.cleanup)
        self.ruta = Path(self.directorio.name) / "almacen.db"
        def conexion():
            db = sqlite3.connect(self.ruta, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            return db
        self.conexion = conexion
        def usuario(authorization: str = Header(default="")):
            rol = authorization.removeprefix("Bearer ")
            if rol not in ("administrador", "ayudante", "otro"):
                raise HTTPException(401, "Sin acceso")
            return {"id": 1 if rol == "administrador" else 2, "rol": rol}
        def administrador(authorization: str = Header(default="")):
            resultado = usuario(authorization)
            if resultado["rol"] != "administrador":
                raise HTTPException(403, "Solo administrador")
            return resultado
        self.app = FastAPI()
        self.app.include_router(crear_almacen(conexion, usuario, administrador))
        self.cliente = self.enterContext(TestClient(self.app))
        self.cliente.headers["Authorization"] = "Bearer ayudante"

    def alta(self, **datos):
        return self.cliente.post("/almacen/materiales", json={
            "id": str(uuid4()), "nombre": "Silicona blanca", "unidad": "botes",
            "cantidad": "12", "minimo": "5", **datos,
        })

    def movimiento(self, material, tipo, cantidad, **datos):
        return self.cliente.post(f"/almacen/materiales/{material['id']}/movimientos", json={
            "id": str(uuid4()), "tipo": tipo, "cantidad": cantidad, **datos,
        })

    def materiales(self):
        respuesta = self.cliente.get("/almacen/materiales")
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.json()

    def test_salida_basica_12_menos_3_son_9(self):
        alta = self.alta()
        self.assertEqual(alta.status_code, 201)
        material = alta.json()
        self.assertEqual(material["cantidad"], "12")
        salida = self.movimiento(material, "salida", "3")
        self.assertEqual(salida.status_code, 201)
        self.assertEqual(salida.json()["stock_resultante"], "9")
        self.assertEqual(self.materiales()[0]["cantidad"], "9")
        historial = self.cliente.get("/almacen/movimientos").json()["movimientos"]
        self.assertEqual(len(historial), 2)
        self.assertEqual(historial[0]["tipo"], "salida")
        self.assertTrue(historial[0]["creado_en"])
        self.assertNotIn("usuario_id", historial[0])
        self.assertNotIn("usuario", historial[0])
        self.assertNotIn("ubicacion", material)
        self.assertEqual(historial[0]["motivo"], "")

    def test_entrada_y_cantidades_decimales_exactas(self):
        material = self.alta(nombre="Cable", unidad="metros", cantidad="10.1").json()
        self.movimiento(material, "entrada", "0.2")
        self.movimiento(material, "salida", "0.3")
        self.assertEqual(self.materiales()[0]["cantidad"], "10")

    def test_minimo_y_agotado(self):
        material = self.alta().json()
        self.movimiento(material, "salida", "8")
        self.assertEqual(self.materiales()[0]["situacion"], "Falta reponer")
        self.movimiento(material, "salida", "4")
        self.assertEqual(self.materiales()[0]["situacion"], "Agotado")
        sin_minimo = self.alta(nombre="Tornillo", cantidad="1", minimo=None).json()
        self.assertEqual(sin_minimo["situacion"], "Hay")
        self.assertIsNone(sin_minimo["minimo"])

    def test_salida_excesiva_no_altera_stock_ni_historial(self):
        material = self.alta().json()
        self.assertEqual(self.movimiento(material, "salida", "13").status_code, 409)
        self.assertEqual(self.materiales()[0]["cantidad"], "12")
        self.assertEqual(len(self.cliente.get("/almacen/movimientos").json()["movimientos"]), 1)

    def test_recuento_con_motivo_y_proteccion_de_version(self):
        material = self.alta().json()
        self.assertEqual(self.movimiento(material, "recuento", "7").status_code, 422)
        self.movimiento(material, "salida", "1")
        self.assertEqual(self.movimiento(material, "recuento", "7", motivo="Contado", version=1).status_code, 409)
        actual = self.materiales()[0]
        respuesta = self.movimiento(actual, "recuento", "0", motivo="Contado y agotado", version=actual["version"])
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()["stock_anterior"], "11")
        self.assertEqual(respuesta.json()["stock_resultante"], "0")

    def test_reintentar_alta_y_salida_no_duplica(self):
        ident = str(uuid4())
        primera = self.alta(id=ident).json()
        self.assertEqual(self.alta(id=ident).json(), primera)
        solicitud = str(uuid4())
        salida = self.movimiento(primera, "salida", "3", id=solicitud).json()
        self.assertEqual(self.movimiento(primera, "salida", "3", id=solicitud).json(), salida)
        self.assertEqual(self.movimiento(primera, "salida", "4", id=solicitud).status_code, 409)
        self.assertEqual(self.alta(id=ident, cantidad="99").status_code, 409)
        self.assertEqual(self.materiales()[0]["cantidad"], "9")
        self.assertEqual(len(self.cliente.get("/almacen/movimientos").json()["movimientos"]), 2)

    def test_no_crea_material_duplicado_y_ayudante_no_edita(self):
        material = self.alta().json()
        self.assertEqual(self.alta(nombre="  SILICONA   BLANCA ").status_code, 409)
        datos = {"nombre": "Otro", "unidad": "botes", "minimo": "3", "version": material["version"]}
        self.assertEqual(self.cliente.put("/almacen/materiales/" + material["id"], json=datos).status_code, 403)
        self.assertEqual(self.materiales()[0]["nombre"], "Silicona blanca")

    def test_admin_edita_desactiva_y_reactiva_sin_borrar(self):
        material = self.alta().json()
        self.cliente.headers["Authorization"] = "Bearer administrador"
        url = "/almacen/materiales/" + material["id"]
        datos = {"nombre": "Silicona blanca", "unidad": "botes", "minimo": "10", "version": 1, "activo": False}
        actual = self.cliente.put(url, json=datos)
        self.assertEqual(actual.status_code, 200)
        self.assertFalse(actual.json()["activo"])
        self.assertEqual(self.movimiento(material, "salida", "1").status_code, 409)
        self.assertEqual(self.cliente.put(url, json=datos).status_code, 409)
        datos.update(version=actual.json()["version"], activo=True)
        self.assertTrue(self.cliente.put(url, json=datos).json()["activo"])
        datos.update(version=self.materiales()[0]["version"], unidad="cajas")
        self.assertEqual(self.cliente.put(url, json=datos).status_code, 422)
        self.assertEqual(self.materiales()[0]["cantidad"], "12")

    def test_validacion(self):
        for datos in (
            {"nombre": " "}, {"cantidad": "-1"}, {"cantidad": "NaN"},
            {"cantidad": "Infinity"}, {"cantidad": "0.0001"}, {"minimo": "-1"},
            {"cantidad": "1000001"}, {"unidad": "inventada"}, {"ubicacion": "cajon"},
        ):
            with self.subTest(datos=datos):
                self.assertEqual(self.alta(**datos).status_code, 422)
        self.assertEqual(self.materiales(), [])
        material = self.alta().json()
        for tipo, cantidad in (("entrada", "0"), ("salida", "0"), ("salida", "-1"), ("salida", "0.0001")):
            with self.subTest(tipo=tipo, cantidad=cantidad):
                self.assertEqual(self.movimiento(material, tipo, cantidad).status_code, 422)

    def test_no_supera_cantidad_maxima(self):
        material = self.alta(cantidad="1000000").json()
        self.assertEqual(self.movimiento(material, "entrada", "0.001").status_code, 422)
        self.assertEqual(self.materiales()[0]["cantidad"], "1000000")

    def test_autorizacion(self):
        for rol, esperado in (("", 401), ("otro", 403)):
            self.cliente.headers["Authorization"] = "Bearer " + rol
            self.assertEqual(self.cliente.get("/almacen/materiales").status_code, esperado)
            self.assertEqual(self.cliente.get("/almacen/movimientos").status_code, esperado)
            self.assertEqual(self.alta().status_code, esperado)

    def test_historial_paginado_y_filtrado(self):
        material = self.alta().json()
        for _ in range(3):
            self.movimiento(material, "entrada", "1")
        otro = self.alta(nombre="Regleta").json()
        url = "/almacen/movimientos?limite=2&material_id=" + material["id"]
        primera = self.cliente.get(url).json()
        segunda = self.cliente.get(url, params={"limite": 2, "material_id": material["id"], "antes": primera["siguiente"]}).json()
        ids = [m["id"] for m in primera["movimientos"] + segunda["movimientos"]]
        self.assertEqual(len(set(ids)), 4)
        self.assertIsNone(segunda["siguiente"])
        self.assertNotIn(otro["id"], ids)

    def test_dos_salidas_simultaneas_no_generan_stock_negativo(self):
        material = self.alta(cantidad="3").json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            respuestas = list(pool.map(lambda _: self.movimiento(material, "salida", "2").status_code, range(2)))
        self.assertEqual(sorted(respuestas), [201, 409])
        self.assertEqual(self.materiales()[0]["cantidad"], "1")

    def test_error_base_explicito_y_rollback(self):
        material = self.alta().json()
        with closing(self.conexion()) as db:
            db.execute("CREATE TRIGGER fallo_movimiento BEFORE INSERT ON almacen_movimientos BEGIN SELECT RAISE(ABORT,'fallo de prueba'); END")
            db.commit()
        with self.assertLogs("almacen", level="ERROR"):
            self.assertEqual(self.movimiento(material, "salida", "3").status_code, 503)
        self.assertEqual(self.materiales()[0]["cantidad"], "12")

    def test_despliegue_incluye_archivos(self):
        raiz = Path(__file__).resolve().parents[1]
        incluidos = set()
        for linea in (raiz / "Dockerfile").read_text().splitlines():
            if linea.startswith("COPY "):
                incluidos.update(shlex.split(linea)[1:-1])
        for nombre in ("almacen.py", "app_web/almacen.html", "app_web/almacen.js", "app_web/almacen.css", "app_web/inicio_ayudante.html"):
            self.assertIn(nombre, incluidos)
            self.assertTrue((raiz / nombre).is_file())

    def test_menu_ayudantes_y_vuelta_desde_fichajes(self):
        raiz = Path(__file__).resolve().parents[1] / "app_web"
        login = (raiz / "login.html").read_text(encoding="utf-8")
        menu = (raiz / "inicio_ayudante.html").read_text(encoding="utf-8")
        fichajes = (raiz / "ayudante.html").read_text(encoding="utf-8")
        self.assertIn("'/app/inicio_ayudante.html'", login)
        self.assertIn('href="/app/almacen.html"', menu)
        self.assertIn('href="/app/ayudante.html"', menu)
        self.assertIn('href="/app/inicio_ayudante.html">Volver al menú', fichajes)

    def carpeta(self, nombre="Siliconas", **datos):
        return self.cliente.post("/almacen/carpetas", json={"id": str(uuid4()), "nombre": nombre, **datos})

    def test_carpetas_y_variantes_con_stock_independiente(self):
        carpeta = self.carpeta().json()
        blanca = self.alta(nombre="Blanca", carpeta_id=carpeta["id"]).json()
        negra = self.alta(nombre="Negra", carpeta_id=carpeta["id"], cantidad="4").json()
        salida = self.movimiento(blanca, "salida", "3").json()
        stocks = {m["id"]: m["cantidad"] for m in self.materiales()}
        self.assertEqual(stocks, {blanca["id"]: "9", negra["id"]: "4"})
        self.assertEqual(salida["nombre"], "Siliconas / Blanca")
        self.assertEqual(self.cliente.get("/almacen/carpetas").json(), [carpeta])
        self.assertEqual(self.alta(nombre="BLANCA", carpeta_id=carpeta["id"]).status_code, 409)
        otra = self.carpeta("Pinturas").json()
        self.assertEqual(self.alta(nombre="Blanca", carpeta_id=otra["id"]).status_code, 201)
        historial = self.cliente.get("/almacen/movimientos", params={"carpeta_id": carpeta["id"]}).json()["movimientos"]
        self.assertEqual(len(historial), 3)
        self.assertEqual({m["material_id"] for m in historial}, {blanca["id"], negra["id"]})

    def test_carpeta_reintento_y_validacion(self):
        ident = str(uuid4())
        primera = self.carpeta(id=ident)
        self.assertEqual(primera.status_code, 201)
        self.assertEqual(self.carpeta(id=ident).json(), primera.json())
        self.assertEqual(self.carpeta("Otro", id=ident).status_code, 409)
        self.assertEqual(self.carpeta(" SILICONAS ").status_code, 409)
        self.assertEqual(self.carpeta("  ").status_code, 422)
        self.assertEqual(self.alta(carpeta_id=str(uuid4())).status_code, 404)
        self.assertEqual(self.materiales(), [])

    def test_reubicar_material_anterior_conserva_stock_e_historial(self):
        material = self.alta().json()
        self.movimiento(material, "salida", "3")
        antes = self.cliente.get("/almacen/movimientos").json()
        carpeta = self.carpeta().json()
        self.cliente.headers["Authorization"] = "Bearer administrador"
        datos = {"nombre": "Blanca", "unidad": "botes", "minimo": "5", "version": 2, "carpeta_id": carpeta["id"]}
        actual = self.cliente.put("/almacen/materiales/" + material["id"], json=datos)
        self.assertEqual(actual.status_code, 200)
        self.assertEqual(actual.json()["cantidad"], "9")
        self.assertEqual(actual.json()["id"], material["id"])
        self.assertEqual(actual.json()["carpeta_id"], carpeta["id"])
        self.assertEqual(self.cliente.get("/almacen/movimientos").json(), antes)
        # Clientes antiguos que no envian carpeta no deben desasignarla.
        datos.pop("carpeta_id")
        datos["version"] = actual.json()["version"]
        actual = self.cliente.put("/almacen/materiales/" + material["id"], json=datos)
        self.assertEqual(actual.json()["carpeta_id"], carpeta["id"])
        self.assertEqual(self.movimiento(actual.json(), "salida", "1").json()["nombre"], "Siliconas / Blanca")

    def test_migracion_legacy_no_modifica_materiales_ni_movimientos(self):
        from almacen import inicializar_almacen
        material = self.alta().json()
        self.movimiento(material, "salida", "3")
        with closing(self.conexion()) as db:
            db.execute("ALTER TABLE almacen_materiales DROP COLUMN carpeta_id")
            db.execute("DROP TABLE almacen_carpetas")
            db.commit()
            materiales = [tuple(f) for f in db.execute("SELECT * FROM almacen_materiales")]
            movimientos = [tuple(f) for f in db.execute("SELECT * FROM almacen_movimientos")]
            inicializar_almacen(db)
            inicializar_almacen(db)
            db.commit()
            self.assertEqual([tuple(f)[:-1] for f in db.execute("SELECT * FROM almacen_materiales")], materiales)
            self.assertEqual([tuple(f) for f in db.execute("SELECT * FROM almacen_movimientos")], movimientos)
        self.assertIsNone(self.materiales()[0]["carpeta_id"])

    def test_permisos_carpetas_y_reintento_alta_legacy(self):
        ident = str(uuid4())
        material = self.alta(id=ident).json()
        carpeta = self.carpeta().json()
        self.cliente.headers["Authorization"] = "Bearer administrador"
        self.cliente.put("/almacen/materiales/" + ident, json={
            "nombre": "Blanca", "unidad": "botes", "minimo": "5", "version": 1, "carpeta_id": carpeta["id"],
        })
        self.cliente.headers["Authorization"] = "Bearer ayudante"
        self.assertEqual(self.alta(id=ident).json()["carpeta_id"], carpeta["id"])
        for rol, esperado in (("", 401), ("otro", 403)):
            self.cliente.headers["Authorization"] = "Bearer " + rol
            self.assertEqual(self.cliente.get("/almacen/carpetas").status_code, esperado)
            self.assertEqual(self.carpeta("Prueba").status_code, esperado)


@unittest.skipUnless(os.getenv("DATABASE_URL"), "Requiere PostgreSQL; solo tablas temporales")
class AlmacenPostgresTests(unittest.TestCase):
    def test_movimientos_postgres_reales_sin_tocar_stock_publico(self):
        from almacen import inicializar_almacen
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=15) as db:
            with closing(sqlite3.connect(":memory:")) as esquema:
                inicializar_almacen(esquema)
                sql = [f[0] for f in esquema.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name DESC")]
            orden = {"almacen_carpetas": 0, "almacen_materiales": 1, "almacen_movimientos": 2}
            for sentencia in sorted(sql, key=lambda s: orden[s.split()[2]]):
                db.execute(sentencia.replace("CREATE TABLE ", "CREATE TEMP TABLE ", 1))
            db.execute("SET LOCAL search_path TO pg_temp")
            class Conexion:
                def __init__(self):
                    self.db = db
                def execute(self, sql, parametros=()):
                    return db.execute(sql.replace("?", "%s"), parametros)
                def __enter__(self):
                    return self
                def __exit__(self, tipo, valor, traza):
                    if tipo:
                        raise AssertionError("Fallo en transaccion temporal") from valor
            wrapper = Conexion()
            inicializar_almacen(wrapper)
            app = FastAPI()
            def usuario():
                return {"id": 99, "rol": "administrador"}
            router = crear_almacen(lambda: wrapper, usuario, usuario)
            app.include_router(router)
            rutas = {r.path + ":" + next(iter(r.methods)): r.endpoint for r in router.routes}
            from almacen import NuevoMaterial, Movimiento, NuevaCarpeta
            carpeta = rutas["/almacen/carpetas:POST"](NuevaCarpeta(id=uuid4(), nombre="Siliconas"))
            ident = uuid4()
            material = rutas["/almacen/materiales:POST"](NuevoMaterial(id=ident, nombre="Blanca", cantidad="12", carpeta_id=carpeta["id"]), usuario())
            salida = rutas["/almacen/materiales/{ident}/movimientos:POST"](
                ident, Movimiento(id=uuid4(), tipo="salida", cantidad="3"), usuario(),
            )
            self.assertEqual(material["cantidad"], "12")
            self.assertEqual(salida["stock_resultante"], "9")
            self.assertEqual(salida["nombre"], "Siliconas / Blanca")
            self.assertEqual(material["carpeta_id"], carpeta["id"])
            self.assertTrue(db.execute("SELECT relrowsecurity FROM pg_class WHERE oid='pg_temp.almacen_materiales'::regclass").fetchone()["relrowsecurity"])
