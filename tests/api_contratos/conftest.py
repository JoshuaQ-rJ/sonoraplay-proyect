"""Datos F4 de prueba insertados a mano y cliente HTTP contra la base de prueba."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from sonoraplay.api_contratos.db import get_session
from sonoraplay.api_contratos.main import create_app
from sonoraplay.api_contratos.models import Contrato, ExclusionTerritorial, TitularDerechos

INICIO = date(2026, 9, 1)

# Titular con cambio de % a mitad de mes (RN-07): 50 % hasta el 14, 40 % desde el 15.
T_CAMBIO = uuid.UUID("11111111-1111-4111-8111-111111111111")
# Titular con condición territorial (Q7): 60 % general y 45 % en CO.
T_TERRITORIO = uuid.UUID("22222222-2222-4222-8222-222222222222")
# Titular con exclusión (RN-08): 35 % general, MX excluido.
T_EXCLUSION = uuid.UUID("33333333-3333-4333-8333-333333333333")
T_INEXISTENTE = uuid.UUID("99999999-9999-4999-8999-999999999999")

PISTA_A, PISTA_D = "A" * 22, "D" * 22
PISTA_B, PISTA_C = "B" * 22, "C" * 22


def _cid(*partes: object) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, ":".join(map(str, partes)))


def _contrato(titular, pista, pct, desde, hasta=None, territorio=None, n=0) -> Contrato:
    return Contrato(
        contrato_id=_cid(titular, pista, territorio, n),
        titular_id=titular,
        track_id=pista,
        porcentaje=Decimal(pct),
        territorio=territorio,
        valido_desde=desde,
        valido_hasta=hasta,
    )


@pytest.fixture
def db_f4(db_vacia):
    titulares = [
        TitularDerechos(titular_id=T_CAMBIO, nombre="Sello Cambio", tipo="sello", pais="CO"),
        TitularDerechos(
            titular_id=T_TERRITORIO, nombre="Distri Territorio", tipo="distribuidora", pais="MX"
        ),
        TitularDerechos(
            titular_id=T_EXCLUSION, nombre="Sociedad Exclusión", tipo="sociedad_gestion", pais="CL"
        ),
    ]
    contratos = []
    # Dos pistas con las mismas condiciones, como en el seed F4: 4 períodos para paginar.
    for pista in (PISTA_A, PISTA_D):
        contratos += [
            _contrato(T_CAMBIO, pista, 50, INICIO, date(2026, 9, 14), n=0),
            _contrato(T_CAMBIO, pista, 40, date(2026, 9, 15), n=1),
        ]
    contratos += [
        _contrato(T_TERRITORIO, PISTA_B, 60, INICIO),
        _contrato(T_TERRITORIO, PISTA_B, 45, INICIO, territorio="CO"),
    ]
    general_excl = _contrato(T_EXCLUSION, PISTA_C, 35, INICIO)
    contratos.append(general_excl)
    exclusion = ExclusionTerritorial(contrato_id=general_excl.contrato_id, pais="MX")
    # Sin relationship() la unidad de trabajo no ordena por FK: se hace flush por tabla.
    with Session(db_vacia) as s:
        for lote in (titulares, contratos, [exclusion]):
            s.add_all(lote)
            s.flush()
        s.commit()
    return db_vacia


@pytest.fixture
def sesion(db_f4):
    with Session(db_f4) as s:
        yield s


@pytest.fixture
def cliente(db_f4):
    app = create_app()

    def _sesion_prueba():
        with Session(db_f4) as s:
            yield s

    app.dependency_overrides[get_session] = _sesion_prueba
    with TestClient(app) as c:
        yield c
