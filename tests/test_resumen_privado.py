import contextlib
import hashlib
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, Depends, Header
from fastapi.testclient import TestClient

from autenticacion import hash_password
import api_central as api
import resumen_privado as privado


class ResumenPrivadoTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE usuarios(id INTEGER PRIMARY KEY,password_salt TEXT,password_hash TEXT,activo INTEGER)"
        )
        salt, digest = hash_password("CuentaPrueba2026!")
        self.db.execute("INSERT INTO usuarios VALUES(1,?,?,1)", (salt, digest))
        self.db.commit()
        self.usuario = {"id": 1, "rol": "administrador"}

        @contextlib.contextmanager
        def conexion():
            with self.db:
                yield self.db

        def admin():
            if self.usuario["rol"] != "administrador":
                from fastapi import HTTPException
                raise HTTPException(403)
            return self.usuario

        app = FastAPI()
        router, acceso = privado.crear_acceso_privado(conexion, admin)
        app.include_router(router)

        @app.get("/panel-resumen")
        def panel(usuario=Depends(acceso)):
            return {"importe": 1234}

        @app.get("/resumen-economico")
        def economia(usuario=Depends(acceso)):
            return {"importe": 5678}

        self.client = TestClient(app, headers={"Authorization": "Bearer sesion-prueba"})
        self.client.__enter__()
        self.addCleanup(self.db.close)
        self.addCleanup(self.client.__exit__, None, None, None)

    def configurar(self, **datos):
        return self.client.put("/resumen-privado/configuracion", json={
            "password_admin": "CuentaPrueba2026!", "password_nueva": "PrivadaPrueba2026!",
            **datos,
        })

    def abrir(self, clave="PrivadaPrueba2026!"):
        return self.client.post("/resumen-privado/abrir", json={"password": clave})

    def cabecera(self):
        self.assertEqual(self.configurar().status_code, 200)
        respuesta = self.abrir()
        self.assertEqual(respuesta.status_code, 200)
        return {"X-Resumen-Token": respuesta.json()["token"]}

    def test_endpoints_reales_exigen_acceso_privado(self):
        for nombre in ("/panel-resumen", "/resumen-economico"):
            ruta = next(r for r in api.app.routes if getattr(r, "path", None) == nombre)
            self.assertEqual(ruta.dependant.dependencies[0].call, api.resumen_autorizado)

    def test_bloqueado_incluso_con_sesion_admin_y_enlaces_directos(self):
        for ruta in ("/panel-resumen", "/resumen-economico"):
            respuesta = self.client.get(ruta)
            self.assertEqual(respuesta.status_code, 403)
            self.assertIn("no-store", respuesta.headers["cache-control"])
            self.assertNotIn("importe", respuesta.json())

    def test_configurar_exige_reautenticacion_y_clave_distinta(self):
        self.assertEqual(self.configurar(password_admin="Incorrecta").status_code, 403)
        self.assertEqual(self.configurar(password_nueva="corta").status_code, 422)
        self.assertEqual(self.configurar(password_nueva="CuentaPrueba2026!").status_code, 422)
        self.assertFalse(self.client.get("/resumen-privado/estado").json()["configurado"])
        self.assertEqual(self.configurar().status_code, 200)
        fila = self.db.execute("SELECT * FROM resumen_privado").fetchone()
        self.assertNotIn("PrivadaPrueba2026!", tuple(fila))
        self.assertEqual(fila["propietario_id"], 1)

    def test_desbloqueo_valido_protege_ambos_resumenes_y_no_cache(self):
        cabecera = self.cabecera()
        for ruta in ("/panel-resumen", "/resumen-economico"):
            respuesta = self.client.get(ruta, headers=cabecera)
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn("no-store", respuesta.headers["cache-control"])
        token = cabecera["X-Resumen-Token"]
        fila = self.db.execute("SELECT token_hash FROM sesiones_resumen_privado").fetchone()
        self.assertNotEqual(fila["token_hash"], token)
        self.assertEqual(fila["token_hash"], hashlib.sha256(token.encode()).hexdigest())

    def test_token_caduca_y_no_admite_falsificacion(self):
        cabecera = self.cabecera()
        self.assertEqual(self.client.get("/panel-resumen", headers={"X-Resumen-Token": "inventado"}).status_code, 403)
        self.db.execute("UPDATE sesiones_resumen_privado SET caduca=0")
        self.db.commit()
        self.assertEqual(self.client.get("/panel-resumen", headers=cabecera).status_code, 403)

    def test_token_vinculado_a_usuario_y_sesion_de_login(self):
        cabecera = self.cabecera()
        self.assertEqual(self.client.get("/panel-resumen", headers={
            **cabecera, "Authorization": "Bearer otra-sesion"
        }).status_code, 403)
        self.usuario = {"id": 2, "rol": "administrador"}
        self.assertEqual(self.client.get("/panel-resumen", headers=cabecera).status_code, 403)
        self.assertEqual(self.abrir().status_code, 403)
        self.assertEqual(self.configurar().status_code, 403)
        self.assertEqual(self.client.get("/resumen-privado/estado").status_code, 403)

    def test_cerrar_revoca_token_en_servidor(self):
        cabecera = self.cabecera()
        self.assertEqual(self.client.post("/resumen-privado/cerrar", headers=cabecera).status_code, 200)
        self.assertEqual(self.client.get("/panel-resumen", headers=cabecera).status_code, 403)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sesiones_resumen_privado").fetchone()[0], 0)

    def test_cinco_intentos_bloquean_y_se_persisten(self):
        self.configurar()
        for _ in range(4):
            self.assertEqual(self.abrir("Incorrecta").status_code, 403)
        self.assertEqual(self.abrir("Incorrecta").status_code, 429)
        self.assertEqual(self.abrir().status_code, 429)
        self.assertEqual(self.configurar().status_code, 429)
        with patch.object(privado.time, "time", return_value=privado.time.time() + 301):
            self.assertEqual(self.abrir().status_code, 200)

    def test_cambiar_clave_exige_actual_y_revoca_accesos(self):
        cabecera = self.cabecera()
        self.assertEqual(self.configurar(password_nueva="NuevaPrueba2026!").status_code, 403)
        self.assertEqual(self.configurar(
            password_nueva="NuevaPrueba2026!", password_actual="PrivadaPrueba2026!"
        ).status_code, 200)
        self.assertEqual(self.client.get("/panel-resumen", headers=cabecera).status_code, 403)
        self.assertEqual(self.abrir().status_code, 403)
        self.assertEqual(self.abrir("NuevaPrueba2026!").status_code, 200)

    def test_ayudante_no_configura_ni_abre(self):
        self.usuario = {"id": 2, "rol": "ayudante"}
        self.assertEqual(self.configurar().status_code, 403)
        self.assertEqual(self.abrir().status_code, 403)
        self.assertEqual(self.client.get("/panel-resumen").status_code, 403)

    def test_configuracion_simultanea_no_cambia_propietario(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "privado.db"

            @contextlib.contextmanager
            def conexion():
                db = sqlite3.connect(ruta, timeout=5, check_same_thread=False)
                db.row_factory = sqlite3.Row
                try:
                    with db:
                        yield db
                finally:
                    db.close()

            with conexion() as db:
                db.execute("CREATE TABLE usuarios(id INTEGER PRIMARY KEY,password_salt TEXT,password_hash TEXT,activo INTEGER)")
                salt, digest = hash_password("CuentaPrueba2026!")
                db.executemany("INSERT INTO usuarios VALUES(?,?,?,1)", [(1, salt, digest), (2, salt, digest)])

            def admin(x_usuario: int = Header(default=1)):
                return {"id": x_usuario, "rol": "administrador"}

            app = FastAPI()
            router, _ = privado.crear_acceso_privado(conexion, admin)
            app.include_router(router)
            original = privado.hash_password

            def hash_lento(clave):
                time.sleep(0.2)
                return original(clave)

            with TestClient(app) as cliente, patch.object(privado, "hash_password", side_effect=hash_lento):
                def configurar(usuario):
                    return cliente.put("/resumen-privado/configuracion", headers={"X-Usuario": str(usuario)}, json={
                        "password_admin": "CuentaPrueba2026!", "password_nueva": "PrivadaPrueba2026!",
                    }).status_code

                with ThreadPoolExecutor(max_workers=2) as ejecutor:
                    estados = list(ejecutor.map(configurar, (1, 2)))
                self.assertEqual(sorted(estados), [200, 403])


if __name__ == "__main__":
    unittest.main()
