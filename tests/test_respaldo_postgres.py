import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import respaldo


@unittest.skipUnless(os.getenv("ALUCARPIN_TEST_POSTGRES"), "Requiere un cluster local temporal de PostgreSQL")
class RespaldoPostgresTests(unittest.TestCase):
    def test_copia_y_restauracion_nativas_en_bases_aisladas(self):
        configuracion = conninfo_to_dict(os.environ["ALUCARPIN_TEST_POSTGRES"])
        self.assertEqual(configuracion.get("host"), "127.0.0.1", "Solo se permite un cluster de prueba local")
        origen = f"alucarpin_origen_{uuid4().hex}"
        destino = f"alucarpin_destino_{uuid4().hex}"
        url_origen = make_conninfo(**{**configuracion, "dbname": origen})
        url_destino = make_conninfo(**{**configuracion, "dbname": destino})
        with psycopg.connect(os.environ["ALUCARPIN_TEST_POSTGRES"], autocommit=True) as administrador:
            for nombre in (origen, destino):
                administrador.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
            try:
                with psycopg.connect(url_origen) as db:
                    db.execute("""
                        CREATE SCHEMA taller;
                        CREATE TYPE taller.estado AS ENUM ('Pendiente', 'Terminado');
                        CREATE TABLE public.obras (
                            id BIGSERIAL PRIMARY KEY, nombre TEXT NOT NULL,
                            estado taller.estado DEFAULT 'Pendiente'
                        );
                        CREATE TABLE taller.gastos (
                            id BIGSERIAL PRIMARY KEY, obra_id BIGINT REFERENCES public.obras(id),
                            importe NUMERIC(12,2), creado TIMESTAMPTZ, fecha DATE, dato BYTEA,
                            extra JSONB, tags TEXT[], referencia UUID DEFAULT gen_random_uuid()
                        );
                        CREATE INDEX idx_gastos_obra ON taller.gastos(obra_id);
                        CREATE VIEW taller.resumen AS SELECT obra_id,SUM(importe) AS total FROM taller.gastos GROUP BY obra_id;
                        CREATE TABLE taller.auditoria (accion TEXT);
                        CREATE FUNCTION taller.registrar() RETURNS trigger LANGUAGE plpgsql AS
                        $$BEGIN INSERT INTO taller.auditoria VALUES (NEW.nombre); RETURN NEW; END$$;
                        CREATE TRIGGER obra_nueva AFTER INSERT ON public.obras FOR EACH ROW EXECUTE FUNCTION taller.registrar();
                        INSERT INTO public.obras(nombre) VALUES ('Jose; Jaca'),('Eliminada');
                        SELECT setval('public.obras_id_seq',50,true);
                        DELETE FROM public.obras WHERE id=2;
                        INSERT INTO taller.gastos(obra_id,importe,creado,fecha,dato,extra,tags)
                        VALUES (1,19314.27,'2026-10-05 21:00:00+02','2026-10-05',decode('0010ff','hex'),
                            '{"confirmado":true}',ARRAY['ventana','blanco']), (1,0,NULL,NULL,NULL,NULL,NULL);
                    """)
                with tempfile.TemporaryDirectory() as carpeta:
                    copia = Path(carpeta) / "postgres.zip"
                    datos, manifiesto = respaldo.crear_respaldo(url_origen, None)
                    self.assertEqual(manifiesto["motor"], "postgresql")
                    self.assertEqual(manifiesto["tablas"]["taller.gastos"]["filas"], 2)
                    copia.write_bytes(datos)
                    respaldo.verificar_postgres(copia, url_destino)
                    with psycopg.connect(url_destino) as db:
                        self.assertEqual(str(db.execute("SELECT total FROM taller.resumen").fetchone()[0]), "19314.27")
                        self.assertEqual(bytes(db.execute("SELECT dato FROM taller.gastos WHERE id=1").fetchone()[0]), b"\x00\x10\xff")
                        self.assertEqual(db.execute("INSERT INTO public.obras(nombre) VALUES ('Nueva') RETURNING id").fetchone()[0], 51)
                        self.assertEqual(db.execute("SELECT COUNT(*) FROM taller.auditoria").fetchone()[0], 3)
                    with self.assertRaises(respaldo.ErrorRespaldo):
                        respaldo.verificar_postgres(copia, url_destino)
                    with psycopg.connect(url_origen) as db:
                        self.assertEqual(db.execute("SELECT COUNT(*) FROM public.obras").fetchone()[0], 1)
                        self.assertEqual(db.execute("SELECT last_value FROM public.obras_id_seq").fetchone()[0], 50)
            finally:
                for nombre in (origen, destino):
                    administrador.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(nombre)))


if __name__ == "__main__":
    unittest.main()
