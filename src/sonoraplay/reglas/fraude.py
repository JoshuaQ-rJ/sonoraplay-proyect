"""RN-03 · detección de granjas de reproducción como funciones puras (EG-18, ADR-0005).

Datos entran, datos salen: sin archivos, BD ni reloj del sistema. Todo en UTC (EG-11 Q4, ADR-0002).
Una cuenta es sospechosa si cumple cualquiera de las 3 señales; sus reproducciones de todo el mes
de liquidación quedan "en_revision" (EG-11 Q3).
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from sonoraplay.config import ReglasFraudeConfig

VENTANA_24H = timedelta(hours=24)

EstadoFraude = Literal["en_revision", "valida_para_fraude"]
EN_REVISION: EstadoFraude = "en_revision"
VALIDA_PARA_FRAUDE: EstadoFraude = "valida_para_fraude"


@dataclass(frozen=True)
class Reproduccion:
    """Reproducción mínima para RN-03.

    Sale de los eventos F2 (EG-15, ADR-0004); la correspondencia de campos está en
    `docs/datos/eventos-f2.md` (`user_id` → `cuenta_id`, `device_id` → `dispositivo_id`).
    `inicio` debe ser aware: un datetime naive lanza ValueError y cualquier otra zona se
    normaliza a UTC (ADR-0002).
    """

    cuenta_id: str
    dispositivo_id: str
    artista_id: str
    inicio: datetime
    ms_escuchados: int

    def __post_init__(self) -> None:
        if self.inicio.tzinfo is None or self.inicio.utcoffset() is None:
            raise ValueError(f"inicio debe ser un datetime aware en UTC (ADR-0002): {self.inicio}")
        if self.ms_escuchados < 0:
            raise ValueError(f"ms_escuchados no puede ser negativo: {self.ms_escuchados}")
        object.__setattr__(self, "inicio", self.inicio.astimezone(UTC))

    @property
    def fin(self) -> datetime:
        return self.inicio + timedelta(milliseconds=self.ms_escuchados)


class SenalFraude(StrEnum):
    """Las 3 señales de RN-03. El informe de fraude (EG-43) las agrupa por tipo."""

    HORAS_24H = "horas_24h"
    CONCENTRACION_ARTISTA = "concentracion_artista"
    DISPOSITIVO_COMPARTIDO = "dispositivo_compartido"


@dataclass(frozen=True)
class ResultadoFraude:
    cuenta_id: str
    sospechosa: bool
    senales: frozenset[SenalFraude]


# --- Señal 1 ---------------------------------------------------------------------------------


def _max_escuchado_en_ventana(reps: Iterable[Reproduccion], ventana: timedelta) -> timedelta:
    """Máximo tiempo escuchado en cualquier ventana móvil [a, a + ventana).

    El total es lineal a trozos en `a`; sus máximos caen donde la ventana empieza en el inicio de
    una reproducción o termina en el fin de una. Se recorren esos candidatos en orden con dos
    punteros sobre las reproducciones ordenadas por inicio. Una reproducción que cruza el borde
    cuenta solo la parte que cae dentro.
    """
    intervalos = sorted((r.inicio, r.fin) for r in reps)
    if not intervalos:
        return timedelta(0)
    duracion_max = max(fin - ini for ini, fin in intervalos)
    candidatos = sorted({ini for ini, _ in intervalos} | {fin - ventana for _, fin in intervalos})

    mejor = timedelta(0)
    lo = hi = 0
    for a in candidatos:
        b = a + ventana
        while hi < len(intervalos) and intervalos[hi][0] < b:
            hi += 1
        while lo < hi and intervalos[lo][0] + duracion_max <= a:
            lo += 1
        total = sum(
            (min(fin, b) - max(ini, a) for ini, fin in intervalos[lo:hi] if fin > a),
            timedelta(0),
        )
        mejor = max(mejor, total)
    return mejor


def senal_horas_24h(reps_de_una_cuenta: Iterable[Reproduccion], cfg: ReglasFraudeConfig) -> bool:
    """RN-03 señal 1: más de `horas_max_24h` escuchadas en una ventana móvil de 24 h.

    Ventana móvil y no día calendario (ADR-0005). Exactamente 20 h no se marca.
    """
    maximo = _max_escuchado_en_ventana(reps_de_una_cuenta, VENTANA_24H)
    return maximo > timedelta(hours=cfg.horas_max_24h)


# --- Señal 2 ---------------------------------------------------------------------------------


def oyentes_unicos_por_artista(reps_del_mes: Iterable[Reproduccion]) -> dict[str, int]:
    """Cuentas distintas que escucharon a cada artista en el mes UTC (EG-11 Q2)."""
    cuentas: dict[str, set[str]] = defaultdict(set)
    for r in reps_del_mes:
        cuentas[r.artista_id].add(r.cuenta_id)
    return {artista: len(c) for artista, c in cuentas.items()}


def senal_concentracion_artista(
    reps_de_una_cuenta: Sequence[Reproduccion],
    oyentes_por_artista: Mapping[str, int],
    cfg: ReglasFraudeConfig,
) -> bool:
    """RN-03 señal 2: más del 70 % de las reproducciones del mes a un artista con < 1.000 oyentes.

    Se cuentan reproducciones, no milisegundos. Exactamente 70 % o 1.000 oyentes no se marca.
    Solo un artista puede superar el 70 %, así que basta con mirar al más escuchado.
    """
    if not reps_de_una_cuenta:
        return False
    por_artista: dict[str, int] = defaultdict(int)
    for r in reps_de_una_cuenta:
        por_artista[r.artista_id] += 1
    artista, n = max(por_artista.items(), key=lambda kv: kv[1])
    concentrada = n / len(reps_de_una_cuenta) > cfg.porcentaje_max_artista
    return concentrada and oyentes_por_artista.get(artista, 0) < cfg.oyentes_min_artista


# --- Señal 3 ---------------------------------------------------------------------------------


def cuentas_por_dispositivo(reps_del_mes: Iterable[Reproduccion]) -> dict[str, set[str]]:
    """Cuentas distintas vistas en cada dispositivo durante el mes."""
    cuentas: dict[str, set[str]] = defaultdict(set)
    for r in reps_del_mes:
        cuentas[r.dispositivo_id].add(r.cuenta_id)
    return dict(cuentas)


def senal_dispositivo_compartido(
    cuenta_id: str,
    cuentas_por_dispositivo: Mapping[str, set[str]],
    cfg: ReglasFraudeConfig,
) -> bool:
    """RN-03 señal 3: la cuenta usó algún dispositivo con más de 5 cuentas (5 no se marca)."""
    return any(
        cuenta_id in cuentas and len(cuentas) > cfg.cuentas_max_dispositivo
        for cuentas in cuentas_por_dispositivo.values()
    )


# --- Evaluación y exclusión ------------------------------------------------------------------


def evaluar_cuentas(
    reps_del_mes: Sequence[Reproduccion], cfg: ReglasFraudeConfig
) -> dict[str, ResultadoFraude]:
    """Evalúa RN-03 para cada cuenta del mes y devuelve qué señales cumplió (para EG-43).

    Los agregados (oyentes por artista, cuentas por dispositivo) se calculan una sola vez.
    Todas las reproducciones deben ser del mismo mes UTC (EG-11 Q2/Q3); si no, ValueError.
    """
    meses = {(r.inicio.year, r.inicio.month) for r in reps_del_mes}
    if len(meses) > 1:
        raise ValueError(f"evaluar_cuentas espera un solo mes UTC de liquidación: {sorted(meses)}")

    oyentes = oyentes_unicos_por_artista(reps_del_mes)
    dispositivos = cuentas_por_dispositivo(reps_del_mes)
    por_cuenta: dict[str, list[Reproduccion]] = defaultdict(list)
    for r in reps_del_mes:
        por_cuenta[r.cuenta_id].append(r)

    resultados = {}
    for cuenta_id, reps in por_cuenta.items():
        senales = set()
        if senal_horas_24h(reps, cfg):
            senales.add(SenalFraude.HORAS_24H)
        if senal_concentracion_artista(reps, oyentes, cfg):
            senales.add(SenalFraude.CONCENTRACION_ARTISTA)
        if senal_dispositivo_compartido(cuenta_id, dispositivos, cfg):
            senales.add(SenalFraude.DISPOSITIVO_COMPARTIDO)
        resultados[cuenta_id] = ResultadoFraude(cuenta_id, bool(senales), frozenset(senales))
    return resultados


def marcar_exclusion(
    reps_del_mes: Iterable[Reproduccion], resultados: Mapping[str, ResultadoFraude]
) -> list[tuple[Reproduccion, EstadoFraude]]:
    """Asigna estado a cada reproducción del mes sin borrar ni reordenar nada (EG-11 Q3).

    Todas las reproducciones de una cuenta sospechosa quedan "en_revision" (excluidas de la bolsa
    hasta la revisión); el resto queda "valida_para_fraude". Si la revisión libera la cuenta, se
    pagan como ajuste (ADR-0007).
    """
    sospechosas = {c for c, r in resultados.items() if r.sospechosa}
    return [
        (r, EN_REVISION if r.cuenta_id in sospechosas else VALIDA_PARA_FRAUDE) for r in reps_del_mes
    ]
