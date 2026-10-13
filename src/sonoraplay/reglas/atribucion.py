"""RN-04 · atribución offline por mes UTC, sin E/S ni reloj del sistema (EG-22)."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from statistics import median
from typing import Any

from sonoraplay.config import AtribucionOfflineConfig

Evento = Mapping[str, Any]


class TipoAtribucion(StrEnum):
    NORMAL = "normal"
    AJUSTE = "ajuste"


@dataclass(frozen=True)
class ResultadoAtribucion:
    mes_reproduccion: date
    mes_liquidacion: date
    tipo: TipoAtribucion


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError("Los timestamps deben tener zona horaria (ADR-0002)")
    return valor.astimezone(UTC)


def _mes(valor: datetime) -> date:
    return date(valor.year, valor.month, 1)


def _siguiente_mes(mes: date) -> date:
    return date(mes.year + (mes.month == 12), (mes.month % 12) + 1, 1)


def _mes_anterior(mes: date) -> date:
    return date(mes.year - (mes.month == 1), ((mes.month - 2) % 12) + 1, 1)


def _corte(mes: date, cfg: AtribucionOfflineConfig) -> datetime:
    """Primer instante después del corte de sincronización de `mes` (incluye el minuto 23:59)."""
    return datetime(
        mes.year, mes.month, cfg.dia_corte, cfg.hora_corte, cfg.minuto_corte, tzinfo=UTC
    ) + timedelta(minutes=1)


def corregir_reloj_online(
    dispositivo: datetime,
    servidor: datetime,
    cfg: AtribucionOfflineConfig,
    *,
    es_offline: bool,
) -> datetime:
    """Corrige eventos online si el desfase supera la tolerancia.

    Un evento offline se devuelve sin cambios: su `server_ts` es la sincronización tardía, no
    la hora de la escucha, y usarlo movería la reproducción de mes.
    """
    dispositivo, servidor = _utc(dispositivo), _utc(servidor)
    if es_offline:
        return dispositivo
    if abs((servidor - dispositivo).total_seconds()) > cfg.tolerancia_reloj_segundos:
        return servidor
    return dispositivo


def _iso_z(valor: datetime) -> str:
    return valor.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def corregir_reloj_sesion(eventos: Iterable[Evento], cfg: AtribucionOfflineConfig) -> list[Evento]:
    """Corrige el reloj de una sesión completa con un solo desfase (paso 3 de eventos-f2.md).

    El desfase es la mediana de `server_ts − device_ts` de sus eventos online. Si supera la
    tolerancia, se suma ese mismo desfase al `device_ts` de **todos** los eventos, así los tramos
    conservan su duración. Una sesión con algún evento offline se devuelve sin cambios: su
    `server_ts` es la sincronización tardía, no la hora de la escucha. Devuelve copias.
    """
    eventos = list(eventos)
    if not eventos or any(e.get("is_offline", False) for e in eventos):
        return eventos
    desfase = median(
        _utc(datetime.fromisoformat(e["server_ts"])) - _utc(datetime.fromisoformat(e["device_ts"]))
        for e in eventos
    )
    if abs(desfase.total_seconds()) <= cfg.tolerancia_reloj_segundos:
        return eventos
    return [
        {**e, "device_ts": _iso_z(datetime.fromisoformat(e["device_ts"]) + desfase)}
        for e in eventos
    ]


def atribuir_reproduccion(
    reproducida_en: datetime,
    sincronizada_en: datetime,
    es_offline: bool,
    cfg: AtribucionOfflineConfig,
    *,
    reproducida_corregida_en: datetime | None = None,
) -> ResultadoAtribucion:
    """Asigna el mes real o un ajuste sin reabrir liquidaciones cerradas.

    El corte incluye todo el minuto 23:59 UTC del día 2. Una sincronización posterior es un
    ajuste y va a la primera liquidación todavía abierta: la del mes anterior a la
    sincronización si esta llega antes del corte de su propio mes, o la del mes de la
    sincronización si no. Nunca antes del mes siguiente al de la escucha.
    """
    original = _utc(reproducida_en)
    sincronizada = _utc(sincronizada_en)
    efectiva = _utc(reproducida_corregida_en) if reproducida_corregida_en else original
    if sincronizada < efectiva:
        raise ValueError("La sincronización no puede preceder la reproducción corregida")

    mes_real = _mes(efectiva)
    mes_sync = _mes(sincronizada)
    if not es_offline or mes_sync == mes_real:
        return ResultadoAtribucion(mes_real, mes_real, TipoAtribucion.NORMAL)

    siguiente = _siguiente_mes(mes_real)
    if sincronizada < _corte(siguiente, cfg):
        return ResultadoAtribucion(mes_real, mes_real, TipoAtribucion.NORMAL)

    abierta = _mes_anterior(mes_sync) if sincronizada < _corte(mes_sync, cfg) else mes_sync
    return ResultadoAtribucion(mes_real, max(abierta, siguiente), TipoAtribucion.AJUSTE)
