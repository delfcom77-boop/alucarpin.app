import hashlib
import json
import logging
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)
MAXIMO = 1_000_000_000


class DatosMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=160)
    unidad: Literal["unidades", "botes", "cartuchos", "cajas", "metros", "rollos", "bolsas", "kg"] = "unidades"
    minimo: Decimal | None = Field(default=None, ge=0, le=1_000_000, decimal_places=3, allow_inf_nan=False)
    carpeta_id: UUID | None = None

    @field_validator("nombre")
    @classmethod
    def nombre_limpio(cls, valor):
        valor = " ".join(valor.split())
        if not valor:
            raise ValueError("Escribe el nombre del material.")
        return valor


class NuevoMaterial(DatosMaterial):
    id: UUID
    cantidad: Decimal = Field(default=Decimal(0), ge=0, le=1_000_000, decimal_places=3, allow_inf_nan=False)


class EditarMaterial(DatosMaterial):
    version: int = Field(gt=0)
    activo: bool = True


class Movimiento(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    tipo: Literal["entrada", "salida", "recuento"]
    cantidad: Decimal = Field(ge=0, le=1_000_000, decimal_places=3, allow_inf_nan=False)
    version: int | None = Field(default=None, gt=0)
    motivo: str = Field(default="", max_length=300)

    @field_validator("motivo")
    @classmethod
    def motivo_limpio(cls, valor):
        return valor.strip()


class NuevaCarpeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    nombre: str = Field(min_length=1, max_length=160)

    @field_validator("nombre")
    @classmethod
    def nombre_limpio(cls, valor):
        return DatosMaterial.nombre_limpio(valor)


class RenombrarCarpeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=160)
    nombre_anterior: str = Field(min_length=1, max_length=160)

    @field_validator("nombre")
    @classmethod
    def nombre_limpio(cls, valor):
        return DatosMaterial.nombre_limpio(valor)


class BorrarCarpeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmar_nombre: str = Field(min_length=1, max_length=160)


class BorrarMaterial(BorrarCarpeta):
    version: int = Field(gt=0)


def unidades(valor):
    return int(valor * 1000)


def cantidad_texto(valor):
    return format(Decimal(valor) / 1000, ".3f").rstrip("0").rstrip(".") if valor else "0"


def clave_nombre(nombre):
    return unicodedata.normalize("NFKC", nombre).casefold()


def firma(datos):
    return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def inicializar_almacen(db):
    db.execute("CREATE TABLE IF NOT EXISTS almacen_responsables (usuario_id BIGINT PRIMARY KEY)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS almacen_carpetas (id TEXT PRIMARY KEY, "
        "nombre TEXT NOT NULL, nombre_clave TEXT NOT NULL UNIQUE, creado_en TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS almacen_materiales ("
        "id TEXT PRIMARY KEY, nombre TEXT NOT NULL, nombre_clave TEXT NOT NULL UNIQUE, "
        "unidad TEXT NOT NULL, cantidad BIGINT NOT NULL CHECK(cantidad>=0 AND cantidad<=1000000000), "
        "minimo BIGINT CHECK(minimo>=0 AND minimo<=1000000000), activo INTEGER NOT NULL DEFAULT 1, "
        "version INTEGER NOT NULL DEFAULT 1, creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL, "
        "alta_firma TEXT NOT NULL, alta_usuario BIGINT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS almacen_movimientos ("
        "id TEXT PRIMARY KEY, material_id TEXT NOT NULL REFERENCES almacen_materiales(id), "
        "tipo TEXT NOT NULL, cantidad BIGINT NOT NULL, stock_anterior BIGINT NOT NULL, "
        "stock_resultante BIGINT NOT NULL, nombre TEXT NOT NULL, unidad TEXT NOT NULL, "
        "motivo TEXT NOT NULL, creado_en TEXT NOT NULL, solicitud_firma TEXT NOT NULL, "
        "usuario_id BIGINT NOT NULL)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_almacen_movimientos_fecha ON almacen_movimientos(creado_en, id)")
    if hasattr(db, "db"):
        db.execute("ALTER TABLE almacen_materiales ADD COLUMN IF NOT EXISTS carpeta_id TEXT REFERENCES almacen_carpetas(id)")
    else:
        columnas = {f[1] for f in db.execute("PRAGMA table_info(almacen_materiales)")}
        if "carpeta_id" not in columnas:
            db.execute("ALTER TABLE almacen_materiales ADD COLUMN carpeta_id TEXT REFERENCES almacen_carpetas(id)")
    if hasattr(db, "db"):
        db.execute("ALTER TABLE almacen_responsables ENABLE ROW LEVEL SECURITY")
        db.execute("ALTER TABLE almacen_carpetas ENABLE ROW LEVEL SECURITY")
        db.execute("ALTER TABLE almacen_materiales ENABLE ROW LEVEL SECURITY")
        db.execute("ALTER TABLE almacen_movimientos ENABLE ROW LEVEL SECURITY")


def publico_material(fila):
    return {
        "id": fila["id"], "nombre": fila["nombre"], "unidad": fila["unidad"],
        "cantidad": cantidad_texto(fila["cantidad"]),
        "minimo": cantidad_texto(fila["minimo"]) if fila["minimo"] is not None else None,
        "activo": bool(fila["activo"]), "version": fila["version"],
        "carpeta_id": fila["carpeta_id"],
        "situacion": "Agotado" if fila["cantidad"] == 0 else
        "Falta reponer" if fila["minimo"] is not None and fila["cantidad"] < fila["minimo"] else "Hay",
    }


def publico_movimiento(fila):
    return {**{c: fila[c] for c in (
        "id", "material_id", "tipo", "nombre", "unidad", "motivo", "creado_en",
    )}, **{c: cantidad_texto(fila[c]) for c in ("cantidad", "stock_anterior", "stock_resultante")}}


def crear_almacen(conexion, usuario_actual, administrador):
    @contextmanager
    def transaccion(escritura=False):
        try:
            db = conexion()
            try:
                with db:
                    if escritura and isinstance(db, sqlite3.Connection):
                        db.execute("BEGIN IMMEDIATE")
                    elif escritura and hasattr(db, "db"):
                        # Borrar una carpeta y sus variantes debe excluir entradas/salidas simultaneas.
                        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('almacen-escritura',0))")
                    yield db
            finally:
                if isinstance(db, sqlite3.Connection):
                    db.close()
        except (sqlite3.Error, psycopg.Error) as error:
            logger.exception("No se pudo completar la operacion de almacen.")
            raise HTTPException(503, "El almacen no esta disponible. No repitas la operacion con otra referencia; reintenta la misma solicitud.") from error

    def acceso(usuario=Depends(usuario_actual)):
        if usuario["rol"] not in ("administrador", "ayudante"):
            raise HTTPException(403, "No tienes acceso al almacen.")
        return usuario

    def puede_gestionar(usuario):
        if usuario["rol"] == "administrador":
            return True
        with transaccion() as db:
            return db.execute(
                "SELECT usuario_id FROM almacen_responsables WHERE usuario_id=?", (usuario["id"],),
            ).fetchone() is not None

    def responsable(usuario=Depends(acceso)):
        if not puede_gestionar(usuario):
            raise HTTPException(403, "Solo el administrador o un responsable del almacen puede modificar o eliminar.")
        return usuario

    def iniciar():
        with transaccion() as db:
            inicializar_almacen(db)

    def bloquear_solicitud(db, ident):
        if hasattr(db, "db"):
            db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", (ident,))

    def material(db, ident, bloquear=False):
        fila = db.execute(
            "SELECT * FROM almacen_materiales WHERE id=?"
            + (" FOR UPDATE" if bloquear and hasattr(db, "db") else ""), (str(ident),),
        ).fetchone()
        if not fila:
            raise HTTPException(404, "El material no existe.")
        return fila

    def clave_variante(nombre, carpeta):
        return carpeta + ":" + clave_nombre(nombre) if carpeta else clave_nombre(nombre)

    def nombre_completo(db, nombre, carpeta):
        if not carpeta:
            return nombre
        fila = db.execute("SELECT nombre FROM almacen_carpetas WHERE id=?", (carpeta,)).fetchone()
        if not fila:
            raise HTTPException(404, "La carpeta no existe.")
        return fila["nombre"] + " / " + nombre

    def comprobar_nombre(db, nombre, ident, carpeta=None):
        fila = db.execute(
            "SELECT id FROM almacen_materiales WHERE nombre_clave=?", (clave_variante(nombre, carpeta),),
        ).fetchone()
        if fila and fila["id"] != ident:
            raise HTTPException(409, "Ya existe ese material, tambien puede estar desactivado. Buscalo antes de crear otro.")

    router = APIRouter(dependencies=[Depends(acceso)], on_startup=[iniciar])

    @router.get("/almacen/permisos")
    def permisos(usuario=Depends(acceso)):
        return {"gestionar": puede_gestionar(usuario)}

    @router.get("/almacen/carpetas")
    def carpetas():
        with transaccion() as db:
            return [dict(f) for f in db.execute(
                "SELECT id,nombre FROM almacen_carpetas ORDER BY nombre_clave,id"
            ).fetchall()]

    @router.post("/almacen/carpetas", status_code=201)
    def crear_carpeta(datos: NuevaCarpeta):
        ident, clave = str(datos.id), clave_nombre(datos.nombre)
        with transaccion(True) as db:
            bloquear_solicitud(db, "almacen-carpeta:" + ident)
            bloquear_solicitud(db, "almacen-carpeta-nombre:" + clave)
            anterior = db.execute("SELECT id,nombre FROM almacen_carpetas WHERE id=?", (ident,)).fetchone()
            if anterior:
                if anterior["nombre"] != datos.nombre:
                    raise HTTPException(409, "La referencia ya se utilizo para otra carpeta.")
                return dict(anterior)
            if db.execute("SELECT id FROM almacen_carpetas WHERE nombre_clave=?", (clave,)).fetchone():
                raise HTTPException(409, "Ya existe esa carpeta. Abrela para anadir variantes.")
            db.execute(
                "INSERT INTO almacen_carpetas(id,nombre,nombre_clave,creado_en) VALUES(?,?,?,?)",
                (ident, datos.nombre, clave, datetime.now(timezone.utc).isoformat()),
            )
            return {"id": ident, "nombre": datos.nombre}

    @router.put("/almacen/carpetas/{ident}")
    def renombrar_carpeta(ident: UUID, datos: RenombrarCarpeta, usuario=Depends(responsable)):
        ident = str(ident)
        with transaccion(True) as db:
            fila = db.execute("SELECT id,nombre FROM almacen_carpetas WHERE id=?", (ident,)).fetchone()
            if not fila:
                raise HTTPException(404, "La carpeta ya no existe.")
            if fila["nombre"] == datos.nombre:
                return dict(fila)
            if fila["nombre"] != datos.nombre_anterior:
                raise HTTPException(409, "La carpeta cambio de nombre. Actualiza antes de modificarla.")
            clave = clave_nombre(datos.nombre)
            otra = db.execute("SELECT id FROM almacen_carpetas WHERE nombre_clave=?", (clave,)).fetchone()
            if otra and otra["id"] != ident:
                raise HTTPException(409, "Ya existe otra carpeta con ese nombre.")
            db.execute("UPDATE almacen_carpetas SET nombre=?,nombre_clave=? WHERE id=?", (datos.nombre, clave, ident))
            return {"id": ident, "nombre": datos.nombre}

    @router.delete("/almacen/carpetas/{ident}")
    def borrar_carpeta(ident: UUID, datos: BorrarCarpeta, usuario=Depends(responsable)):
        ident = str(ident)
        with transaccion(True) as db:
            fila = db.execute("SELECT nombre FROM almacen_carpetas WHERE id=?", (ident,)).fetchone()
            if not fila:
                return {"eliminada": True, "id": ident}
            if datos.confirmar_nombre != fila["nombre"]:
                raise HTTPException(409, "Escribe el nombre exacto de la carpeta para confirmar. Si ha cambiado, actualiza el listado.")
            db.execute(
                "DELETE FROM almacen_movimientos WHERE material_id IN "
                "(SELECT id FROM almacen_materiales WHERE carpeta_id=?)", (ident,),
            )
            db.execute("DELETE FROM almacen_materiales WHERE carpeta_id=?", (ident,))
            db.execute("DELETE FROM almacen_carpetas WHERE id=?", (ident,))
            return {"eliminada": True, "id": ident}

    @router.get("/almacen/materiales")
    def listar():
        with transaccion() as db:
            return [publico_material(f) for f in db.execute(
                "SELECT * FROM almacen_materiales ORDER BY nombre_clave,id"
            ).fetchall()]

    @router.post("/almacen/materiales", status_code=201)
    def crear(datos: NuevoMaterial, usuario=Depends(acceso)):
        ident = str(datos.id)
        cantidad = unidades(datos.cantidad)
        minimo = unidades(datos.minimo) if datos.minimo is not None else None
        carpeta = str(datos.carpeta_id) if datos.carpeta_id else None
        contenido_alta = {"nombre": datos.nombre, "unidad": datos.unidad, "cantidad": cantidad, "minimo": minimo}
        if carpeta:
            contenido_alta["carpeta_id"] = carpeta
        contenido = firma(contenido_alta)
        sello = datetime.now(timezone.utc).isoformat()
        with transaccion(True) as db:
            bloquear_solicitud(db, ident)
            # Serializa nombres iguales incluso cuando las altas usan UUID distintos.
            bloquear_solicitud(db, "almacen-nombre:" + clave_variante(datos.nombre, carpeta))
            anterior = db.execute("SELECT * FROM almacen_materiales WHERE id=?", (ident,)).fetchone()
            if anterior:
                if anterior["alta_firma"] != contenido or anterior["alta_usuario"] != usuario["id"]:
                    raise HTTPException(409, "Esta referencia ya se utilizo para otra alta.")
                return publico_material(anterior)
            nombre = nombre_completo(db, datos.nombre, carpeta)
            comprobar_nombre(db, datos.nombre, ident, carpeta)
            db.execute(
                "INSERT INTO almacen_materiales "
                "(id,nombre,nombre_clave,unidad,cantidad,minimo,activo,version,creado_en,actualizado_en,alta_firma,alta_usuario,carpeta_id) "
                "VALUES (?,?,?,?,?,?,1,1,?,?,?,?,?)",
                (ident, datos.nombre, clave_variante(datos.nombre, carpeta), datos.unidad, cantidad, minimo,
                 sello, sello, contenido, usuario["id"], carpeta),
            )
            db.execute(
                "INSERT INTO almacen_movimientos "
                "(id,material_id,tipo,cantidad,stock_anterior,stock_resultante,nombre,unidad,motivo,creado_en,solicitud_firma,usuario_id) "
                "VALUES (?,?, 'inicial',?,0,?,?,?,'',?,?,?)",
                (ident, ident, cantidad, cantidad, nombre, datos.unidad, sello, contenido, usuario["id"]),
            )
            return publico_material(material(db, ident))

    @router.put("/almacen/materiales/{ident}")
    def editar(ident: UUID, datos: EditarMaterial, usuario=Depends(responsable)):
        ident = str(ident)
        with transaccion(True) as db:
            fila = material(db, ident, True)
            if fila["version"] != datos.version:
                raise HTTPException(409, "El material cambio. Actualiza el listado antes de editar.")
            if datos.unidad != fila["unidad"]:
                raise HTTPException(422, "La unidad no se cambia: crea otro material para no mezclar cajas con unidades.")
            carpeta = (str(datos.carpeta_id) if datos.carpeta_id else None) if "carpeta_id" in datos.model_fields_set else fila["carpeta_id"]
            nombre_completo(db, datos.nombre, carpeta)
            bloquear_solicitud(db, "almacen-nombre:" + clave_variante(datos.nombre, carpeta))
            comprobar_nombre(db, datos.nombre, ident, carpeta)
            db.execute(
                "UPDATE almacen_materiales SET nombre=?,nombre_clave=?,minimo=?,activo=?,"
                "version=version+1,actualizado_en=?,carpeta_id=? WHERE id=?",
                (datos.nombre, clave_variante(datos.nombre, carpeta), unidades(datos.minimo) if datos.minimo is not None else None,
                 int(datos.activo), datetime.now(timezone.utc).isoformat(), carpeta, ident),
            )
            return publico_material(material(db, ident))

    @router.delete("/almacen/materiales/{ident}")
    def borrar_material(ident: UUID, datos: BorrarMaterial, usuario=Depends(responsable)):
        ident = str(ident)
        with transaccion(True) as db:
            fila = db.execute("SELECT nombre,version FROM almacen_materiales WHERE id=?", (ident,)).fetchone()
            if not fila:
                return {"eliminado": True, "id": ident}
            if datos.confirmar_nombre != fila["nombre"] or datos.version != fila["version"]:
                raise HTTPException(409, "El nombre o el stock del material cambio. Actualiza el listado y confirma de nuevo.")
            db.execute("DELETE FROM almacen_movimientos WHERE material_id=?", (ident,))
            db.execute("DELETE FROM almacen_materiales WHERE id=?", (ident,))
            return {"eliminado": True, "id": ident}

    @router.post("/almacen/materiales/{ident}/movimientos", status_code=201)
    def mover(ident: UUID, datos: Movimiento, usuario=Depends(acceso)):
        ident, solicitud = str(ident), str(datos.id)
        cantidad = unidades(datos.cantidad)
        if datos.tipo != "recuento" and cantidad == 0:
            raise HTTPException(422, "La entrada o salida debe ser mayor que cero.")
        if datos.tipo == "recuento" and (datos.version is None or not datos.motivo):
            raise HTTPException(422, "Para corregir el stock indica el motivo y actualiza la cantidad actual.")
        contenido = firma({"material": ident, "tipo": datos.tipo, "cantidad": cantidad, "motivo": datos.motivo, "version": datos.version})
        with transaccion(True) as db:
            bloquear_solicitud(db, solicitud)
            anterior = db.execute("SELECT * FROM almacen_movimientos WHERE id=?", (solicitud,)).fetchone()
            if anterior:
                if anterior["solicitud_firma"] != contenido or anterior["usuario_id"] != usuario["id"]:
                    raise HTTPException(409, "Esta referencia ya se uso en otro movimiento.")
                return publico_movimiento(anterior)
            fila = material(db, ident, True)
            if not fila["activo"]:
                raise HTTPException(409, "El material esta desactivado.")
            stock = fila["cantidad"]
            nuevo = stock + cantidad if datos.tipo == "entrada" else stock - cantidad if datos.tipo == "salida" else cantidad
            if nuevo < 0:
                raise HTTPException(409, "No hay suficiente material. Actualiza el listado y revisa la cantidad.")
            if nuevo > MAXIMO:
                raise HTTPException(422, "La cantidad total supera el limite de un millon.")
            if datos.tipo == "recuento" and datos.version != fila["version"]:
                raise HTTPException(409, "El stock cambio mientras contabas. Actualiza antes de corregirlo.")
            sello = datetime.now(timezone.utc).isoformat()
            db.execute(
                "UPDATE almacen_materiales SET cantidad=?,version=version+1,actualizado_en=? WHERE id=?",
                (nuevo, sello, ident),
            )
            db.execute(
                "INSERT INTO almacen_movimientos "
                "(id,material_id,tipo,cantidad,stock_anterior,stock_resultante,nombre,unidad,motivo,creado_en,solicitud_firma,usuario_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (solicitud, ident, datos.tipo, cantidad, stock, nuevo, nombre_completo(db, fila["nombre"], fila["carpeta_id"]), fila["unidad"],
                 datos.motivo, sello, contenido, usuario["id"]),
            )
            return publico_movimiento(db.execute("SELECT * FROM almacen_movimientos WHERE id=?", (solicitud,)).fetchone())

    @router.get("/almacen/movimientos")
    def historial(material_id: UUID | None = None, limite: int = Query(50, ge=1, le=100),
                  antes: str | None = Query(None, max_length=100), carpeta_id: UUID | None = None):
        with transaccion() as db:
            condiciones, parametros = [], []
            if material_id:
                condiciones.append("material_id=?")
                parametros.append(str(material_id))
            if carpeta_id:
                condiciones.append("material_id IN (SELECT id FROM almacen_materiales WHERE carpeta_id=?)")
                parametros.append(str(carpeta_id))
            if antes:
                condiciones.append("(creado_en || '|' || id) < ?")
                parametros.append(antes)
            where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
            filas = db.execute(
                "SELECT * FROM almacen_movimientos" + where
                + " ORDER BY creado_en DESC,id DESC LIMIT ?", tuple(parametros) + (limite + 1,),
            ).fetchall()
            visibles = filas[:limite]
            cursor = visibles[-1]["creado_en"] + "|" + visibles[-1]["id"] if len(filas) > limite else None
            return {"movimientos": [publico_movimiento(f) for f in visibles], "siguiente": cursor}

    return router
