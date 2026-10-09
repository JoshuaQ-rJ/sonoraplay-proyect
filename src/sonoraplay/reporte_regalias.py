"""Contrato del reporte de regalías (EG-21). Sin dependencias de FastAPI ni de la base.

La API de sellos (EG-21) solo **lee** la tabla `reporte_regalias` (`db/ddl/003`). Las funciones de
liquidación (EG-23) y el job de Spark (EG-37) la llenan devolviendo `FilaReporte`. Cambios a este
contrato se coordinan con ADR-0007. Detalle y ejemplo: docs/servicios/api-titulares.md.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

CENTAVO = Decimal("0.01")
ESCALA_PARTICIPACION = Decimal("0.000001")
_PAIS = re.compile(r"^[A-Z]{2}$")


class Componente(StrEnum):
    """Componentes de la bolsa (EG-11 Q8)."""

    SUSCRIPCION = "suscripcion"  # planes pagos: individual, familiar, estudiante
    PUBLICIDAD = "publicidad"  # plan gratuito


def redondear_usd(valor: Decimal) -> Decimal:
    """Redondeo del contrato: 2 decimales, ROUND_HALF_UP (RNF-02)."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FilaReporte:
    """Una fila de `reporte_regalias`, sin `liquidacion_id` (lo asigna quien publica).

    Una fila por titular, país, componente y % contractual: si el % cambió a mitad de mes
    (RN-07), hay una fila por cada %. En cada fila se cumple
    `regalia_usd = redondear_usd(bolsa × participacion × porcentaje_contractual / 100)`.
    """

    titular_id: uuid.UUID
    periodo: date  # primer día del mes UTC (ADR-0002)
    pais: str  # país de facturación, ISO 3166-1 alfa-2 (Q6)
    componente: Componente
    reproducciones_validas: int
    participacion: Decimal  # de 0 a 1, hasta 6 decimales
    porcentaje_contractual: Decimal  # de 0 a 100, hasta 2 decimales
    regalia_usd: Decimal  # USD, hasta 2 decimales

    def __post_init__(self) -> None:
        if self.periodo.day != 1:
            raise ValueError("periodo debe ser el primer día del mes")
        if not _PAIS.match(self.pais):
            raise ValueError("pais debe ser un código ISO de 2 letras mayúsculas")
        Componente(self.componente)
        if self.reproducciones_validas < 0:
            raise ValueError("reproducciones_validas no puede ser negativo")
        _validar(self.participacion, "participacion", Decimal(0), Decimal(1), ESCALA_PARTICIPACION)
        _validar(self.porcentaje_contractual, "porcentaje_contractual", Decimal(0), Decimal(100))
        _validar(self.regalia_usd, "regalia_usd", Decimal(0), None)


def _validar(
    valor: Decimal,
    nombre: str,
    minimo: Decimal,
    maximo: Decimal | None,
    escala: Decimal = CENTAVO,
) -> None:
    if not isinstance(valor, Decimal):
        raise TypeError(f"{nombre} debe ser Decimal (no float: se pierden centavos)")
    if valor < minimo or (maximo is not None and valor > maximo):
        raise ValueError(f"{nombre} fuera de rango: {valor}")
    if valor != valor.quantize(escala):
        raise ValueError(f"{nombre} tiene más decimales de los permitidos ({escala})")
