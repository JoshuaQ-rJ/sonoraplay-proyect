"""Pruebas de RN-03 (detección de granjas) · EG-18 · ADR-0005."""

import copy
from datetime import UTC, datetime, timedelta, timezone

import pytest

from sonoraplay.config import ReglasFraudeConfig
from sonoraplay.reglas.fraude import (
    EN_REVISION,
    VALIDA_PARA_FRAUDE,
    Reproduccion,
    ResultadoFraude,
    SenalFraude,
    cuentas_por_dispositivo,
    evaluar_cuentas,
    marcar_exclusion,
    oyentes_unicos_por_artista,
    senal_concentracion_artista,
    senal_dispositivo_compartido,
    senal_horas_24h,
)

CFG = ReglasFraudeConfig()
HORA_MS = 3_600_000
BASE = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)


def rep(
    cuenta: str = "c1",
    dispositivo: str = "d1",
    artista: str = "a1",
    inicio: datetime = BASE,
    ms: int = 180_000,
) -> Reproduccion:
    """Fábrica de reproducciones con valores por defecto válidos."""
    return Reproduccion(
        cuenta_id=cuenta,
        dispositivo_id=dispositivo,
        artista_id=artista,
        inicio=inicio,
        ms_escuchados=ms,
    )


def horas_seguidas(horas: int, desde: datetime = BASE, artistas: int = 1, **kw) -> list:
    """`horas` reproducciones de 1 h consecutivas, rotando entre `artistas` artistas."""
    return [
        rep(inicio=desde + timedelta(hours=i), ms=HORA_MS, artista=f"a{i % artistas}", **kw)
        for i in range(horas)
    ]


def reparto(top: int, total: int, cuenta: str = "c1") -> list:
    """`total` reproducciones de una cuenta: `top` al artista A y el resto a otros."""
    return [
        rep(
            cuenta=cuenta,
            artista="A" if i < top else f"otro{i}",
            inicio=BASE + timedelta(minutes=i),
        )
        for i in range(total)
    ]


def compartido(n_cuentas: int, dispositivo: str = "d1") -> list:
    return [rep(cuenta=f"c{i}", dispositivo=dispositivo) for i in range(1, n_cuentas + 1)]


# --- Señal 1: > 20 h en cualquier ventana móvil de 24 h -------------------------------------


@pytest.mark.parametrize(
    ("reps", "esperado"),
    [
        pytest.param(horas_seguidas(21), True, id="positivo-21h-en-24h"),
        pytest.param(horas_seguidas(19, artistas=12), False, id="legitimo-19h-musica-variada"),
        pytest.param(horas_seguidas(20), False, id="limite-exactamente-20h"),
        pytest.param([], False, id="sin-reproducciones"),
    ],
)
def test_senal_horas_24h(reps, esperado):
    assert senal_horas_24h(reps, CFG) is esperado


def test_ventana_movil_cruza_dia_calendario():
    # 21 h entre las 18:00 del día 1 y las 17:59 del día 2: ningún día calendario supera 20 h
    # (6 h y 15 h), pero la ventana móvil de 24 h sí.
    dia1 = horas_seguidas(6, desde=datetime(2026, 9, 10, 18, 0, tzinfo=UTC))
    dia2 = horas_seguidas(15, desde=datetime(2026, 9, 11, 2, 59, tzinfo=UTC))
    assert dia2[-1].inicio + timedelta(hours=1) == datetime(2026, 9, 11, 17, 59, tzinfo=UTC)
    assert senal_horas_24h(dia1 + dia2, CFG) is True


@pytest.mark.parametrize(
    ("inicio_b", "esperado"),
    [
        # A: 00:00–12:00. B: 12 h. Ninguna ventana de 24 h contiene A y B completas.
        pytest.param(datetime(2026, 9, 10, 13, 0, tzinfo=UTC), True, id="hueco-1h-cuenta-23h"),
        pytest.param(datetime(2026, 9, 10, 20, 0, tzinfo=UTC), False, id="hueco-8h-cuenta-16h"),
    ],
)
def test_reproduccion_que_cruza_borde_cuenta_solo_la_parte_dentro(inicio_b, esperado):
    reps = [rep(inicio=BASE, ms=12 * HORA_MS), rep(inicio=inicio_b, ms=12 * HORA_MS)]
    assert senal_horas_24h(reps, CFG) is esperado


def test_horas_24h_no_depende_del_orden_de_entrada():
    reps = horas_seguidas(21)
    assert senal_horas_24h(list(reversed(reps)), CFG) is True


# --- Señal 2: > 70 % a un artista con < 1.000 oyentes únicos en el mes ----------------------


@pytest.mark.parametrize(
    ("top", "total", "oyentes", "esperado"),
    [
        pytest.param(8, 10, 300, True, id="positivo-80pct-artista-300-oyentes"),
        pytest.param(8, 10, 50_000, False, id="legitimo-80pct-artista-50000-oyentes"),
        pytest.param(7, 10, 300, False, id="limite-exactamente-70pct"),
        pytest.param(8, 10, 1_000, False, id="limite-exactamente-1000-oyentes"),
        pytest.param(8, 10, 999, True, id="999-oyentes"),
        pytest.param(71, 100, 300, True, id="71pct"),
    ],
)
def test_senal_concentracion_artista(top, total, oyentes, esperado):
    # El dict de oyentes se pasa directo: no hace falta crear 50.000 reproducciones.
    reps = reparto(top, total)
    oyentes_por_artista = {"A": oyentes} | {f"otro{i}": 50_000 for i in range(total)}
    assert senal_concentracion_artista(reps, oyentes_por_artista, CFG) is esperado


def test_concentracion_sin_reproducciones():
    assert senal_concentracion_artista([], {}, CFG) is False


def test_oyentes_unicos_cuenta_cuentas_no_reproducciones():
    reps = [
        rep(cuenta="c1", artista="A"),
        rep(cuenta="c1", artista="A", inicio=BASE + timedelta(hours=1)),
        rep(cuenta="c2", artista="A"),
        rep(cuenta="c2", artista="B"),
    ]
    assert oyentes_unicos_por_artista(reps) == {"A": 2, "B": 1}


# --- Señal 3: dispositivo con > 5 cuentas ---------------------------------------------------


@pytest.mark.parametrize(
    ("n_cuentas", "esperado"),
    [
        pytest.param(6, True, id="positivo-dispositivo-6-cuentas"),
        pytest.param(5, False, id="legitimo-limite-familia-5-cuentas"),
        pytest.param(1, False, id="dispositivo-personal"),
    ],
)
def test_senal_dispositivo_compartido(n_cuentas, esperado):
    por_dispositivo = cuentas_por_dispositivo(compartido(n_cuentas))
    assert senal_dispositivo_compartido("c1", por_dispositivo, CFG) is esperado


def test_dispositivo_marca_si_alguno_de_sus_dispositivos_supera():
    reps = compartido(6, "granja") + [rep(cuenta="c1", dispositivo="movil-propio")]
    por_dispositivo = cuentas_por_dispositivo(reps)
    assert por_dispositivo["movil-propio"] == {"c1"}
    assert senal_dispositivo_compartido("c1", por_dispositivo, CFG) is True
    assert senal_dispositivo_compartido("desconocida", por_dispositivo, CFG) is False


# --- Evaluación por cuenta -------------------------------------------------------------------


def variada(cuenta: str, n: int = 4) -> list:
    """Cuenta sana: pocas reproducciones repartidas entre `n` artistas (100/n %)."""
    return [
        rep(cuenta=cuenta, dispositivo=f"dev-{cuenta}", artista=f"x{i}", inicio=BASE)
        for i in range(n)
    ]


def test_cuenta_con_dos_senales_devuelve_ambas():
    # 21 h en 24 h, todas al artista A, que solo tiene 1 oyente en el mes.
    granja = horas_seguidas(21, cuenta="c1")
    resultados = evaluar_cuentas(granja + variada("c2"), CFG)
    assert resultados["c1"] == ResultadoFraude(
        cuenta_id="c1",
        sospechosa=True,
        senales=frozenset({SenalFraude.HORAS_24H, SenalFraude.CONCENTRACION_ARTISTA}),
    )


def test_cuenta_sin_senales():
    resultados = evaluar_cuentas(variada("c2"), CFG)
    assert resultados == {"c2": ResultadoFraude("c2", sospechosa=False, senales=frozenset())}


def test_cualquier_senal_sola_marca_sospechosa():
    reps = compartido(6, "granja") + [
        rep(cuenta=f"c{i}", dispositivo="granja", artista=f"y{j}")
        for i in range(1, 7)
        for j in range(4)
    ]
    resultados = evaluar_cuentas(reps, CFG)
    assert all(r.sospechosa for r in resultados.values())
    assert all(r.senales == {SenalFraude.DISPOSITIVO_COMPARTIDO} for r in resultados.values())


def test_evaluar_rechaza_reproducciones_de_varios_meses():
    reps = [rep(), rep(inicio=datetime(2026, 10, 1, tzinfo=UTC))]
    with pytest.raises(ValueError, match="mes"):
        evaluar_cuentas(reps, CFG)


def test_evaluar_sin_reproducciones():
    assert evaluar_cuentas([], CFG) == {}


# --- Exclusión (Q3: todo el mes en revisión) -------------------------------------------------


def test_marcar_exclusion_todo_el_mes_de_la_sospechosa():
    sospechosa = horas_seguidas(21, cuenta="c1", dispositivo="d1") + [
        rep(cuenta="c1", inicio=datetime(2026, 9, 28, tzinfo=UTC))  # otro día del mismo mes
    ]
    sana = variada("c2")
    reps = sospechosa + sana
    resultados = evaluar_cuentas(reps, CFG)

    marcadas = marcar_exclusion(reps, resultados)

    assert [r for r, _ in marcadas] == reps  # no borra ni reordena nada
    assert all(estado == EN_REVISION for r, estado in marcadas if r.cuenta_id == "c1")
    assert all(estado == VALIDA_PARA_FRAUDE for r, estado in marcadas if r.cuenta_id == "c2")


# --- Contrato de entrada ---------------------------------------------------------------------


def test_datetime_naive_lanza_value_error():
    with pytest.raises(ValueError, match="UTC"):
        rep(inicio=datetime(2026, 9, 10, 12, 0))


def test_datetime_con_otra_zona_se_normaliza_a_utc():
    bogota = timezone(timedelta(hours=-5))
    r = rep(inicio=datetime(2026, 9, 30, 20, 0, tzinfo=bogota))
    assert r.inicio == datetime(2026, 10, 1, 1, 0, tzinfo=UTC)
    assert r.inicio.tzinfo is UTC


def test_ms_negativos_lanza_value_error():
    with pytest.raises(ValueError, match="ms_escuchados"):
        rep(ms=-1)


def test_funciones_no_modifican_sus_entradas():
    reps = horas_seguidas(21) + compartido(6, "granja")
    oyentes = oyentes_unicos_por_artista(reps)
    por_dispositivo = cuentas_por_dispositivo(reps)
    copias = copy.deepcopy((reps, oyentes, por_dispositivo))

    senal_horas_24h(reps, CFG)
    senal_concentracion_artista(reps, oyentes, CFG)
    senal_dispositivo_compartido("c1", por_dispositivo, CFG)
    resultados = evaluar_cuentas(reps, CFG)
    copia_resultados = copy.deepcopy(resultados)
    marcar_exclusion(reps, resultados)

    assert (reps, oyentes, por_dispositivo) == copias
    assert resultados == copia_resultados
