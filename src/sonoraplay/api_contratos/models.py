"""Modelos SQLModel de F4 y modelos de respuesta de la API.

Las tablas las define `db/ddl/002_f4_contratos.sql` (EG-14). Aquí solo se **mapean**: nunca se
llama a `SQLModel.metadata.create_all`. Si cambia el DDL, se actualiza este archivo.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CHAR, Column, ForeignKey, Numeric, String, Text, Uuid
from sqlmodel import Field, SQLModel

# --- Tablas (espejo del DDL) -----------------------------------------------------------------


class TitularDerechos(SQLModel, table=True):
    __tablename__ = "titulares_derechos"

    titular_id: uuid.UUID = Field(primary_key=True)
    nombre: str = Field(sa_column=Column(Text, nullable=False))
    tipo: str = Field(sa_column=Column(Text, nullable=False))
    pais: str = Field(sa_column=Column(CHAR(2), nullable=False))


class Contrato(SQLModel, table=True):
    __tablename__ = "contratos"

    contrato_id: uuid.UUID = Field(primary_key=True)
    titular_id: uuid.UUID = Field(foreign_key="titulares_derechos.titular_id")
    track_id: str = Field(sa_column=Column(String(22), nullable=False))
    porcentaje: Decimal = Field(sa_column=Column(Numeric(5, 2), nullable=False))
    # NULL = condición general; un país = condición territorial adicional (Q7).
    territorio: str | None = Field(default=None, sa_column=Column(CHAR(2), nullable=True))
    valido_desde: date
    # Inclusivo; NULL = sin fecha de fin.
    valido_hasta: date | None = None


class ExclusionTerritorial(SQLModel, table=True):
    __tablename__ = "exclusiones_territoriales"

    contrato_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid, ForeignKey("contratos.contrato_id", ondelete="CASCADE"), primary_key=True
        )
    )
    pais: str = Field(sa_column=Column(CHAR(2), primary_key=True))


# --- Respuestas de la API (no son tablas) ----------------------------------------------------

PORCENTAJE_DESC = "Porcentaje de regalías del titular, de 0 a 100 (50.0 = 50 %)."


class PorcentajeVigente(SQLModel):
    titular_id: uuid.UUID
    track_id: str = Field(description="Pista cuya condición se aplicó.")
    fecha: date
    pais: str | None = Field(default=None, description="País consultado (ISO 3166-1 alfa-2).")
    porcentaje: float = Field(description=PORCENTAJE_DESC)
    territorio_aplicado: str | None = Field(
        default=None, description="País de la condición territorial usada; null = general (Q7)."
    )
    excluido: bool = Field(
        description="True si el país está excluido en la condición general (RN-08). "
        "En ese caso porcentaje = 0."
    )
    contrato_id: uuid.UUID
    valido_desde: date
    valido_hasta: date | None = Field(default=None, description="Inclusivo; null = sin fin.")


class CondicionOut(SQLModel):
    contrato_id: uuid.UUID
    track_id: str
    territorio: str | None = Field(default=None, description="null = condición general.")
    porcentaje: float = Field(description=PORCENTAJE_DESC)
    valido_desde: date
    valido_hasta: date | None = Field(default=None, description="Inclusivo; null = sin fin.")
    exclusiones: list[str] = Field(default_factory=list, description="Países excluidos (RN-08).")


class CondicionesPagina(SQLModel):
    titular_id: uuid.UUID
    total: int = Field(description="Total de períodos del titular, sin paginar.")
    limit: int
    offset: int
    condiciones: list[CondicionOut]


class Salud(SQLModel):
    status: str = "ok"


class ErrorOut(SQLModel):
    detail: str
