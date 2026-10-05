from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

import api_central as api
import respaldo


class ConexionSinFallbackTests(unittest.TestCase):
    def test_error_postgres_no_abre_sqlite_y_devuelve_503(self):
        with (patch.object(api, "DATABASE_URL", "postgresql://prueba"),
              patch.object(api, "ConexionPostgres", side_effect=api.psycopg.OperationalError("Fallo")),
              patch.object(api.sqlite3, "connect") as local,
              self.assertLogs(api.logger, level="ERROR")):
            with self.assertRaises(api.HTTPException) as error:
                api.conexion()
        self.assertEqual(error.exception.status_code, 503)
        local.assert_not_called()

    def test_inicio_falla_sin_inicializar_otra_base(self):
        with (patch.object(api, "DATABASE_URL", "postgresql://prueba"),
              patch.object(api, "ConexionPostgres", side_effect=api.psycopg.OperationalError("Fallo")),
              patch.object(api.sqlite3, "connect") as local,
              self.assertLogs(api.logger, level="ERROR")):
            with self.assertRaises(api.HTTPException):
                api.inicializar_base_datos()
        local.assert_not_called()

    def test_fallo_de_tabla_en_inicio_no_se_oculta(self):
        db = MagicMock()
        db.execute.side_effect = api.psycopg.errors.UndefinedTable("Falta tabla")
        with patch.object(api, "DATABASE_URL", "postgresql://prueba"), patch.object(api, "conexion") as conectar:
            conectar.return_value.__enter__.return_value = db
            with self.assertRaises(api.psycopg.errors.UndefinedTable):
                api.inicializar_base_datos()

    def test_inicializar_usuarios_acepta_fila_postgres(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = {"cantidad": 1}
        api.inicializar_usuarios(db)
        self.assertEqual(db.execute.call_count, 1)


class RespaldoTests(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.carpeta = Path(carpeta.name)
        self.origen = self.carpeta / "origen.sqlite"
        self.copia = self.carpeta / "copia.zip"
        with closing(sqlite3.connect(self.origen)) as db:
            db.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE obras (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);
                CREATE TABLE gastos (id INTEGER PRIMARY KEY, obra_id INTEGER REFERENCES obras(id), importe REAL, dato BLOB);
                CREATE INDEX idx_gastos_obra ON gastos(obra_id);
                CREATE VIEW vista_obras AS SELECT nombre FROM obras;
                CREATE TABLE auditoria (accion TEXT);
                CREATE TRIGGER nueva_obra AFTER INSERT ON obras BEGIN INSERT INTO auditoria VALUES ('alta'); END;
                INSERT INTO obras VALUES (1,'José; Jaca');
                INSERT INTO obras VALUES (50,'Eliminada');
                DELETE FROM obras WHERE id=50;
                INSERT INTO gastos VALUES (1,1,19314.27,X'0010FF');
                INSERT INTO gastos VALUES (2,1,0,NULL);
            """)
        self.antes = self.origen.read_bytes()

    def crear(self):
        datos, manifiesto = respaldo.crear_respaldo(None, self.origen)
        self.copia.write_bytes(datos)
        return datos, manifiesto

    def test_restaura_datos_esquema_indices_vistas_triggers_y_secuencias(self):
        _, manifiesto = self.crear()
        destino = self.carpeta / "restaurada.sqlite"
        resultado = respaldo.verificar_sqlite(self.copia, destino)
        self.assertEqual(resultado, manifiesto)
        self.assertEqual(self.antes, self.origen.read_bytes())
        with closing(sqlite3.connect(destino)) as db:
            self.assertEqual(db.execute("SELECT * FROM gastos ORDER BY id").fetchall(),
                             [(1, 1, 19314.27, b"\x00\x10\xff"), (2, 1, 0.0, None)])
            db.execute("INSERT INTO obras(nombre) VALUES ('Nueva')")
            self.assertEqual(db.execute("SELECT MAX(id) FROM obras").fetchone()[0], 51)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM vista_obras").fetchone()[0], 2)
            self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='idx_gastos_obra'").fetchone())

    def test_copia_consistente_incluye_datos_wal(self):
        with closing(sqlite3.connect(self.origen)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT INTO obras(nombre) VALUES ('En WAL')")
            db.commit()
            self.crear()
            respaldo.verificar_sqlite(self.copia, self.carpeta / "wal-restaurada.sqlite")
        with closing(sqlite3.connect(self.carpeta / "wal-restaurada.sqlite")) as restaurada:
            self.assertEqual(restaurada.execute("SELECT nombre FROM obras ORDER BY id DESC LIMIT 1").fetchone()[0], "En WAL")

    def test_no_sobrescribe_destinos_existentes_ni_origen(self):
        self.crear()
        with self.assertRaises(respaldo.ErrorRespaldo):
            respaldo.verificar_sqlite(self.copia, self.origen)
        self.assertEqual(self.origen.read_bytes(), self.antes)

    def test_fuente_inexistente_no_crea_base_vacia(self):
        ruta = self.carpeta / "ausente.sqlite"
        with self.assertRaises(respaldo.ErrorRespaldo):
            respaldo.crear_respaldo(None, ruta)
        self.assertFalse(ruta.exists())

    def test_detecta_archivo_corrupto_y_manifiesto_adulterado(self):
        datos, manifiesto = self.crear()
        with zipfile.ZipFile(io.BytesIO(datos)) as original:
            base = original.read("base.sqlite")
        for alterar_base in (True, False):
            contenido = base + b"cambio" if alterar_base else base
            alterado = {**manifiesto, "tablas": {}}
            with zipfile.ZipFile(self.copia, "w") as paquete:
                paquete.writestr("base.sqlite", contenido)
                paquete.writestr("manifiesto.json", json.dumps(alterado))
            destino = self.carpeta / "no-verificada.sqlite"
            with self.assertRaises(respaldo.ErrorRespaldo):
                respaldo.verificar_sqlite(self.copia, destino)
            self.assertFalse(destino.exists())

    def test_conserva_y_avisa_incidencias_preexistentes_de_claves(self):
        with closing(sqlite3.connect(self.origen)) as db:
            db.execute("INSERT INTO gastos VALUES (3,999,10,NULL)")
            db.commit()
        _, manifiesto = self.crear()
        self.assertEqual(len(manifiesto["avisos_claves_foraneas"]), 1)
        respaldo.verificar_sqlite(self.copia, self.carpeta / "incidencias.sqlite")

    def test_zip_con_ruta_extra_no_se_extrae(self):
        datos, _ = self.crear()
        with zipfile.ZipFile(self.copia, "a") as paquete:
            paquete.writestr("../fuera.sqlite", "no")
        with self.assertRaises(respaldo.ErrorRespaldo):
            respaldo.leer_respaldo(self.copia)
        self.assertFalse((self.carpeta.parent / "fuera.sqlite").exists())

    def test_huella_independiente_del_orden_y_detecta_cambio_mismo_recuento(self):
        self.assertEqual(respaldo.huella_filas(iter([(1,), (2,)])),
                         respaldo.huella_filas(iter([(2,), (1,)])))
        self.assertNotEqual(respaldo.huella_filas(iter([(1,), (2,)])),
                            respaldo.huella_filas(iter([(1,), (3,)])))

    def test_endpoint_zip_sin_cache_y_solo_administrador(self):
        with patch.object(api, "DATABASE_URL", None), patch.object(api, "DATABASE_PATH", self.origen):
            respuesta = api.descargar_copia_seguridad({})
        self.assertEqual(respuesta.media_type, "application/zip")
        self.assertEqual(respuesta.headers["cache-control"], "no-store")
        self.assertIn("attachment", respuesta.headers["content-disposition"])
        self.copia.write_bytes(respuesta.body)
        respaldo.verificar_sqlite(self.copia, self.carpeta / "endpoint.sqlite")
        ruta = next(r for r in api.app.routes if r.name == "descargar_copia_seguridad")
        self.assertIn(api.administrador, [d.call for d in ruta.dependant.dependencies])

    def test_error_de_respaldo_es_visible_sin_falso_archivo(self):
        with patch.object(api, "crear_respaldo", side_effect=respaldo.ErrorRespaldo("Falta pg_dump")), self.assertLogs(api.logger, level="ERROR"):
            with self.assertRaises(api.HTTPException) as error:
                api.descargar_copia_seguridad({})
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("pg_dump", error.exception.detail)

    def test_postgres_no_expone_url_en_argumentos_ni_en_error(self):
        secreto = "postgresql://usuario:secreto@localhost/base"
        with patch.object(respaldo.shutil, "which", return_value="pg_dump"), patch.object(respaldo.subprocess, "run") as ejecutar:
            ejecutar.return_value.returncode = 1
            ejecutar.return_value.stderr = secreto.encode()
            with self.assertRaises(respaldo.ErrorRespaldo) as error:
                respaldo.ejecutar_postgres("pg_dump", ["--format=custom"], secreto)
            self.assertNotIn(secreto, str(error.exception))
            self.assertNotIn(secreto, ejecutar.call_args.args[0])
            self.assertEqual(ejecutar.call_args.kwargs["env"]["PGDATABASE"], "base")
            self.assertEqual(ejecutar.call_args.kwargs["env"]["PGPASSWORD"], "secreto")

    def test_falta_herramienta_y_timeout_no_son_exito(self):
        with patch.object(respaldo.shutil, "which", return_value=None):
            with self.assertRaises(respaldo.ErrorRespaldo):
                respaldo.ejecutar_postgres("pg_dump", [], "postgresql://localhost/prueba")
        with patch.object(respaldo.shutil, "which", return_value="pg_dump"), patch.object(respaldo.subprocess, "run", side_effect=subprocess.TimeoutExpired("pg_dump", 120)):
            with self.assertRaises(respaldo.ErrorRespaldo):
                respaldo.ejecutar_postgres("pg_dump", [], "postgresql://localhost/prueba")

    def test_destino_postgres_con_objetos_se_rechaza_antes_de_restaurar(self):
        datos = b"dump-prueba"
        with zipfile.ZipFile(self.copia, "w") as paquete:
            paquete.writestr("base.dump", datos)
            paquete.writestr("manifiesto.json", json.dumps({
                "formato": "alucarpin-respaldo", "version": 1, "motor": "postgresql",
                "archivo": "base.dump", "bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest(),
            }))
        with patch.object(respaldo.psycopg, "connect") as conectar, patch.object(respaldo, "ejecutar_postgres") as restaurar:
            conectar.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (1,)
            with self.assertRaises(respaldo.ErrorRespaldo):
                respaldo.verificar_postgres(self.copia, "destino")
        restaurar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
