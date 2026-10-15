"""Endpoints de la API de sellos con TestClient (EG-21, criterios 1, 3 y 4)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from sonoraplay.api_titulares.auth import VAR_SECRETO, SecretoInvalido, emitir_token
from sonoraplay.api_titulares.db import get_session
from sonoraplay.api_titulares.main import create_app
from tests.api_titulares.conftest import (
    LIQ_AGO,
    LIQ_SEP_V2,
    SECRETO_PRUEBA,
    T_A,
    T_SIN_REPORTE,
    bearer,
)

RUTAS_A = ["/me/reportes", f"/titulares/{T_A}/reportes"]
RUTAS_A_PLANTILLA = ["/me/reportes", "/titulares/{titular_id}/reportes"]

# --- Criterio 1: 200 con el reporte propio ---------------------------------------------------


@pytest.mark.parametrize("ruta", RUTAS_A)
def test_200_con_el_reporte_propio(cliente, token, ruta):
    r = cliente.get(ruta, headers=bearer(token(T_A)))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["titular_id"] == str(T_A)
    assert len(cuerpo["filas"]) == 5  # agosto (1) + septiembre V2 (4)


def test_las_dos_rutas_devuelven_lo_mismo(cliente, token):
    h = bearer(token(T_A))
    assert cliente.get(RUTAS_A[0], headers=h).json() == cliente.get(RUTAS_A[1], headers=h).json()


def test_titular_sin_reporte_200_vacio(cliente, token):
    r = cliente.get("/me/reportes", headers=bearer(token(T_SIN_REPORTE)))
    assert r.status_code == 200
    assert r.json() == {"titular_id": str(T_SIN_REPORTE), "filas": [], "totales": []}


# --- Criterio 4: contenido del reporte -------------------------------------------------------


def test_campos_y_decimales_como_string(cliente, token):
    r = cliente.get("/me/reportes?periodo=2026-09&pais=CO", headers=bearer(token(T_A)))
    assert r.json()["filas"] == [
        {
            "periodo": "2026-09",
            "pais": "CO",
            "componente": "suscripcion",
            "reproducciones_validas": 1200,
            "participacion": "0.050000",
            "porcentaje_contractual": "80.00",
            "regalia_usd": "2080.00",
            "liquidacion_id": str(LIQ_SEP_V2),
        },
        {
            "periodo": "2026-09",
            "pais": "CO",
            "componente": "publicidad",
            "reproducciones_validas": 900,
            "participacion": "0.100000",
            "porcentaje_contractual": "80.00",
            "regalia_usd": "720.00",
            "liquidacion_id": str(LIQ_SEP_V2),
        },
    ]


def test_total_por_mes_y_pais(cliente, token):
    totales = cliente.get("/me/reportes", headers=bearer(token(T_A))).json()["totales"]
    assert totales == [
        {
            "periodo": "2026-08",
            "pais": "CO",
            "liquidacion_id": str(LIQ_AGO),
            "reproducciones_validas": 800,
            "regalia_usd": "500.00",
        },
        {
            "periodo": "2026-09",
            "pais": "CO",
            "liquidacion_id": str(LIQ_SEP_V2),
            "reproducciones_validas": 2100,
            "regalia_usd": "2800.00",
        },
        {
            "periodo": "2026-09",
            "pais": "MX",
            "liquidacion_id": str(LIQ_SEP_V2),
            "reproducciones_validas": 1200,
            "regalia_usd": "1191.66",
        },
    ]


def test_por_defecto_la_ultima_liquidacion_publicada(cliente, token):
    filas = cliente.get("/me/reportes?periodo=2026-09", headers=bearer(token(T_A))).json()["filas"]
    assert {f["liquidacion_id"] for f in filas} == {str(LIQ_SEP_V2)}
    assert not {"1000.00", "9999.99"} & {f["regalia_usd"] for f in filas}


def test_dos_porcentajes_en_el_mes_dos_filas(cliente, token):
    r = cliente.get("/me/reportes?pais=MX", headers=bearer(token(T_A)))
    assert [f["porcentaje_contractual"] for f in r.json()["filas"]] == ["50.00", "40.00"]


@pytest.mark.parametrize(
    "query", ["periodo=2026-9", "periodo=2026-13", "periodo=09-2026", "pais=co"]
)
def test_filtros_invalidos_422(cliente, token, query):
    assert cliente.get(f"/me/reportes?{query}", headers=bearer(token(T_A))).status_code == 422


# --- Criterio 3: 401 -------------------------------------------------------------------------


def _vencido():
    hace = datetime.now(UTC) - timedelta(hours=2)
    return emitir_token(T_A, SECRETO_PRUEBA, timedelta(hours=1), ahora=hace)


CASOS_401 = {
    "sin encabezado": lambda token: {},
    "esquema Basic": lambda token: {"Authorization": "Basic dXN1YXJpbzpjbGF2ZQ=="},
    "bearer vacío": lambda token: {"Authorization": "Bearer "},
    "vencido": lambda token: bearer(_vencido()),
    "firma inválida": lambda token: bearer(token(T_A, clave="otro-secreto-" + "y" * 32)),
    "aud incorrecto": lambda token: bearer(token(T_A, aud="api-contratos")),
    "iss incorrecto": lambda token: bearer(token(T_A, iss="otro-emisor")),
    "sub no es UUID": lambda token: bearer(token(T_A, sub="sello-a")),
    "basura": lambda token: bearer("no.es.un.jwt"),
}


@pytest.mark.parametrize("ruta", RUTAS_A)
@pytest.mark.parametrize("caso", CASOS_401)
def test_401_con_www_authenticate(cliente, token, ruta, caso):
    r = cliente.get(ruta, headers=CASOS_401[caso](token))
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert "titular_id" not in r.text


def test_401_vencido_lo_dice(cliente):
    r = cliente.get("/me/reportes", headers=bearer(_vencido()))
    assert r.json() == {"detail": "El token venció"}


# --- Arranque, salud y OpenAPI ---------------------------------------------------------------


@pytest.mark.parametrize("valor", [None, "corto", "cambia_esto"])
def test_la_app_no_arranca_sin_secreto_valido(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv(VAR_SECRETO, raising=False)
    else:
        monkeypatch.setenv(VAR_SECRETO, valor)
    with pytest.raises(SecretoInvalido), TestClient(create_app()):
        pass


def test_health_200(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_503_si_la_base_no_responde(app_titulares):
    # Puerto 1 en localhost: la conexión se rechaza de inmediato.
    caida = create_engine("postgresql+psycopg://x:y@127.0.0.1:1/nada?connect_timeout=2")

    def _sesion_caida():
        with Session(caida) as s:
            yield s

    app_titulares.dependency_overrides[get_session] = _sesion_caida
    with TestClient(app_titulares) as c:
        assert c.get("/health").status_code == 503


def test_openapi_documenta_endpoints_y_seguridad_bearer(cliente):
    spec = cliente.get("/openapi.json").json()
    assert spec["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
        "description": spec["components"]["securitySchemes"]["HTTPBearer"]["description"],
    }
    for ruta in RUTAS_A_PLANTILLA:
        get = spec["paths"][ruta]["get"]
        assert get["security"] == [{"HTTPBearer": []}]
        ok = get["responses"]["200"]["content"]["application/json"]
        assert ok["schema"]["$ref"] == "#/components/schemas/ReporteOut"
        assert {"401"} <= set(get["responses"])
        assert {p["name"] for p in get["parameters"]} >= {"periodo", "pais"}
    assert "403" in spec["paths"]["/titulares/{titular_id}/reportes"]["get"]["responses"]
    assert "security" not in spec["paths"]["/health"]["get"]
    fila = spec["components"]["schemas"]["FilaReporteOut"]["properties"]
    for campo in ("regalia_usd", "porcentaje_contractual", "participacion"):
        assert fila[campo]["type"] == "string"
    assert cliente.get("/docs").status_code == 200
