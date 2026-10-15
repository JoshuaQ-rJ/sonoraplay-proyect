"""Modelos SQLModel del reporte de regalías y modelos de respuesta de la API.

Las tablas las define `db/ddl/003_reportes_regalias.sql` (EG-21). Aquí solo se **mapean**: nunca se
llama a `SQLModel.metadata.create_all`. Si cambia el DDL, se actualiza este archivo.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer
from sqlalchemy import CHAR, Column, DateTime, Numeric, Text, Uuid
from sqlmodel import Field, SQLModel

from sonoraplay.reporte_regalias import CENTAVO, ESCALA_PARTICIPACION, Componente, FilaReporte

# --- Tablas (espejo del DDL) -----------------------------------------------------------------
# Sin FK declaradas en el ORM: el DDL las impone y esta API solo lee.


class Liquidacion(SQLModel, table=True):
    __tablename__ = "liquidaciones"

    liquidacion_id: uuid.UUID = Field(primary_key=True)
    periodo: date
    creada_en: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    # NULL = en proceso; la API no la muestra.
    publicada_en: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class ReporteRegalias(SQLModel, table=True):
    __tablename__ = "reporte_regalias"

    liquidacion_id: uuid.UUID = Field(sa_column=Column(Uuid, primary_key=True))
    titular_id: uuid.UUID = Field(sa_column=Column(Uuid, primary_key=True))
    periodo: date
    pais: str = Field(sa_column=Column(CHAR(2), primary_key=True))
    componente: str = Field(sa_column=Column(Text, primary_key=True))
    reproducciones_validas: int
    participacion: Decimal = Field(sa_column=Column(Numeric(9, 6), nullable=False))
    porcentaje_contractual: Decimal = Field(sa_column=Column(Numeric(5, 2), primary_key=True))
    regalia_usd: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))

    @classmethod
    def desde_fila(cls, fila: FilaReporte, liquidacion_id: uuid.UUID) -> "ReporteRegalias":
        """Fila del contrato (EG-23 / EG-37) lista para insertar en una liquidación."""
        return cls(
            liquidacion_id=liquidacion_id,
            titular_id=fila.titular_id,
            periodo=fila.periodo,
            pais=fila.pais,
            componente=str(fila.componente),
            reproducciones_validas=fila.reproducciones_validas,
            participacion=fila.participacion,
            porcentaje_contractual=fila.porcentaje_contractual,
            regalia_usd=fila.regalia_usd,
        )


# --- Respuestas de la API (no son tablas) ----------------------------------------------------
# Los Decimal se serializan como string con escala fija: un float perdería centavos (RNF-02).


def _texto_con_escala(escala: Decimal) -> PlainSerializer:
    return PlainSerializer(lambda d: str(d.quantize(escala)), return_type=str, when_used="json")


Dinero = Annotated[Decimal, _texto_con_escala(CENTAVO)]
Porcentaje = Annotated[Decimal, _texto_con_escala(CENTAVO)]
Participacion = Annotated[Decimal, _texto_con_escala(ESCALA_PARTICIPACION)]

PERIODO_DESC = "Mes liquidado (YYYY-MM, UTC)."
DINERO_DESC = 'USD como string con 2 decimales (ROUND_HALF_UP), p. ej. "2800.00".'


class FilaReporteOut(SQLModel):
    periodo: str = Field(description=PERIODO_DESC, schema_extra={"examples": ["2026-09"]})
    pais: str = Field(description="País de facturación, ISO 3166-1 alfa-2 (Q6).")
    componente: Componente = Field(
        description="Componente de la bolsa (Q8): suscripcion = planes pagos, "
        "publicidad = plan gratuito."
    )
    reproducciones_validas: int
    participacion: Participacion = Field(
        description="Fracción de las reproducciones válidas del componente en ese país, de 0 a 1, "
        "como string con 6 decimales.",
        schema_extra={"examples": ["0.050000"]},
    )
    porcentaje_contractual: Porcentaje = Field(
        description="% contractual aplicado, de 0 a 100, como string con 2 decimales. Si el % "
        "cambió a mitad de mes (RN-07) hay una fila por cada %.",
        schema_extra={"examples": ["80.00"]},
    )
    regalia_usd: Dinero = Field(description=DINERO_DESC, schema_extra={"examples": ["2080.00"]})
    liquidacion_id: uuid.UUID = Field(description="Liquidación de la que sale la fila.")


class TotalMesPais(SQLModel):
    periodo: str = Field(description=PERIODO_DESC)
    pais: str
    liquidacion_id: uuid.UUID
    reproducciones_validas: int
    regalia_usd: Dinero = Field(description=DINERO_DESC, schema_extra={"examples": ["2800.00"]})


class ReporteOut(SQLModel):
    titular_id: uuid.UUID
    filas: list[FilaReporteOut]
    totales: list[TotalMesPais] = Field(description="Suma de las filas por mes y país.")


class Salud(SQLModel):
    status: str = "ok"


class ErrorOut(SQLModel):
    detail: str
