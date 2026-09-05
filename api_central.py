from datetime import date, datetime
import os
from pathlib import Path
import sqlite3
import sys
from typing import Literal, Optional

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from base_datos import ruta_base_datos
from autenticacion import crear_token, inicializar_usuarios, password_valida, usuario_desde_token


BASE_PATH = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DATABASE_PATH = ruta_base_datos()
DATABASE_URL = os.getenv("DATABASE_URL")
app = FastAPI(title="API AlucarpinSamitier", version="0.1.0")
app.mount("/app", StaticFiles(directory=str(BASE_PATH / "app_web"), html=True), name="app")
seguridad = HTTPBearer(auto_error=False)
SECRETO_SESION = os.getenv("ALUCARPIN_SESSION_SECRET", "cambiar-secreto-local-alucarpin")


class ConexionPostgres:
    def __init__(self, url):
        self.db = psycopg.connect(url, row_factory=dict_row)

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traza):
        if tipo:
            self.db.rollback()
        else:
            self.db.commit()
        self.db.close()

    def execute(self, sql, parametros=()):
        return self.db.execute(sql.replace("?", "%s"), parametros)

    def commit(self):
        self.db.commit()


class FichajeCreate(BaseModel):
    ayudante_id: int
    fecha: date
    tipo_destino: Literal["faena", "presupuesto"] = "faena"
    cliente: str = Field(min_length=1)
    obra: str = Field(min_length=1)
    ubicacion: str = ""
    poblacion: str = ""


class FichajeUpdate(BaseModel):
    fecha: Optional[date] = None
    tipo_destino: Optional[Literal["faena", "presupuesto"]] = None
    cliente: Optional[str] = Field(default=None, min_length=1)
    obra: Optional[str] = Field(default=None, min_length=1)
    ubicacion: Optional[str] = None
    poblacion: Optional[str] = None


class PagoCreate(BaseModel):
    ayudante_id: int
    desde: date
    hasta: date
    precio_dia: float = Field(ge=0)
    importe_pagado: float = Field(default=0, ge=0)
    fecha_pago: Optional[date] = None


class LoginCreate(BaseModel):
    usuario: str
    password: str


class PasswordUpdate(BaseModel):
    password: str = Field(min_length=8)


class EstadoUsuarioUpdate(BaseModel):
    activo: bool


def conexion():
    if DATABASE_URL:
        return ConexionPostgres(DATABASE_URL)
    db = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar_base_datos():
    if DATABASE_URL:
        return
    with conexion() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS ayudantes (
                id INTEGER PRIMARY KEY,
                nombre TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS fichajes_ayudantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ayudante_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                tipo_destino TEXT NOT NULL DEFAULT 'faena',
                cliente TEXT NOT NULL DEFAULT '',
                obra TEXT NOT NULL,
                ubicacion TEXT NOT NULL DEFAULT '',
                poblacion TEXT NOT NULL DEFAULT '',
                confirmado_ayudante INTEGER NOT NULL DEFAULT 1,
                sincronizado INTEGER NOT NULL DEFAULT 0,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ayudante_id) REFERENCES ayudantes(id),
                UNIQUE (ayudante_id, fecha, cliente, obra, ubicacion, poblacion)
            );
            CREATE TABLE IF NOT EXISTS liquidaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ayudante_id INTEGER NOT NULL,
                desde TEXT NOT NULL,
                hasta TEXT NOT NULL,
                precio_dia REAL NOT NULL,
                importe_pagado REAL NOT NULL DEFAULT 0,
                fecha_pago TEXT,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ayudante_id) REFERENCES ayudantes(id)
            );
        """)
        columnas = {
            fila[1] for fila in db.execute("PRAGMA table_info(fichajes_ayudantes)")
        }
        if "cliente" not in columnas:
            db.execute("ALTER TABLE fichajes_ayudantes ADD COLUMN cliente TEXT NOT NULL DEFAULT ''")
        if "tipo_destino" not in columnas:
            db.execute("ALTER TABLE fichajes_ayudantes ADD COLUMN tipo_destino TEXT NOT NULL DEFAULT 'faena'")

        tablas = {
            fila[0]
            for fila in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "fichajes" in tablas:
            db.execute("""
                INSERT OR IGNORE INTO fichajes_ayudantes
                (id, ayudante_id, fecha, tipo_destino, cliente, obra,
                 ubicacion, poblacion, confirmado_ayudante, sincronizado,
                 creado_en, actualizado_en)
                SELECT id, ayudante_id, fecha, 'faena', '', obra,
                       ubicacion, poblacion, confirmado_ayudante, 0,
                       creado_en, actualizado_en
                FROM fichajes
            """)

        inicializar_usuarios(db)

        indices = db.execute("PRAGMA index_list(fichajes_ayudantes)").fetchall()
        for indice in indices:
            nombre_indice = indice[1]
            columnas_indice = [
                fila[2]
                for fila in db.execute(f"PRAGMA index_info('{nombre_indice}')")
            ]
            if columnas_indice == ["ayudante_id", "fecha", "obra"]:
                db.execute("""
                    CREATE TABLE fichajes_ayudantes_nuevo (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ayudante_id INTEGER NOT NULL,
                        fecha TEXT NOT NULL,
                        tipo_destino TEXT NOT NULL DEFAULT 'faena',
                        cliente TEXT NOT NULL DEFAULT '',
                        obra TEXT NOT NULL,
                        ubicacion TEXT NOT NULL DEFAULT '',
                        poblacion TEXT NOT NULL DEFAULT '',
                        confirmado_ayudante INTEGER NOT NULL DEFAULT 1,
                        sincronizado INTEGER NOT NULL DEFAULT 0,
                        creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (ayudante_id) REFERENCES ayudantes(id),
                        UNIQUE (ayudante_id, fecha, cliente, obra, ubicacion, poblacion)
                    )
                """)
                db.execute("""
                    INSERT INTO fichajes_ayudantes_nuevo
                    (id, ayudante_id, fecha, tipo_destino, cliente, obra, ubicacion, poblacion,
                     confirmado_ayudante, sincronizado, creado_en, actualizado_en)
                    SELECT id, ayudante_id, fecha, tipo_destino, cliente, obra, ubicacion, poblacion,
                           confirmado_ayudante, sincronizado, creado_en, actualizado_en
                    FROM fichajes_ayudantes
                """)
                db.execute("DROP TABLE fichajes_ayudantes")
                db.execute(
                    "ALTER TABLE fichajes_ayudantes_nuevo RENAME TO fichajes_ayudantes"
                )
                break


@app.on_event("startup")
def startup():
    inicializar_base_datos()


def usuario_actual(credenciales: HTTPAuthorizationCredentials = Depends(seguridad)):
    if not credenciales:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")
    usuario_id = usuario_desde_token(credenciales.credentials, SECRETO_SESION)
    if usuario_id is None:
        raise HTTPException(status_code=401, detail="Sesión no válida o caducada")
    with conexion() as db:
        usuario = db.execute(
            "SELECT id, usuario, rol, ayudante_id FROM usuarios WHERE id = ? AND activo = 1",
            (usuario_id,),
        ).fetchone()
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuario no válido")
    return dict(usuario)


def administrador(usuario=Depends(usuario_actual)):
    if usuario["rol"] != "administrador":
        raise HTTPException(status_code=403, detail="Solo el administrador puede realizar esta acción")
    return usuario


@app.get("/salud")
def salud():
    return {"estado": "ok", "servicio": "AlucarpinSamitier"}


@app.post("/login")
def login(datos: LoginCreate):
    with conexion() as db:
        usuario = db.execute(
            "SELECT id, usuario, password_salt, password_hash, rol, ayudante_id FROM usuarios WHERE usuario = ? AND activo = 1",
            (datos.usuario.strip().lower(),),
        ).fetchone()
    if not usuario or not password_valida(datos.password, usuario["password_salt"], usuario["password_hash"]):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    return {
        "token": crear_token(usuario["id"], SECRETO_SESION),
        "usuario": usuario["usuario"],
        "rol": usuario["rol"],
        "ayudante_id": usuario["ayudante_id"],
    }


@app.get("/yo")
def yo(usuario=Depends(usuario_actual)):
    return usuario


@app.get("/usuarios")
def listar_usuarios(usuario=Depends(administrador)):
    with conexion() as db:
        filas = db.execute(
            """
            SELECT u.id, u.usuario, u.rol, u.ayudante_id,
                   a.nombre AS nombre_ayudante, u.activo
            FROM usuarios AS u
            LEFT JOIN ayudantes AS a ON a.id = u.ayudante_id
            ORDER BY u.rol, u.usuario
            """
        ).fetchall()
    return [dict(fila) for fila in filas]


@app.patch("/usuarios/{usuario_id}/password")
def cambiar_password_usuario(usuario_id: int, datos: PasswordUpdate, usuario=Depends(administrador)):
    from autenticacion import hash_password
    salt, digest = hash_password(datos.password)
    with conexion() as db:
        cursor = db.execute(
            "UPDATE usuarios SET password_salt = ?, password_hash = ? WHERE id = ?",
            (salt, digest, usuario_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        db.commit()
    return {"actualizado": True}


@app.patch("/usuarios/{usuario_id}/estado")
def cambiar_estado_usuario(usuario_id: int, datos: EstadoUsuarioUpdate, usuario=Depends(administrador)):
    if usuario_id == usuario["id"] and not datos.activo:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")
    with conexion() as db:
        cursor = db.execute(
            "UPDATE usuarios SET activo = ? WHERE id = ?",
            (1 if datos.activo else 0, usuario_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        db.commit()
    return {"actualizado": True, "activo": datos.activo}


@app.get("/ayudantes")
def listar_ayudantes(usuario=Depends(usuario_actual)):
    with conexion() as db:
        if usuario["rol"] == "ayudante":
            consulta = "SELECT id, nombre, 1 AS activo FROM ayudantes WHERE id = ? ORDER BY nombre"
            parametros = (usuario["ayudante_id"],)
        else:
            consulta = "SELECT id, nombre, 1 AS activo FROM ayudantes ORDER BY nombre"
            parametros = ()
        return [dict(fila) for fila in db.execute(consulta, parametros)]


@app.get("/ayudantes/{ayudante_id}/fichajes")
def listar_fichajes(
    ayudante_id: int,
    desde: Optional[date] = Query(default=None),
    hasta: Optional[date] = Query(default=None),
    usuario=Depends(usuario_actual),
):
    if usuario["rol"] == "ayudante" and ayudante_id != usuario["ayudante_id"]:
        raise HTTPException(status_code=403, detail="No puedes consultar otro ayudante")
    condiciones = ["ayudante_id = ?"]
    parametros = [ayudante_id]
    if desde:
        condiciones.append("fecha >= ?")
        parametros.append(desde.isoformat())
    if hasta:
        condiciones.append("fecha <= ?")
        parametros.append(hasta.isoformat())
    with conexion() as db:
        filas = db.execute(
            f"SELECT * FROM fichajes_ayudantes WHERE {' AND '.join(condiciones)} ORDER BY fecha DESC, id DESC",
            parametros,
        ).fetchall()
        return [dict(fila) for fila in filas]


@app.post("/fichajes", status_code=201)
def crear_fichaje(fichaje: FichajeCreate, usuario=Depends(usuario_actual)):
    if usuario["rol"] == "ayudante" and fichaje.ayudante_id != usuario["ayudante_id"]:
        raise HTTPException(status_code=403, detail="No puedes registrar otro ayudante")
    try:
        with conexion() as db:
            parametros = (fichaje.ayudante_id, fichaje.fecha.isoformat(), fichaje.tipo_destino, fichaje.cliente.strip(), fichaje.obra.strip(), fichaje.ubicacion.strip(), fichaje.poblacion.strip())
            if DATABASE_URL:
                fila = db.execute(
                    "INSERT INTO fichajes_ayudantes (ayudante_id, fecha, tipo_destino, cliente, obra, ubicacion, poblacion, confirmado_ayudante, sincronizado) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1) RETURNING *",
                    parametros,
                ).fetchone()
            else:
                db.execute(
                    "INSERT INTO fichajes_ayudantes (ayudante_id, fecha, tipo_destino, cliente, obra, ubicacion, poblacion, confirmado_ayudante, sincronizado) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)",
                    parametros,
                )
                fila = db.execute("SELECT * FROM fichajes_ayudantes WHERE id = last_insert_rowid()").fetchone()
            return dict(fila)
    except (sqlite3.IntegrityError, psycopg.IntegrityError) as error:
        raise HTTPException(status_code=409, detail=f"Fichaje duplicado o ayudante inexistente: {error}") from error


@app.patch("/fichajes/{fichaje_id}")
def modificar_fichaje(fichaje_id: int, cambios: FichajeUpdate, usuario=Depends(usuario_actual)):
    datos = cambios.model_dump(exclude_unset=True)
    if "fecha" in datos:
        datos["fecha"] = datos["fecha"].isoformat()
    datos = {clave: valor.strip() if isinstance(valor, str) else valor for clave, valor in datos.items()}
    if not datos:
        raise HTTPException(status_code=400, detail="No hay datos para modificar")
    datos["actualizado_en"] = datetime.utcnow().isoformat(timespec="seconds")
    columnas = ", ".join(f"{clave} = ?" for clave in datos)
    with conexion() as db:
        if usuario["rol"] == "ayudante":
            permitido = db.execute("SELECT 1 FROM fichajes_ayudantes WHERE id = ? AND ayudante_id = ?", (fichaje_id, usuario["ayudante_id"])).fetchone()
            if not permitido:
                raise HTTPException(status_code=403, detail="No puedes modificar este fichaje")
        cursor = db.execute(
            f"UPDATE fichajes_ayudantes SET {columnas} WHERE id = ?",
            [*datos.values(), fichaje_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Fichaje no encontrado")
        return dict(db.execute("SELECT * FROM fichajes_ayudantes WHERE id = ?", (fichaje_id,)).fetchone())

@app.delete("/fichajes/{fichaje_id}")
def borrar_fichaje(fichaje_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        cursor = db.execute(
            "DELETE FROM fichajes_ayudantes WHERE id = ?", (fichaje_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Fichaje no encontrado")
        return {"eliminado": True, "id": fichaje_id}


@app.post("/liquidaciones", status_code=201)
def crear_liquidacion(pago: PagoCreate, usuario=Depends(administrador)):
    with conexion() as db:
        dia_laborable = "EXTRACT(DOW FROM fecha) NOT IN (0, 6)" if DATABASE_URL else "strftime('%w', fecha) NOT IN ('0', '6')"
        dias = db.execute(
            f"SELECT COUNT(*) AS cantidad FROM fichajes_ayudantes WHERE ayudante_id = ? AND fecha BETWEEN ? AND ? AND confirmado_ayudante = 1 AND {dia_laborable}",
            (pago.ayudante_id, pago.desde.isoformat(), pago.hasta.isoformat()),
        ).fetchone()["cantidad"]
        total = round(dias * pago.precio_dia, 2)
        pendiente = round(max(total - pago.importe_pagado, 0), 2)
        estado = "Pagado" if pendiente == 0 and total > 0 else "Pendiente"
        parametros = (
            pago.ayudante_id,
            pago.desde.isoformat(),
            pago.hasta.isoformat(),
            pago.precio_dia,
            pago.importe_pagado,
            pago.fecha_pago.isoformat() if pago.fecha_pago else None,
        )
        existente = db.execute(
            "SELECT id FROM liquidaciones WHERE ayudante_id = ? AND desde = ? AND hasta = ? ORDER BY id DESC LIMIT 1",
            parametros[:3],
        ).fetchone()
        if existente:
            db.execute(
                "UPDATE liquidaciones SET precio_dia = ?, importe_pagado = ?, fecha_pago = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
                (parametros[3], parametros[4], parametros[5], existente["id"]),
            )
            accion = "modificado"
        else:
            db.execute(
                "INSERT INTO liquidaciones (ayudante_id, desde, hasta, precio_dia, importe_pagado, fecha_pago) VALUES (?, ?, ?, ?, ?, ?)",
                parametros,
            )
            accion = "guardado"
        return {"ayudante_id": pago.ayudante_id, "desde": pago.desde, "hasta": pago.hasta, "dias": dias, "precio_dia": pago.precio_dia, "total": total, "importe_pagado": pago.importe_pagado, "pendiente": pendiente, "estado": estado, "accion": accion}
