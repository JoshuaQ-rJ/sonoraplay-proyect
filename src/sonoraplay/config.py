"""Configuración central de SonoraPlay. Todo sale de variables de entorno."""

import os
from dataclasses import dataclass
from datetime import date
from typing import Literal

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


# Catálogo F1 (EG-12)
N_TITULARES = 1_500
SEMILLA_CATALOGO = 42


# --- Umbrales de reglas de negocio ----------------------------------------------------------
# Cada bloque cita su regla y el ADR que justifica los valores. Recalibrar aquí, no en el código.


@dataclass(frozen=True)
class ReglasFraudeConfig:
    """RN-03 · detección de granjas (EG-18). Valores justificados en ADR-0005."""

    # RN-03 señal 1: horas escuchadas en cualquier ventana móvil de 24 h. Se marca si > 20.
    horas_max_24h: float = 20
    # RN-03 señal 2: fracción de las reproducciones del mes a un solo artista. Se marca si > 0,70...
    porcentaje_max_artista: float = 0.70
    # ...y ese artista tiene < 1.000 oyentes únicos en el mes UTC (EG-11 Q2).
    oyentes_min_artista: int = 1_000
    # RN-03 señal 3: cuentas distintas en un mismo dispositivo. Se marca si > 5 (ADR-0005:
    # protege a las familias de hasta 5 cuentas).
    cuentas_max_dispositivo: int = 5
    # EG-11 Q3: se excluye todo el mes de liquidación de la cuenta sospechosa ("en_revision").
    periodo_exclusion: Literal["mes"] = "mes"


@dataclass(frozen=True)
class ReglasValidezConfig:
    """RN-01 y RN-02 · validez y tope diario (EG-17). Supuestos de EG-11 Q1 y Q4, ADR-0002."""

    # RN-01: un tramo continuo de al menos estos segundos hace válida la reproducción (>= 30 s).
    # EG-11 Q1: la pausa, el seek o la interrupción antes del umbral reinician el conteo.
    segundos_min_validez: int = 30
    # RN-02: máximo de reproducciones válidas pagables por track, usuario y día.
    # EG-11 Q4 / ADR-0002: el "día" es la fecha UTC.
    max_reproducciones_dia: int = 10


@dataclass(frozen=True)
class ContratosConfig:
    """EG-14 · parámetros reproducibles del seed F4."""

    semilla: int = 42
    fecha_inicio: date = date(2026, 9, 1)
    fraccion_cambios: float = 0.15
    fraccion_exclusiones: float = 0.10
    fraccion_condiciones_territoriales: float = 0.10
    porcentaje_min: int = 30
    porcentaje_max: int = 70

    def __post_init__(self) -> None:
        for nombre in (
            "fraccion_cambios",
            "fraccion_exclusiones",
            "fraccion_condiciones_territoriales",
        ):
            valor = getattr(self, nombre)
            if not 0 <= valor <= 1:
                raise ValueError(f"{nombre} debe estar entre 0 y 1")
        if not 0 <= self.porcentaje_min <= self.porcentaje_max <= 100:
            raise ValueError("los porcentajes contractuales deben estar entre 0 y 100")
