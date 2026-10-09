"""Armado del reporte (puro) y consulta de la última liquidación publicada."""

from datetime import date
from decimal import Decimal

from sonoraplay.api_titulares import repositories as repo
from sonoraplay.api_titulares import services
from sonoraplay.api_titulares.models import ReporteRegalias
from tests.api_titulares.conftest import (
    AGO,
    FILAS_A_SEP_V2,
    LIQ_AGO,
    LIQ_SEP_V2,
    SEP,
    T_A,
    T_SIN_REPORTE,
)

# --- construir_reporte (sin base) ------------------------------------------------------------


def test_totales_por_mes_y_pais():
    filas = [ReporteRegalias.desde_fila(f, LIQ_SEP_V2) for f in FILAS_A_SEP_V2]
    reporte = services.construir_reporte(T_A, filas)
    assert len(reporte.filas) == 4
    totales = {(t.periodo, t.pais): t for t in reporte.totales}
    assert set(totales) == {("2026-09", "CO"), ("2026-09", "MX")}
    assert totales[("2026-09", "CO")].regalia_usd == Decimal("2800.00")
    assert totales[("2026-09", "CO")].reproducciones_validas == 2100
    assert totales[("2026-09", "MX")].regalia_usd == Decimal("1191.66")
    assert totales[("2026-09", "MX")].liquidacion_id == LIQ_SEP_V2


def test_reporte_vacio():
    reporte = services.construir_reporte(T_SIN_REPORTE, [])
    assert (reporte.filas, reporte.totales) == ([], [])


def test_periodo_texto_ida_y_vuelta():
    assert services.texto_a_periodo("2026-09") == date(2026, 9, 1)
    assert services.periodo_a_texto(date(2026, 9, 1)) == "2026-09"


# --- repositorio (con base) ------------------------------------------------------------------


def test_ultima_liquidacion_publicada_de_cada_mes(sesion):
    filas = repo.filas_ultima_liquidacion(sesion, T_A, None, None)
    assert {(f.periodo, f.liquidacion_id) for f in filas} == {(AGO, LIQ_AGO), (SEP, LIQ_SEP_V2)}
    # Ni V1 (reemplazada) ni el borrador sin publicar.
    assert Decimal("1000.00") not in {f.regalia_usd for f in filas}
    assert Decimal("9999.99") not in {f.regalia_usd for f in filas}


def test_filtros_por_periodo_y_pais(sesion):
    filas = repo.filas_ultima_liquidacion(sesion, T_A, SEP, "MX")
    assert [(f.pais, f.porcentaje_contractual) for f in filas] == [
        ("MX", Decimal("50.00")),
        ("MX", Decimal("40.00")),
    ]


def test_orden_estable(sesion):
    filas = repo.filas_ultima_liquidacion(sesion, T_A, SEP, None)
    assert [(f.pais, f.componente, f.porcentaje_contractual) for f in filas] == [
        ("CO", "suscripcion", Decimal("80.00")),
        ("CO", "publicidad", Decimal("80.00")),
        ("MX", "suscripcion", Decimal("50.00")),
        ("MX", "suscripcion", Decimal("40.00")),
    ]


def test_titular_sin_reporte(sesion):
    assert repo.filas_ultima_liquidacion(sesion, T_SIN_REPORTE, None, None) == []


def test_mes_sin_liquidacion(sesion):
    assert repo.filas_ultima_liquidacion(sesion, T_A, date(2026, 7, 1), None) == []
