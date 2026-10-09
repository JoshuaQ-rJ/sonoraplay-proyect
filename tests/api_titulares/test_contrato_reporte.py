"""Contrato del reporte para la EG-23 / EG-37: `FilaReporte`, unidades y redondeo."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from sonoraplay.reporte_regalias import Componente, FilaReporte, redondear_usd
from tests.api_titulares.conftest import T_A, fila

SEP = date(2026, 9, 1)


def test_ejemplo_criterio_1_eg23_da_2800():
    """CO: suscripción 52.000 × 5 % y publicidad 9.000 × 10 %, contrato 80 % → 2.800,00 USD."""
    pct = Decimal("80")
    suscripcion = redondear_usd(Decimal("52000") * Decimal("0.05") * pct / 100)
    publicidad = redondear_usd(Decimal("9000") * Decimal("0.10") * pct / 100)
    assert (suscripcion, publicidad) == (Decimal("2080.00"), Decimal("720.00"))
    assert suscripcion + publicidad == Decimal("2800.00")
    filas = [
        fila(T_A, SEP, "CO", "suscripcion", 1200, "0.05", "80", str(suscripcion)),
        fila(T_A, SEP, "CO", "publicidad", 900, "0.10", "80", str(publicidad)),
    ]
    assert sum(f.regalia_usd for f in filas) == Decimal("2800.00")


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("0.005", "0.01"), ("0.015", "0.02"), ("2.345", "2.35"), ("2.344999", "2.34")],
)
def test_redondeo_half_up(valor, esperado):
    assert redondear_usd(Decimal(valor)) == Decimal(esperado)


def test_componentes_q8():
    assert {c.value for c in Componente} == {"suscripcion", "publicidad"}


def _kwargs(**cambios):
    base = {
        "titular_id": uuid.uuid4(),
        "periodo": SEP,
        "pais": "CO",
        "componente": Componente.SUSCRIPCION,
        "reproducciones_validas": 10,
        "participacion": Decimal("0.5"),
        "porcentaje_contractual": Decimal("80"),
        "regalia_usd": Decimal("10.00"),
    }
    return base | cambios


def test_fila_valida():
    assert FilaReporte(**_kwargs()).regalia_usd == Decimal("10.00")


@pytest.mark.parametrize(
    "cambios",
    [
        {"periodo": date(2026, 9, 15)},
        {"pais": "co"},
        {"pais": "COL"},
        {"componente": "regalos"},
        {"reproducciones_validas": -1},
        {"participacion": Decimal("1.000001")},
        {"participacion": Decimal("-0.1")},
        {"participacion": Decimal("0.0000001")},
        {"porcentaje_contractual": Decimal("100.01")},
        {"porcentaje_contractual": Decimal("80.001")},
        {"regalia_usd": Decimal("-0.01")},
        {"regalia_usd": Decimal("10.005")},
    ],
)
def test_fila_rechaza_valores_fuera_del_contrato(cambios):
    with pytest.raises(ValueError):
        FilaReporte(**_kwargs(**cambios))


def test_fila_rechaza_float():
    with pytest.raises(TypeError, match="Decimal"):
        FilaReporte(**_kwargs(regalia_usd=10.0))
