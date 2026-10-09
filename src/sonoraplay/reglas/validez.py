"""RN-01 (validez de 30 s) y RN-02 (tope diario) como funciones puras (EG-17).

Datos entran, datos salen: sin archivos, BD ni reloj del sistema, para portarlas a Spark en el
Sprint 4. Todo en UTC (EG-11 Q4, ADR-0002). Los umbrales salen de `ReglasValidezConfig`.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from sonoraplay.config import ReglasValidezConfig


@dataclass(frozen=True)
class ReproduccionValidez:
    """Reproducción ya reconstruida, con lo mínimo para RN-01 y RN-02.

    Sale de los eventos F2 (EG-15, ADR-0004); la correspondencia de campos está en
    `docs/datos/eventos-f2.md`. `ms_continuos_max` es el tramo continuo más largo: una pausa,
    un seek o una interrupción cortan el tramo (EG-11 Q1).
    `inicio` debe ser aware: un datetime naive lanza ValueError y cualquier otra zona se normaliza
    a UTC (ADR-0002).
    """

    reproduccion_id: str
    cuenta_id: str
    track_id: str
    inicio: datetime
    ms_continuos_max: int

    def __post_init__(self) -> None:
        if self.inicio.tzinfo is None or self.inicio.utcoffset() is None:
            raise ValueError(f"inicio debe ser un datetime aware en UTC (ADR-0002): {self.inicio}")
        if self.ms_continuos_max < 0:
            raise ValueError(f"ms_continuos_max no puede ser negativo: {self.ms_continuos_max}")
        object.__setattr__(self, "inicio", self.inicio.astimezone(UTC))


class MotivoValidez(StrEnum):
    """Por qué una reproducción se paga o no. Lo reutilizan el informe de fraude y la liquidación.

    Las no pagables quedan marcadas, no se borran.
    """

    PAGABLE = "pagable"
    DURACION_INSUFICIENTE = "duracion_insuficiente"
    TOPE_DIARIO = "tope_diario"


@dataclass(frozen=True)
class ResultadoValidez:
    reproduccion_id: str
    valida_rn01: bool
    pagable: bool
    motivo: MotivoValidez


def es_valida(rep: ReproduccionValidez, cfg: ReglasValidezConfig) -> bool:
    """RN-01: válida si tiene un tramo continuo de al menos 30 s (exactamente 30 s es válido)."""
    return rep.ms_continuos_max >= cfg.segundos_min_validez * 1_000


def dia_utc(rep: ReproduccionValidez) -> date:
    """Día de RN-02: la fecha UTC del inicio (EG-11 Q4, ADR-0002)."""
    return rep.inicio.date()


def aplicar_tope_diario(
    reps: Sequence[ReproduccionValidez], cfg: ReglasValidezConfig
) -> list[ResultadoValidez]:
    """RN-02: solo las 10 primeras reproducciones válidas por track, usuario y día UTC se pagan.

    Solo las válidas por RN-01 compiten por el tope. El orden es por `inicio` y desempata por
    `reproduccion_id`, así el resultado no depende del orden de entrada. Devuelve un resultado por
    reproducción, en el mismo orden de la entrada. Un `reproduccion_id` repetido lanza ValueError.
    """
    vistos: set[str] = set()
    for r in reps:
        if r.reproduccion_id in vistos:
            raise ValueError(f"reproduccion_id repetido: {r.reproduccion_id}")
        vistos.add(r.reproduccion_id)

    grupos: dict[tuple[str, str, date], list[ReproduccionValidez]] = defaultdict(list)
    for r in reps:
        if es_valida(r, cfg):
            grupos[(r.cuenta_id, r.track_id, dia_utc(r))].append(r)

    fuera_de_tope: set[str] = set()
    for grupo in grupos.values():
        ordenado = sorted(grupo, key=lambda r: (r.inicio, r.reproduccion_id))
        fuera_de_tope.update(r.reproduccion_id for r in ordenado[cfg.max_reproducciones_dia :])

    resultados = []
    for r in reps:
        if not es_valida(r, cfg):
            motivo = MotivoValidez.DURACION_INSUFICIENTE
        elif r.reproduccion_id in fuera_de_tope:
            motivo = MotivoValidez.TOPE_DIARIO
        else:
            motivo = MotivoValidez.PAGABLE
        resultados.append(
            ResultadoValidez(
                reproduccion_id=r.reproduccion_id,
                valida_rn01=motivo != MotivoValidez.DURACION_INSUFICIENTE,
                pagable=motivo == MotivoValidez.PAGABLE,
                motivo=motivo,
            )
        )
    return resultados
