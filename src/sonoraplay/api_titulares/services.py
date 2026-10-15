"""Armado del reporte de un titular (RF-05). `construir_reporte` es pura, sin base de datos."""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlmodel import Session

from sonoraplay.api_titulares import repositories as repo
from sonoraplay.api_titulares.models import (
    FilaReporteOut,
    ReporteOut,
    ReporteRegalias,
    TotalMesPais,
)
from sonoraplay.reporte_regalias import Componente


def texto_a_periodo(texto: str) -> date:
    """'2026-09' → date(2026, 9, 1). El router ya validó el formato."""
    anio, mes = texto.split("-")
    return date(int(anio), int(mes), 1)


def periodo_a_texto(periodo: date) -> str:
    return periodo.strftime("%Y-%m")


def construir_reporte(titular_id: uuid.UUID, filas: Sequence[ReporteRegalias]) -> ReporteOut:
    """Filas en el orden recibido y un total por mes y país, en orden de aparición."""
    totales: dict[tuple[date, str], TotalMesPais] = {}
    for f in filas:
        clave = (f.periodo, f.pais)
        if clave not in totales:
            totales[clave] = TotalMesPais(
                periodo=periodo_a_texto(f.periodo),
                pais=f.pais,
                liquidacion_id=f.liquidacion_id,
                reproducciones_validas=0,
                regalia_usd=Decimal("0.00"),
            )
        total = totales[clave]
        total.reproducciones_validas += f.reproducciones_validas
        total.regalia_usd += f.regalia_usd
    return ReporteOut(
        titular_id=titular_id,
        filas=[
            FilaReporteOut(
                periodo=periodo_a_texto(f.periodo),
                pais=f.pais,
                componente=Componente(f.componente),
                reproducciones_validas=f.reproducciones_validas,
                participacion=f.participacion,
                porcentaje_contractual=f.porcentaje_contractual,
                regalia_usd=f.regalia_usd,
                liquidacion_id=f.liquidacion_id,
            )
            for f in filas
        ],
        totales=list(totales.values()),
    )


def reporte_de_titular(
    session: Session, titular_id: uuid.UUID, periodo: str | None = None, pais: str | None = None
) -> ReporteOut:
    """Reporte del titular autenticado. Quién puede pedirlo lo decide el router (CA-08)."""
    fecha = texto_a_periodo(periodo) if periodo is not None else None
    filas = repo.filas_ultima_liquidacion(session, titular_id, fecha, pais)
    return construir_reporte(titular_id, filas)
