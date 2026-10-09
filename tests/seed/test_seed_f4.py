"""Pruebas de aceptación de EG-14 · seed F4."""

from datetime import date

import pandas as pd
import pytest

from sonoraplay.config import ContratosConfig
from sonoraplay.seed.f4_contratos import FuentesF1, ejecutar, generar


@pytest.fixture
def fuentes():
    titulares = pd.DataFrame(
        [
            {
                "titular_id": "11111111-1111-4111-8111-111111111111",
                "nombre": "A",
                "tipo": "sello",
                "pais": "CO",
            },
            {
                "titular_id": "22222222-2222-4222-8222-222222222222",
                "nombre": "B",
                "tipo": "distribuidora",
                "pais": "MX",
            },
            {
                "titular_id": "33333333-3333-4333-8333-333333333333",
                "nombre": "C",
                "tipo": "sociedad_gestion",
                "pais": "CL",
            },
        ]
    )
    catalogo = pd.DataFrame(
        [
            {"track_id": "A" * 22, "titular_id": titulares.iloc[0].titular_id},
            {"track_id": "D" * 22, "titular_id": titulares.iloc[0].titular_id},
            {"track_id": "B" * 22, "titular_id": titulares.iloc[1].titular_id},
            {"track_id": "C" * 22, "titular_id": titulares.iloc[2].titular_id},
        ]
    )
    return FuentesF1(titulares, catalogo)


def cfg(**cambios):
    base = dict(
        semilla=42,
        fecha_inicio=date(2026, 9, 1),
        fraccion_cambios=1.0,
        fraccion_exclusiones=1.0,
        fraccion_condiciones_territoriales=1.0,
    )
    return ContratosConfig(**(base | cambios))


def test_cada_titular_tiene_contrato_y_track_de_f1(fuentes):
    titulares, contratos, _ = generar(fuentes, cfg())
    ids = {str(x["titular_id"]) for x in titulares}
    assert {str(c["titular_id"]) for c in contratos} == ids
    tracks = set(fuentes.catalogo["track_id"])
    assert all(c["track_id"] in tracks for c in contratos)


def test_cada_pista_del_catalogo_tiene_condicion_general(fuentes):
    _, contratos, _ = generar(fuentes, cfg())
    generales = {c["track_id"] for c in contratos if c["territorio"] is None}
    assert generales == set(fuentes.catalogo["track_id"])


def test_cambios_mitad_mes_no_se_solapan(fuentes):
    _, contratos, _ = generar(fuentes, cfg())
    por_condicion = {}
    for c in contratos:
        if c["territorio"] is None:
            por_condicion.setdefault((c["titular_id"], c["track_id"]), []).append(c)
    for periodos in por_condicion.values():
        periodos.sort(key=lambda x: x["valido_desde"])
        assert len(periodos) == 2
        assert periodos[0]["valido_hasta"] == date(2026, 9, 14)
        assert periodos[1]["valido_desde"] == date(2026, 9, 15)
        assert periodos[0]["valido_hasta"] < periodos[1]["valido_desde"]


def test_porcentajes_entre_cero_y_cien(fuentes):
    _, contratos, _ = generar(fuentes, cfg())
    assert all(0 <= c["porcentaje"] <= 100 for c in contratos)


def test_exclusiones_y_territorio_opcional(fuentes):
    _, contratos, exclusiones = generar(fuentes, cfg())
    assert exclusiones
    # Cada (titular, pista) tiene una condición territorial además de la general.
    territoriales = {}
    for c in contratos:
        if c["territorio"] is not None:
            territoriales[(c["titular_id"], c["track_id"])] = c["territorio"]
    generales = {(c["titular_id"], c["track_id"]) for c in contratos if c["territorio"] is None}
    assert set(territoriales) == generales
    # Las exclusiones solo están en contratos generales.
    por_id = {c["contrato_id"]: c for c in contratos}
    assert all(por_id[e["contrato_id"]]["territorio"] is None for e in exclusiones)
    # El país excluido es distinto del territorio.
    for e in exclusiones:
        c = por_id[e["contrato_id"]]
        assert e["pais"] != territoriales[(c["titular_id"], c["track_id"])]
    # Cada titular excluye un solo país.
    paises_por_titular = {}
    for e in exclusiones:
        paises_por_titular.setdefault(por_id[e["contrato_id"]]["titular_id"], set()).add(e["pais"])
    assert all(len(paises) == 1 for paises in paises_por_titular.values())


def test_misma_semilla_mismos_datos(fuentes):
    assert generar(fuentes, cfg()) == generar(fuentes, cfg())


def test_sin_cambios_ni_exclusiones_tambien_es_valido(fuentes):
    _, contratos, exclusiones = generar(
        fuentes,
        cfg(fraccion_cambios=0, fraccion_exclusiones=0, fraccion_condiciones_territoriales=0),
    )
    assert len(contratos) == len(fuentes.catalogo)
    assert not exclusiones
    assert all(c["territorio"] is None and c["valido_hasta"] is None for c in contratos)


def test_seed_idempotente_en_postgresql(db_vacia, fuentes, tmp_path):
    """Dos cargas idénticas no duplican filas en PostgreSQL."""
    fuentes.titulares.to_parquet(tmp_path / "titulares.parquet", index=False)
    fuentes.catalogo.to_parquet(tmp_path / "catalogo_f1.parquet", index=False)
    primera = ejecutar(db_vacia, tmp_path, cfg())
    segunda = ejecutar(db_vacia, tmp_path, cfg())
    assert primera == segunda
    assert primera["titulares_derechos"] == len(fuentes.titulares)
    # 2 períodos generales + 1 territorial por pista; la exclusión va en los 2 generales.
    assert primera["contratos"] == 3 * len(fuentes.catalogo)
    assert primera["exclusiones_territoriales"] == 2 * len(fuentes.catalogo)
