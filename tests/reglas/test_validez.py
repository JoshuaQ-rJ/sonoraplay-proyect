"""Pruebas de RN-01 (validez de 30 s) y RN-02 (tope diario) · EG-17 · EG-11 Q1/Q4 · ADR-0002."""

import copy
import random
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from sonoraplay.reglas.validez import (
    MotivoValidez,
    ReproduccionValidez,
    ResultadoValidez,
    aplicar_tope_diario,
    dia_utc,
    es_valida,
)

from sonoraplay.config import ReglasValidezConfig

CFG = ReglasValidezConfig()
BASE = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
BOGOTA = timezone(timedelta(hours=-5))


def rep(
    rid: str = "r00",
    cuenta: str = "c1",
    track: str = "t1",
    inicio: datetime = BASE,
    ms: int = 180_000,
) -> ReproduccionValidez:
    """Fábrica de reproducciones con valores por defecto válidos (3 min continuos)."""
    return ReproduccionValidez(
        reproduccion_id=rid,
        cuenta_id=cuenta,
        track_id=track,
        inicio=inicio,
        ms_continuos_max=ms,
    )


def seguidas(n: int, desde: datetime = BASE, prefijo: str = "r", **kw) -> list:
    """`n` reproducciones válidas separadas 1 min, con ids `r00`, `r01`... en orden de inicio."""
    return [
        rep(rid=f"{prefijo}{i:02d}", inicio=desde + timedelta(minutes=i), **kw) for i in range(n)
    ]


def motivos(resultados: list[ResultadoValidez]) -> list[MotivoValidez]:
    return [r.motivo for r in resultados]


def pagables(resultados: list[ResultadoValidez]) -> int:
    return sum(r.pagable for r in resultados)


# --- CA-01 / RN-01: tramo continuo >= 30 s ---------------------------------------------------


@pytest.mark.parametrize(
    ("ms", "esperado"),
    [
        pytest.param(29_000, False, id="29s"),
        pytest.param(29_999, False, id="29999ms"),
        pytest.param(30_000, True, id="limite-30000ms"),
        pytest.param(30 * 1_000, True, id="30s"),
        pytest.param(31_000, True, id="31s"),
        pytest.param(0, False, id="cero"),
        # EG-11 Q1: 15 s + pausa + 20 s; la pausa reinicia el conteo y el tramo más largo es 20 s.
        pytest.param(max(15_000, 20_000), False, id="pausa-15s-mas-20s"),
    ],
)
def test_es_valida(ms, esperado):
    assert es_valida(rep(ms=ms), CFG) is esperado


# --- CA-02 / RN-02: máximo 10 por track, usuario y día UTC -----------------------------------


def test_once_validas_mismo_dia_solo_cuentan_las_diez_primeras():
    resultados = aplicar_tope_diario(seguidas(11), CFG)

    assert motivos(resultados) == [MotivoValidez.PAGABLE] * 10 + [MotivoValidez.TOPE_DIARIO]
    undecima = resultados[10]
    assert undecima == ResultadoValidez(
        reproduccion_id="r10", valida_rn01=True, pagable=False, motivo=MotivoValidez.TOPE_DIARIO
    )


@pytest.mark.parametrize(
    "reordenar",
    [
        pytest.param(lambda reps: list(reversed(reps)), id="invertido"),
        pytest.param(lambda reps: random.Random(42).sample(reps, len(reps)), id="barajado"),
    ],
)
def test_tope_no_depende_del_orden_de_entrada(reordenar):
    entrada = reordenar(seguidas(11))
    resultados = aplicar_tope_diario(entrada, CFG)

    fuera = [r.reproduccion_id for r in resultados if not r.pagable]
    assert fuera == ["r10"]


def test_empate_de_inicio_desempata_por_reproduccion_id():
    reps = [rep(rid=f"r{i:02d}", inicio=BASE) for i in range(11)]
    for entrada in (reps, list(reversed(reps))):
        resultados = aplicar_tope_diario(entrada, CFG)
        assert [r.reproduccion_id for r in resultados if not r.pagable] == ["r10"]


def test_adr0002_once_entre_2350_y_2359_utc():
    desde = datetime(2026, 9, 10, 23, 50, tzinfo=UTC)
    reps = [rep(rid=f"r{i:02d}", inicio=desde + timedelta(seconds=54 * i)) for i in range(11)]
    assert reps[-1].inicio == datetime(2026, 9, 10, 23, 59, tzinfo=UTC)
    assert pagables(aplicar_tope_diario(reps, CFG)) == 10


def test_exactamente_diez_son_todas_pagables():
    resultados = aplicar_tope_diario(seguidas(10), CFG)
    assert all(r.pagable for r in resultados)


def test_no_valida_por_rn01_no_consume_cupo():
    reps = seguidas(10) + [rep(rid="corta", inicio=BASE + timedelta(seconds=30), ms=29_000)]
    resultados = aplicar_tope_diario(reps, CFG)

    assert pagables(resultados) == 10
    assert resultados[-1] == ResultadoValidez(
        reproduccion_id="corta",
        valida_rn01=False,
        pagable=False,
        motivo=MotivoValidez.DURACION_INSUFICIENTE,
    )


def test_solo_las_validas_compiten_por_el_tope():
    # 12 reproducciones; la 2.ª dura 29 s. Las 11 válidas compiten: queda fuera la 12.ª, no la 11.ª.
    reps = seguidas(12)
    reps[1] = rep(rid=reps[1].reproduccion_id, inicio=reps[1].inicio, ms=29_000)
    resultados = aplicar_tope_diario(reps, CFG)

    assert resultados[1].motivo == MotivoValidez.DURACION_INSUFICIENTE
    assert resultados[10].motivo == MotivoValidez.PAGABLE
    assert resultados[11].motivo == MotivoValidez.TOPE_DIARIO


@pytest.mark.parametrize(
    ("grupo_a", "grupo_b"),
    [
        pytest.param({"track": "A"}, {"track": "B"}, id="dos-tracks-mismo-usuario"),
        pytest.param({"cuenta": "c1"}, {"cuenta": "c2"}, id="dos-usuarios-mismo-track"),
    ],
)
def test_tope_es_por_track_usuario_y_dia(grupo_a, grupo_b):
    reps = seguidas(11, prefijo="a", **grupo_a) + seguidas(11, prefijo="b", **grupo_b)
    resultados = aplicar_tope_diario(reps, CFG)

    assert pagables(resultados) == 20
    assert {r.reproduccion_id for r in resultados if not r.pagable} == {"a10", "b10"}


def test_sin_reproducciones():
    assert aplicar_tope_diario([], CFG) == []


def test_reproduccion_id_duplicado_lanza_value_error():
    with pytest.raises(ValueError, match="reproduccion_id"):
        aplicar_tope_diario([rep(rid="x"), rep(rid="x", inicio=BASE + timedelta(minutes=1))], CFG)


def test_resultado_conserva_el_orden_de_entrada():
    entrada = list(reversed(seguidas(11)))
    resultados = aplicar_tope_diario(entrada, CFG)
    assert [r.reproduccion_id for r in resultados] == [r.reproduccion_id for r in entrada]


# --- CA-02 / día UTC (EG-11 Q4, ADR-0002) ----------------------------------------------------


def test_once_repartidas_en_dos_dias_utc_cuentan_todas():
    reps = seguidas(6) + seguidas(5, desde=BASE + timedelta(days=1), prefijo="d2-")
    assert pagables(aplicar_tope_diario(reps, CFG)) == 11


def test_adr0002_seis_a_las_2359_y_cinco_a_las_0001():
    reps = [
        rep(rid=f"a{i}", inicio=datetime(2026, 9, 10, 23, 59, i, tzinfo=UTC)) for i in range(6)
    ] + [rep(rid=f"b{i}", inicio=datetime(2026, 9, 11, 0, 1, i, tzinfo=UTC)) for i in range(5)]
    assert pagables(aplicar_tope_diario(reps, CFG)) == 11


@pytest.mark.parametrize(
    ("inicio", "dia"),
    [
        pytest.param(datetime(2026, 9, 10, 23, 59, 59, tzinfo=UTC), date(2026, 9, 10), id="2359"),
        pytest.param(datetime(2026, 9, 11, 0, 0, 0, tzinfo=UTC), date(2026, 9, 11), id="0000"),
        pytest.param(datetime(2026, 9, 10, 19, 30, tzinfo=BOGOTA), date(2026, 9, 11), id="-0500"),
    ],
)
def test_dia_utc(inicio, dia):
    assert dia_utc(rep(inicio=inicio)) == dia


def test_borde_de_medianoche_son_dias_distintos():
    antes = [
        rep(rid=f"r{i:02d}", inicio=datetime(2026, 9, 10, 23, 59, 59, tzinfo=UTC))
        for i in range(10)
    ]
    despues = rep(rid="r10", inicio=datetime(2026, 9, 11, 0, 0, 0, tzinfo=UTC))
    assert pagables(aplicar_tope_diario(antes + [despues], CFG)) == 11


@pytest.mark.parametrize(
    ("local", "pagable"),
    [
        # 07:30 -05:00 = 12:30Z del día 10: es la 11.ª de ese día UTC.
        pytest.param(datetime(2026, 9, 10, 7, 30, tzinfo=BOGOTA), False, id="mismo-dia-utc"),
        # 19:30 -05:00 del día 10 = 00:30Z del día 11: cuenta en el día 11.
        pytest.param(datetime(2026, 9, 10, 19, 30, tzinfo=BOGOTA), True, id="dia-siguiente-utc"),
    ],
)
def test_zona_menos_cinco_cuenta_en_su_dia_utc(local, pagable):
    reps = seguidas(10) + [rep(rid="bogota", inicio=local)]
    resultados = aplicar_tope_diario(reps, CFG)
    assert resultados[-1].pagable is pagable


# --- Contrato de entrada, config y pureza ----------------------------------------------------


def test_datetime_naive_lanza_value_error():
    with pytest.raises(ValueError, match="UTC"):
        rep(inicio=datetime(2026, 9, 10, 12, 0))


def test_datetime_con_otra_zona_se_normaliza_a_utc():
    r = rep(inicio=datetime(2026, 9, 30, 20, 0, tzinfo=BOGOTA))
    assert r.inicio == datetime(2026, 10, 1, 1, 0, tzinfo=UTC)
    assert r.inicio.tzinfo is UTC


def test_ms_negativos_lanza_value_error():
    with pytest.raises(ValueError, match="ms_continuos_max"):
        rep(ms=-1)


def test_config_por_defecto():
    assert CFG.segundos_min_validez == 30
    assert CFG.max_reproducciones_dia == 10


def test_umbrales_salen_de_la_config():
    cfg = ReglasValidezConfig(segundos_min_validez=20, max_reproducciones_dia=3)
    assert es_valida(rep(ms=25_000), cfg) is True
    assert es_valida(rep(ms=25_000), CFG) is False
    assert pagables(aplicar_tope_diario(seguidas(4), cfg)) == 3


def test_funciones_no_modifican_sus_entradas():
    reps = list(reversed(seguidas(11))) + [rep(rid="corta", ms=1_000)]
    copia = copy.deepcopy(reps)

    for r in reps:
        es_valida(r, CFG)
        dia_utc(r)
    aplicar_tope_diario(reps, CFG)

    assert reps == copia  # mismo contenido y mismo orden
