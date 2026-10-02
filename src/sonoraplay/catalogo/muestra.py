"""Muestra pequeña de F1 para las pruebas (data/samples/f1_muestra.csv, sí se sube).

Uso: python -m sonoraplay.catalogo.muestra [--entrada data/raw/dataset.csv]

Incluye a propósito los casos que prueban las reglas de EG-12: pistas en 2+ géneros
(con y sin empate de popularidad), un duplicado exacto, la fila inválida y dos pistas
con mismo nombre y artista pero distinto track_id. El resto se completa al azar (semilla 42).
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd

from sonoraplay.config import SEMILLA_CATALOGO

TAMANO = 200


def construir_muestra(
    crudo: pd.DataFrame, tamano: int = TAMANO, semilla: int = SEMILLA_CATALOGO
) -> pd.DataFrame:
    rng = random.Random(semilla)
    filas = crudo.dropna(subset=["track_id"])
    por_track = filas.groupby("track_id")
    n_generos = por_track["track_genre"].nunique()
    n_pop = por_track["popularity"].nunique()
    n_filas = por_track.size()

    def elegir(ids: pd.Index, k: int) -> list[str]:
        return rng.sample(sorted(ids), k)

    multi = n_generos[n_generos >= 2].index
    tracks = (
        elegir(multi[n_pop[multi] == 1], 6)  # empate de popularidad
        + elegir(multi[n_pop[multi] > 1], 3)  # popularidad distinta
        + elegir(n_generos[n_generos >= 4].index, 2)
        + elegir(n_filas[n_filas > n_generos].index, 1)  # duplicado exacto (mismo género)
    )
    unicos = n_filas[n_filas == 1].index
    validas = filas[filas["track_id"].isin(unicos)].dropna(subset=["artists", "track_name"])
    homonimas = validas.groupby(["track_name", "artists"])["track_id"].nunique()
    nombre, artistas = rng.choice(sorted(homonimas[homonimas >= 2].index))
    par = validas[(validas["track_name"] == nombre) & (validas["artists"] == artistas)]
    tracks += sorted(par["track_id"])[:2]

    invalidas = crudo[
        crudo[["track_id", "artists", "track_name"]].isna().any(axis=1)
        | (crudo["duration_ms"] <= 0)
    ]
    base = pd.concat([crudo[crudo["track_id"].isin(tracks)], invalidas])
    resto = crudo.drop(base.index)
    resto = resto[resto["track_id"].isin(unicos)]
    relleno = resto.loc[rng.sample(sorted(resto.index), max(tamano - len(base), 0))]
    return pd.concat([base, relleno]).sort_index()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m sonoraplay.catalogo.muestra")
    p.add_argument("--entrada", type=Path, default=Path("data/raw/dataset.csv"))
    p.add_argument("--salida", type=Path, default=Path("data/samples/f1_muestra.csv"))
    a = p.parse_args(argv)
    crudo = pd.read_csv(a.entrada, index_col=0)
    muestra = construir_muestra(crudo)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    muestra.to_csv(a.salida)  # conserva la columna índice, igual que el CSV crudo
    print(f"{len(muestra)} filas escritas en {a.salida}")


if __name__ == "__main__":
    main()
