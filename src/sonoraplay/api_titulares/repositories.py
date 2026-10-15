"""Consultas sobre el reporte de regalías. Siempre filtran por el titular autenticado."""

import uuid
from datetime import date

from sqlalchemy import func
from sqlmodel import Session, col, select

from sonoraplay.api_titulares.models import Liquidacion, ReporteRegalias


def filas_ultima_liquidacion(
    session: Session, titular_id: uuid.UUID, periodo: date | None, pais: str | None
) -> list[ReporteRegalias]:
    """Filas del titular en la última liquidación **publicada** de cada mes (ADR-0007).

    La última es la de mayor `publicada_en` del mes, para todos los titulares: si una
    re-liquidación ya no incluye al titular, ese mes no le devuelve filas.
    """
    # row_number() = 1: una liquidación por mes, la más reciente en publicarse.
    orden = func.row_number().over(
        partition_by=col(Liquidacion.periodo),
        order_by=(
            col(Liquidacion.publicada_en).desc(),
            col(Liquidacion.creada_en).desc(),
            col(Liquidacion.liquidacion_id).desc(),
        ),
    )
    publicadas = select(Liquidacion.liquidacion_id, orden.label("n")).where(
        col(Liquidacion.publicada_en).is_not(None)
    )
    if periodo is not None:
        publicadas = publicadas.where(Liquidacion.periodo == periodo)
    ranking = publicadas.subquery()
    ultimas = select(ranking.c.liquidacion_id).where(ranking.c.n == 1)
    consulta = select(ReporteRegalias).where(
        ReporteRegalias.titular_id == titular_id,
        col(ReporteRegalias.liquidacion_id).in_(ultimas),
    )
    if pais is not None:
        consulta = consulta.where(ReporteRegalias.pais == pais)
    consulta = consulta.order_by(
        col(ReporteRegalias.periodo),
        col(ReporteRegalias.pais),
        col(ReporteRegalias.componente).desc(),  # suscripcion antes que publicidad
        col(ReporteRegalias.porcentaje_contractual).desc(),
    )
    return list(session.exec(consulta).all())
