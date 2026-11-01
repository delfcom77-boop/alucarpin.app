import logging
import sqlite3
from datetime import date
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from costes_ayudantes import consultar_costes, destinos_costes, guardar_imputacion, inicializar_imputaciones

logger = logging.getLogger(__name__)


class ImputacionDia(BaseModel):
    destino: Literal["alucarpin", "faena", "presupuesto", "propio"]
    id: int | None = Field(default=None, gt=0)
    version: int = Field(ge=0)


def crear_imputaciones(conexion, administrador, postgres=False):
    def iniciar():
        with conexion() as db:
            inicializar_imputaciones(db)
            if postgres:
                db.execute("ALTER TABLE imputaciones_ayudantes ENABLE ROW LEVEL SECURITY")

    router = APIRouter(dependencies=[Depends(administrador)], on_startup=[iniciar])

    @router.get("/costes-ayudantes")
    def consultar(fecha: date):
        try:
            with conexion() as db:
                costes, _ = consultar_costes(db, postgres)
                costes = [c for c in costes if c["fecha"] == fecha.isoformat()]
                destinos = destinos_costes(db)
            return {"fecha": fecha, "costes": costes, "destinos": destinos}
        except (sqlite3.Error, psycopg.Error) as error:
            logger.exception("No se pudieron consultar los costes diarios.")
            raise HTTPException(503, "No se pudieron consultar los costes del día.") from error

    @router.put("/costes-ayudantes/{ayudante_id}/{fecha}")
    def guardar(ayudante_id: int, fecha: date, datos: ImputacionDia):
        try:
            with conexion() as db:
                if not postgres:
                    db.execute("BEGIN IMMEDIATE")
                return guardar_imputacion(db, ayudante_id, fecha, datos.destino, datos.id, datos.version, postgres)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        except (sqlite3.Error, psycopg.Error) as error:
            logger.exception("No se pudo guardar el destino del coste diario.")
            raise HTTPException(503, "No se ha confirmado el destino del gasto. Actualiza y revisa antes de reintentar.") from error

    return router
