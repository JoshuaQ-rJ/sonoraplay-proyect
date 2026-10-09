"""Pruebas HTTP de EG-20 con TestClient, contra la base de prueba."""

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from sonoraplay.api_contratos.db import get_session
from sonoraplay.api_contratos.main import create_app
from tests.api_contratos.conftest import (
    PISTA_A,
    PISTA_B,
    PISTA_C,
    PISTA_D,
    T_CAMBIO,
    T_EXCLUSION,
    T_INEXISTENTE,
    T_TERRITORIO,
)


def porcentaje(cliente, titular, **params):
    return cliente.get(f"/titulares/{titular}/porcentaje", params=params)


# --- Criterio 1 · RN-07 -----------------------------------------------------------------------


def test_cambio_a_mitad_de_mes_50_el_14_y_40_el_15(cliente):
    dia14 = porcentaje(cliente, T_CAMBIO, fecha="2026-09-14")
    dia15 = porcentaje(cliente, T_CAMBIO, fecha="2026-09-15")
    assert dia14.status_code == dia15.status_code == 200
    assert dia14.json()["porcentaje"] == 50
    assert dia14.json()["valido_hasta"] == "2026-09-14"
    assert dia15.json()["porcentaje"] == 40
    assert dia15.json()["valido_hasta"] is None


def test_respuesta_completa(cliente):
    cuerpo = porcentaje(cliente, T_CAMBIO, fecha="2026-09-15", track_id=PISTA_D).json()
    assert set(cuerpo) == {
        "titular_id",
        "track_id",
        "fecha",
        "pais",
        "porcentaje",
        "territorio_aplicado",
        "excluido",
        "contrato_id",
        "valido_desde",
        "valido_hasta",
    }
    assert cuerpo["track_id"] == PISTA_D
    assert isinstance(cuerpo["porcentaje"], float)


def test_sin_track_id_usa_la_menor_pista(cliente):
    assert porcentaje(cliente, T_CAMBIO, fecha="2026-09-15").json()["track_id"] == PISTA_A


# --- Criterio 2 · errores ---------------------------------------------------------------------


def test_titular_inexistente_404(cliente):
    r = porcentaje(cliente, T_INEXISTENTE, fecha="2026-09-15")
    assert r.status_code == 404
    assert r.json()["detail"] == "Titular no encontrado"


def test_sin_condicion_vigente_404_con_otro_mensaje(cliente):
    r = porcentaje(cliente, T_CAMBIO, fecha="2026-08-31")
    assert r.status_code == 404
    assert r.json()["detail"] == "El titular no tiene una condición vigente en esa fecha"


def test_pista_ajena_al_titular_404(cliente):
    r = porcentaje(cliente, T_CAMBIO, fecha="2026-09-15", track_id=PISTA_B)
    assert r.status_code == 404


def test_fecha_invalida_422(cliente):
    for fecha in ("2026-02-30", "15/09/2026", "hoy"):
        assert porcentaje(cliente, T_CAMBIO, fecha=fecha).status_code == 422


def test_sin_fecha_422(cliente):
    assert cliente.get(f"/titulares/{T_CAMBIO}/porcentaje").status_code == 422


def test_uuid_invalido_422(cliente):
    assert cliente.get("/titulares/no-es-uuid/porcentaje?fecha=2026-09-15").status_code == 422
    assert cliente.get("/titulares/123/condiciones").status_code == 422


def test_pais_invalido_422(cliente):
    for pais in ("co", "COL", "1A"):
        assert porcentaje(cliente, T_CAMBIO, fecha="2026-09-15", pais=pais).status_code == 422


# --- Q7 y RN-08 -------------------------------------------------------------------------------


def test_q7_territorial_frente_a_general(cliente):
    co = porcentaje(cliente, T_TERRITORIO, fecha="2026-09-20", pais="CO").json()
    mx = porcentaje(cliente, T_TERRITORIO, fecha="2026-09-20", pais="MX").json()
    sin_pais = porcentaje(cliente, T_TERRITORIO, fecha="2026-09-20").json()
    assert (co["porcentaje"], co["territorio_aplicado"]) == (45, "CO")
    assert (mx["porcentaje"], mx["territorio_aplicado"]) == (60, None)
    assert (sin_pais["porcentaje"], sin_pais["territorio_aplicado"]) == (60, None)


def test_rn08_pais_excluido_200_con_porcentaje_cero(cliente):
    r = porcentaje(cliente, T_EXCLUSION, fecha="2026-09-20", pais="MX")
    assert r.status_code == 200
    assert r.json()["excluido"] is True
    assert r.json()["porcentaje"] == 0


def test_rn08_otro_pais_no_excluido(cliente):
    cuerpo = porcentaje(cliente, T_EXCLUSION, fecha="2026-09-20", pais="CO").json()
    assert cuerpo["excluido"] is False
    assert cuerpo["porcentaje"] == 35


# --- Criterio 3 · /condiciones ----------------------------------------------------------------


def test_condiciones_lista_periodos(cliente):
    r = cliente.get(f"/titulares/{T_CAMBIO}/condiciones")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 4
    assert [(c["track_id"], c["porcentaje"], c["valido_desde"]) for c in cuerpo["condiciones"]] == [
        (PISTA_A, 50, "2026-09-01"),
        (PISTA_A, 40, "2026-09-15"),
        (PISTA_D, 50, "2026-09-01"),
        (PISTA_D, 40, "2026-09-15"),
    ]


def test_condiciones_incluye_territorio_y_exclusiones(cliente):
    territorio = cliente.get(f"/titulares/{T_TERRITORIO}/condiciones").json()["condiciones"]
    assert [c["territorio"] for c in territorio] == [None, "CO"]  # general primero
    exclusion = cliente.get(f"/titulares/{T_EXCLUSION}/condiciones").json()["condiciones"]
    assert exclusion[0]["track_id"] == PISTA_C
    assert exclusion[0]["exclusiones"] == ["MX"]


def test_condiciones_paginacion(cliente):
    url = f"/titulares/{T_CAMBIO}/condiciones"
    p1 = cliente.get(url, params={"limit": 3, "offset": 0}).json()
    p2 = cliente.get(url, params={"limit": 3, "offset": 3}).json()
    assert (len(p1["condiciones"]), len(p2["condiciones"])) == (3, 1)
    assert p1["total"] == p2["total"] == 4
    ids = {c["contrato_id"] for c in p1["condiciones"] + p2["condiciones"]}
    assert len(ids) == 4


def test_condiciones_limites_de_paginacion_422(cliente):
    url = f"/titulares/{T_CAMBIO}/condiciones"
    assert cliente.get(url, params={"limit": 0}).status_code == 422
    assert cliente.get(url, params={"limit": 1001}).status_code == 422
    assert cliente.get(url, params={"offset": -1}).status_code == 422


def test_condiciones_titular_inexistente_404(cliente):
    assert cliente.get(f"/titulares/{T_INEXISTENTE}/condiciones").status_code == 404


# --- Criterios 4 y 6 · OpenAPI y /health ------------------------------------------------------


def test_health_200(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_503_si_la_base_no_responde():
    app = create_app()
    # Puerto 1 en localhost: la conexión se rechaza de inmediato.
    caida = create_engine("postgresql+psycopg://x:y@127.0.0.1:1/nada?connect_timeout=2")

    def _sesion_caida():
        with Session(caida) as s:
            yield s

    app.dependency_overrides[get_session] = _sesion_caida
    with TestClient(app) as c:
        assert c.get("/health").status_code == 503


def test_openapi_documenta_endpoints_y_esquemas(cliente):
    spec = cliente.get("/openapi.json").json()
    rutas = {
        "/health": "Salud",
        "/titulares/{titular_id}/porcentaje": "PorcentajeVigente",
        "/titulares/{titular_id}/condiciones": "CondicionesPagina",
    }
    for ruta, esquema in rutas.items():
        ok = spec["paths"][ruta]["get"]["responses"]["200"]["content"]["application/json"]
        assert ok["schema"]["$ref"] == f"#/components/schemas/{esquema}"
    assert {"PorcentajeVigente", "CondicionesPagina", "CondicionOut"} <= set(
        spec["components"]["schemas"]
    )
    parametros = {
        p["name"] for p in spec["paths"]["/titulares/{titular_id}/porcentaje"]["get"]["parameters"]
    }
    assert parametros == {"titular_id", "fecha", "track_id", "pais"}
    assert cliente.get("/docs").status_code == 200
