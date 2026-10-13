import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

class RegistroDia(BaseModel):
    solicitud_id: UUID
    fecha: date
    origen: Literal["faena", "presupuesto", "propio"] | None = None
    origen_id: int | None = Field(default=None, gt=0)
    tipo: Literal["faena", "presupuesto", "reparacion"]
    cliente: str = Field(default="", max_length=160)
    obra: str = Field(default="", max_length=300)
    ubicacion: str = Field(default="", max_length=300)
    poblacion: str = Field(default="", max_length=160)
    observaciones: str = Field(default="", max_length=2000)
    num_presupuesto: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validar(self):
        if (self.origen is None) != (self.origen_id is None):
            raise ValueError("Selecciona un trabajo existente completo o crea uno nuevo.")
        if self.origen is None and (not self.cliente.strip() or not self.obra.strip()):
            raise ValueError("Cliente y obra son obligatorios para un trabajo nuevo.")
        if self.origen and self.origen != {
            "faena": "faena", "presupuesto": "presupuesto", "reparacion": "propio"
        }[self.tipo]:
            raise ValueError("El trabajo seleccionado no corresponde al tipo indicado.")
        if self.fecha > date.today():
            raise ValueError("Un día trabajado no puede tener una fecha futura. Usa Agenda para planificar.")
        return self


def crear_diario(conexion, administrador):
    @contextmanager
    def conexion_diario():
        try:
            with conexion() as db:
                yield db
        except (sqlite3.Error, psycopg.Error) as error:
            logger.error("No se pudo completar la operación del diario de trabajo.")
            raise HTTPException(503, "El diario no está disponible. No se ha guardado una parte del registro; reintenta la misma solicitud.") from error

    def publico(fila):
        return {campo: fila[campo] for campo in (
            "solicitud_id", "origen", "origen_id", "fecha", "tipo", "cliente",
            "obra", "ubicacion", "poblacion", "observaciones", "creado_en"
        )}

    def iniciar():
        with conexion() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS diario_trabajo ("
                "solicitud_id TEXT PRIMARY KEY, contenido_hash TEXT NOT NULL, usuario_id BIGINT NOT NULL, "
                "origen TEXT NOT NULL, origen_id BIGINT NOT NULL, fecha DATE NOT NULL, "
                "tipo TEXT NOT NULL, cliente TEXT NOT NULL, obra TEXT NOT NULL, "
                "ubicacion TEXT NOT NULL, poblacion TEXT NOT NULL, observaciones TEXT NOT NULL, "
                "creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "UNIQUE (origen, origen_id, fecha))"
            )

    router = APIRouter(dependencies=[Depends(administrador)], on_startup=[iniciar])

    @router.get("/mis-dias")
    def listar():
        with conexion_diario() as db:
            dias = [dict(f) for f in db.execute(
                "SELECT j.fecha, 'faena' AS origen, f.id AS origen_id, 'faena' AS tipo, "
                "f.cliente, f.obra, f.ubicacion, f.poblacion FROM jornadas_faenas j "
                "JOIN faenas f ON f.id = j.faena_id"
            ).fetchall()]
            dias += [dict(f) for f in db.execute(
                "SELECT j.fecha, 'presupuesto' AS origen, p.id AS origen_id, 'presupuesto' AS tipo, "
                "p.cliente, 'Presupuesto ' || coalesce(p.num_presupuesto, '') AS obra, "
                "'' AS ubicacion, '' AS poblacion FROM jornadas_propias j "
                "JOIN presupuestos p ON p.id = j.presupuesto_id"
            ).fetchall()]
            dias += [dict(f) for f in db.execute(
                "SELECT j.fecha, 'propio' AS origen, t.id AS origen_id, t.tipo, "
                "t.cliente, t.obra, t.ubicacion, t.poblacion FROM jornadas_propias j "
                "JOIN trabajos_propios t ON t.id = j.trabajo_id"
            ).fetchall()]
            detalles = {
                (f["origen"], f["origen_id"], str(f["fecha"])): dict(f)
                for f in db.execute("SELECT * FROM diario_trabajo").fetchall()
            }
        for dia in dias:
            dia["fecha"] = str(dia["fecha"])
            detalle = detalles.get((dia["origen"], dia["origen_id"], dia["fecha"]))
            for campo in ("cliente", "obra", "ubicacion", "poblacion", "observaciones", "creado_en"):
                dia[campo] = detalle[campo] if detalle else dia.get(campo)
        return sorted(dias, key=lambda d: (d["fecha"], d["origen"], d["origen_id"]), reverse=True)

    @router.post("/registro-dia", status_code=201)
    def registrar(datos: RegistroDia, usuario=Depends(administrador)):
        solicitud = str(datos.solicitud_id)
        contenido = hashlib.sha256(json.dumps(
            datos.model_dump(mode="json"), sort_keys=True, ensure_ascii=True
        ).encode()).hexdigest()
        with conexion_diario() as db:
            if hasattr(db, "db"):
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (solicitud,))
            else:
                db.execute("BEGIN IMMEDIATE")
            anterior = db.execute(
                "SELECT * FROM diario_trabajo WHERE solicitud_id = ?", (solicitud,)
            ).fetchone()
            if anterior:
                if anterior["contenido_hash"] != contenido or anterior["usuario_id"] != usuario["id"]:
                    raise HTTPException(409, "La solicitud ya se utilizó para otro registro.")
                return publico(anterior)
            tipo = datos.tipo
            origen = datos.origen or {"faena": "faena", "presupuesto": "presupuesto", "reparacion": "propio"}[tipo]
            ident = datos.origen_id
            tabla = {"faena": "faenas", "presupuesto": "presupuestos", "propio": "trabajos_propios"}[origen]
            if ident:
                trabajo = db.execute(f"SELECT * FROM {tabla} WHERE id = ?", (ident,)).fetchone()
                if not trabajo or (origen == "propio" and trabajo["tipo"] != "reparacion"):
                    raise HTTPException(404, "El trabajo seleccionado no existe.")
                cliente = trabajo["cliente"]
                obra = datos.obra.strip() or (
                    f"Presupuesto {trabajo['num_presupuesto'] or ''}" if origen == "presupuesto"
                    else trabajo["obra"] or "Sin nombre de obra"
                )
                ubicacion = datos.ubicacion.strip() or (trabajo["ubicacion"] or "" if origen != "presupuesto" else "")
                poblacion = datos.poblacion.strip() or (trabajo["poblacion"] or "" if origen != "presupuesto" else "")
            else:
                cliente, obra = datos.cliente.strip(), datos.obra.strip()
                ubicacion, poblacion = datos.ubicacion.strip(), datos.poblacion.strip()
                fecha = datos.fecha.isoformat()
                if origen == "faena":
                    trabajo = db.execute(
                        "INSERT INTO faenas (cliente, obra, fecha, ubicacion, poblacion, precio, ayudantes, estado_revision) "
                        "VALUES (?, ?, ?, ?, ?, 0, 'No', 'Pendiente de revisar') RETURNING id",
                        (cliente, obra, fecha, ubicacion, poblacion),
                    ).fetchone()
                elif origen == "presupuesto":
                    numero = (datos.num_presupuesto or "").strip() or None
                    if numero and hasattr(db, "db"):
                        db.execute(
                            "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
                            (f"diario-presupuesto:{numero}",),
                        )
                    if numero and db.execute("SELECT id FROM presupuestos WHERE num_presupuesto = ?", (numero,)).fetchone():
                        raise HTTPException(409, "Ese presupuesto ya existe. Selecciónalo como trabajo existente.")
                    trabajo = db.execute(
                        "INSERT INTO presupuestos (cliente, num_presupuesto, fecha, bruto, iva, total_iva, "
                        "presupuesto_iva, efectivo, estado, presupuesto_final, estado_revision) "
                        "VALUES (?, ?, ?, 0, 0, 0, 0, 0, 'Presupuesto', 0, 'Pendiente de revisar') RETURNING id",
                        (cliente, numero, fecha),
                    ).fetchone()
                else:
                    trabajo = db.execute(
                        "INSERT INTO trabajos_propios (tipo, fecha_inicio, cliente, obra, ubicacion, poblacion, "
                        "observaciones, estado_revision) VALUES ('reparacion', ?, ?, ?, ?, ?, ?, "
                        "'Pendiente de revisar') RETURNING id",
                        (fecha, cliente, obra, ubicacion, poblacion, datos.observaciones.strip()),
                    ).fetchone()
                ident = trabajo["id"]
            tabla_dias, columna = (
                ("jornadas_faenas", "faena_id") if origen == "faena" else
                ("jornadas_propias", "presupuesto_id" if origen == "presupuesto" else "trabajo_id")
            )
            dia = db.execute(
                f"INSERT INTO {tabla_dias} ({columna}, fecha) VALUES (?, ?) "
                f"ON CONFLICT ({columna}, fecha) DO NOTHING RETURNING fecha",
                (ident, datos.fecha.isoformat()),
            ).fetchone()
            if not dia:
                raise HTTPException(409, "Ya has registrado ese día en este trabajo. No se ha duplicado.")
            db.execute(
                "INSERT INTO diario_trabajo (solicitud_id, contenido_hash, usuario_id, origen, origen_id, fecha, "
                "tipo, cliente, obra, ubicacion, poblacion, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (solicitud, contenido, usuario["id"], origen, ident, datos.fecha.isoformat(),
                 tipo, cliente, obra, ubicacion, poblacion, datos.observaciones.strip()),
            )
            return publico(db.execute("SELECT * FROM diario_trabajo WHERE solicitud_id = ?", (solicitud,)).fetchone())

    return router
