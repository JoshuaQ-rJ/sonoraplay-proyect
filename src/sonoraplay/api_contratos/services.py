"""Reglas de F4: vigencia (RN-07), condición territorial (Q7) y exclusiones (RN-08).

`elegir_condicion` es pura, sin base de datos; el resto orquesta los repositorios.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlmodel import Session

from sonoraplay.api_contratos import repositories as repo
from sonoraplay.api_contratos.models import (
    CondicionesPagina,
    CondicionOut,
    Contrato,
    PorcentajeVigente,
)


class TitularNoEncontrado(LookupError):
    pass


class SinCondicionVigente(LookupError):
    pass


@dataclass(frozen=True)
class Eleccion:
    contrato: Contrato
    excluido: bool


def elegir_condicion(
    vigentes: list[Contrato], exclusiones: dict[uuid.UUID, list[str]], pais: str | None
) -> Eleccion:
    """Elige la condición que aplica a una pista entre las vigentes en una fecha.

    1. RN-08: si `pais` está excluido en la condición general vigente, se excluye. La exclusión
       manda sobre una condición territorial (modelo-f4: la territorial no sustituye RN-08).
    2. Q7: si hay una condición territorial vigente para `pais`, se usa esa.
    3. Si no, la condición general (`territorio` NULL).

    El DDL impide solapamientos por titular/pista/territorio, así que hay a lo sumo una general
    y una territorial por país.
    """
    general = next((c for c in vigentes if c.territorio is None), None)
    if (
        general is not None
        and pais is not None
        and pais in exclusiones.get(general.contrato_id, [])
    ):
        return Eleccion(general, excluido=True)
    if pais is not None:
        territorial = next((c for c in vigentes if c.territorio == pais), None)
        if territorial is not None:
            return Eleccion(territorial, excluido=False)
    if general is not None:
        return Eleccion(general, excluido=False)
    raise SinCondicionVigente("El titular no tiene una condición vigente en esa fecha")


def porcentaje_vigente(
    session: Session,
    titular_id: uuid.UUID,
    fecha: date,
    track_id: str | None = None,
    pais: str | None = None,
) -> PorcentajeVigente:
    """% que aplica a un titular en una fecha, opcionalmente para una pista y un país.

    Sin `track_id` se usa la menor pista del titular con condición vigente: en el seed F4 todas
    las pistas de un titular comparten condiciones (EG-14), así que cualquiera sirve.
    """
    if not repo.titular_existe(session, titular_id):
        raise TitularNoEncontrado("Titular no encontrado")
    if track_id is None:
        track_id = repo.pista_con_vigencia(session, titular_id, fecha)
        if track_id is None:
            raise SinCondicionVigente("El titular no tiene una condición vigente en esa fecha")
    vigentes = repo.condiciones_vigentes(session, titular_id, track_id, fecha)
    exclusiones = repo.exclusiones_de(session, [c.contrato_id for c in vigentes])
    eleccion = elegir_condicion(vigentes, exclusiones, pais)
    c = eleccion.contrato
    return PorcentajeVigente(
        titular_id=titular_id,
        track_id=track_id,
        fecha=fecha,
        pais=pais,
        porcentaje=0.0 if eleccion.excluido else float(c.porcentaje),
        territorio_aplicado=c.territorio,
        excluido=eleccion.excluido,
        contrato_id=c.contrato_id,
        valido_desde=c.valido_desde,
        valido_hasta=c.valido_hasta,
    )


def listar_condiciones(
    session: Session, titular_id: uuid.UUID, limit: int, offset: int
) -> CondicionesPagina:
    """Períodos de vigencia del titular con sus exclusiones territoriales (RN-08)."""
    if not repo.titular_existe(session, titular_id):
        raise TitularNoEncontrado("Titular no encontrado")
    contratos = repo.condiciones_paginadas(session, titular_id, limit, offset)
    exclusiones = repo.exclusiones_de(session, [c.contrato_id for c in contratos])
    return CondicionesPagina(
        titular_id=titular_id,
        total=repo.contar_condiciones(session, titular_id),
        limit=limit,
        offset=offset,
        condiciones=[
            CondicionOut(
                contrato_id=c.contrato_id,
                track_id=c.track_id,
                territorio=c.territorio,
                porcentaje=float(c.porcentaje),
                valido_desde=c.valido_desde,
                valido_hasta=c.valido_hasta,
                exclusiones=exclusiones.get(c.contrato_id, []),
            )
            for c in contratos
        ],
    )
