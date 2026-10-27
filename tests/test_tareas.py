import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import shlex

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from tareas import (
    TareaInvalida, TareaModificada, filtrar_tareas, guardar_tarea,
    inicializar_tareas, listar_tareas, obtener_tarea,
)
from tareas_api import crear_tareas


class TareasModeloTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        inicializar_tareas(self.db)

    def crear(self, **datos):
        return guardar_tarea(self.db, {"titulo": "Llamar a Maria", **datos})

    def test_creacion_y_migracion_idempotente(self):
        with patch("tareas.ahora", return_value="2026-10-27T18:00:00+00:00"):
            tarea = self.crear()
        self.assertEqual(tarea["creado_en"], "2026-10-27T18:00:00+00:00")
        self.assertEqual(tarea["hecha_en"], "")
        self.assertEqual(tarea["estado"], "Pendiente")
        inicializar_tareas(self.db)
        self.assertEqual(listar_tareas(self.db), [tarea])

    def test_hecha_registra_automaticamente_y_editar_conserva_fecha(self):
        tarea = self.crear()
        with patch("tareas.ahora", return_value="2026-10-27T19:00:00+00:00"):
            hecha = guardar_tarea(self.db, dict(tarea, estado="Hecha"), tarea["id"], tarea["version"])
        self.assertEqual(hecha["hecha_en"], "2026-10-27T19:00:00+00:00")
        with patch("tareas.ahora", return_value="2026-10-28T08:00:00+00:00"):
            editada = guardar_tarea(self.db, dict(hecha, notas="Ya he hablado"), hecha["id"], hecha["version"])
        self.assertEqual(editada["hecha_en"], hecha["hecha_en"])
        self.assertEqual(editada["creado_en"], tarea["creado_en"])
        self.assertEqual(len(listar_tareas(self.db)), 1)

    def test_reabrir_y_terminar_de_nuevo(self):
        tarea = self.crear(estado="Hecha")
        pendiente = guardar_tarea(self.db, dict(tarea, estado="Pendiente"), tarea["id"], tarea["version"])
        self.assertEqual(pendiente["hecha_en"], "")
        with patch("tareas.ahora", return_value="2026-10-28T12:00:00+00:00"):
            hecha = guardar_tarea(self.db, dict(pendiente, estado="Hecha"), pendiente["id"], pendiente["version"])
        self.assertEqual(hecha["hecha_en"], "2026-10-28T12:00:00+00:00")

    def test_version_antigua_no_sobrescribe(self):
        tarea = self.crear()
        actual = guardar_tarea(self.db, dict(tarea, titulo="Cambio en app"), tarea["id"], tarea["version"])
        with self.assertRaises(TareaModificada):
            guardar_tarea(self.db, dict(tarea, titulo="Cambio antiguo"), tarea["id"], tarea["version"])
        self.assertEqual(obtener_tarea(self.db, tarea["id"]), actual)

    def test_reintentar_alta_no_duplica(self):
        ident = str(uuid4())
        primera = guardar_tarea(self.db, {"titulo": "Comprar tornillos"}, ident)
        self.assertEqual(guardar_tarea(self.db, {"titulo": "Comprar tornillos"}, ident), primera)
        with self.assertRaises(TareaModificada):
            guardar_tarea(self.db, {"titulo": "Otro contenido"}, ident)
        self.assertEqual(len(listar_tareas(self.db)), 1)

    def test_validacion(self):
        for datos in (
            {"titulo": " "}, {"titulo": "a" * 241}, {"notas": "a" * 4001},
            {"tipo": "invalido"}, {"prioridad": "invalida"}, {"estado": "invalido"},
            {"fecha_prevista": "2026-02-30"}, {"fecha_prevista": "20261027"},
            {"fecha_prevista": None}, {"titulo": None},
        ):
            with self.subTest(datos=str(datos)[:80]), self.assertRaises(TareaInvalida):
                self.crear(**datos)
        self.assertEqual(listar_tareas(self.db), [])

    def test_filtros_no_pierden_sin_fecha_y_busqueda_notas_sin_acentos(self):
        hoy = self.crear(titulo="Presupuesto", fecha_prevista="2026-10-27", tipo="Presupuesto")
        atrasada = self.crear(titulo="Llamar", fecha_prevista="2026-10-26", prioridad="Alta")
        sin_fecha = self.crear(titulo="Material", notas="José · revisión", cliente="Pepe")
        hecha = self.crear(titulo="Acabada", estado="Hecha", fecha_prevista="2026-10-26")
        tareas = listar_tareas(self.db)
        def ids(filtro, **kw):
            return {t["id"] for t in filtrar_tareas(tareas, filtro, hoy=date(2026, 10, 27), **kw)}
        self.assertEqual(ids("Hoy"), {hoy["id"]})
        self.assertEqual(ids("Atrasadas"), {atrasada["id"]})
        self.assertEqual(ids("Hechas"), {hecha["id"]})
        self.assertEqual(ids("Pendientes"), {hoy["id"], atrasada["id"], sin_fecha["id"]})
        self.assertEqual(ids("Todas", busqueda="jose"), {sin_fecha["id"]})
        self.assertEqual(ids("Todas", prioridad="Alta"), {atrasada["id"]})
        self.assertEqual(ids("Todas", tipo="Presupuesto"), {hoy["id"]})


class TareasAPITests(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        ruta = Path(self.carpeta.name) / "tareas.db"
        def conexion():
            db = sqlite3.connect(ruta)
            db.row_factory = sqlite3.Row
            return db
        self.conexion = conexion
        def administrador(authorization: str = Header(default="")):
            if authorization != "Bearer prueba-local":
                raise HTTPException(403, "Solo administrador")
            return {"id": 1}
        app = FastAPI()
        app.include_router(crear_tareas(conexion, administrador))
        self.cliente = self.enterContext(TestClient(app))
        self.cliente.headers["Authorization"] = "Bearer prueba-local"
        self.ident = str(uuid4())

    def crear(self, **datos):
        return self.cliente.post("/tareas", json={"id": self.ident, "titulo": "Llamar a Maria", **datos})

    def test_alta_listado_y_reintento(self):
        creada = self.crear()
        self.assertEqual(creada.status_code, 201)
        self.assertEqual(self.crear().json(), creada.json())
        self.assertEqual(self.cliente.get("/tareas").json(), [creada.json()])

    def test_finalizacion_y_conflicto(self):
        tarea = self.crear().json()
        datos = {c: tarea[c] for c in ("titulo", "tipo", "cliente", "obra", "notas", "fecha_prevista", "prioridad", "estado", "version")}
        datos["estado"] = "Hecha"
        respuesta = self.cliente.put("/tareas/" + self.ident, json=datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["hecha_en"])
        self.assertEqual(self.cliente.put("/tareas/" + self.ident, json=datos).status_code, 409)

    def test_validacion_y_campos_automaticos_no_editables(self):
        for datos in ({"titulo": " "}, {"fecha_prevista": "2026-02-30"}, {"hecha_en": "ayer"}, {"version": 1}):
            with self.subTest(datos=datos):
                self.assertEqual(self.crear(**datos).status_code, 422)
        self.assertEqual(self.cliente.get("/tareas").json(), [])

    def test_identificador_incorrecto_y_tarea_ausente(self):
        self.assertEqual(self.cliente.put("/tareas/invalido", json={"titulo": "Una", "version": 1}).status_code, 422)
        self.assertEqual(self.cliente.put("/tareas/" + self.ident, json={"titulo": "Una", "version": 1}).status_code, 404)

    def test_todas_las_operaciones_requieren_administrador(self):
        self.cliente.headers.pop("Authorization")
        self.assertEqual(self.cliente.get("/tareas").status_code, 403)
        self.assertEqual(self.crear().status_code, 403)
        self.assertEqual(self.cliente.put("/tareas/" + self.ident, json={"titulo": "Una", "version": 1}).status_code, 403)

    def test_error_base_no_simula_exito(self):
        with closing(self.conexion()) as db:
            db.execute("DROP TABLE tareas")
            db.commit()
        with self.assertLogs("tareas_api", level="ERROR"):
            respuesta = self.crear()
        self.assertEqual(respuesta.status_code, 503)


class TareasDespliegueTests(unittest.TestCase):
    def test_imagen_incluye_modulos_y_recursos_del_apartado(self):
        raiz = Path(__file__).resolve().parents[1]
        incluidos = set()
        for linea in (raiz / "Dockerfile").read_text().splitlines():
            if linea.startswith("COPY "):
                incluidos.update(shlex.split(linea)[1:-1])
        for archivo in ("tareas.py", "tareas_api.py", "app_web/tareas.html", "app_web/tareas.css", "app_web/tareas.js"):
            self.assertIn(archivo, incluidos)
            self.assertTrue((raiz / archivo).is_file())
