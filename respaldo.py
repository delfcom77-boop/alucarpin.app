"""Copias nativas y comprobacion de restauracion en destinos separados."""

import argparse
import base64
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
from uuid import UUID
import zipfile

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

MAX_BYTES = 256 * 1024 * 1024
PLAZO = 120


class ErrorRespaldo(RuntimeError):
    pass


def valor_json(valor):
    if isinstance(valor, (bytes, memoryview)):
        return {"binario": base64.b64encode(bytes(valor)).decode("ascii")}
    if isinstance(valor, (datetime, date)):
        return {"fecha": valor.isoformat()}
    if isinstance(valor, Decimal):
        return {"decimal": str(valor)}
    if isinstance(valor, UUID):
        return {"uuid": str(valor)}
    raise TypeError(f"Tipo no soportado en el inventario: {type(valor).__name__}")


def huella_filas(cursor):
    huellas = []
    for fila in cursor:
        contenido = json.dumps(list(fila), ensure_ascii=True, sort_keys=True,
                               separators=(",", ":"), default=valor_json).encode("utf-8")
        huellas.append(hashlib.sha256(contenido).digest())
    return {"filas": len(huellas), "sha256_datos": hashlib.sha256(b"".join(sorted(huellas))).hexdigest()}


def inventario_sqlite(db):
    resultado = {}
    for (nombre,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        identificador = '"' + nombre.replace('"', '""') + '"'
        cursor = db.execute(f"SELECT * FROM {identificador}")
        resultado[nombre] = {"columnas": [c[0] for c in cursor.description], **huella_filas(cursor)}
    esquema = db.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall()
    return {"tablas": resultado, "sha256_esquema": hashlib.sha256(
        json.dumps(esquema, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()}


def integridad_sqlite(db):
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ErrorRespaldo("La base SQLite no supera la comprobacion de integridad.")
    return sorted([list(fila) for fila in db.execute("PRAGMA foreign_key_check")], key=repr)


def inventario_postgres(db, alcance="completa"):
    resultado = {}
    consulta = (
        "SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind IN ('r','p') AND n.nspname NOT LIKE 'pg_%' "
        "AND n.nspname <> 'information_schema'"
    )
    if alcance == "aplicacion":
        consulta += " AND n.nspname = 'public'"
    tablas = db.execute(consulta + " ORDER BY n.nspname,c.relname").fetchall()
    for esquema, nombre in tablas:
        with db.cursor(name=f"inventario_{len(resultado)}") as cursor:
            cursor.execute(sql.SQL("SELECT * FROM {}.{}").format(sql.Identifier(esquema), sql.Identifier(nombre)))
            resultado[f"{esquema}.{nombre}"] = {
                "columnas": [c.name for c in cursor.description], **huella_filas(cursor),
            }
    return {"tablas": resultado}


def ejecutar_postgres(programa, argumentos, url):
    if not shutil.which(programa):
        raise ErrorRespaldo(f"Falta {programa}. Instala las herramientas cliente de PostgreSQL para continuar.")
    entorno = os.environ.copy()
    variables = {
        "dbname": "PGDATABASE", "host": "PGHOST", "hostaddr": "PGHOSTADDR",
        "port": "PGPORT", "user": "PGUSER", "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE", "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY",
        "sslrootcert": "PGSSLROOTCERT", "sslcrl": "PGSSLCRL",
        "sslcrldir": "PGSSLCRLDIR", "application_name": "PGAPPNAME",
        "connect_timeout": "PGCONNECT_TIMEOUT", "options": "PGOPTIONS",
        "service": "PGSERVICE", "passfile": "PGPASSFILE",
        "client_encoding": "PGCLIENTENCODING", "target_session_attrs": "PGTARGETSESSIONATTRS",
        "channel_binding": "PGCHANNELBINDING",
        "ssl_min_protocol_version": "PGSSLMINPROTOCOLVERSION",
        "ssl_max_protocol_version": "PGSSLMAXPROTOCOLVERSION", "gssencmode": "PGGSSENCMODE",
    }
    try:
        parametros = conninfo_to_dict(url)
    except psycopg.Error as error:
        raise ErrorRespaldo("La configuracion de conexion PostgreSQL no es valida.") from error
    if any(clave not in variables for clave in parametros):
        raise ErrorRespaldo("La conexion tiene parametros que las herramientas de respaldo no admiten.")
    for clave, valor in parametros.items():
        entorno[variables[clave]] = valor
    entorno["PGCONNECT_TIMEOUT"] = "15"
    try:
        resultado = subprocess.run([programa, *argumentos], env=entorno, capture_output=True, timeout=PLAZO)
    except subprocess.TimeoutExpired as error:
        raise ErrorRespaldo(f"{programa} ha superado el tiempo limite. La operacion no se considera verificada.") from error
    if resultado.returncode:
        # El stderr puede contener datos de conexion: nunca se envia al navegador.
        raise ErrorRespaldo(f"{programa} no ha completado la operacion. Revisa permisos y compatibilidad de versiones; no hay una copia o restauracion verificada.")


def crear_respaldo(url, ruta_sqlite, alcance="completa"):
    if alcance not in {"completa", "aplicacion"}:
        raise ErrorRespaldo("El alcance del respaldo no es valido.")
    with tempfile.TemporaryDirectory(prefix="alucarpin-respaldo-") as carpeta:
        archivo = Path(carpeta) / ("base.dump" if url else "base.sqlite")
        try:
            if url:
                with psycopg.connect(url, connect_timeout=15) as db:
                    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    db.execute("SET LOCAL TIME ZONE 'UTC'")
                    db.execute("SET LOCAL statement_timeout = '120s'")
                    snapshot = db.execute("SELECT pg_export_snapshot()").fetchone()[0]
                    inventario = inventario_postgres(db, alcance)
                    argumentos = ["--format=custom", "--no-password", f"--snapshot={snapshot}", f"--file={archivo}"]
                    if alcance == "aplicacion":
                        argumentos.append("--schema=public")
                    ejecutar_postgres("pg_dump", argumentos, url)
                    motor = "postgresql"
            else:
                inicio = time.monotonic()

                def progreso(estado, pendientes, total):
                    if time.monotonic() - inicio > PLAZO:
                        raise ErrorRespaldo("La copia SQLite ha superado el tiempo limite.")

                with closing(sqlite3.connect(Path(ruta_sqlite).resolve().as_uri() + "?mode=ro", uri=True)) as origen:
                    with closing(sqlite3.connect(archivo)) as destino:
                        origen.backup(destino, pages=256, progress=progreso)
                        inventario = inventario_sqlite(destino)
                        inventario["avisos_claves_foraneas"] = integridad_sqlite(destino)
                motor = "sqlite"
        except (sqlite3.Error, psycopg.Error) as error:
            raise ErrorRespaldo("No se pudo leer la base configurada para generar el respaldo. No se ha usado otra base.") from error
        if archivo.stat().st_size > MAX_BYTES:
            raise ErrorRespaldo("La base supera el limite de 256 MB para la descarga web. Usa un respaldo nativo administrado fuera de la web.")
        datos = archivo.read_bytes()
        manifiesto = {
            "formato": "alucarpin-respaldo", "version": 1, "motor": motor,
            "creado_utc": datetime.now(timezone.utc).isoformat(), "archivo": archivo.name,
            "bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest(), **inventario,
            "alcance_copia": alcance,
            "alcance": ("Todos los objetos y datos del esquema public de la app; excluye esquemas internos "
                        "de Supabase y extensiones externas. En SQLite incluye toda la base."
                        if alcance == "aplicacion" else
                        "Base de datos completa; necesita un servidor con sus extensiones compatibles."),
            "exclusiones": "No incluye archivos externos, variables de entorno ni roles globales de PostgreSQL.",
        }
        salida = io.BytesIO()
        with zipfile.ZipFile(salida, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
            paquete.writestr(archivo.name, datos)
            paquete.writestr("manifiesto.json", json.dumps(manifiesto, ensure_ascii=True, indent=2))
        return salida.getvalue(), manifiesto


def leer_respaldo(ruta):
    try:
        with zipfile.ZipFile(ruta) as paquete:
            if paquete.getinfo("manifiesto.json").file_size > 1024 * 1024:
                raise ErrorRespaldo("El manifiesto supera el limite permitido.")
            manifiesto = json.loads(paquete.read("manifiesto.json"))
            if manifiesto.get("formato") != "alucarpin-respaldo" or manifiesto.get("version") != 1:
                raise ErrorRespaldo("El formato o la version del respaldo no es compatible.")
            if manifiesto.get("alcance_copia", "completa") not in {"completa", "aplicacion"}:
                raise ErrorRespaldo("El alcance del respaldo no es compatible.")
            motor = manifiesto.get("motor")
            nombre = {"sqlite": "base.sqlite", "postgresql": "base.dump"}.get(motor)
            if not nombre or manifiesto.get("archivo") != nombre or set(paquete.namelist()) != {nombre, "manifiesto.json"}:
                raise ErrorRespaldo("El contenido del respaldo no es valido.")
            if paquete.getinfo(nombre).file_size > MAX_BYTES:
                raise ErrorRespaldo("El respaldo supera el limite de 256 MB.")
            datos = paquete.read(nombre)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as error:
        raise ErrorRespaldo("No se pudo leer el archivo de respaldo.") from error
    if len(datos) != manifiesto.get("bytes") or hashlib.sha256(datos).hexdigest() != manifiesto.get("sha256"):
        raise ErrorRespaldo("La copia esta incompleta o su huella SHA-256 no coincide.")
    return datos, manifiesto


def comprobar_inventario(actual, manifiesto):
    for clave in actual:
        if actual[clave] != manifiesto.get(clave):
            raise ErrorRespaldo(f"La restauracion no coincide con el respaldo: {clave}. No debe usarse como recuperacion verificada.")


def verificar_sqlite(ruta, destino):
    datos, manifiesto = leer_respaldo(ruta)
    if manifiesto["motor"] != "sqlite":
        raise ErrorRespaldo("Esta copia requiere PostgreSQL, no SQLite.")
    destino = Path(destino)
    try:
        with destino.open("xb") as archivo:
            archivo.write(datos)
    except FileExistsError as error:
        raise ErrorRespaldo("El destino ya existe. No se sobrescribe ninguna base; elige un archivo nuevo.") from error
    try:
        with closing(sqlite3.connect(destino.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            actual = inventario_sqlite(db)
            actual["avisos_claves_foraneas"] = integridad_sqlite(db)
            comprobar_inventario(actual, manifiesto)
    except (sqlite3.Error, ErrorRespaldo, TypeError, ValueError):
        destino.unlink()
        raise
    return manifiesto


def verificar_postgres(ruta, url):
    datos, manifiesto = leer_respaldo(ruta)
    if manifiesto["motor"] != "postgresql":
        raise ErrorRespaldo("Esta copia requiere SQLite, no PostgreSQL.")
    with psycopg.connect(url, connect_timeout=15) as db:
        objetos = db.execute(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' LIMIT 1"
        ).fetchone()
        funciones = db.execute(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' LIMIT 1"
        ).fetchone()
        tipos = db.execute(
            "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' LIMIT 1"
        ).fetchone()
        if objetos or funciones or tipos:
            raise ErrorRespaldo("El destino PostgreSQL no esta vacio. No se restaura sobre una base existente.")
    with tempfile.TemporaryDirectory(prefix="alucarpin-restauracion-") as carpeta:
        archivo = Path(carpeta) / "base.dump"
        archivo.write_bytes(datos)
        argumentos = ["--no-password", "--exit-on-error", "--single-transaction", "--no-owner", "--no-acl"]
        if manifiesto.get("alcance_copia") == "aplicacion":
            argumentos.extend(["--clean", "--if-exists"])
        ejecutar_postgres("pg_restore", [*argumentos, "--dbname=", str(archivo)], url)
    with psycopg.connect(url, connect_timeout=15) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        db.execute("SET LOCAL TIME ZONE 'UTC'")
        db.execute("SET LOCAL statement_timeout = '120s'")
        comprobar_inventario(inventario_postgres(db, manifiesto.get("alcance_copia", "completa")), manifiesto)
    return manifiesto


def main():
    parser = argparse.ArgumentParser(description="Restaura y compara una copia confiable en una base separada. Nunca uses el destino de produccion.")
    parser.add_argument("copia", type=Path)
    destinos = parser.add_mutually_exclusive_group(required=True)
    destinos.add_argument("--destino-sqlite", type=Path, help="Archivo nuevo; no puede existir")
    destinos.add_argument("--destino-postgres-env", help="Nombre de variable con URL de una base NUEVA y VACIA")
    parser.add_argument("--confirmar-copia-confiable", action="store_true", help="Un dump PostgreSQL puede ejecutar codigo; usa solo copias propias")
    args = parser.parse_args()
    try:
        if not args.confirmar_copia_confiable:
            raise ErrorRespaldo("Confirma que es una copia propia y confiable con --confirmar-copia-confiable.")
        if args.destino_sqlite:
            manifiesto = verificar_sqlite(args.copia, args.destino_sqlite)
        else:
            url = os.getenv(args.destino_postgres_env)
            if not url:
                raise ErrorRespaldo("La variable del destino PostgreSQL no esta configurada.")
            if url == os.getenv("DATABASE_URL"):
                raise ErrorRespaldo("El destino coincide con DATABASE_URL. No se permite restaurar produccion.")
            manifiesto = verificar_postgres(args.copia, url)
    except (ErrorRespaldo, OSError, sqlite3.Error, psycopg.Error) as error:
        # Los errores del driver pueden contener identificadores de conexion.
        mensaje = str(error) if isinstance(error, ErrorRespaldo) else "Fallo de acceso o de base de datos. La restauracion no esta verificada."
        parser.exit(1, f"ERROR: {mensaje}\n")
    print(f"RESTAURACION VERIFICADA: {len(manifiesto['tablas'])} tablas; esquema SQLite y contenido comparados cuando corresponde.")
    if manifiesto.get("avisos_claves_foraneas"):
        print("AVISO: la copia conserva incidencias de claves foraneas que ya existian en el origen.")


if __name__ == "__main__":
    main()
