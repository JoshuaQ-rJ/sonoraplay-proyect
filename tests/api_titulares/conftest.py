"""Reportes de regalías insertados a mano, tokens de prueba y cliente HTTP (EG-21).

El secreto de firma es **de prueba**: se pone con `monkeypatch` y nunca sale de `.env`.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from sonoraplay.api_titulares.auth import (
    ALGORITMO,
    AUDIENCIA,
    EMISOR,
    VAR_SECRETO,
    emitir_token,
)
from sonoraplay.api_titulares.db import get_session
from sonoraplay.api_titulares.main import create_app
from sonoraplay.api_titulares.models import Liquidacion, ReporteRegalias
from sonoraplay.reporte_regalias import Componente, FilaReporte

SECRETO_PRUEBA = "solo-para-pruebas-" + "x" * 32

T_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
T_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
T_SIN_REPORTE = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
T_INEXISTENTE = uuid.UUID("99999999-9999-4999-8999-999999999999")

AGO, SEP = date(2026, 8, 1), date(2026, 9, 1)
LIQ_AGO = uuid.UUID("0a000000-0000-4000-8000-000000000001")
# Septiembre se liquidó dos veces (ADR-0007): la API debe mostrar LIQ_SEP_V2.
LIQ_SEP_V1 = uuid.UUID("09000000-0000-4000-8000-000000000001")
LIQ_SEP_V2 = uuid.UUID("09000000-0000-4000-8000-000000000002")
# Creada después de V2 pero sin publicar: nunca se muestra.
LIQ_SEP_BORRADOR = uuid.UUID("09000000-0000-4000-8000-000000000003")

CUANDO = datetime(2026, 10, 1, 12, tzinfo=UTC)


def fila(titular, periodo, pais, componente, repro, part, pct, usd) -> FilaReporte:
    return FilaReporte(
        titular_id=titular,
        periodo=periodo,
        pais=pais,
        componente=Componente(componente),
        reproducciones_validas=repro,
        participacion=Decimal(part),
        porcentaje_contractual=Decimal(pct),
        regalia_usd=Decimal(usd),
    )


# Caso del criterio 1 de la EG-23: CO, suscripción 52.000 × 5 % y publicidad 9.000 × 10 %,
# contrato 80 % → 2.080,00 + 720,00 = 2.800,00 USD.
FILAS_A_SEP_V2 = [
    fila(T_A, SEP, "CO", "suscripcion", 1200, "0.05", "80", "2080.00"),
    fila(T_A, SEP, "CO", "publicidad", 900, "0.10", "80", "720.00"),
    # Cambio de % a mitad de mes (RN-07): una fila por cada %.
    fila(T_A, SEP, "MX", "suscripcion", 700, "0.029167", "50", "758.33"),
    fila(T_A, SEP, "MX", "suscripcion", 500, "0.020833", "40", "433.33"),
]
FILAS_B_SEP_V2 = [fila(T_B, SEP, "AR", "suscripcion", 4321, "0.123456", "65", "1234.56")]
FILAS_A_SEP_V1 = [fila(T_A, SEP, "CO", "suscripcion", 1000, "0.04", "80", "1000.00")]
FILAS_A_BORRADOR = [fila(T_A, SEP, "CO", "suscripcion", 1, "0.000001", "80", "9999.99")]
FILAS_A_AGO = [fila(T_A, AGO, "CO", "suscripcion", 800, "0.03", "80", "500.00")]


@pytest.fixture
def db_reportes(db_vacia):
    with Session(db_vacia) as s:
        s.execute(
            text(
                "INSERT INTO titulares_derechos (titular_id, nombre, tipo, pais) VALUES "
                "(:a, 'Sello A', 'sello', 'CO'), (:b, 'Sello B', 'sello', 'AR'), "
                "(:c, 'Distri sin reporte', 'distribuidora', 'MX')"
            ),
            {"a": T_A, "b": T_B, "c": T_SIN_REPORTE},
        )
        s.add_all(
            [
                Liquidacion(
                    liquidacion_id=LIQ_AGO, periodo=AGO, creada_en=CUANDO, publicada_en=CUANDO
                ),
                Liquidacion(
                    liquidacion_id=LIQ_SEP_V1, periodo=SEP, creada_en=CUANDO, publicada_en=CUANDO
                ),
                Liquidacion(
                    liquidacion_id=LIQ_SEP_V2,
                    periodo=SEP,
                    creada_en=CUANDO + timedelta(days=4),
                    publicada_en=CUANDO + timedelta(days=4, hours=1),
                ),
                Liquidacion(
                    liquidacion_id=LIQ_SEP_BORRADOR,
                    periodo=SEP,
                    creada_en=CUANDO + timedelta(days=6),
                ),
            ]
        )
        s.flush()
        lotes = {
            LIQ_AGO: FILAS_A_AGO,
            LIQ_SEP_V1: FILAS_A_SEP_V1,
            LIQ_SEP_V2: FILAS_A_SEP_V2 + FILAS_B_SEP_V2,
            LIQ_SEP_BORRADOR: FILAS_A_BORRADOR,
        }
        for liq, filas in lotes.items():
            s.add_all(ReporteRegalias.desde_fila(f, liq) for f in filas)
        s.commit()
    return db_vacia


@pytest.fixture
def sesion(db_reportes):
    with Session(db_reportes) as s:
        yield s


@pytest.fixture
def secreto(monkeypatch):
    monkeypatch.setenv(VAR_SECRETO, SECRETO_PRUEBA)
    return SECRETO_PRUEBA


@pytest.fixture
def token(secreto) -> Callable[..., str]:
    """`token(T_A)` = token válido; `token(T_A, aud="otra")` cambia o agrega claims."""

    def _token(titular: uuid.UUID, clave: str = secreto, **claims) -> str:
        if not claims:
            return emitir_token(titular, clave, timedelta(hours=1))
        ahora = datetime.now(UTC)
        base = {
            "sub": str(titular),
            "iss": EMISOR,
            "aud": AUDIENCIA,
            "iat": ahora,
            "exp": ahora + timedelta(hours=1),
        }
        base.update(claims)
        return jwt.encode({k: v for k, v in base.items() if v is not None}, clave, ALGORITMO)

    return _token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def app_titulares(secreto):
    return create_app()


@pytest.fixture
def cliente(app_titulares, db_reportes):
    def _sesion_prueba():
        with Session(db_reportes) as s:
            yield s

    app_titulares.dependency_overrides[get_session] = _sesion_prueba
    with TestClient(app_titulares) as c:
        yield c
