"""De eventos F2 a reproducciones para RN-01 y RN-02 (EG-19). Función pura.

Implementa los pasos de "De eventos a reproducciones" de `docs/datos/eventos-f2.md` que necesita
el esqueleto (EG-24): deduplicar por `event_id`, agrupar por `session_id`, corregir el reloj de
la sesión (EG-22), ordenar y armar los tramos continuos. Quedan fuera la resolución de artista y
la cuarentena (EG-18, EG-35) y las marcas de calidad (`sin_fin`, tramo inconsistente).
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sonoraplay.config import AtribucionOfflineConfig
from sonoraplay.reglas.atribucion import corregir_reloj_sesion
from sonoraplay.reglas.validez import ReproduccionValidez

ABREN = {"start", "resume"}
CIERRAN_TRAMO = {"pause", "skip", "end"}
CIERRAN_SESION = {"skip", "end"}
_MS = timedelta(milliseconds=1)
_ATRIBUCION = AtribucionOfflineConfig()

Evento = Mapping[str, Any]


def _ts(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


@dataclass(frozen=True)
class ReproduccionF2(ReproduccionValidez):
    """Reproducción reconstruida desde F2, con lo que RN-04 necesita para atribuirla (EG-22).

    Es una `ReproduccionValidez`, así que entra tal cual en RN-01 y RN-02; los campos extra no
    viajan a la regla pura de validez. `inicio` ya trae el reloj corregido. `sincronizado` es el
    `server_ts` del último evento de la sesión, en UTC.
    """

    is_offline: bool
    sincronizado: datetime

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.sincronizado.tzinfo is None or self.sincronizado.utcoffset() is None:
            raise ValueError(f"sincronizado debe ser un datetime aware: {self.sincronizado}")
        object.__setattr__(self, "sincronizado", self.sincronizado.astimezone(UTC))


def deduplicar(eventos: Iterable[Evento]) -> list[Evento]:
    """Un evento por `event_id`; ante un reintento queda el de menor `server_ts` (ADR-0004)."""
    por_id: dict[str, Evento] = {}
    for e in eventos:
        previo = por_id.get(e["event_id"])
        if previo is None or _ts(e["server_ts"]) < _ts(previo["server_ts"]):
            por_id[e["event_id"]] = e
    return list(por_id.values())


def tramos(sesion: Iterable[Evento]) -> list[int]:
    """ms de cada tramo continuo de una sesión ya ordenada.

    Un tramo abre con `start` o `resume` y cierra con el siguiente `pause`, `skip` o `end`. Cuenta
    `min(Δposition_ms, Δdevice_ts)` y nunca menos de 0. Un tramo sin cierre cuenta 0 (defecto
    "evento sin fin"). Los eventos fuera de orden se ignoran, igual que todo lo que llega después
    del `skip` o `end`.
    """
    resultado: list[int] = []
    abierto: Evento | None = None
    empezo = False
    for e in sesion:
        tipo = e["event_type"]
        if tipo in ABREN:
            # Solo un start, y un resume solo después de él y con el tramo anterior cerrado.
            valido = not empezo if tipo == "start" else empezo
            if abierto is None and valido:
                abierto, empezo = e, True
        elif tipo in CIERRAN_TRAMO and abierto is not None:
            d_pos = e["position_ms"] - abierto["position_ms"]
            d_ts = (_ts(e["device_ts"]) - _ts(abierto["device_ts"])) // _MS
            resultado.append(max(0, min(d_pos, d_ts)))
            abierto = None
        if tipo in CIERRAN_SESION and empezo:
            break
    if abierto is not None:
        resultado.append(0)
    return resultado


def reconstruir(
    eventos: Iterable[Evento], cfg: AtribucionOfflineConfig = _ATRIBUCION
) -> list[ReproduccionF2]:
    """Una reproducción por sesión con `start`, ordenadas por `inicio` y `session_id`.

    `reproduccion_id` = `session_id`, `cuenta_id` = `user_id`, `inicio` = `device_ts` corregido
    del `start`, `ms_continuos_max` = el tramo más largo, `is_offline` = algún evento offline y
    `sincronizado` = `server_ts` del último evento. Antes de ordenar se corrige el reloj de cada
    sesión online (`corregir_reloj_sesion`, EG-22). Una sesión sin `start` no produce reproducción.
    """
    sesiones: dict[str, list[Evento]] = defaultdict(list)
    for e in deduplicar(eventos):
        sesiones[e["session_id"]].append(e)

    reps = []
    for session_id, crudos in sesiones.items():
        evs = corregir_reloj_sesion(crudos, cfg)
        evs.sort(key=lambda e: (_ts(e["device_ts"]), _ts(e["server_ts"])))
        start = next((e for e in evs if e["event_type"] == "start"), None)
        if start is None:
            continue
        reps.append(
            ReproduccionF2(
                reproduccion_id=session_id,
                cuenta_id=start["user_id"],
                track_id=start["track_id"],
                inicio=_ts(start["device_ts"]),
                ms_continuos_max=max(tramos(evs), default=0),
                is_offline=any(e.get("is_offline", False) for e in evs),
                sincronizado=_ts(evs[-1]["server_ts"]),
            )
        )
    return sorted(reps, key=lambda r: (r.inicio, r.reproduccion_id))
