"""Titulares de derechos (sellos, distribuidoras, sociedades de gestión) y su asignación.

HU 03 · EG-12. Cada artista principal tiene un único titular; todas sus pistas lo comparten.
La asignación sigue pesos tipo Zipf: pocos "majors" concentran muchos artistas (skew, tema 15).
"""

from __future__ import annotations

import random
import uuid
from pathlib import Path

import pandas as pd
from faker import Faker

from sonoraplay.config import N_TITULARES, SEMILLA_CATALOGO
from sonoraplay.seed.f3_suscripciones import NAMESPACE, PAISES

PESOS_TIPO = {"sello": 60, "distribuidora": 25, "sociedad_gestion": 15}
ZIPF_S = 1.0  # exponente: 1.0 = Zipf clásico; más alto, más concentración


def titular_id(n: int) -> str:
    """UUID determinista del titular n (mismo namespace que el seed F3)."""
    return str(uuid.uuid5(NAMESPACE, f"titular-{n}"))


def generar_titulares(n: int = N_TITULARES, semilla: int = SEMILLA_CATALOGO) -> pd.DataFrame:
    """n titulares; el titular 1 es el más grande en la asignación Zipf."""
    fake = Faker("es_CO")
    fake.seed_instance(semilla)
    rng = random.Random(semilla)
    filas = [
        {
            "titular_id": titular_id(k),
            "nombre": fake.company(),
            "tipo": rng.choices(list(PESOS_TIPO), weights=list(PESOS_TIPO.values()))[0],
            "pais": rng.choice(PAISES),
        }
        for k in range(1, n + 1)
    ]
    return pd.DataFrame(filas).astype("string")


def asignar_titulares(
    catalogo: pd.DataFrame, titulares: pd.DataFrame, semilla: int = SEMILLA_CATALOGO
) -> pd.DataFrame:
    """Agrega `titular_id` al catálogo, uno por artista_principal.

    Los primeros len(titulares) artistas (tras barajar) reciben un titular cada uno, para que
    ninguno quede vacío; el resto se reparte con pesos 1/k^ZIPF_S.
    """
    artistas = sorted(catalogo["artista_principal"].unique())
    ids = titulares["titular_id"].tolist()
    if len(artistas) < len(ids):
        raise ValueError(f"Hay {len(artistas)} artistas para {len(ids)} titulares")
    rng = random.Random(semilla)
    rng.shuffle(artistas)
    pesos = [1 / (k + 1) ** ZIPF_S for k in range(len(ids))]
    elegidos = list(range(len(ids))) + rng.choices(
        range(len(ids)), weights=pesos, k=len(artistas) - len(ids)
    )
    mapa = {a: ids[i] for a, i in zip(artistas, elegidos, strict=True)}
    catalogo = catalogo.copy()
    catalogo["titular_id"] = catalogo["artista_principal"].map(mapa).astype("string")
    return catalogo


def main(salida: Path, n: int = N_TITULARES, semilla: int = SEMILLA_CATALOGO) -> dict[str, int]:
    """Escribe titulares.parquet y agrega titular_id a catalogo_f1.parquet."""
    ruta = salida / "catalogo_f1.parquet"
    titulares = generar_titulares(n, semilla)
    catalogo = asignar_titulares(
        pd.read_parquet(ruta).drop(columns="titular_id", errors="ignore"), titulares, semilla
    )
    titulares.to_parquet(salida / "titulares.parquet", index=False)
    catalogo.to_parquet(ruta, index=False)
    por_titular = catalogo.groupby("titular_id")["artista_principal"].nunique()
    resumen = {
        "titulares": len(titulares),
        "titulares_con_artistas": len(por_titular),
        "artistas_titular_mayor": int(por_titular.max()),
        "artistas_titular_mediana": int(por_titular.median()),
        "pistas_titular_mayor": int(catalogo["titular_id"].value_counts().max()),
    }
    for k, v in resumen.items():
        print(f"{k:<32}{v:>10,}")
    return resumen
