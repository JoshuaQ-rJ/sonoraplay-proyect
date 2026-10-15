"""Consultas de vigencia sobre las tablas F4 reales (DDL de EG-14)."""

from datetime import date

import pytest

from sonoraplay.api_contratos import repositories as repo
from tests.api_contratos.conftest import PISTA_A, PISTA_B, T_CAMBIO, T_INEXISTENTE, T_TERRITORIO


@pytest.mark.parametrize(
    ("fecha", "esperado"),
    [
        (date(2026, 8, 31), []),  # antes del primer período
        (date(2026, 9, 1), [50]),
        (date(2026, 9, 14), [50]),  # valido_hasta es inclusivo
        (date(2026, 9, 15), [40]),
        (date(2030, 1, 1), [40]),  # valido_hasta NULL = sin fin
    ],
)
def test_vigencia_en_los_bordes(sesion, fecha, esperado):
    vigentes = repo.condiciones_vigentes(sesion, T_CAMBIO, PISTA_A, fecha)
    assert [int(c.porcentaje) for c in vigentes] == esperado


def test_vigentes_incluye_general_y_territorial(sesion):
    vigentes = repo.condiciones_vigentes(sesion, T_TERRITORIO, PISTA_B, date(2026, 9, 20))
    assert sorted((c.territorio or "", int(c.porcentaje)) for c in vigentes) == [
        ("", 60),
        ("CO", 45),
    ]


def test_pista_con_vigencia_es_la_menor(sesion):
    assert repo.pista_con_vigencia(sesion, T_CAMBIO, date(2026, 9, 20)) == PISTA_A
    assert repo.pista_con_vigencia(sesion, T_CAMBIO, date(2026, 8, 1)) is None


def test_titular_existe(sesion):
    assert repo.titular_existe(sesion, T_CAMBIO)
    assert not repo.titular_existe(sesion, T_INEXISTENTE)
