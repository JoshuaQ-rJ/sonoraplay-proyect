"""Catálogo F1 limpio: una fila por track_id y tabla puente de géneros.

HU 03 · EG-12. Decisión y cifras en docs/adr/0003-duplicados-f1.md.
Funciones puras (DataFrame entra, DataFrame sale); solo main() toca disco.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

TEXTO = ["track_id", "artists", "album_name", "track_name", "track_genre"]
ENTEROS = ["popularity", "duration_ms", "key", "mode", "time_signature"]
DECIMALES = [
    "danceability",
    "energy",
    "loudness",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo",
]
OBLIGATORIAS = ["track_id", "artists", "track_name"]


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Quita la columna índice sobrante, recorta espacios y fija los tipos."""
    df = df.drop(columns=["Unnamed: 0"], errors="ignore").copy()
    for c in TEXTO:
        df[c] = df[c].astype("string").str.strip().replace("", pd.NA)
    for c in ENTEROS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in DECIMALES:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df["explicit"] = (
        df["explicit"]
        .map({True: True, False: False, "True": True, "False": False})
        .astype("boolean")
    )
    return df


def descartar_invalidas(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa las filas sin track_id, artists o track_name, o con duration_ms <= 0.

    Devuelve (validas, descartadas); descartadas lleva la columna `motivo`.
    """
    motivo = pd.Series(pd.NA, index=df.index, dtype="string")
    dur = df["duration_ms"]
    motivo = motivo.mask(dur.isna() | (dur <= 0), "duration_ms<=0")
    for c in reversed(OBLIGATORIAS):  # el primer campo que falta gana
        motivo = motivo.mask(df[c].isna(), f"sin_{c}")
    malas = motivo.notna()
    descartadas = df[malas].assign(motivo=motivo[malas]).reset_index(drop=True)
    return df[~malas].reset_index(drop=True), descartadas


def unificar_duplicados(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Una fila por track_id; los géneros pasan a la tabla puente (track_id, genero).

    genero_principal = género de la fila con mayor popularidad; empate → primero alfabético.
    Pistas con distinto track_id NO se unen aunque compartan nombre y artista.
    """
    track_generos = (
        df[["track_id", "track_genre"]]
        .drop_duplicates()
        .rename(columns={"track_genre": "genero"})
        .sort_values(["track_id", "genero"], kind="mergesort")
        .reset_index(drop=True)
    )
    catalogo = (
        df.sort_values(
            ["track_id", "popularity", "track_genre"],
            ascending=[True, False, True],
            kind="mergesort",
        )
        .drop_duplicates("track_id", keep="first")
        .rename(columns={"track_genre": "genero_principal"})
        .reset_index(drop=True)
    )
    n_generos = track_generos.groupby("track_id").size()
    catalogo["n_generos"] = catalogo["track_id"].map(n_generos).astype("Int64")
    return catalogo, track_generos


def artista_principal(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega `artista_principal`: el texto antes del primer ';' de artists."""
    df = df.copy()
    df["artista_principal"] = df["artists"].str.split(";").str[0].str.strip().astype("string")
    return df


def limpiar(crudo: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Pipeline completo. Devuelve (catalogo, track_generos, resumen)."""
    validas, descartadas = descartar_invalidas(normalizar(crudo))
    catalogo, track_generos = unificar_duplicados(validas)
    catalogo = artista_principal(catalogo)
    resumen = {
        "filas_leidas": len(crudo),
        "filas_descartadas": len(descartadas),
        "filas_fusionadas": len(validas) - len(catalogo),
        "track_id_finales": len(catalogo),
        "artistas_principales": catalogo["artista_principal"].nunique(),
        "filas_track_generos": len(track_generos),
    }
    for m, n in descartadas["motivo"].value_counts().sort_index().items():
        resumen[f"descartadas_{m}"] = int(n)
    return catalogo, track_generos, resumen


def main(entrada: Path, salida: Path) -> dict[str, int]:
    """Lee el CSV crudo, escribe catalogo_f1.parquet y track_generos.parquet."""
    catalogo, track_generos, resumen = limpiar(pd.read_csv(entrada))
    salida.mkdir(parents=True, exist_ok=True)
    catalogo.to_parquet(salida / "catalogo_f1.parquet", index=False)
    track_generos.to_parquet(salida / "track_generos.parquet", index=False)
    for k, v in resumen.items():
        print(f"{k:<32}{v:>10,}")
    return resumen
