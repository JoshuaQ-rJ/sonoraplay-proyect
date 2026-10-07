"""Seed F4 · contratos de titulares. Determinista e idempotente.

EG-14. Lee los IDs reales producidos por EG-12 para no inventar titulares ni pistas.
"""

from __future__ import annotations

import argparse
import random
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, MetaData, Table, create_engine, func, select
from sqlalchemy.dialects.postgresql import insert

from sonoraplay.config import ContratosConfig, database_url
from sonoraplay.seed.f3_suscripciones import NAMESPACE

PAISES = ["CO", "MX", "BR", "AR", "CL", "PE"]


def det_uuid(semilla: int, entidad: str, *partes: object) -> uuid.UUID:
    """UUID5 estable: la misma semilla y llave producen el mismo contrato."""
    return uuid.uuid5(NAMESPACE, ":".join(str(x) for x in (semilla, entidad, *partes)))


@dataclass(frozen=True)
class FuentesF1:
    titulares: pd.DataFrame
    catalogo: pd.DataFrame


def leer_fuentes(directorio: Path) -> FuentesF1:
    """Lee titulares.parquet y catalogo_f1.parquet generados por EG-12."""
    titulares = pd.read_parquet(directorio / "titulares.parquet")
    catalogo = pd.read_parquet(directorio / "catalogo_f1.parquet")
    requeridos_t = {"titular_id", "nombre", "tipo", "pais"}
    requeridos_c = {"track_id", "titular_id"}
    if not requeridos_t <= set(titulares.columns):
        raise ValueError(f"titulares.parquet requiere {sorted(requeridos_t)}")
    if not requeridos_c <= set(catalogo.columns):
        raise ValueError(f"catalogo_f1.parquet requiere {sorted(requeridos_c)}")
    if titulares["titular_id"].duplicated().any():
        raise ValueError("titulares.parquet contiene titular_id duplicados")
    if catalogo["track_id"].duplicated().any():
        raise ValueError("catalogo_f1.parquet contiene track_id duplicados")
    desconocidos = set(catalogo["titular_id"]) - set(titulares["titular_id"])
    if desconocidos:
        raise ValueError("el catálogo contiene titular_id que no existen en titulares.parquet")
    return FuentesF1(titulares=titulares, catalogo=catalogo)


def generar(fuentes: FuentesF1, cfg: ContratosConfig) -> tuple[list[dict], list[dict], list[dict]]:
    """Genera titulares, condiciones contractuales y exclusiones para cargar en PostgreSQL."""
    titulares_db = fuentes.titulares[["titular_id", "nombre", "tipo", "pais"]].to_dict("records")
    por_titular = {
        str(t): sorted(g["track_id"].astype(str).tolist())
        for t, g in fuentes.catalogo.groupby("titular_id", sort=True)
    }
    contratos: list[dict] = []
    exclusiones: list[dict] = []

    for fila in titulares_db:
        tid = str(fila["titular_id"])
        tracks = por_titular.get(tid, [])
        if not tracks:
            raise ValueError(f"titular {tid} no tiene pistas en catalogo_f1.parquet")
        rng = random.Random(f"{cfg.semilla}:f4:{tid}")
        cambia = rng.random() < cfg.fraccion_cambios
        excluye = rng.random() < cfg.fraccion_exclusiones
        territorial = rng.random() < cfg.fraccion_condiciones_territoriales
        territorio = rng.choice(PAISES) if territorial else None
        porcentaje = rng.randint(cfg.porcentaje_min, cfg.porcentaje_max)
        track_id = rng.choice(tracks)

        periodos = [(cfg.fecha_inicio, None, porcentaje)]
        if cambia:
            corte = cfg.fecha_inicio + timedelta(days=14)
            nuevo = rng.randint(cfg.porcentaje_min, cfg.porcentaje_max)
            if nuevo == porcentaje:
                nuevo = cfg.porcentaje_min if porcentaje != cfg.porcentaje_min else cfg.porcentaje_max
            periodos = [
                (cfg.fecha_inicio, corte - timedelta(days=1), porcentaje),
                (corte, None, nuevo),
            ]

        for n, (desde, hasta, pct) in enumerate(periodos):
            cid = det_uuid(cfg.semilla, "contrato", tid, track_id, territorio or "general", n)
            contratos.append(
                {
                    "contrato_id": cid,
                    "titular_id": uuid.UUID(tid),
                    "track_id": track_id,
                    "porcentaje": pct,
                    "territorio": territorio,
                    "valido_desde": desde,
                    "valido_hasta": hasta,
                }
            )
            if excluye:
                candidatos = [p for p in PAISES if p != territorio]
                pais = rng.choice(candidatos)
                exclusiones.append({"contrato_id": cid, "pais": pais})

    return titulares_db, contratos, exclusiones


def ejecutar(engine: Engine, directorio_f1: Path, cfg: ContratosConfig) -> dict[str, int]:
    """Carga F4 con ON CONFLICT DO NOTHING y devuelve conteos."""
    fuentes = leer_fuentes(directorio_f1)
    titulares, contratos, exclusiones = generar(fuentes, cfg)
    md = MetaData()
    tablas = {
        n: Table(n, md, autoload_with=engine)
        for n in ["titulares_derechos", "contratos", "exclusiones_territoriales"]
    }
    with engine.begin() as conn:
        conn.execute(insert(tablas["titulares_derechos"]).on_conflict_do_nothing(), titulares)
        conn.execute(insert(tablas["contratos"]).on_conflict_do_nothing(), contratos)
        if exclusiones:
            conn.execute(
                insert(tablas["exclusiones_territoriales"]).on_conflict_do_nothing(), exclusiones
            )
    with engine.connect() as conn:
        return {n: conn.scalar(select(func.count()).select_from(t)) for n, t in tablas.items()}


def main() -> None:
    """Ejecuta el seed F4 usando DATABASE_URL, igual que el resto de seeds."""
    parser = argparse.ArgumentParser(description="Seed F4 de contratos")
    parser.add_argument("--datos-f1", type=Path, default=Path("data/processed"))
    parser.add_argument("--semilla", type=int, default=42)
    args = parser.parse_args()
    engine = create_engine(database_url())
    conteos = ejecutar(engine, args.datos_f1, ContratosConfig(semilla=args.semilla))
    for tabla, total in conteos.items():
        print(f"{tabla:<28}{total:>10,}")


if __name__ == "__main__":
    main()
