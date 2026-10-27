import logging
import sqlite3
from contextlib import contextmanager
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tareas import (
    TareaInvalida, TareaModificada, guardar_tarea, inicializar_tareas,
    listar_tareas, obtener_tarea,
)

logger = logging.getLogger(__name__)


class DatosTarea(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: str = Field(min_length=1, max_length=240)
    tipo: Literal["Otro", "Llamada", "Presupuesto", "Material", "Visita"] = "Otro"
    cliente: str = Field(default="", max_length=160)
    obra: str = Field(default="", max_length=300)
    notas: str = Field(default="", max_length=4000)
    fecha_prevista: str = Field(default="", max_length=10)
    prioridad: Literal["Normal", "Alta"] = "Normal"
    estado: Literal["Pendiente", "Hecha"] = "Pendiente"


class NuevaTarea(DatosTarea):
    id: UUID


class CambioTarea(DatosTarea):
    version: int = Field(gt=0)


def crear_tareas(conexion, administrador):
    @contextmanager
    def transaccion():
        try:
            db = conexion()
            try:
                with db:
                    yield db
            finally:
                if isinstance(db, sqlite3.Connection):
                    db.close()
        except TareaInvalida as error:
            raise HTTPException(422, str(error)) from error
        except TareaModificada as error:
            raise HTTPException(409, str(error)) from error
        except (sqlite3.Error, psycopg.Error) as error:
            logger.exception("No se pudo completar la operacion de tareas.")
            raise HTTPException(503, "Tareas no esta disponible. Recarga antes de reintentar.") from error

    def iniciar():
        with transaccion() as db:
            inicializar_tareas(db)

    router = APIRouter(dependencies=[Depends(administrador)], on_startup=[iniciar])

    @router.get("/tareas")
    def listar():
        with transaccion() as db:
            return listar_tareas(db)

    @router.post("/tareas", status_code=201)
    def crear(datos: NuevaTarea):
        with transaccion() as db:
            return guardar_tarea(db, datos.model_dump(exclude={"id"}), str(datos.id))

    @router.put("/tareas/{ident}")
    def modificar(ident: UUID, datos: CambioTarea):
        with transaccion() as db:
            if not obtener_tarea(db, str(ident)):
                raise HTTPException(404, "La tarea no existe.")
            return guardar_tarea(db, datos.model_dump(exclude={"version"}), str(ident), datos.version)

    return router
