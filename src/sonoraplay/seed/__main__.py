"""Uso: python -m sonoraplay.seed --modo dev|completo [--semilla N] [--tasa-defectos 0.02]"""

import argparse
import os
import time

from sqlalchemy import create_engine

from sonoraplay.config import VOLUMENES, SeedConfig, database_url
from sonoraplay.seed.f3_suscripciones import ejecutar


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="python -m sonoraplay.seed", description="Seed reproducible F3"
    )
    p.add_argument("--modo", choices=VOLUMENES, default="dev")
    p.add_argument("--semilla", type=int, default=int(os.environ.get("SEED", "42")))
    p.add_argument("--usuarios", type=int, help="Sobrescribe el volumen del modo")
    p.add_argument(
        "--tasa-defectos", type=float, default=float(os.environ.get("TASA_DEFECTOS", "0.02"))
    )
    a = p.parse_args(argv)
    if not 0 <= a.tasa_defectos <= 1:
        p.error("--tasa-defectos debe estar entre 0 y 1")

    cfg = SeedConfig(
        semilla=a.semilla, usuarios=a.usuarios or VOLUMENES[a.modo], tasa_defectos=a.tasa_defectos
    )
    engine = create_engine(database_url())
    t0 = time.perf_counter()
    for tabla, n in ejecutar(engine, cfg).items():
        print(f"{tabla:<20}{n:>12,}")
    print(f"Seed F3 terminado en {time.perf_counter() - t0:.1f} s (semilla={cfg.semilla})")


if __name__ == "__main__":
    main()
