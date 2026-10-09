"""Health check para el contenedor y el target del ALB (ECS)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from sonoraplay.api_titulares.db import get_session
from sonoraplay.api_titulares.models import ErrorOut, Salud

router = APIRouter(tags=["salud"])


@router.get(
    "/health",
    response_model=Salud,
    summary="Estado de la API y de su conexión a PostgreSQL",
    responses={503: {"model": ErrorOut, "description": "La base de datos no responde"}},
)
def health(session: Annotated[Session, Depends(get_session)]) -> Salud:
    try:
        session.exec(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "La base de datos no responde"
        ) from None
    return Salud()
