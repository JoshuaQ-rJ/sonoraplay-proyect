"""RN-04 · atribución offline por mes UTC, sin E/S ni reloj del sistema (EG-22)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from sonoraplay.config import AtribucionOfflineConfig


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
    dispositivo: datetime, servidor: datetime, cfg: AtribucionOfflineConfig
) -> datetime:
    """Corrige eventos online si el desfase supera la tolerancia.

    Para eventos offline, no inferir el desfase a partir de la sincronización tardía:
    se debe proporcionar un timestamp ya corregido por una fuente confiable.
    """
    dispositivo, servidor = _utc(dispositivo), _utc(servidor)
    if abs((servidor - dispositivo).total_seconds()) > cfg.tolerancia_reloj_segundos:
        return servidor
    return dispositivo


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
