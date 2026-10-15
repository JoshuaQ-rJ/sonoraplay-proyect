"""Pruebas offline para EG-30: no dependen de APIs externas."""
from datetime import date

import pytest

from sonoraplay.fuentes.eg30 import generar_f5, ultimo_dia, validar_paises, validar_tasas


def paises():
    return [
        {"pais": c, "monedas": [m]}
        for c, m in [("BR", "BRL"), ("CL", "CLP"), ("CO", "COP"), ("MX", "MXN"), ("PE", "PEN")]
    ]


def test_ultimo_dia_bisiesto():
    assert ultimo_dia("2024-02") == date(2024, 2, 29)


def test_f5_determinista_y_menos_de_mil():
    a = generar_f5("2026-09", paises(), 42)
    assert a == generar_f5("2026-09", paises(), 42)
    assert len(a) == 5
    assert all(f["moneda"] in {"BRL", "CLP", "COP", "MXN", "PEN"} for f in a)


def test_f5_exige_moneda_de_f7():
    with pytest.raises(ValueError, match="moneda"):
        generar_f5("2026-09", [{"pais": "BR", "monedas": ["USD"]}])


def test_f6_rechaza_faltantes():
    with pytest.raises(ValueError, match="cobertura"):
        validar_tasas({"rates": {"BRL": 5}}, ("BRL", "COP"))


def test_f7_rechaza_incompleta():
    with pytest.raises(ValueError, match="incompleta"):
        validar_paises([{"cca2": "CO", "currencies": {"COP": {}}, "region": "Americas"}])
