"""Distribuye el calculo compartido antes de compilar el programa Windows."""

import argparse
import hashlib
from pathlib import Path
import shutil


def distribuir(escritorio):
    if not (escritorio / "AlucarpinSamitier.spec").is_file():
        raise ValueError("El destino no contiene el proyecto de escritorio.")
    origen = Path(__file__).resolve().parents[1] / "resumen_economico.py"
    destino = escritorio / origen.name
    shutil.copy2(origen, destino)
    if hashlib.sha256(origen.read_bytes()).digest() != hashlib.sha256(destino.read_bytes()).digest():
        raise RuntimeError("El modulo distribuido no coincide con el origen.")
    print("Resumen economico distribuido y verificado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("escritorio", type=Path)
    distribuir(parser.parse_args().escritorio)
