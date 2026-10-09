"""Consultas sobre F4. Sin reglas de negocio: qué condición aplica lo decide `services`."""

import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import ColumnElement, func, nulls_first, or_
from sqlmodel import Session, col, select

from sonoraplay.api_contratos.models import Contrato, ExclusionTerritorial, TitularDerechos


def _vigente_en(fecha: date) -> ColumnElement[bool]:
    # valido_hasta es INCLUSIVO: el DDL lo trata como daterange(desde, hasta + 1, '[)').
    # Con 50 % hasta el 14 y 40 % desde el 15, el día 14 cae en el primer período.
    return (col(Contrato.valido_desde) <= fecha) & or_(
        col(Contrato.valido_hasta).is_(None), col(Contrato.valido_hasta) >= fecha
    )


def titular_existe(session: Session, titular_id: uuid.UUID) -> bool:
    return session.get(TitularDerechos, titular_id) is not None


def pista_con_vigencia(session: Session, titular_id: uuid.UUID, fecha: date) -> str | None:
    """Menor track_id del titular con alguna condición vigente en `fecha` (orden estable)."""
    consulta = select(func.min(Contrato.track_id)).where(
        Contrato.titular_id == titular_id, _vigente_en(fecha)
    )
    return session.exec(consulta).one()


def condiciones_vigentes(
    session: Session, titular_id: uuid.UUID, track_id: str, fecha: date
) -> list[Contrato]:
    """Condición general y territoriales de una pista vigentes en `fecha`."""
    consulta = select(Contrato).where(
        Contrato.titular_id == titular_id,
        Contrato.track_id == track_id,
        _vigente_en(fecha),
    )
    return list(session.exec(consulta).all())


def exclusiones_de(session: Session, contrato_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Países excluidos por contrato, ordenados."""
    if not contrato_ids:
        return {}
    consulta = (
        select(ExclusionTerritorial)
        .where(col(ExclusionTerritorial.contrato_id).in_(contrato_ids))
        .order_by(ExclusionTerritorial.contrato_id, ExclusionTerritorial.pais)
    )
    por_contrato: dict[uuid.UUID, list[str]] = defaultdict(list)
    for fila in session.exec(consulta):
        por_contrato[fila.contrato_id].append(fila.pais)
    return dict(por_contrato)


def contar_condiciones(session: Session, titular_id: uuid.UUID) -> int:
    consulta = select(func.count()).select_from(Contrato).where(Contrato.titular_id == titular_id)
    return session.exec(consulta).one()


def condiciones_paginadas(
    session: Session, titular_id: uuid.UUID, limit: int, offset: int
) -> list[Contrato]:
    """Todos los períodos del titular. Orden estable: pista, general primero, fecha de inicio."""
    consulta = (
        select(Contrato)
        .where(Contrato.titular_id == titular_id)
        .order_by(
            Contrato.track_id,
            nulls_first(col(Contrato.territorio)),
            Contrato.valido_desde,
            Contrato.contrato_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.exec(consulta).all())
