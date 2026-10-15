"""Endpoints de contratos F4. Solo HTTP: las reglas están en `services`."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlmodel import Session

from sonoraplay.api_contratos import services
from sonoraplay.api_contratos.db import get_session
from sonoraplay.api_contratos.models import CondicionesPagina, ErrorOut, PorcentajeVigente

router = APIRouter(prefix="/titulares", tags=["contratos"])

SesionDep = Annotated[Session, Depends(get_session)]
TitularId = Annotated[uuid.UUID, Path(description="UUID del titular de derechos.")]
NO_ENCONTRADO = {404: {"model": ErrorOut, "description": "Titular o condición no encontrada"}}


@router.get(
    "/{titular_id}/porcentaje",
    response_model=PorcentajeVigente,
    summary="% vigente de un titular en una fecha (RN-07, Q7, RN-08)",
    responses=NO_ENCONTRADO,
)
def obtener_porcentaje(
    session: SesionDep,
    titular_id: TitularId,
    fecha: Annotated[date, Query(description="Fecha de la reproducción (YYYY-MM-DD).")],
    track_id: Annotated[
        str | None,
        Query(
            max_length=22,
            description="Pista. Si se omite, se usa la menor pista del titular con condición "
            "vigente (en F4 todas sus pistas comparten condiciones).",
        ),
    ] = None,
    pais: Annotated[
        str | None,
        Query(
            pattern="^[A-Z]{2}$",
            description="País de la reproducción (ISO 3166-1 alfa-2, en mayúsculas).",
        ),
    ] = None,
) -> PorcentajeVigente:
    try:
        return services.porcentaje_vigente(session, titular_id, fecha, track_id, pais)
    except (services.TitularNoEncontrado, services.SinCondicionVigente) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None


@router.get(
    "/{titular_id}/condiciones",
    response_model=CondicionesPagina,
    summary="Períodos de vigencia y exclusiones territoriales de un titular (RN-08)",
    responses=NO_ENCONTRADO,
)
def listar_condiciones(
    session: SesionDep,
    titular_id: TitularId,
    limit: Annotated[int, Query(ge=1, le=1000, description="Máximo de períodos.")] = 100,
    offset: Annotated[int, Query(ge=0, description="Períodos a saltar.")] = 0,
) -> CondicionesPagina:
    try:
        return services.listar_condiciones(session, titular_id, limit, offset)
    except services.TitularNoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
