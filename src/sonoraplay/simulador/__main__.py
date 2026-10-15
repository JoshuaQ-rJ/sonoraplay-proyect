"""Uso: python -m sonoraplay.simulador [--eventos N] [--semilla N] [--salida F] [--datos-f1 DIR]"""

import argparse
from pathlib import Path

from sqlalchemy import create_engine

from sonoraplay.config import SimuladorConfig, database_url
from sonoraplay.simulador.f2_minimo import ejecutar


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="python -m sonoraplay.simulador", description="Simulador F2 mínimo (EG-19)"
    )
    p.add_argument("--eventos", type=int, default=SimuladorConfig.eventos)
    p.add_argument("--semilla", type=int, default=SimuladorConfig.semilla)
    p.add_argument("--salida", type=Path, default=Path("data/processed/eventos_f2.jsonl"))
    p.add_argument("--datos-f1", type=Path, default=Path("data/processed"))
    a = p.parse_args(argv)
    try:
        cfg = SimuladorConfig(semilla=a.semilla, eventos=a.eventos)
    except ValueError as e:
        p.error(str(e))

    n = ejecutar(create_engine(database_url()), a.datos_f1, a.salida, cfg)
    print(f"{n} eventos F2 escritos en {a.salida} (semilla={cfg.semilla}, día={cfg.fecha_base})")


if __name__ == "__main__":
    main()
