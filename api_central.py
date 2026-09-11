from datetime import date, datetime
import os
from pathlib import Path
import sqlite3
import sys
from typing import Literal, Optional

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, HTTPException, Query, Response
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
    tipo_destino: Literal["faena", "presupuesto", "reparacion"] = "faena"
    cliente: str = Field(min_length=1)
    obra: str = Field(min_length=1)
    ubicacion: str = ""
    poblacion: str = ""
    num_presupuesto: Optional[str] = None


class FichajeUpdate(BaseModel):
    fecha: Optional[date] = None
    tipo_destino: Optional[Literal["faena", "presupuesto", "reparacion"]] = None
    cliente: Optional[str] = Field(default=None, min_length=1)
    obra: Optional[str] = Field(default=None, min_length=1)
    ubicacion: Optional[str] = None
    poblacion: Optional[str] = None
    num_presupuesto: Optional[str] = None


class FichajeVinculacion(BaseModel):
    faena_id: Optional[int] = None


class TrabajoCreate(BaseModel):
    tipo: Literal["faena", "presupuesto", "reparacion"]
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    cliente: str = Field(min_length=1)
    obra: str = Field(min_length=1)
    ubicacion: str = ""
    poblacion: str = ""
    observaciones: str = ""
    num_presupuesto: Optional[str] = None
    importe: float = Field(default=0, ge=0)
    estado_cobro: Literal["No cobrado", "Cobrado"] = "No cobrado"
    forma_pago: str = ""
    fecha_cobro: Optional[date] = None


class TrabajoUpdate(TrabajoCreate):
    pass


class CitaCreate(BaseModel):
    fecha: date
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    tipo: Literal["visita", "reparacion", "reunion", "llamada", "presupuesto", "otro"] = "visita"
    cliente: str = ""
    ubicacion: str = ""
    poblacion: str = ""
    telefono: str = ""
    observaciones: str = ""
    estado: Literal["Pendiente", "Realizada", "Cancelada"] = "Pendiente"


class CitaUpdate(CitaCreate):
    pass


class SeguimientoCreate(BaseModel):
    fecha_llamada: Optional[date] = None
    fecha_recordatorio: Optional[date] = None
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    cliente: str = ""
    telefono: str = ""
    ubicacion: str = ""
    poblacion: str = ""
    motivo: str = Field(min_length=1)
    observaciones: str = ""
    estado: Literal["Pendiente", "Realizado"] = "Pendiente"


class SeguimientoUpdate(SeguimientoCreate):
    pass


class SilencioCalendarioCreate(BaseModel):
    fecha: date
    motivo: str = "Sin sonido"


class PagoCreate(BaseModel):
    ayudante_id: int
    desde: date
    hasta: date
    precio_dia: float = Field(ge=0)
    importe_pagado: float = Field(default=0, ge=0)
    fecha_pago: Optional[date] = None


class GastoCreate(BaseModel):
    tipo: Literal["faena", "presupuesto"]
    concepto: str = Field(min_length=1)
    proveedor: str = ""
    fecha: Optional[date] = None
    importe: float = Field(default=0, ge=0)
    bruto: float = Field(default=0, ge=0)
    iva: float = Field(default=0, ge=0)
    estado_pago: str = "No pagado"
    forma_pago: str = ""
    faena_id: Optional[int] = None
    num_presupuesto: Optional[str] = None
    categoria: str = "Extras"
    numero_documento: str = ""


class PagoGastoCreate(BaseModel):
    fecha: Optional[date] = None
    importe: float = Field(gt=0)
    forma_pago: str = "Transferencia"
    observaciones: str = ""


class PagoJornadaUpdate(BaseModel):
    importe: float = Field(default=50, ge=0)
    importe_pagado: float = Field(default=0, ge=0)
    forma_pago: str = "Efectivo"
    estado_pago: Literal["No pagado", "Parcial", "Pagado"] = "No pagado"


class LoginCreate(BaseModel):
    usuario: str
    password: str


class PasswordUpdate(BaseModel):
    password: str = Field(min_length=8)


class EstadoUsuarioUpdate(BaseModel):
    activo: bool


class AyudanteCreate(BaseModel):
    nombre: str = Field(min_length=1)


class AyudanteUpdate(BaseModel):
    nombre: str = Field(min_length=1)


class FaenaCreate(BaseModel):
    cliente: str = Field(min_length=1)
    obra: Optional[str] = None
    fecha: Optional[date] = None
    ubicacion: Optional[str] = None
    poblacion: Optional[str] = None
    precio: float = Field(default=0, ge=0)
    ayudantes: Optional[str] = None


class FaenaUpdate(BaseModel):
    cliente: Optional[str] = None
    obra: Optional[str] = None
    fecha: Optional[date] = None
    ubicacion: Optional[str] = None
    poblacion: Optional[str] = None
    precio: Optional[float] = Field(default=None, ge=0)
    ayudantes: Optional[str] = None


class PresupuestoCreate(BaseModel):
    cliente: str = Field(min_length=1)
    num_presupuesto: Optional[str] = None
    fecha: Optional[date] = None
    bruto: float = Field(default=0, ge=0)
    iva: float = Field(default=0, ge=0)
    total_iva: float = Field(default=0, ge=0)
    presupuesto_iva: float = Field(default=0, ge=0)
    efectivo: float = Field(default=0, ge=0)
    estado: Optional[str] = None
    presupuesto_final: float = Field(default=0, ge=0)


class PresupuestoUpdate(BaseModel):
    cliente: Optional[str] = None
    num_presupuesto: Optional[str] = None
    fecha: Optional[date] = None
    bruto: Optional[float] = Field(default=None, ge=0)
    iva: Optional[float] = Field(default=None, ge=0)
    total_iva: Optional[float] = Field(default=None, ge=0)
    presupuesto_iva: Optional[float] = Field(default=None, ge=0)
    efectivo: Optional[float] = Field(default=None, ge=0)
    estado: Optional[str] = None
    presupuesto_final: Optional[float] = Field(default=None, ge=0)


def conexion():
    if DATABASE_URL:
        return ConexionPostgres(DATABASE_URL)
    db = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar_base_datos():
    if DATABASE_URL:
        with conexion() as db:
            inicializar_usuarios(db)
            db.execute("ALTER TABLE fichajes_ayudantes ADD COLUMN IF NOT EXISTS num_presupuesto TEXT")
            db.execute("""
                CREATE TABLE IF NOT EXISTS trabajos_propios (
                    id BIGSERIAL PRIMARY KEY,
                    tipo TEXT NOT NULL,
                    fecha_inicio DATE NOT NULL,
                    fecha_fin DATE,
                    cliente TEXT NOT NULL,
                    obra TEXT NOT NULL,
                    ubicacion TEXT NOT NULL DEFAULT '',
                    poblacion TEXT NOT NULL DEFAULT '',
                    observaciones TEXT NOT NULL DEFAULT '',
                    num_presupuesto TEXT,
                    importe DOUBLE PRECISION NOT NULL DEFAULT 0,
                    estado_cobro TEXT NOT NULL DEFAULT 'No cobrado',
                    forma_pago TEXT NOT NULL DEFAULT '',
                    fecha_cobro DATE,
                    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS citas_agenda (
                    id BIGSERIAL PRIMARY KEY,
                    fecha DATE NOT NULL,
                    hora TEXT NOT NULL,
                    duracion_minutos INTEGER NOT NULL DEFAULT 60,
                    tipo TEXT NOT NULL DEFAULT 'visita',
                    cliente TEXT NOT NULL DEFAULT '',
                    ubicacion TEXT NOT NULL DEFAULT '',
                    poblacion TEXT NOT NULL DEFAULT '',
                    telefono TEXT NOT NULL DEFAULT '',
                    observaciones TEXT NOT NULL DEFAULT '',
                    estado TEXT NOT NULL DEFAULT 'Pendiente',
                    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS seguimientos_agenda (
                    id BIGSERIAL PRIMARY KEY,
                    fecha_llamada DATE NOT NULL DEFAULT CURRENT_DATE,
                    fecha_recordatorio DATE NOT NULL,
                    hora TEXT NOT NULL,
                    cliente TEXT NOT NULL DEFAULT '',
                    telefono TEXT NOT NULL DEFAULT '',
                    ubicacion TEXT NOT NULL DEFAULT '',
                    poblacion TEXT NOT NULL DEFAULT '',
                    motivo TEXT NOT NULL,
                    observaciones TEXT NOT NULL DEFAULT '',
                    estado TEXT NOT NULL DEFAULT 'Pendiente',
                    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("CREATE TABLE IF NOT EXISTS calendario_silencios (fecha DATE PRIMARY KEY, motivo TEXT NOT NULL DEFAULT 'Sin sonido')")
            db.execute("ALTER TABLE seguimientos_agenda ADD COLUMN IF NOT EXISTS fecha_llamada DATE")
            db.execute("ALTER TABLE seguimientos_agenda ADD COLUMN IF NOT EXISTS ubicacion TEXT NOT NULL DEFAULT ''")
            db.execute("ALTER TABLE seguimientos_agenda ADD COLUMN IF NOT EXISTS poblacion TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE seguimientos_agenda SET fecha_llamada = fecha_recordatorio WHERE fecha_llamada IS NULL")
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
                    num_presupuesto TEXT,
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
            CREATE TABLE IF NOT EXISTS trabajos_propios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                fecha_inicio TEXT NOT NULL,
                fecha_fin TEXT,
                cliente TEXT NOT NULL,
                obra TEXT NOT NULL,
                ubicacion TEXT NOT NULL DEFAULT '',
                poblacion TEXT NOT NULL DEFAULT '',
                observaciones TEXT NOT NULL DEFAULT '',
                num_presupuesto TEXT,
                importe REAL NOT NULL DEFAULT 0,
                estado_cobro TEXT NOT NULL DEFAULT 'No cobrado',
                forma_pago TEXT NOT NULL DEFAULT '',
                fecha_cobro TEXT,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS citas_agenda (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                duracion_minutos INTEGER NOT NULL DEFAULT 60,
                tipo TEXT NOT NULL DEFAULT 'visita',
                cliente TEXT NOT NULL DEFAULT '',
                ubicacion TEXT NOT NULL DEFAULT '',
                poblacion TEXT NOT NULL DEFAULT '',
                telefono TEXT NOT NULL DEFAULT '',
                observaciones TEXT NOT NULL DEFAULT '',
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS seguimientos_agenda (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_llamada TEXT NOT NULL DEFAULT CURRENT_DATE,
                fecha_recordatorio TEXT NOT NULL,
                hora TEXT NOT NULL,
                cliente TEXT NOT NULL DEFAULT '',
                telefono TEXT NOT NULL DEFAULT '',
                ubicacion TEXT NOT NULL DEFAULT '',
                poblacion TEXT NOT NULL DEFAULT '',
                motivo TEXT NOT NULL,
                observaciones TEXT NOT NULL DEFAULT '',
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS calendario_silencios (
                fecha TEXT PRIMARY KEY,
                motivo TEXT NOT NULL DEFAULT 'Sin sonido'
            );
        """)
        columnas_seguimientos = {
            fila[1] for fila in db.execute("PRAGMA table_info(seguimientos_agenda)")
        }
        if "fecha_llamada" not in columnas_seguimientos:
            db.execute("ALTER TABLE seguimientos_agenda ADD COLUMN fecha_llamada TEXT")
            db.execute("UPDATE seguimientos_agenda SET fecha_llamada = fecha_recordatorio WHERE fecha_llamada IS NULL")
        if "ubicacion" not in columnas_seguimientos:
            db.execute("ALTER TABLE seguimientos_agenda ADD COLUMN ubicacion TEXT NOT NULL DEFAULT ''")
        if "poblacion" not in columnas_seguimientos:
            db.execute("ALTER TABLE seguimientos_agenda ADD COLUMN poblacion TEXT NOT NULL DEFAULT ''")
        columnas = {
            fila[1] for fila in db.execute("PRAGMA table_info(fichajes_ayudantes)")
        }
        if "cliente" not in columnas:
            db.execute("ALTER TABLE fichajes_ayudantes ADD COLUMN cliente TEXT NOT NULL DEFAULT ''")
        if "tipo_destino" not in columnas:
            db.execute("ALTER TABLE fichajes_ayudantes ADD COLUMN tipo_destino TEXT NOT NULL DEFAULT 'faena'")
        if "num_presupuesto" not in columnas:
            db.execute("ALTER TABLE fichajes_ayudantes ADD COLUMN num_presupuesto TEXT")

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
                        num_presupuesto TEXT,
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
                        num_presupuesto, confirmado_ayudante, sincronizado, creado_en, actualizado_en)
                    SELECT id, ayudante_id, fecha, tipo_destino, cliente, obra, ubicacion, poblacion,
                              num_presupuesto, confirmado_ayudante, sincronizado, creado_en, actualizado_en
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


@app.get("/resumen-gestion")
def resumen_gestion(usuario=Depends(administrador)):
    avisos = []

    def consultar(consulta, etiqueta):
        try:
            with conexion() as db:
                return [dict(fila) for fila in db.execute(consulta).fetchall()]
        except Exception as error:
            avisos.append(f"{etiqueta}: {type(error).__name__}")
            return []

    faenas = consultar(
        "SELECT id, cliente, obra, fecha, ubicacion, poblacion, precio, ayudantes "
        "FROM faenas ORDER BY fecha DESC, id DESC",
        "faenas",
    )
    presupuestos = consultar(
        "SELECT id, cliente, num_presupuesto, fecha, bruto, iva, "
        "presupuesto_final, estado FROM presupuestos ORDER BY fecha DESC, id DESC",
        "presupuestos",
    )
    gastos = []
    for nombres, tipo in (
        (("gastos_faenas_extras", "gasto_faenas"), "faena"),
        (("gastos_presupuestos", "gasto_presupuesto"), "presupuesto"),
    ):
        for tabla in nombres:
            filas = consultar(
                f"SELECT id, proveedor, concepto, importe, "
                f"COALESCE(importe_pagado, pagado, 0) AS importe_pagado, "
                f"forma_pago, fecha, estado_pago, categoria FROM {tabla} "
                f"ORDER BY fecha DESC, id DESC",
                tabla,
            )
            if filas or not avisos or not avisos[-1].startswith(tabla + ":"):
                for gasto in filas:
                    gasto["tipo"] = tipo
                gastos.extend(filas)
                break

    return {
        "faenas": faenas,
        "presupuestos": presupuestos,
        "gastos": gastos,
        "totales": {
            "faenas": len(faenas),
            "presupuestos": len(presupuestos),
            "gastos": len(gastos),
        },
        "avisos": avisos,
    }


@app.get("/gastos")
def listar_gastos(
    tipo: Optional[Literal["faena", "presupuesto"]] = None,
    usuario=Depends(administrador),
):
    configuraciones = (
        (("gastos_faenas_extras", "gasto_faenas"), "faena"),
        (("gastos_presupuestos", "gasto_presupuesto"), "presupuesto"),
    )
    resultado = []
    with conexion() as db:
        for nombres, tipo_gasto in configuraciones:
            if tipo and tipo != tipo_gasto:
                continue
            tabla = next(
                (
                    nombre for nombre in nombres
                    if db.execute(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = ?",
                        (nombre,),
                    ).fetchone()
                ),
                None,
            ) if DATABASE_URL else next(
                (
                    nombre for nombre in nombres
                    if db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (nombre,),
                    ).fetchone()
                ),
                None,
            )
            if not tabla:
                continue
            referencia = "faena_id" if tipo_gasto == "faena" else "num_presupuesto"
            filas = db.execute(
                f"SELECT id, {referencia}, proveedor, concepto, importe, "
                f"COALESCE(importe_pagado, pagado, 0) AS importe_pagado, "
                f"forma_pago, fecha, estado_pago, categoria FROM {tabla} "
                f"ORDER BY fecha DESC, id DESC"
            ).fetchall()
            for fila in filas:
                gasto = dict(fila)
                gasto["tipo"] = tipo_gasto
                gasto["pendiente"] = round(
                    max(float(gasto["importe"] or 0) - float(gasto["importe_pagado"] or 0), 0),
                    2,
                )
                resultado.append(gasto)
    return resultado


@app.post("/gastos", status_code=201)
def crear_gasto(datos: GastoCreate, usuario=Depends(administrador)):
    if datos.tipo == "faena" and datos.faena_id is None:
        raise HTTPException(status_code=400, detail="El gasto de faena necesita una faena")
    if datos.tipo == "presupuesto" and not datos.num_presupuesto:
        raise HTTPException(status_code=400, detail="El gasto de presupuesto necesita un número")

    nombres = (
        ("gastos_faenas_extras", "gasto_faenas")
        if datos.tipo == "faena"
        else ("gastos_presupuestos", "gasto_presupuesto")
    )
    columnas = [
        "concepto", "proveedor", "fecha", "importe", "bruto", "iva",
        "estado_pago", "forma_pago", "categoria", "numero_documento",
    ]
    valores = [
        datos.concepto.strip(), datos.proveedor.strip(),
        datos.fecha.isoformat() if datos.fecha else None, datos.importe,
        datos.bruto, datos.iva, datos.estado_pago, datos.forma_pago.strip(),
        datos.categoria.strip(), datos.numero_documento.strip(),
    ]
    if datos.tipo == "faena":
        columnas.insert(0, "faena_id")
        valores.insert(0, datos.faena_id)
        columnas.extend(["pagado", "importe_pagado"])
        valores.extend([0, 0])
    else:
        columnas.insert(0, "num_presupuesto")
        valores.insert(0, datos.num_presupuesto.strip())
        columnas.extend(["importe_pagado", "resto_pago", "pagado"])
        valores.extend([0, datos.importe, 0])

    with conexion() as db:
        if datos.tipo == "faena":
            existe = db.execute("SELECT 1 FROM faenas WHERE id = ?", (datos.faena_id,)).fetchone()
        else:
            existe = db.execute(
                "SELECT 1 FROM presupuestos WHERE num_presupuesto = ?",
                (datos.num_presupuesto.strip(),),
            ).fetchone()
        if not existe:
            raise HTTPException(status_code=400, detail="El destino del gasto no existe")

        tabla = next(
            (
                nombre for nombre in nombres
                if db.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        ) if DATABASE_URL else next(
            (
                nombre for nombre in nombres
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        )
        if not tabla:
            raise HTTPException(status_code=503, detail="La tabla de gastos no está disponible")
        nombres_columnas = ", ".join(columnas)
        marcadores = ", ".join("?" for _ in columnas)
        if DATABASE_URL:
            fila = db.execute(
                f"INSERT INTO {tabla} ({nombres_columnas}) VALUES ({marcadores}) RETURNING *",
                valores,
            ).fetchone()
        else:
            db.execute(
                f"INSERT INTO {tabla} ({nombres_columnas}) VALUES ({marcadores})",
                valores,
            )
            fila = db.execute(
                f"SELECT * FROM {tabla} WHERE id = last_insert_rowid()"
            ).fetchone()
    resultado = dict(fila)
    resultado["tipo"] = datos.tipo
    return resultado


@app.patch("/gastos/{tipo}/{gasto_id}")
def modificar_gasto(
    tipo: Literal["faena", "presupuesto"],
    gasto_id: int,
    datos: GastoCreate,
    usuario=Depends(administrador),
):
    if datos.tipo != tipo:
        raise HTTPException(status_code=400, detail="El tipo de la ruta y del gasto no coincide")
    nombres = (
        ("gastos_faenas_extras", "gasto_faenas")
        if tipo == "faena"
        else ("gastos_presupuestos", "gasto_presupuesto")
    )
    columnas = ["concepto", "proveedor", "fecha", "importe", "bruto", "iva", "estado_pago", "forma_pago", "categoria", "numero_documento"]
    valores = [
        datos.concepto.strip(), datos.proveedor.strip(),
        datos.fecha.isoformat() if datos.fecha else None, datos.importe,
        datos.bruto, datos.iva, datos.estado_pago, datos.forma_pago.strip(),
        datos.categoria.strip(), datos.numero_documento.strip(),
    ]
    if tipo == "faena":
        if datos.faena_id is None:
            raise HTTPException(status_code=400, detail="El gasto de faena necesita una faena")
        columnas.insert(0, "faena_id")
        valores.insert(0, datos.faena_id)
    else:
        if not datos.num_presupuesto:
            raise HTTPException(status_code=400, detail="El gasto de presupuesto necesita un número")
        columnas.insert(0, "num_presupuesto")
        valores.insert(0, datos.num_presupuesto.strip())
    asignaciones = ", ".join(f"{columna} = ?" for columna in columnas)

    with conexion() as db:
        tabla = next(
            (
                nombre for nombre in nombres
                if db.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        ) if DATABASE_URL else next(
            (
                nombre for nombre in nombres
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        )
        if not tabla:
            raise HTTPException(status_code=503, detail="La tabla de gastos no está disponible")
        if tipo == "faena":
            existe = db.execute("SELECT 1 FROM faenas WHERE id = ?", (datos.faena_id,)).fetchone()
        else:
            existe = db.execute(
                "SELECT 1 FROM presupuestos WHERE num_presupuesto = ?",
                (datos.num_presupuesto.strip(),),
            ).fetchone()
        if not existe:
            raise HTTPException(status_code=400, detail="El destino del gasto no existe")
        cursor = db.execute(
            f"UPDATE {tabla} SET {asignaciones} WHERE id = ?",
            [*valores, gasto_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Gasto no encontrado")
        fila = db.execute(f"SELECT * FROM {tabla} WHERE id = ?", (gasto_id,)).fetchone()
    resultado = dict(fila)
    resultado["tipo"] = tipo
    return resultado


@app.delete("/gastos/{tipo}/{gasto_id}")
def borrar_gasto(
    tipo: Literal["faena", "presupuesto"],
    gasto_id: int,
    usuario=Depends(administrador),
):
    nombres = (
        ("gastos_faenas_extras", "gasto_faenas")
        if tipo == "faena"
        else ("gastos_presupuestos", "gasto_presupuesto")
    )
    with conexion() as db:
        tabla = next(
            (
                nombre for nombre in nombres
                if db.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        ) if DATABASE_URL else next(
            (
                nombre for nombre in nombres
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        )
        if not tabla:
            raise HTTPException(status_code=503, detail="La tabla de gastos no está disponible")
        cursor = db.execute(f"DELETE FROM {tabla} WHERE id = ?", (gasto_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Gasto no encontrado")
    return {"eliminado": True, "id": gasto_id, "tipo": tipo}


@app.post("/gastos/{tipo}/{gasto_id}/pagos", status_code=201)
def registrar_pago_gasto(
    tipo: Literal["faena", "presupuesto"],
    gasto_id: int,
    pago: PagoGastoCreate,
    usuario=Depends(administrador),
):
    nombres_gasto = (
        ("gastos_faenas_extras", "gasto_faenas")
        if tipo == "faena"
        else ("gastos_presupuestos", "gasto_presupuesto")
    )
    with conexion() as db:
        tabla_gasto = next(
            (
                nombre for nombre in nombres_gasto
                if db.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        ) if DATABASE_URL else next(
            (
                nombre for nombre in nombres_gasto
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        )
        if not tabla_gasto:
            raise HTTPException(status_code=503, detail="La tabla de gastos no está disponible")
        gasto = db.execute(
            f"SELECT id, importe, COALESCE(importe_pagado, pagado, 0) AS importe_pagado "
            f"FROM {tabla_gasto} WHERE id = ?",
            (gasto_id,),
        ).fetchone()
        if not gasto:
            raise HTTPException(status_code=404, detail="Gasto no encontrado")

        nombres_pagos = ("pagos_gastos",)
        tabla_pagos = next(
            (
                nombre for nombre in nombres_pagos
                if db.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        ) if DATABASE_URL else next(
            (
                nombre for nombre in nombres_pagos
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (nombre,),
                ).fetchone()
            ),
            None,
        )
        if not tabla_pagos:
            raise HTTPException(status_code=503, detail="La tabla de pagos de gastos no está disponible")
        importe_pagado = float(gasto["importe_pagado"] or 0) + pago.importe
        estado = "Pagado" if importe_pagado >= float(gasto["importe"] or 0) else "Parcial"
        importe_banco = pago.importe if pago.forma_pago.lower() != "efectivo" else 0
        importe_efectivo = pago.importe if pago.forma_pago.lower() == "efectivo" else 0
        if DATABASE_URL:
            fila_pago = db.execute(
                f"INSERT INTO {tabla_pagos} "
                "(gasto_id, fecha, importe_banco, importe_efectivo, observaciones, tipo_gasto, importe, forma_pago) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
                (gasto_id, pago.fecha.isoformat() if pago.fecha else None,
                 importe_banco, importe_efectivo, pago.observaciones,
                 tipo, pago.importe, pago.forma_pago),
            ).fetchone()
        else:
            db.execute(
                f"INSERT INTO {tabla_pagos} "
                "(gasto_id, fecha, importe_banco, importe_efectivo, observaciones, tipo_gasto, importe, forma_pago) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (gasto_id, pago.fecha.isoformat() if pago.fecha else None,
                 importe_banco, importe_efectivo, pago.observaciones,
                 tipo, pago.importe, pago.forma_pago),
            )
            fila_pago = db.execute(
                f"SELECT * FROM {tabla_pagos} WHERE id = last_insert_rowid()"
            ).fetchone()
        db.execute(
            f"UPDATE {tabla_gasto} SET importe_pagado = ?, pagado = ?, estado_pago = ? WHERE id = ?",
            (importe_pagado, importe_pagado, estado, gasto_id),
        )
    return {"pago": dict(fila_pago), "importe_pagado": importe_pagado, "estado_pago": estado}


@app.get("/gastos/{tipo}/{gasto_id}/pagos")
def listar_pagos_gasto(
    tipo: Literal["faena", "presupuesto"],
    gasto_id: int,
    usuario=Depends(administrador),
):
    with conexion() as db:
        existe = db.execute(
            "SELECT 1 FROM pagos_gastos WHERE gasto_id = ? AND tipo_gasto = ? LIMIT 1",
            (gasto_id, tipo),
        ).fetchone()
        if not existe:
            nombres_gasto = (
                ("gastos_faenas_extras", "gasto_faenas")
                if tipo == "faena"
                else ("gastos_presupuestos", "gasto_presupuesto")
            )
            tabla = next(
                (
                    nombre for nombre in nombres_gasto
                    if db.execute(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = ?",
                        (nombre,),
                    ).fetchone()
                ),
                None,
            ) if DATABASE_URL else next(
                (
                    nombre for nombre in nombres_gasto
                    if db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (nombre,),
                    ).fetchone()
                ),
                None,
            )
            if not tabla or not db.execute(
                f"SELECT 1 FROM {tabla} WHERE id = ?", (gasto_id,)
            ).fetchone():
                raise HTTPException(status_code=404, detail="Gasto no encontrado")
        filas = db.execute(
            "SELECT id, gasto_id, fecha, importe_banco, importe_efectivo, "
            "observaciones, tipo_gasto, importe, forma_pago "
            "FROM pagos_gastos WHERE gasto_id = ? AND tipo_gasto = ? ORDER BY fecha DESC, id DESC",
            (gasto_id, tipo),
        ).fetchall()
    return [dict(fila) for fila in filas]


@app.get("/citas")
def listar_citas(usuario=Depends(administrador)):
    with conexion() as db:
        filas = db.execute(
            "SELECT * FROM citas_agenda ORDER BY fecha, hora, id"
        ).fetchall()
    return [dict(fila) for fila in filas]


@app.get("/alarmas")
def listar_alarmas(usuario=Depends(administrador)):
    with conexion() as db:
        notas = db.execute("SELECT id, fecha_recordatorio AS fecha, hora, cliente, ubicacion, poblacion, motivo AS detalle, estado FROM seguimientos_agenda WHERE estado = 'Pendiente'").fetchall()
        citas = db.execute("SELECT id, fecha, hora, cliente, ubicacion, poblacion, observaciones AS detalle, estado FROM citas_agenda WHERE estado = 'Pendiente'").fetchall()
        trabajos = db.execute("SELECT id, fecha_inicio AS fecha, '' AS hora, cliente, ubicacion, poblacion, obra AS detalle, estado_cobro AS estado FROM trabajos_propios WHERE fecha_inicio >= CURRENT_DATE").fetchall()
    alarmas = []
    for fila in notas:
        item = dict(fila); item.update(tipo="nota", referencia_id=item.pop("id")); alarmas.append(item)
    for fila in citas:
        item = dict(fila); item.update(tipo="cita", referencia_id=item.pop("id")); alarmas.append(item)
    for fila in trabajos:
        item = dict(fila); item.update(tipo="trabajo", referencia_id=item.pop("id")); alarmas.append(item)
    return sorted(alarmas, key=lambda item: (str(item.get("fecha") or ""), str(item.get("hora") or "")))


@app.post("/calendario/silenciar")
def silenciar_dia(datos: SilencioCalendarioCreate, usuario=Depends(administrador)):
    fecha = datos.fecha.isoformat()
    with conexion() as db:
        if DATABASE_URL:
            db.execute("INSERT INTO calendario_silencios (fecha, motivo) VALUES (?, ?) ON CONFLICT (fecha) DO UPDATE SET motivo = EXCLUDED.motivo", (fecha, datos.motivo.strip() or "Sin sonido"))
        else:
            db.execute("INSERT OR REPLACE INTO calendario_silencios (fecha, motivo) VALUES (?, ?)", (fecha, datos.motivo.strip() or "Sin sonido"))
    return {"fecha": fecha, "silenciado": True}


@app.post("/citas", status_code=201)
def crear_cita(datos: CitaCreate, usuario=Depends(administrador)):
    valores = datos.model_dump()
    valores["fecha"] = valores["fecha"].isoformat()
    valores = {clave: valor.strip() if isinstance(valor, str) else valor for clave, valor in valores.items()}
    columnas = ", ".join(valores)
    marcadores = ", ".join("?" for _ in valores)
    with conexion() as db:
        if DATABASE_URL:
            fila = db.execute(
                f"INSERT INTO citas_agenda ({columnas}) VALUES ({marcadores}) RETURNING *",
                tuple(valores.values()),
            ).fetchone()
        else:
            db.execute(f"INSERT INTO citas_agenda ({columnas}) VALUES ({marcadores})", tuple(valores.values()))
            fila = db.execute("SELECT * FROM citas_agenda WHERE id = last_insert_rowid()").fetchone()
    return dict(fila)


@app.patch("/citas/{cita_id}")
def modificar_cita(cita_id: int, datos: CitaUpdate, usuario=Depends(administrador)):
    valores = datos.model_dump()
    valores["fecha"] = valores["fecha"].isoformat()
    valores = {clave: valor.strip() if isinstance(valor, str) else valor for clave, valor in valores.items()}
    asignaciones = ", ".join(f"{clave} = ?" for clave in valores)
    with conexion() as db:
        cursor = db.execute(
            f"UPDATE citas_agenda SET {asignaciones}, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            [*valores.values(), cita_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Cita no encontrada")
        fila = db.execute("SELECT * FROM citas_agenda WHERE id = ?", (cita_id,)).fetchone()
    return dict(fila)


@app.delete("/citas/{cita_id}")
def borrar_cita(cita_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        cursor = db.execute("DELETE FROM citas_agenda WHERE id = ?", (cita_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Cita no encontrada")
    return {"eliminada": True}


@app.get("/citas/{cita_id}/calendario")
def calendario_cita(cita_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        cita = db.execute("SELECT * FROM citas_agenda WHERE id = ?", (cita_id,)).fetchone()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    fecha = cita["fecha"]
    if hasattr(fecha, "strftime"):
        fecha_texto = fecha.strftime("%Y%m%d")
    else:
        fecha_texto = str(fecha).replace("-", "")
    inicio = datetime.strptime(f"{fecha_texto} {cita['hora']}", "%Y%m%d %H:%M")
    from datetime import timedelta
    fin = inicio + timedelta(minutes=int(cita["duracion_minutos"]))
    titulo = f"{cita['tipo'].capitalize()}" + (f": {cita['cliente']}" if cita["cliente"] else "")
    ubicacion = ", ".join(filter(None, [cita["ubicacion"], cita["poblacion"]]))
    contenido = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Alucarpin//Agenda//ES", "X-WR-CALNAME:Alucarpin", "BEGIN:VEVENT",
        f"UID:alucarpin-cita-{cita_id}@alucarpin.app", f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{fin.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(titulo)}", f"LOCATION:{_ics_escape(ubicacion)}",
        f"DESCRIPTION:{_ics_escape(cita['observaciones'])}", "END:VEVENT", "END:VCALENDAR", "",
    ])
    return Response(content=contenido, media_type="text/calendar", headers={"Content-Disposition": f'attachment; filename="alucarpin-cita-{cita_id}.ics"'})


@app.get("/seguimientos")
def listar_seguimientos(usuario=Depends(administrador)):
    with conexion() as db:
        filas = db.execute(
            "SELECT * FROM seguimientos_agenda ORDER BY estado, fecha_recordatorio, hora, id"
        ).fetchall()
    return [dict(fila) for fila in filas]


@app.post("/seguimientos", status_code=201)
def crear_seguimiento(datos: SeguimientoCreate, usuario=Depends(administrador)):
    valores = datos.model_dump()
    valores["fecha_llamada"] = (valores.get("fecha_llamada") or date.today()).isoformat()
    valores["fecha_recordatorio"] = (valores.get("fecha_recordatorio") or date.today()).isoformat()
    valores = {clave: valor.strip() if isinstance(valor, str) else valor for clave, valor in valores.items()}
    columnas = ", ".join(valores)
    marcadores = ", ".join("?" for _ in valores)
    with conexion() as db:
        if DATABASE_URL:
            fila = db.execute(
                f"INSERT INTO seguimientos_agenda ({columnas}) VALUES ({marcadores}) RETURNING *",
                tuple(valores.values()),
            ).fetchone()
        else:
            db.execute(f"INSERT INTO seguimientos_agenda ({columnas}) VALUES ({marcadores})", tuple(valores.values()))
            fila = db.execute("SELECT * FROM seguimientos_agenda WHERE id = last_insert_rowid()").fetchone()
    return dict(fila)


@app.patch("/seguimientos/{seguimiento_id}")
def modificar_seguimiento(seguimiento_id: int, datos: SeguimientoUpdate, usuario=Depends(administrador)):
    valores = datos.model_dump()
    with conexion() as db:
        existente = db.execute(
            "SELECT fecha_recordatorio FROM seguimientos_agenda WHERE id = ?",
            (seguimiento_id,),
        ).fetchone()
    if not existente:
        raise HTTPException(status_code=404, detail="Seguimiento no encontrado")
    valores["fecha_llamada"] = (valores.get("fecha_llamada") or date.today()).isoformat()
    fecha_recordatorio = valores.get("fecha_recordatorio") or existente["fecha_recordatorio"]
    valores["fecha_recordatorio"] = fecha_recordatorio.isoformat() if hasattr(fecha_recordatorio, "isoformat") else fecha_recordatorio
    valores = {clave: valor.strip() if isinstance(valor, str) else valor for clave, valor in valores.items()}
    asignaciones = ", ".join(f"{clave} = ?" for clave in valores)
    with conexion() as db:
        cursor = db.execute(
            f"UPDATE seguimientos_agenda SET {asignaciones}, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            [*valores.values(), seguimiento_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Seguimiento no encontrado")
        fila = db.execute("SELECT * FROM seguimientos_agenda WHERE id = ?", (seguimiento_id,)).fetchone()
    return dict(fila)


@app.delete("/seguimientos/{seguimiento_id}")
def borrar_seguimiento(seguimiento_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        cursor = db.execute("DELETE FROM seguimientos_agenda WHERE id = ?", (seguimiento_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Seguimiento no encontrado")
    return {"eliminado": True}


@app.get("/seguimientos/{seguimiento_id}/calendario")
def calendario_seguimiento(seguimiento_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        seguimiento = db.execute("SELECT * FROM seguimientos_agenda WHERE id = ?", (seguimiento_id,)).fetchone()
    if not seguimiento:
        raise HTTPException(status_code=404, detail="Seguimiento no encontrado")
    fecha = seguimiento["fecha_recordatorio"]
    fecha_texto = fecha.strftime("%Y%m%d") if hasattr(fecha, "strftime") else str(fecha).replace("-", "")
    inicio = datetime.strptime(f"{fecha_texto} {seguimiento['hora']}", "%Y%m%d %H:%M")
    from datetime import timedelta
    fin = inicio + timedelta(minutes=15)
    titulo = f"Llamar" + (f": {seguimiento['cliente']}" if seguimiento["cliente"] else "")
    fecha_llamada = seguimiento["fecha_llamada"] or ""
    ubicacion = ", ".join(filter(None, [seguimiento["ubicacion"], seguimiento["poblacion"]]))
    descripcion = " | ".join(filter(None, [f"Llamada recibida el {fecha_llamada}", seguimiento["motivo"], seguimiento["observaciones"], ubicacion, seguimiento["telefono"]]))
    recurrencia = ["RRULE:FREQ=DAILY;COUNT=365"] if seguimiento["estado"] == "Pendiente" else []
    contenido = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Alucarpin//Agenda//ES", "BEGIN:VEVENT",
        f"UID:alucarpin-seguimiento-{seguimiento_id}@alucarpin.app", f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{fin.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(titulo)}", f"DESCRIPTION:{_ics_escape(descripcion)}",
        *recurrencia,
        "BEGIN:VALARM", "TRIGGER:-PT0M", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(titulo)}", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR", "",
    ])
    return Response(content=contenido, media_type="text/calendar", headers={"Content-Disposition": f'attachment; filename="alucarpin-seguimiento-{seguimiento_id}.ics"'})


@app.get("/calendario.ics")
def calendario_completo(usuario=Depends(administrador)):
    eventos = []
    with conexion() as db:
        trabajos = db.execute("SELECT * FROM trabajos_propios ORDER BY fecha_inicio, id").fetchall()
        citas = db.execute("SELECT * FROM citas_agenda ORDER BY fecha, hora, id").fetchall()
        seguimientos = db.execute("SELECT * FROM seguimientos_agenda ORDER BY fecha_recordatorio, hora, id").fetchall()
        silencios = db.execute("SELECT fecha FROM calendario_silencios").fetchall()
    fechas_silenciadas = {fila["fecha"].isoformat() if hasattr(fila["fecha"], "isoformat") else str(fila["fecha"]) for fila in silencios}

    from datetime import timedelta
    for trabajo in trabajos:
        inicio = trabajo["fecha_inicio"]
        fin = trabajo["fecha_fin"] or inicio
        inicio_texto = inicio.strftime("%Y%m%d") if hasattr(inicio, "strftime") else str(inicio).replace("-", "")
        if hasattr(fin, "strftime"):
            fin_fecha = fin + timedelta(days=1)
            fin_texto = fin_fecha.strftime("%Y%m%d")
        else:
            partes = str(fin).split("-")
            fin_texto = (date(int(partes[0]), int(partes[1]), int(partes[2])) + timedelta(days=1)).strftime("%Y%m%d")
        titulo = f"{trabajo['tipo'].capitalize()}: {trabajo['cliente']} - {trabajo['obra']}"
        ubicacion = ", ".join(filter(None, [trabajo["ubicacion"], trabajo["poblacion"]]))
        eventos.append([f"UID:alucarpin-trabajo-{trabajo['id']}@alucarpin.app", f"DTSTART;VALUE=DATE:{inicio_texto}", f"DTEND;VALUE=DATE:{fin_texto}", f"SUMMARY:{_ics_escape(titulo)}", f"LOCATION:{_ics_escape(ubicacion)}", f"DESCRIPTION:{_ics_escape(trabajo['observaciones'])}"])

    for cita in citas:
        fecha_texto = cita["fecha"].strftime("%Y%m%d") if hasattr(cita["fecha"], "strftime") else str(cita["fecha"]).replace("-", "")
        inicio = datetime.strptime(f"{fecha_texto} {cita['hora']}", "%Y%m%d %H:%M")
        fin = inicio + timedelta(minutes=int(cita["duracion_minutos"]))
        titulo = f"{cita['tipo'].capitalize()}" + (f": {cita['cliente']}" if cita["cliente"] else "")
        ubicacion = ", ".join(filter(None, [cita["ubicacion"], cita["poblacion"]]))
        eventos.append([f"UID:alucarpin-cita-{cita['id']}@alucarpin.app", f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{fin.strftime('%Y%m%dT%H%M%S')}", f"SUMMARY:{_ics_escape(titulo)}", f"LOCATION:{_ics_escape(ubicacion)}", f"DESCRIPTION:{_ics_escape(cita['observaciones'])}"])

    for seguimiento in seguimientos:
        titulo = f"Llamar" + (f": {seguimiento['cliente']}" if seguimiento["cliente"] else "")
        ubicacion = ", ".join(filter(None, [seguimiento["ubicacion"], seguimiento["poblacion"]]))
        descripcion = " | ".join(filter(None, [f"Llamada recibida el {seguimiento['fecha_llamada']}", seguimiento["motivo"], seguimiento["observaciones"], ubicacion, seguimiento["telefono"]]))
        inicio_fecha = seguimiento["fecha_recordatorio"] if hasattr(seguimiento["fecha_recordatorio"], "strftime") else date.fromisoformat(str(seguimiento["fecha_recordatorio"]))
        for dias in range(365 if seguimiento["estado"] == "Pendiente" else 1):
            fecha_evento = inicio_fecha + timedelta(days=dias)
            fecha_iso = fecha_evento.isoformat()
            fecha_texto = fecha_evento.strftime("%Y%m%d")
            inicio = datetime.strptime(f"{fecha_texto} {seguimiento['hora']}", "%Y%m%d %H:%M")
            fin = inicio + timedelta(minutes=15)
            alarma = [] if fecha_evento.weekday() >= 5 or fecha_iso in fechas_silenciadas else ["BEGIN:VALARM", "TRIGGER:-PT0M", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(titulo)}", "END:VALARM"]
            eventos.append([f"UID:alucarpin-seguimiento-{seguimiento['id']}-{fecha_iso}@alucarpin.app", f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{fin.strftime('%Y%m%dT%H%M%S')}", f"SUMMARY:{_ics_escape(titulo)}", f"DESCRIPTION:{_ics_escape(descripcion)}", *alarma])

    lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Alucarpin//Agenda//ES", "X-WR-CALNAME:Alucarpin"]
    for evento in eventos:
        lineas.extend(["BEGIN:VEVENT", f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}", *evento, "END:VEVENT"])
    lineas.extend(["END:VCALENDAR", ""])
    return Response(content="\r\n".join(lineas), media_type="text/calendar", headers={"Content-Disposition": 'attachment; filename="alucarpin-calendario-completo.ics"'})


def _trabajo_datos(datos):
    valores = datos.model_dump()
    for clave in ("fecha_inicio", "fecha_fin", "fecha_cobro"):
        if valores.get(clave):
            valores[clave] = valores[clave].isoformat()
    for clave in ("cliente", "obra", "ubicacion", "poblacion", "observaciones", "num_presupuesto", "forma_pago"):
        if isinstance(valores.get(clave), str):
            valores[clave] = valores[clave].strip()
    if valores["fecha_fin"] and valores["fecha_fin"] < valores["fecha_inicio"]:
        raise HTTPException(status_code=400, detail="La fecha final no puede ser anterior a la inicial")
    if valores["tipo"] == "presupuesto" and not valores["num_presupuesto"]:
        raise HTTPException(status_code=400, detail="Selecciona un presupuesto existente")
    if valores["estado_cobro"] == "Cobrado" and not valores["fecha_cobro"]:
        valores["fecha_cobro"] = valores["fecha_inicio"]
    return valores


@app.get("/presupuestos")
def listar_presupuestos(q: str = "", usuario=Depends(usuario_actual)):
    patron = f"%{q.strip()}%"
    try:
        with conexion() as db:
            filas = db.execute(
                """
                SELECT id, cliente, num_presupuesto, fecha, bruto, iva, total_iva, presupuesto_iva, efectivo, estado, presupuesto_final
                FROM presupuestos
                WHERE (? = '' OR cliente LIKE ? OR num_presupuesto LIKE ?)
                ORDER BY id DESC
                """,
                (q.strip(), patron, patron),
            ).fetchall()
    except Exception as error:
        if "no such table" in str(error).lower() or "does not exist" in str(error).lower():
            return []
        raise HTTPException(status_code=503, detail="La tabla de presupuestos no está disponible") from error
    return [dict(fila) for fila in filas]


@app.post("/presupuestos", status_code=201)
def crear_presupuesto(datos: PresupuestoCreate, usuario=Depends(administrador)):
    valores = datos.model_dump()
    if valores.get("fecha"):
        valores["fecha"] = valores["fecha"].isoformat()
    columnas = ", ".join(valores.keys())
    marcadores = ", ".join("?" for _ in valores)
    with conexion() as db:
        if DATABASE_URL:
            fila = db.execute(
                f"INSERT INTO presupuestos ({columnas}) VALUES ({marcadores}) RETURNING *",
                tuple(valores.values()),
            ).fetchone()
        else:
            db.execute(
                f"INSERT INTO presupuestos ({columnas}) VALUES ({marcadores})",
                tuple(valores.values()),
            )
            fila = db.execute("SELECT * FROM presupuestos WHERE id = last_insert_rowid()").fetchone()
    return dict(fila)


@app.patch("/presupuestos/{presupuesto_id}")
def modificar_presupuesto(presupuesto_id: int, datos: PresupuestoUpdate, usuario=Depends(administrador)):
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(status_code=400, detail="No hay datos para modificar")
    if cambios.get("fecha"):
        cambios["fecha"] = cambios["fecha"].isoformat()
    with conexion() as db:
        existente = db.execute(
            "SELECT 1 FROM presupuestos WHERE id = ?", (presupuesto_id,)
        ).fetchone()
        if not existente:
            raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
        set_clause = ", ".join(f"{clave} = ?" for clave in cambios.keys())
        db.execute(
            f"UPDATE presupuestos SET {set_clause} WHERE id = ?",
            tuple(list(cambios.values()) + [presupuesto_id]),
        )
        fila = db.execute("SELECT * FROM presupuestos WHERE id = ?", (presupuesto_id,)).fetchone()
    return dict(fila)


@app.delete("/presupuestos/{presupuesto_id}")
def borrar_presupuesto(presupuesto_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        cursor = db.execute("DELETE FROM presupuestos WHERE id = ?", (presupuesto_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    return {"eliminado": True, "id": presupuesto_id}


@app.get("/faenas")
def listar_faenas(usuario=Depends(administrador)):
    try:
        with conexion() as db:
            filas = db.execute(
                "SELECT id, cliente, obra, fecha, ubicacion, poblacion, precio, ayudantes "
                "FROM faenas ORDER BY fecha DESC, id DESC"
            ).fetchall()
    except Exception as error:
        if "no such table" in str(error).lower() or "does not exist" in str(error).lower():
            return []
        raise HTTPException(status_code=503, detail="La tabla de faenas no está disponible") from error
    return [dict(fila) for fila in filas]


@app.post("/faenas", status_code=201)
def crear_faena(datos: FaenaCreate, usuario=Depends(administrador)):
    valores = datos.model_dump()
    if valores.get("fecha"):
        valores["fecha"] = valores["fecha"].isoformat()
    columnas = ", ".join(valores.keys())
    marcadores = ", ".join("?" for _ in valores)
    with conexion() as db:
        if DATABASE_URL:
            fila = db.execute(
                f"INSERT INTO faenas ({columnas}) VALUES ({marcadores}) RETURNING *",
                tuple(valores.values()),
            ).fetchone()
        else:
            db.execute(
                f"INSERT INTO faenas ({columnas}) VALUES ({marcadores})",
                tuple(valores.values()),
            )
            fila = db.execute("SELECT * FROM faenas WHERE id = last_insert_rowid()").fetchone()
    return dict(fila)


@app.patch("/faenas/{faena_id}")
def modificar_faena(faena_id: int, datos: FaenaUpdate, usuario=Depends(administrador)):
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(status_code=400, detail="No hay datos para modificar")
    if cambios.get("fecha"):
        cambios["fecha"] = cambios["fecha"].isoformat()
    with conexion() as db:
        existente = db.execute(
            "SELECT 1 FROM faenas WHERE id = ?", (faena_id,)
        ).fetchone()
        if not existente:
            raise HTTPException(status_code=404, detail="Faena no encontrada")
        set_clause = ", ".join(f"{clave} = ?" for clave in cambios.keys())
        db.execute(
            f"UPDATE faenas SET {set_clause} WHERE id = ?",
            tuple(list(cambios.values()) + [faena_id]),
        )
        fila = db.execute("SELECT * FROM faenas WHERE id = ?", (faena_id,)).fetchone()
    return dict(fila)


@app.delete("/faenas/{faena_id}")
def borrar_faena(faena_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        cursor = db.execute("DELETE FROM faenas WHERE id = ?", (faena_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Faena no encontrada")
    return {"eliminado": True, "id": faena_id}


@app.get("/trabajos")
def listar_trabajos(usuario=Depends(administrador)):
    with conexion() as db:
        filas = db.execute(
            "SELECT * FROM trabajos_propios ORDER BY fecha_inicio DESC, id DESC"
        ).fetchall()
    return [dict(fila) for fila in filas]


@app.post("/trabajos", status_code=201)
def crear_trabajo(datos: TrabajoCreate, usuario=Depends(administrador)):
    valores = _trabajo_datos(datos)
    columnas = ", ".join(valores)
    marcadores = ", ".join("?" for _ in valores)
    with conexion() as db:
        if valores["num_presupuesto"]:
            presupuesto = db.execute(
                "SELECT 1 FROM presupuestos WHERE num_presupuesto = ? LIMIT 1",
                (valores["num_presupuesto"],),
            ).fetchone()
            if not presupuesto:
                raise HTTPException(status_code=400, detail="El presupuesto seleccionado no existe")
        if DATABASE_URL:
            fila = db.execute(
                f"INSERT INTO trabajos_propios ({columnas}) VALUES ({marcadores}) RETURNING *",
                tuple(valores.values()),
            ).fetchone()
        else:
            db.execute(
                f"INSERT INTO trabajos_propios ({columnas}) VALUES ({marcadores})",
                tuple(valores.values()),
            )
            fila = db.execute("SELECT * FROM trabajos_propios WHERE id = last_insert_rowid()").fetchone()
    return dict(fila)


@app.patch("/trabajos/{trabajo_id}")
def modificar_trabajo(trabajo_id: int, datos: TrabajoUpdate, usuario=Depends(administrador)):
    valores = _trabajo_datos(datos)
    asignaciones = ", ".join(f"{clave} = ?" for clave in valores)
    with conexion() as db:
        cursor = db.execute(
            f"UPDATE trabajos_propios SET {asignaciones}, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            [*valores.values(), trabajo_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado")
        fila = db.execute("SELECT * FROM trabajos_propios WHERE id = ?", (trabajo_id,)).fetchone()
    return dict(fila)


@app.delete("/trabajos/{trabajo_id}")
def borrar_trabajo(trabajo_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        cursor = db.execute("DELETE FROM trabajos_propios WHERE id = ?", (trabajo_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {"eliminado": True}


def _ics_escape(valor):
    return str(valor or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@app.get("/trabajos/{trabajo_id}/calendario")
def calendario_trabajo(trabajo_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        trabajo = db.execute("SELECT * FROM trabajos_propios WHERE id = ?", (trabajo_id,)).fetchone()
    if not trabajo:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    inicio = trabajo["fecha_inicio"].strftime("%Y%m%d") if hasattr(trabajo["fecha_inicio"], "strftime") else str(trabajo["fecha_inicio"]).replace("-", "")
    fecha_fin = trabajo["fecha_fin"] or trabajo["fecha_inicio"]
    if hasattr(fecha_fin, "toordinal"):
        from datetime import timedelta
        fecha_fin = fecha_fin + timedelta(days=1)
        fin = fecha_fin.strftime("%Y%m%d")
    else:
        partes = str(fecha_fin).split("-")
        fecha_fin = date(int(partes[0]), int(partes[1]), int(partes[2]))
        from datetime import timedelta
        fin = (fecha_fin + timedelta(days=1)).strftime("%Y%m%d")
    titulo = f"{trabajo['tipo'].capitalize()}: {trabajo['cliente']} - {trabajo['obra']}"
    descripcion = " | ".join(filter(None, [trabajo["observaciones"], f"Presupuesto {trabajo['num_presupuesto']}" if trabajo["num_presupuesto"] else ""]))
    ubicacion = ", ".join(filter(None, [trabajo["ubicacion"], trabajo["poblacion"]]))
    contenido = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Alucarpin//Agenda//ES", "BEGIN:VEVENT",
        f"UID:alucarpin-trabajo-{trabajo_id}@alucarpin.app", f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{inicio}", f"DTEND;VALUE=DATE:{fin}", f"SUMMARY:{_ics_escape(titulo)}",
        f"LOCATION:{_ics_escape(ubicacion)}", f"DESCRIPTION:{_ics_escape(descripcion)}", "END:VEVENT", "END:VCALENDAR", "",
    ])
    return Response(
        content=contenido,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="alucarpin-trabajo-{trabajo_id}.ics"'},
    )


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


@app.post("/ayudantes", status_code=201)
def crear_ayudante(datos: AyudanteCreate, usuario=Depends(administrador)):
    from autenticacion import hash_password, usuario_normalizado

    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    nombre_usuario = usuario_normalizado(nombre)
    salt, digest = hash_password("Cambiar123!")
    with conexion() as db:
        siguiente_id = db.execute("SELECT COALESCE(MAX(id), 0) + 1 AS siguiente_id FROM ayudantes").fetchone()
        ayudante_id = siguiente_id["siguiente_id"] if isinstance(siguiente_id, dict) else siguiente_id[0]
        try:
            db.execute("INSERT INTO ayudantes (id, nombre) VALUES (?, ?)", (ayudante_id, nombre))
            db.execute(
                "INSERT INTO usuarios (usuario, password_salt, password_hash, rol, ayudante_id) VALUES (?, ?, ?, 'ayudante', ?)",
                (nombre_usuario, salt, digest, ayudante_id),
            )
            db.commit()
        except Exception as error:
            db.rollback()
            if "usuario" in str(error).lower() or "unique" in str(error).lower():
                raise HTTPException(status_code=409, detail="Ya existe un ayudante o usuario con ese nombre") from error
            raise
    return {"id": ayudante_id, "nombre": nombre, "usuario": nombre_usuario, "password_inicial": "Cambiar123!"}


@app.patch("/ayudantes/{ayudante_id}")
def modificar_ayudante(ayudante_id: int, datos: AyudanteUpdate, usuario=Depends(administrador)):
    from autenticacion import usuario_normalizado

    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    nombre_usuario = usuario_normalizado(nombre)
    with conexion() as db:
        existente = db.execute("SELECT id FROM ayudantes WHERE id = ?", (ayudante_id,)).fetchone()
        if not existente:
            raise HTTPException(status_code=404, detail="Ayudante no encontrado")
        try:
            db.execute("UPDATE ayudantes SET nombre = ? WHERE id = ?", (nombre, ayudante_id))
            db.execute("UPDATE usuarios SET usuario = ? WHERE ayudante_id = ?", (nombre_usuario, ayudante_id))
            db.commit()
        except Exception as error:
            db.rollback()
            if "unique" in str(error).lower() or "usuario" in str(error).lower():
                raise HTTPException(status_code=409, detail="Ya existe un ayudante o usuario con ese nombre") from error
            raise
    return {"id": ayudante_id, "nombre": nombre, "usuario": nombre_usuario}


@app.delete("/ayudantes/{ayudante_id}")
def borrar_ayudante(ayudante_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        existente = db.execute("SELECT id FROM ayudantes WHERE id = ?", (ayudante_id,)).fetchone()
        if not existente:
            raise HTTPException(status_code=404, detail="Ayudante no encontrado")
        fichajes = db.execute("SELECT 1 FROM fichajes_ayudantes WHERE ayudante_id = ? LIMIT 1", (ayudante_id,)).fetchone()
        pagos = db.execute("SELECT 1 FROM liquidaciones WHERE ayudante_id = ? LIMIT 1", (ayudante_id,)).fetchone()
        if fichajes or pagos:
            raise HTTPException(status_code=409, detail="No se puede borrar: tiene fichajes o pagos asociados")
        db.execute("DELETE FROM usuarios WHERE ayudante_id = ?", (ayudante_id,))
        db.execute("DELETE FROM ayudantes WHERE id = ?", (ayudante_id,))
        db.commit()
    return {"borrado": True}


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
        registros = [dict(fila) for fila in filas]
        pagos = db.execute(
            "SELECT ayudante_id, desde, hasta, precio_dia, importe_pagado FROM liquidaciones WHERE ayudante_id = ?",
            (ayudante_id,),
        ).fetchall()
        for registro in registros:
            registro["pagado"] = False
            for pago in pagos:
                desde_pago = pago["desde"]
                hasta_pago = pago["hasta"]
                if desde_pago <= registro["fecha"] <= hasta_pago:
                    dia_laborable = "strftime('%w', fecha) NOT IN ('0', '6')" if not DATABASE_URL else "EXTRACT(DOW FROM fecha) NOT IN (0, 6)"
                    cantidad = db.execute(
                        f"SELECT COUNT(*) AS cantidad FROM fichajes_ayudantes WHERE ayudante_id = ? AND fecha BETWEEN ? AND ? AND confirmado_ayudante = 1 AND {dia_laborable}",
                        (ayudante_id, desde_pago, hasta_pago),
                    ).fetchone()["cantidad"]
                    total = round(cantidad * pago["precio_dia"], 2)
                    registro["pagado"] = total > 0 and pago["importe_pagado"] >= total
                    break
        return registros


@app.post("/fichajes", status_code=201)
def crear_fichaje(fichaje: FichajeCreate, usuario=Depends(usuario_actual)):
    if usuario["rol"] == "ayudante" and fichaje.ayudante_id != usuario["ayudante_id"]:
        raise HTTPException(status_code=403, detail="No puedes registrar otro ayudante")
    try:
        with conexion() as db:
            num_presupuesto = fichaje.num_presupuesto.strip() if fichaje.num_presupuesto else None
            if fichaje.tipo_destino == "presupuesto" and num_presupuesto:
                presupuesto = db.execute(
                    "SELECT 1 FROM presupuestos WHERE num_presupuesto = ? LIMIT 1",
                    (num_presupuesto,),
                ).fetchone()
                if not presupuesto:
                    raise HTTPException(status_code=400, detail="El presupuesto seleccionado no existe")
            parametros = (fichaje.ayudante_id, fichaje.fecha.isoformat(), fichaje.tipo_destino, fichaje.cliente.strip(), fichaje.obra.strip(), fichaje.ubicacion.strip(), fichaje.poblacion.strip(), num_presupuesto)
            if DATABASE_URL:
                fila = db.execute(
                    "INSERT INTO fichajes_ayudantes (ayudante_id, fecha, tipo_destino, cliente, obra, ubicacion, poblacion, num_presupuesto, confirmado_ayudante, sincronizado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1) RETURNING *",
                    parametros,
                ).fetchone()
            else:
                db.execute(
                    "INSERT INTO fichajes_ayudantes (ayudante_id, fecha, tipo_destino, cliente, obra, ubicacion, poblacion, num_presupuesto, confirmado_ayudante, sincronizado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
                    parametros,
                )
                fila = db.execute("SELECT * FROM fichajes_ayudantes WHERE id = last_insert_rowid()").fetchone()
            return dict(fila)
    except (sqlite3.IntegrityError, psycopg.IntegrityError) as error:
        raise HTTPException(status_code=409, detail=f"Fichaje duplicado o ayudante inexistente: {error}") from error


@app.patch("/fichajes/{fichaje_id}")
def modificar_fichaje(fichaje_id: int, cambios: FichajeUpdate, usuario=Depends(usuario_actual)):
    datos = cambios.model_dump(exclude_unset=True)
    if datos.get("num_presupuesto"):
        datos["num_presupuesto"] = datos["num_presupuesto"].strip()
        with conexion() as db:
            presupuesto = db.execute(
                "SELECT 1 FROM presupuestos WHERE num_presupuesto = ? LIMIT 1",
                (datos["num_presupuesto"],),
            ).fetchone()
        if not presupuesto:
            raise HTTPException(status_code=400, detail="El presupuesto seleccionado no existe")
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


@app.patch("/fichajes/{fichaje_id}/vinculacion")
def vincular_fichaje(
    fichaje_id: int,
    vinculacion: FichajeVinculacion,
    usuario=Depends(administrador),
):
    with conexion() as db:
        if not db.execute(
            "SELECT 1 FROM fichajes_ayudantes WHERE id = ?", (fichaje_id,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Fichaje no encontrado")
        if vinculacion.faena_id is not None and not db.execute(
            "SELECT 1 FROM faenas WHERE id = ?", (vinculacion.faena_id,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="La faena seleccionada no existe")
        db.execute(
            "UPDATE fichajes_ayudantes SET faena_id_vinculada = ?, "
            "estado_procesamiento = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (
                vinculacion.faena_id,
                "Vinculado" if vinculacion.faena_id is not None else "Pendiente",
                fichaje_id,
            ),
        )
        fila = db.execute(
            "SELECT * FROM fichajes_ayudantes WHERE id = ?", (fichaje_id,)
        ).fetchone()
    return dict(fila)


@app.get("/fichajes/{fichaje_id}/pago")
def consultar_pago_jornada(fichaje_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        fichaje = db.execute(
            "SELECT f.id, f.ayudante_id, f.fecha, f.obra, f.faena_id_vinculada, "
            "a.nombre FROM fichajes_ayudantes f JOIN ayudantes a "
            "ON a.id = f.ayudante_id WHERE f.id = ?",
            (fichaje_id,),
        ).fetchone()
        if not fichaje:
            raise HTTPException(status_code=404, detail="Fichaje no encontrado")
        if not fichaje["faena_id_vinculada"]:
            return {"fichaje_id": fichaje_id, "importe": 50, "forma_pago": "Efectivo", "estado_pago": "No pagado", "creado": False}
        for tabla in ("gastos_faenas_extras", "gasto_faenas"):
            try:
                gasto = db.execute(
                    f"SELECT id, importe, COALESCE(importe_pagado, pagado, 0) AS importe_pagado, forma_pago, estado_pago FROM {tabla} "
                    "WHERE faena_id = ? AND proveedor = ? AND fecha = ? "
                    "AND categoria = 'Ayudantes' ORDER BY id DESC LIMIT 1",
                    (fichaje["faena_id_vinculada"], fichaje["nombre"], fichaje["fecha"]),
                ).fetchone()
                if gasto:
                    estado = "Pagado" if gasto["importe_pagado"] >= gasto["importe"] and gasto["importe"] > 0 else "Parcial" if gasto["importe_pagado"] > 0 else "No pagado"
                    return {"fichaje_id": fichaje_id, "gasto_id": gasto["id"], "importe": gasto["importe"], "importe_pagado": gasto["importe_pagado"], "forma_pago": gasto["forma_pago"], "estado_pago": estado, "creado": True}
            except Exception:
                if DATABASE_URL:
                    db.db.rollback()
        return {"fichaje_id": fichaje_id, "importe": 50, "forma_pago": "Efectivo", "estado_pago": "No pagado", "creado": False}


@app.patch("/fichajes/{fichaje_id}/pago")
def actualizar_pago_jornada(fichaje_id: int, cambios: PagoJornadaUpdate, usuario=Depends(administrador)):
    with conexion() as db:
        estado_calculado = (
            "Pagado" if cambios.importe_pagado >= cambios.importe and cambios.importe > 0
            else "Parcial" if cambios.importe_pagado > 0 else "No pagado"
        )
        fichaje = db.execute(
            "SELECT f.ayudante_id, f.fecha, f.obra, f.faena_id_vinculada, a.nombre "
            "FROM fichajes_ayudantes f JOIN ayudantes a ON a.id = f.ayudante_id "
            "WHERE f.id = ?",
            (fichaje_id,),
        ).fetchone()
        if not fichaje or not fichaje["faena_id_vinculada"]:
            raise HTTPException(status_code=400, detail="El fichaje debe estar vinculado a una faena")
        parametros = (fichaje["faena_id_vinculada"], fichaje["nombre"], fichaje["fecha"])
        for tabla in ("gastos_faenas_extras", "gasto_faenas"):
            try:
                existente = db.execute(
                    f"SELECT id FROM {tabla} WHERE faena_id = ? AND proveedor = ? "
                    "AND fecha = ? AND categoria = 'Ayudantes' ORDER BY id DESC LIMIT 1",
                    parametros,
                ).fetchone()
                if existente:
                    db.execute(
                        f"UPDATE {tabla} SET importe = ?, bruto = ?, forma_pago = ?, "
                        "estado_pago = ?, pagado = ?, importe_pagado = ? WHERE id = ?",
                        (cambios.importe, cambios.importe, cambios.forma_pago,
                         estado_calculado, cambios.importe_pagado, cambios.importe_pagado, existente["id"]),
                    )
                else:
                    db.execute(
                        f"INSERT INTO {tabla} "
                        "(faena_id, concepto, proveedor, bruto, tipo_iva, iva, importe, "
                        "pagado, importe_pagado, forma_pago, fecha, estado_pago, categoria) "
                        "VALUES (?, ?, ?, ?, '0', 0, ?, ?, ?, ?, ?, ?, 'Ayudantes')",
                        (fichaje["faena_id_vinculada"], f"Día trabajado - {fichaje['obra']}",
                         fichaje["nombre"], cambios.importe, cambios.importe,
                         cambios.importe_pagado, cambios.importe_pagado,
                         cambios.forma_pago, fichaje["fecha"], estado_calculado),
                    )
                return {"fichaje_id": fichaje_id, "importe": cambios.importe, "importe_pagado": cambios.importe_pagado, "forma_pago": cambios.forma_pago, "estado_pago": estado_calculado}
            except Exception:
                if DATABASE_URL:
                    db.db.rollback()
        raise HTTPException(status_code=500, detail="No existe una tabla de gastos compatible")


@app.get("/liquidaciones")
def listar_liquidaciones(
    ayudante_id: Optional[int] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    usuario=Depends(administrador),
):
    condiciones = []
    parametros = []
    if ayudante_id is not None:
        condiciones.append("l.ayudante_id = ?")
        parametros.append(ayudante_id)
    if desde is not None:
        condiciones.append("l.hasta >= ?")
        parametros.append(desde.isoformat())
    if hasta is not None:
        condiciones.append("l.desde <= ?")
        parametros.append(hasta.isoformat())
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    dia_laborable = (
        "EXTRACT(DOW FROM f.fecha) NOT IN (0, 6)"
        if DATABASE_URL
        else "strftime('%w', f.fecha) NOT IN ('0', '6')"
    )
    with conexion() as db:
        filas = db.execute(
            f"""
            SELECT l.id, l.ayudante_id, a.nombre AS ayudante,
                   l.desde, l.hasta, l.precio_dia, l.importe_pagado,
                   l.fecha_pago, l.creado_en, l.actualizado_en,
                   COUNT(f.id) FILTER (WHERE {dia_laborable}) AS dias,
                   COUNT(f.id) FILTER (WHERE {dia_laborable}) * l.precio_dia AS total
            FROM liquidaciones l
            JOIN ayudantes a ON a.id = l.ayudante_id
            LEFT JOIN fichajes_ayudantes f
                ON f.ayudante_id = l.ayudante_id
               AND f.fecha BETWEEN l.desde AND l.hasta
               AND f.confirmado_ayudante = 1
            {where}
            GROUP BY l.id, a.nombre
            ORDER BY l.desde DESC, l.id DESC
            """,
            parametros,
        ).fetchall()
    resultado = []
    for fila in filas:
        datos = dict(fila)
        datos["total"] = round(float(datos["total"] or 0), 2)
        datos["importe_pagado"] = round(float(datos["importe_pagado"] or 0), 2)
        datos["pendiente"] = round(
            max(datos["total"] - datos["importe_pagado"], 0), 2
        )
        datos["estado"] = (
            "Pagado" if datos["pendiente"] == 0 and datos["total"] > 0
            else "Pendiente"
        )
        resultado.append(datos)
    return resultado


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


@app.patch("/liquidaciones/{liquidacion_id}")
def modificar_liquidacion(
    liquidacion_id: int,
    pago: PagoCreate,
    usuario=Depends(administrador),
):
    with conexion() as db:
        existente = db.execute(
            "SELECT 1 FROM liquidaciones WHERE id = ?", (liquidacion_id,)
        ).fetchone()
        if not existente:
            raise HTTPException(status_code=404, detail="Liquidación no encontrada")
        db.execute(
            """
            UPDATE liquidaciones
            SET ayudante_id = ?, desde = ?, hasta = ?, precio_dia = ?,
                importe_pagado = ?, fecha_pago = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                pago.ayudante_id, pago.desde.isoformat(), pago.hasta.isoformat(),
                pago.precio_dia, pago.importe_pagado,
                pago.fecha_pago.isoformat() if pago.fecha_pago else None,
                liquidacion_id,
            ),
        )
        fila = db.execute(
            "SELECT * FROM liquidaciones WHERE id = ?", (liquidacion_id,)
        ).fetchone()
    return dict(fila)


@app.delete("/liquidaciones/{liquidacion_id}")
def borrar_liquidacion(liquidacion_id: int, usuario=Depends(administrador)):
    with conexion() as db:
        cursor = db.execute(
            "DELETE FROM liquidaciones WHERE id = ?", (liquidacion_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Liquidación no encontrada")
    return {"eliminado": True, "id": liquidacion_id}
