"""Uso: python -m sonoraplay.catalogo [--entrada data/raw/dataset.csv] [--salida data/processed]"""

import argparse
from pathlib import Path

from sonoraplay.catalogo import asignar_titulares, limpiar_f1
from sonoraplay.config import N_TITULARES, SEMILLA_CATALOGO


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m sonoraplay.catalogo", description="Catálogo F1")
    p.add_argument("--entrada", type=Path, default=Path("data/raw/dataset.csv"))
    p.add_argument("--salida", type=Path, default=Path("data/processed"))
    p.add_argument("--titulares", type=int, default=N_TITULARES)
    p.add_argument("--semilla", type=int, default=SEMILLA_CATALOGO)
    a = p.parse_args(argv)
    if not a.entrada.exists():
        p.error(f"No existe {a.entrada}. Descarga el CSV de F1 (ver README).")

    limpiar_f1.main(a.entrada, a.salida)
    asignar_titulares.main(a.salida, a.titulares, a.semilla)
    print(f"Catálogo F1 escrito en {a.salida} (semilla={a.semilla})")


if __name__ == "__main__":
    main()
