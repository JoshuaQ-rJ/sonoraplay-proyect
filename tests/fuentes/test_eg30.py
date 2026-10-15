"""Pruebas offline para EG-30: no dependen de APIs externas."""

from datetime import date
from urllib.error import URLError

import pytest

import sonoraplay.fuentes.eg30 as eg30
from sonoraplay.fuentes.eg30 import generar_f5, ultimo_dia, validar_paises, validar_tasas


def paises():
    return [
        {"pais": c, "monedas": [m]}
        for c, m in [("AR", "ARS"), ("BR", "BRL"), ("CL", "CLP"), ("CO", "COP"), ("MX", "MXN"), ("PE", "PEN")]
    ]


def test_ultimo_dia_bisiesto():
    assert ultimo_dia("2024-02") == date(2024, 2, 29)


def test_f5_determinista_y_menos_de_mil():
    a = generar_f5("2026-09", paises(), 42)
    assert a == generar_f5("2026-09", paises(), 42)
    assert len(a) == 6
    assert all(f["moneda"] in {"ARS", "BRL", "CLP", "COP", "MXN", "PEN"} for f in a)


def test_f5_exige_moneda_de_f7():
    with pytest.raises(ValueError, match="moneda"):
        generar_f5("2026-09", [{"pais": "BR", "monedas": ["USD"]}])


def test_f6_rechaza_faltantes():
    with pytest.raises(ValueError, match="cobertura"):
        validar_tasas(
            [{"base": "USD", "quote": "BRL", "date": "2026-09-30", "rate": 5}],
            ("BRL", "COP"), date(2026, 9, 30)
        )


def test_f7_rechaza_incompleta():
    with pytest.raises(ValueError, match="incompleta"):
        validar_paises([{"cca2": "CO", "currencies": {"COP": {}}, "region": "Americas"}])


def test_cli_error_de_conexion_sin_traceback(monkeypatch, capsys, tmp_path):
    def conexion_fallida(_url):
        raise URLError("sin conexión")

    monkeypatch.setattr(eg30, "obtener_json", conexion_fallida)
    monkeypatch.setattr("sys.argv", ["eg30", "--mes", "2026-09", "--salida", str(tmp_path)])
    with pytest.raises(SystemExit) as salida:
        eg30.main()
    assert salida.value.code == 1
    error = capsys.readouterr().err
    assert "Error EG-30:" in error
    assert "sin conexión" in error
    assert "Traceback" not in error
    assert list(tmp_path.iterdir()) == []


def test_cli_mes_invalido_sin_traceback(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("sys.argv", ["eg30", "--mes", "2026-13", "--salida", str(tmp_path)])
    with pytest.raises(SystemExit) as salida:
        eg30.main()
    assert salida.value.code == 1
    assert "Error EG-30:" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_f6_normaliza_cierre_domingo_y_decimal():
    filas = [
        {"base": "USD", "quote": "COP", "date": "2026-05-29", "rate": 4000.125}
    ]
    resultado = validar_tasas(filas, ("COP",), date(2026, 5, 31))
    assert resultado[0]["fecha"] == "2026-05-31"
    assert resultado[0]["fecha_observacion"] == "2026-05-29"
    assert resultado[0]["unidades_por_usd"] == "4000.125"


def test_f6_rechaza_fecha_de_otro_mes():
    with pytest.raises(ValueError, match="fuera del mes"):
        validar_tasas(
            [{"base": "USD", "quote": "COP", "date": "2026-04-30", "rate": 4000}],
            ("COP",), date(2026, 5, 31)
        )


def test_ejecutar_no_escribe_si_f6_incompleta(monkeypatch, tmp_path):
    def simular(url):
        if url == eg30.REST_COUNTRIES:
            datos = [
                {"cca2": f"X{i:02d}", "currencies": {"USD": {}}, "region": "Other"}
                for i in range(200)
            ]
            datos += [
                {"cca2": codigo, "currencies": {moneda: {}}, "region": "Americas"}
                for codigo, moneda in eg30.PAIS_MONEDA.items()
            ]
            return datos
        return [{"base": "USD", "quote": "BRL", "date": "2026-09-30", "rate": 5}]

    monkeypatch.setattr(eg30, "obtener_json", simular)
    with pytest.raises(ValueError, match="cobertura"):
        eg30.ejecutar("2026-09", tmp_path)
    assert list(tmp_path.iterdir()) == []
