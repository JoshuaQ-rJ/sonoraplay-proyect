"""Endpoints del reporte de regalías. Solo HTTP: el armado del reporte está en `services`."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlmodel import Session

from sonoraplay.api_titulares import services
from sonoraplay.api_titulares.auth import TitularAutenticado
from sonoraplay.api_titulares.db import get_session
from sonoraplay.api_titulares.models import ErrorOut, ReporteOut

router = APIRouter(tags=["reportes"])

# Mismo mensaje exista o no el titular pedido: no permite averiguar qué titulares hay (CA-08).
NO_PERMITIDO = "No tiene permiso para consultar este titular"

Periodo = Annotated[
    str | None,
    Query(
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Mes a consultar (YYYY-MM). Si se omite, todos los meses liquidados.",
        examples=["2026-09"],
    ),
]
Pais = Annotated[
    str | None,
    Query(pattern="^[A-Z]{2}$", description="País de facturación (ISO 3166-1 alfa-2)."),
]

NO_AUTENTICADO = {401: {"model": ErrorOut, "description": "Falta el token, venció o es inválido"}}
PROHIBIDO = {403: {"model": ErrorOut, "description": "El titular pedido no es el del token"}}


def titular_propio(
    titular_id: Annotated[uuid.UUID, Path(description="UUID del titular (debe ser el del token).")],
    autenticado: TitularAutenticado,
) -> uuid.UUID:
    """CA-08 / RN-11: 403 si el titular del path no es el del token.

    Corre antes que `get_session` (va primero en la firma del endpoint), así que el 403 se
    decide sin consultar la base.
    """
    if titular_id != autenticado:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_PERMITIDO)
    return autenticado


@router.get(
    "/me/reportes",
    response_model=ReporteOut,
    summary="Reporte de regalías del titular del token (recomendado)",
    responses=NO_AUTENTICADO,
)
def mi_reporte(
    titular_id: TitularAutenticado,
    session: Annotated[Session, Depends(get_session)],
    periodo: Periodo = None,
    pais: Pais = None,
) -> ReporteOut:
    """Forma recomendada para los sellos: el titular sale del token, no hay ID que manipular."""
    return services.reporte_de_titular(session, titular_id, periodo, pais)


@router.get(
    "/titulares/{titular_id}/reportes",
    response_model=ReporteOut,
    summary="Reporte de regalías de un titular (solo el propio, CA-08)",
    responses={**NO_AUTENTICADO, **PROHIBIDO},
)
def reporte_titular(
    titular_id: Annotated[uuid.UUID, Depends(titular_propio)],
    session: Annotated[Session, Depends(get_session)],
    periodo: Periodo = None,
    pais: Pais = None,
) -> ReporteOut:
    """Igual que `/me/reportes`, pero con el titular en el path. Otro titular → 403."""
    return services.reporte_de_titular(session, titular_id, periodo, pais)
