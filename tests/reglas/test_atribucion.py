"""CA-04 / RN-04 · pruebas de atribución UTC (EG-22)."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from sonoraplay.config import AtribucionOfflineConfig
from sonoraplay.reglas.atribucion import (
    ResultadoAtribucion,
    TipoAtribucion,
    atribuir_reproduccion,
    corregir_reloj_online,
)

CFG = AtribucionOfflineConfig()
ESCUCHA = datetime(2026, 9, 28, 12, tzinfo=UTC)


def atribuir(sync: datetime, **kw) -> ResultadoAtribucion:
    return atribuir_reproduccion(ESCUCHA, sync, True, CFG, **kw)


@pytest.mark.parametrize(
    "sync",
    [
        datetime(2026, 10, 2, 23, 58, tzinfo=UTC),
        datetime(2026, 10, 2, 23, 59, tzinfo=UTC),
        datetime(2026, 10, 2, 23, 59, 59, tzinfo=UTC),
    ],
)
def test_sincroniza_antes_o_durante_el_minuto_limite(sync):
    assert atribuir(sync) == ResultadoAtribucion(
        date(2026, 9, 1), date(2026, 9, 1), TipoAtribucion.NORMAL
    )


@pytest.mark.parametrize(
    "sync",
    [
        datetime(2026, 10, 3, tzinfo=UTC),
        datetime(2026, 10, 3, 0, 1, tzinfo=UTC),
        datetime(2026, 10, 4, tzinfo=UTC),
    ],
)
def test_tardia_es_ajuste_sin_reabrir_septiembre(sync):
    assert atribuir(sync) == ResultadoAtribucion(
        date(2026, 9, 1), date(2026, 10, 1), TipoAtribucion.AJUSTE
    )


@pytest.mark.parametrize(
    ("sync", "mes_liquidacion"),
    [
        # Octubre (se paga el 3-nov) sigue abierta el 1-nov: no se espera a noviembre.
        (datetime(2026, 11, 1, tzinfo=UTC), date(2026, 10, 1)),
        (datetime(2026, 11, 2, 23, 59, tzinfo=UTC), date(2026, 10, 1)),
        (datetime(2026, 11, 2, 23, 59, 59, tzinfo=UTC), date(2026, 10, 1)),
        # Pasado el corte de noviembre, octubre ya cerró.
        (datetime(2026, 11, 3, tzinfo=UTC), date(2026, 11, 1)),
    ],
)
def test_ajuste_va_a_la_primera_liquidacion_abierta(sync, mes_liquidacion):
    assert atribuir(sync) == ResultadoAtribucion(
        date(2026, 9, 1), mes_liquidacion, TipoAtribucion.AJUSTE
    )


def test_ajuste_muy_tardio_de_diciembre_a_enero():
    resultado = atribuir_reproduccion(
        datetime(2026, 12, 28, tzinfo=UTC),
        datetime(2027, 2, 1, tzinfo=UTC),
        True,
        CFG,
    )
    assert resultado == ResultadoAtribucion(
        date(2026, 12, 1), date(2027, 1, 1), TipoAtribucion.AJUSTE
    )


def test_ajuste_de_noviembre_sincronizado_a_inicios_de_enero_va_a_diciembre():
    resultado = atribuir_reproduccion(
        datetime(2026, 11, 20, tzinfo=UTC),
        datetime(2027, 1, 2, tzinfo=UTC),
        True,
        CFG,
    )
    assert resultado.mes_liquidacion == date(2026, 12, 1)


def test_sincronizacion_en_el_mismo_mes():
    assert atribuir(datetime(2026, 9, 29, tzinfo=UTC)).tipo == TipoAtribucion.NORMAL


def test_online_en_mes_siguiente_no_se_trata_como_offline():
    resultado = atribuir_reproduccion(ESCUCHA, datetime(2026, 10, 4, tzinfo=UTC), False, CFG)
    assert resultado.mes_liquidacion == date(2026, 9, 1)
    assert resultado.tipo == TipoAtribucion.NORMAL


def test_reloj_corregido_define_el_mes_real():
    original = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)
    corregida = datetime(2026, 10, 1, 0, 30, tzinfo=UTC)
    resultado = atribuir_reproduccion(
        original,
        datetime(2026, 10, 2, 12, tzinfo=UTC),
        True,
        CFG,
        reproducida_corregida_en=corregida,
    )
    assert resultado.mes_reproduccion == date(2026, 10, 1)
    assert resultado.mes_liquidacion == date(2026, 10, 1)


def test_corregir_reloj_online_desfasado():
    dispositivo = datetime(2026, 9, 30, 21, tzinfo=UTC)
    servidor = datetime(2026, 10, 1, 0, tzinfo=UTC)
    assert corregir_reloj_online(dispositivo, servidor, CFG, es_offline=False) == servidor


def test_no_corregir_reloj_dentro_de_tolerancia():
    servidor = ESCUCHA + timedelta(seconds=30)
    assert corregir_reloj_online(ESCUCHA, servidor, CFG, es_offline=False) == ESCUCHA


def test_corregir_reloj_no_toca_eventos_offline():
    """La sincronización tardía de un offline no es la hora de la escucha: no cambia de mes."""
    sincronizada = datetime(2026, 10, 5, tzinfo=UTC)
    assert corregir_reloj_online(ESCUCHA, sincronizada, CFG, es_offline=True) == ESCUCHA


def test_utc_desde_otra_zona():
    bogota = timezone(timedelta(hours=-5))
    reproducida = datetime(2026, 9, 30, 20, tzinfo=bogota)
    sincronizada = datetime(2026, 10, 1, 22, tzinfo=bogota)
    resultado = atribuir_reproduccion(reproducida, sincronizada, True, CFG)
    assert resultado.mes_reproduccion == date(2026, 10, 1)


def test_timestamp_sin_zona_rechazado():
    with pytest.raises(ValueError, match="zona horaria"):
        atribuir(datetime(2026, 10, 2, 23, 59))


def test_sync_antes_de_reproduccion_rechazada():
    with pytest.raises(ValueError, match="preceder"):
        atribuir(datetime(2026, 9, 27, tzinfo=UTC))


def test_diciembre_enero():
    resultado = atribuir_reproduccion(
        datetime(2026, 12, 28, tzinfo=UTC),
        datetime(2027, 1, 4, tzinfo=UTC),
        True,
        CFG,
    )
    assert resultado == ResultadoAtribucion(
        date(2026, 12, 1), date(2027, 1, 1), TipoAtribucion.AJUSTE
    )
