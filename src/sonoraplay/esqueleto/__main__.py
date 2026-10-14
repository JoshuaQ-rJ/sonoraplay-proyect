"""Uso: python -m sonoraplay.esqueleto [--eventos F] [--datos-f1 DIR] [--periodo YYYY-MM]
[--pais XX] [--publicidad-usd N]"""

import argparse
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import create_engine

from sonoraplay.config import database_url
from sonoraplay.esqueleto.pipeline import (
    PERIODO_POR_DEFECTO,
    PUBLICIDAD_USD_POR_DEFECTO,
    ejecutar,
    formatear_resumen,
)


def _periodo(texto: str) -> date:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", texto):
        raise argparse.ArgumentTypeError("usa el formato YYYY-MM, p. ej. 2026-09")
    anio, mes = texto.split("-")
    return date(int(anio), int(mes), 1)


def _pais(texto: str) -> str:
    if not re.fullmatch(r"[A-Z]{2}", texto):
        raise argparse.ArgumentTypeError("usa un código ISO de 2 letras mayúsculas, p. ej. CO")
    return texto


def _usd(texto: str) -> Decimal:
    """Decimal directo desde el texto: el dinero nunca pasa por float."""
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"monto inválido: {texto}") from None
    if not valor.is_finite() or valor < 0:
        raise argparse.ArgumentTypeError("el monto debe ser un número >= 0")
    return valor


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="python -m sonoraplay.esqueleto",
        description="Esqueleto de punta a punta (EG-24): eventos F2 → reglas → liquidación de "
        "un país → reporte_regalias.",
    )
    p.add_argument("--eventos", type=Path, default=Path("data/processed/eventos_f2.jsonl"))
    p.add_argument("--datos-f1", type=Path, default=Path("data/processed"))
    p.add_argument(
        "--periodo",
        type=_periodo,
        default=PERIODO_POR_DEFECTO,
        help=f"Mes a liquidar (por defecto {PERIODO_POR_DEFECTO:%Y-%m}).",
    )
    p.add_argument(
        "--pais",
        type=_pais,
        default=None,
        help="País de facturación a liquidar (por defecto, el de más reproducciones pagables).",
    )
    p.add_argument(
        "--publicidad-usd",
        type=_usd,
        default=PUBLICIDAD_USD_POR_DEFECTO,
        help="Ingresos publicitarios del país en el mes, en USD. PROVISIONAL: F5 llega con la "
        f"EG-30 (por defecto {PUBLICIDAD_USD_POR_DEFECTO}).",
    )
    a = p.parse_args(argv)
    liquidacion_id, resumen = ejecutar(
        create_engine(database_url()), a.eventos, a.datos_f1, a.periodo, a.publicidad_usd, a.pais
    )
    print(formatear_resumen(liquidacion_id, resumen))


if __name__ == "__main__":
    main()
