import hashlib
import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, SecretStr

from autenticacion import hash_password, password_valida


DURACION = 300
MAX_INTENTOS = 5


class ClavePrivada(BaseModel):
    password: SecretStr


class ConfiguracionPrivada(BaseModel):
    password_admin: SecretStr
    password_nueva: SecretStr
    password_actual: SecretStr | None = None


def crear_acceso_privado(conexion, administrador):
    def iniciar():
        with conexion() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS resumen_privado ("
                "id INTEGER PRIMARY KEY CHECK (id = 1), propietario_id INTEGER, "
                "salt TEXT, digest TEXT, intentos INTEGER NOT NULL DEFAULT 0, "
                "bloqueado_hasta BIGINT NOT NULL DEFAULT 0)"
            )
            db.execute(
                "INSERT INTO resumen_privado (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS sesiones_resumen_privado ("
                "token_hash TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, "
                "sesion_hash TEXT NOT NULL, caduca BIGINT NOT NULL)"
            )

    def no_cache(response: Response):
        response.headers["Cache-Control"] = "no-store, private"

    router = APIRouter(prefix="/resumen-privado", on_startup=[iniciar],
                       dependencies=[Depends(no_cache)])

    def error(codigo, detalle):
        return HTTPException(codigo, detalle, headers={"Cache-Control": "no-store, private"})

    def huella(valor):
        return hashlib.sha256(valor.encode()).hexdigest()

    def ajustes(db):
        consulta = "SELECT * FROM resumen_privado WHERE id = 1"
        if hasattr(db, "db"):
            consulta += " FOR UPDATE"
        else:
            db.execute("BEGIN IMMEDIATE")
        return db.execute(consulta).fetchone()

    def comprobar_propietario(config, usuario):
        if config["propietario_id"] is not None and config["propietario_id"] != usuario["id"]:
            raise error(403, "Este resumen privado pertenece a otro administrador.")

    def comprobar_bloqueo(config):
        if config["bloqueado_hasta"] > int(time.time()):
            raise error(429, "Demasiados intentos. Espera cinco minutos antes de reintentarlo.")

    def fallo(db, config):
        intentos = config["intentos"] + 1
        bloqueado = int(time.time()) + DURACION if intentos >= MAX_INTENTOS else 0
        db.execute("UPDATE resumen_privado SET intentos = ?, bloqueado_hasta = ? WHERE id = 1",
                   (0 if bloqueado else intentos, bloqueado))
        db.commit()
        raise error(429 if bloqueado else 403,
                    "Demasiados intentos. Espera cinco minutos." if bloqueado else "Contraseña incorrecta.")

    def autorizado(request: Request, response: Response,
                   x_resumen_token: str | None = Header(default=None),
                   usuario=Depends(administrador)):
        no_cache(response)
        if not x_resumen_token:
            raise error(403, "Introduce la contraseña privada del resumen.")
        with conexion() as db:
            sesion = db.execute(
                "SELECT usuario_id, sesion_hash, caduca FROM sesiones_resumen_privado "
                "WHERE token_hash = ?", (huella(x_resumen_token),)
            ).fetchone()
            if (not sesion or sesion["usuario_id"] != usuario["id"]
                    or sesion["caduca"] <= int(time.time())
                    or not secrets.compare_digest(sesion["sesion_hash"],
                                                  huella(request.headers.get("authorization", "")))):
                raise error(403, "El resumen está bloqueado. Introduce de nuevo su contraseña.")
        return usuario

    @router.get("/estado")
    def estado(usuario=Depends(administrador)):
        with conexion() as db:
            config = ajustes(db)
            comprobar_propietario(config, usuario)
            return {"configurado": config["propietario_id"] is not None}

    @router.put("/configuracion")
    def configurar(datos: ConfiguracionPrivada, usuario=Depends(administrador)):
        nueva = datos.password_nueva.get_secret_value()
        if not 8 <= len(nueva) <= 128:
            raise error(422, "La contraseña privada debe tener entre 8 y 128 caracteres.")
        if nueva == datos.password_admin.get_secret_value():
            raise error(422, "Usa una contraseña distinta de la de administrador.")
        with conexion() as db:
            config = ajustes(db)
            comprobar_propietario(config, usuario)
            comprobar_bloqueo(config)
            cuenta = db.execute(
                "SELECT password_salt, password_hash FROM usuarios WHERE id = ? AND activo = 1",
                (usuario["id"],)
            ).fetchone()
            if not cuenta or not password_valida(datos.password_admin.get_secret_value(),
                                                cuenta["password_salt"], cuenta["password_hash"]):
                fallo(db, config)
            if config["propietario_id"] is not None and (
                datos.password_actual is None or not password_valida(
                    datos.password_actual.get_secret_value(), config["salt"], config["digest"]
                )
            ):
                fallo(db, config)
            salt, digest = hash_password(nueva)
            db.execute(
                "UPDATE resumen_privado SET propietario_id = ?, salt = ?, digest = ?, "
                "intentos = 0, bloqueado_hasta = 0 WHERE id = 1",
                (usuario["id"], salt, digest)
            )
            db.execute("DELETE FROM sesiones_resumen_privado")
        return {"configurado": True}

    @router.post("/abrir")
    def abrir(datos: ClavePrivada, request: Request, usuario=Depends(administrador)):
        with conexion() as db:
            config = ajustes(db)
            comprobar_propietario(config, usuario)
            if config["propietario_id"] is None:
                raise error(409, "Configura primero la contraseña privada.")
            comprobar_bloqueo(config)
            clave = datos.password.get_secret_value()
            if len(clave) > 128 or not password_valida(clave, config["salt"], config["digest"]):
                fallo(db, config)
            db.execute("UPDATE resumen_privado SET intentos = 0, bloqueado_hasta = 0 WHERE id = 1")
            db.execute("DELETE FROM sesiones_resumen_privado WHERE caduca <= ?", (int(time.time()),))
            token = secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO sesiones_resumen_privado (token_hash, usuario_id, sesion_hash, caduca) "
                "VALUES (?, ?, ?, ?)",
                (huella(token), usuario["id"], huella(request.headers.get("authorization", "")),
                 int(time.time()) + DURACION)
            )
        return {"token": token, "duracion_segundos": DURACION}

    @router.post("/cerrar")
    def cerrar(x_resumen_token: str | None = Header(default=None),
               usuario=Depends(administrador)):
        if x_resumen_token:
            with conexion() as db:
                db.execute(
                    "DELETE FROM sesiones_resumen_privado WHERE token_hash = ? AND usuario_id = ?",
                    (huella(x_resumen_token), usuario["id"])
                )
        return {"bloqueado": True}

    return router, autorizado
