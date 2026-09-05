import os
import sqlite3
import sys
from pathlib import Path


def ruta_base_datos():
    configurada = os.getenv("ALUCARPIN_DATABASE")
    if configurada:
        return Path(configurada).expanduser().resolve()

    if getattr(sys, "frozen", False):
        carpeta = Path(sys.executable).resolve().parent
    else:
        carpeta = Path(__file__).resolve().parent
    return carpeta / "empresa.db"


def conectar():
    return sqlite3.connect(ruta_base_datos(), timeout=30)
