"""Configuración central de SonoraPlay. Todo sale de variables de entorno."""

import os
from dataclasses import dataclass
from datetime import date

VOLUMENES = {"dev": 10_000, "completo": 900_000}


def database_url() -> str:
    try:
        return os.environ["DATABASE_URL"]
    except KeyError:
        raise SystemExit("Falta DATABASE_URL. Copia .env.example a .env o expórtala.") from None


@dataclass(frozen=True)
class SeedConfig:
    semilla: int = 42
    usuarios: int = VOLUMENES["dev"]
    tasa_defectos: float = 0.02
    fecha_referencia: date = date(2026, 9, 30)  # nunca now(): rompe la reproducibilidad
    fecha_inicio_historia: date = date(2024, 1, 1)
    tamano_lote: int = 5_000
