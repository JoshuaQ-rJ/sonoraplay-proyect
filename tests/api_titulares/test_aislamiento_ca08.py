"""CA-08 / RN-11: el sello A nunca ve datos de B ni puede averiguar si B existe.

Corre en el job `test` del CI con el resto de la suite.
"""

import pytest
from fastapi.testclient import TestClient

from sonoraplay.api_titulares.db import get_session
from sonoraplay.api_titulares.routers.reportes import NO_PERMITIDO
from tests.api_titulares.conftest import T_A, T_B, T_INEXISTENTE, T_SIN_REPORTE, bearer

DATOS_DE_B = [str(T_B), "AR", "4321", "0.123456", "65.00", "1234.56"]


def test_a_pide_b_403(cliente, token):
    r = cliente.get(f"/titulares/{T_B}/reportes", headers=bearer(token(T_A)))
    assert r.status_code == 403
    assert r.json() == {"detail": NO_PERMITIDO}


def test_a_pide_inexistente_403_con_el_mismo_cuerpo_exacto(cliente, token):
    existe = cliente.get(f"/titulares/{T_B}/reportes", headers=bearer(token(T_A)))
    no_existe = cliente.get(f"/titulares/{T_INEXISTENTE}/reportes", headers=bearer(token(T_A)))
    sin_reporte = cliente.get(f"/titulares/{T_SIN_REPORTE}/reportes", headers=bearer(token(T_A)))
    assert existe.status_code == no_existe.status_code == sin_reporte.status_code == 403
    assert existe.content == no_existe.content == sin_reporte.content
    assert existe.headers["content-type"] == no_existe.headers["content-type"]


@pytest.mark.parametrize("pedido", [T_B, T_INEXISTENTE])
@pytest.mark.parametrize("query", ["", "?periodo=2026-09", "?pais=AR", "?periodo=2026-09&pais=AR"])
def test_las_respuestas_403_no_filtran_datos_de_b(cliente, token, pedido, query):
    r = cliente.get(f"/titulares/{pedido}/reportes{query}", headers=bearer(token(T_A)))
    assert r.status_code == 403
    for dato in DATOS_DE_B[1:]:
        assert dato not in r.text


def test_el_403_se_decide_sin_consultar_la_base(app_titulares, token):
    """Si el endpoint pidiera una sesión, esta dependencia haría fallar la prueba."""

    def _sesion_prohibida():
        raise AssertionError("se abrió una sesión de base de datos antes del 403")
        yield  # pragma: no cover

    app_titulares.dependency_overrides[get_session] = _sesion_prohibida
    with TestClient(app_titulares) as c:
        for pedido in (T_B, T_INEXISTENTE):
            r = c.get(f"/titulares/{pedido}/reportes", headers=bearer(token(T_A)))
            assert r.status_code == 403


@pytest.mark.parametrize("ruta", ["/me/reportes", f"/titulares/{T_A}/reportes"])
def test_a_solo_recibe_sus_filas(cliente, token, ruta):
    r = cliente.get(ruta, headers=bearer(token(T_A)))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["titular_id"] == str(T_A)
    assert cuerpo["filas"]
    assert {f["pais"] for f in cuerpo["filas"]} <= {"CO", "MX"}
    for dato in DATOS_DE_B:
        assert dato not in r.text


def test_b_solo_recibe_sus_filas(cliente, token):
    cuerpo = cliente.get("/me/reportes", headers=bearer(token(T_B))).json()
    assert [(f["pais"], f["regalia_usd"]) for f in cuerpo["filas"]] == [("AR", "1234.56")]


def test_sin_token_el_403_no_aplica_primero_401(cliente):
    """Sin token no se llega a comparar titulares: no se revela nada sobre B."""
    r = cliente.get(f"/titulares/{T_B}/reportes")
    assert r.status_code == 401
