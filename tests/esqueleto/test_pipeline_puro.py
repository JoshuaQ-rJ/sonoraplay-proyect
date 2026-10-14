"""EG-24 · partes puras del esqueleto: sin base de datos ni archivos."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from sonoraplay.config import AtribucionOfflineConfig, SimuladorConfig
from sonoraplay.esqueleto.pipeline import (
    PERIODO_POR_DEFECTO,
    Descarte,
    FuentesLiquidacion,
    Suscripcion,
    componente_de_plan,
    elegir_pais,
    liquidar,
    plan_vigente,
    seleccionar_periodo,
)
from sonoraplay.reglas.atribucion import TipoAtribucion
from sonoraplay.reglas.liquidacion import CondicionContrato, Pago, ReproduccionLiquidable
from sonoraplay.reglas.sesiones import ReproduccionF2
from sonoraplay.reporte_regalias import Componente
from sonoraplay.simulador.f2_minimo import FuentesSimulador, Pista, Usuario, generar

SEP = date(2026, 9, 1)
CFG = AtribucionOfflineConfig()


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


# --- Componente por plan (Q8) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("plan", "componente"),
    [
        ("free", Componente.PUBLICIDAD),
        ("individual", Componente.SUSCRIPCION),
        ("familiar", Componente.SUSCRIPCION),
        ("estudiante", Componente.SUSCRIPCION),
    ],
)
def test_componente_de_plan(plan, componente):
    assert componente_de_plan(plan) == componente


def test_plan_desconocido_falla():
    with pytest.raises(ValueError, match="plan desconocido"):
        componente_de_plan("premium")


# --- Selección del período (RN-04) -------------------------------------------------------------


def _rep(rid: str, inicio: datetime, sincronizado: datetime, offline: bool) -> ReproduccionF2:
    return ReproduccionF2(rid, "u", "t", inicio, 60_000, offline, sincronizado)


def test_periodo_por_defecto_es_el_mes_del_simulador():
    assert PERIODO_POR_DEFECTO == date(2026, 9, 1) == SimuladorConfig.fecha_base.replace(day=1)


def test_seleccion_del_periodo_incluye_ajustes_y_deja_fuera_otros_meses():
    reps = [
        _rep("sep", _utc(2026, 9, 15, 8), _utc(2026, 9, 15, 8, 4), False),
        # Offline de agosto sincronizada el 10-sep: agosto ya cerró → ajuste en septiembre.
        _rep("ajuste", _utc(2026, 8, 28), _utc(2026, 9, 10), True),
        # Offline de agosto sincronizada antes del corte del 2-sep → se queda en agosto.
        _rep("agosto", _utc(2026, 8, 28), _utc(2026, 9, 2, 23, 59), True),
        # Offline de septiembre sincronizada el 5-oct → ajuste en octubre.
        _rep("octubre", _utc(2026, 9, 28), _utc(2026, 10, 5), True),
    ]
    seleccion = seleccionar_periodo(reps, SEP, CFG)
    assert [(rep.reproduccion_id, r.tipo) for rep, r in seleccion] == [
        ("sep", TipoAtribucion.NORMAL),
        ("ajuste", TipoAtribucion.AJUSTE),
    ]


def test_periodo_debe_ser_primer_dia():
    with pytest.raises(ValueError, match="primer día"):
        seleccionar_periodo([], date(2026, 9, 15), CFG)


# --- Plan vigente (Q8, RN-10) ------------------------------------------------------------------


def _fuentes(**kw) -> FuentesLiquidacion:
    base = dict(
        titular_de_pista={},
        pais_de_usuario={},
        titular_de_familia={},
        suscripciones={},
        pagos=(),
        condiciones=(),
    )
    return FuentesLiquidacion(**{**base, **kw})


def test_cambio_de_plan_el_dia_del_corte_cuenta_el_nuevo():
    f = _fuentes(
        suscripciones={
            "u": [
                Suscripcion("u", "free", date(2026, 1, 1), date(2026, 9, 10)),
                Suscripcion("u", "individual", date(2026, 9, 10), None),
            ]
        }
    )
    assert plan_vigente("u", date(2026, 9, 9), f) == "free"
    assert plan_vigente("u", date(2026, 9, 10), f) == "individual"


def test_miembro_de_familia_usa_la_suscripcion_del_titular():
    f = _fuentes(
        titular_de_familia={"miembro": "titular"},
        suscripciones={"titular": [Suscripcion("titular", "familiar", date(2026, 1, 1), None)]},
    )
    assert plan_vigente("miembro", date(2026, 9, 15), f) == "familiar"


def test_sin_suscripcion_vigente():
    f = _fuentes(
        suscripciones={"u": [Suscripcion("u", "individual", date(2026, 1, 1), date(2026, 9, 1))]}
    )
    assert plan_vigente("u", date(2026, 9, 1), f) is None
    assert plan_vigente("otro", date(2026, 9, 1), f) is None


# --- País a liquidar ---------------------------------------------------------------------------


def _liq(rid: str, pais: str) -> ReproduccionLiquidable:
    return ReproduccionLiquidable(
        rid, "u", uuid.uuid4(), "t", _utc(2026, 9, 15), pais, pais, Componente.SUSCRIPCION
    )


def test_elegir_pais_mayoria_y_empate_alfabetico():
    assert elegir_pais([_liq("1", "MX"), _liq("2", "CO"), _liq("3", "MX")]) == "MX"
    assert elegir_pais([_liq("1", "MX"), _liq("2", "CO")]) == "CO"


def test_elegir_pais_sin_reproducciones():
    with pytest.raises(ValueError, match="no hay reproducciones"):
        elegir_pais([])


# --- liquidar() sobre los escenarios del simulador ----------------------------------------------

TITULARES = [uuid.UUID(int=i + 1) for i in range(3)]


@pytest.fixture(scope="module")
def caso():
    usuarios = tuple(
        Usuario(f"00000000-0000-4000-8000-{i:012d}", None if i == 19 else "CO") for i in range(20)
    )
    pistas = tuple(Pista(f"{i:02d}" + "x" * 20, 40_000 + i * 15_000) for i in range(30))
    eventos = generar(FuentesSimulador(usuarios, pistas), SimuladorConfig())
    suscripciones = {
        u.usuario_id: [
            Suscripcion(u.usuario_id, "free" if n % 2 else "individual", date(2025, 1, 1), None)
        ]
        for n, u in enumerate(usuarios)
    }
    fuentes = FuentesLiquidacion(
        titular_de_pista={p.track_id: TITULARES[n % 3] for n, p in enumerate(pistas)},
        pais_de_usuario={u.usuario_id: u.pais_facturacion for u in usuarios},
        titular_de_familia={},
        suscripciones=suscripciones,
        pagos=tuple(
            Pago(u, Decimal("9.99"), "aprobado")
            for u, s in suscripciones.items()
            if s[0].plan != "free"
        )
        + (Pago(usuarios[0].usuario_id, Decimal("9.99"), "rechazado"),),
        condiciones=tuple(
            CondicionContrato(
                uuid.UUID(int=100 + n),
                TITULARES[n % 3],
                p.track_id,
                Decimal("50"),
                date(2026, 1, 1),
            )
            for n, p in enumerate(pistas)
        ),
    )
    return eventos, fuentes, liquidar(eventos, fuentes, SEP, Decimal("20000"))


def test_a_y_c_quedan_fuera_por_duracion_y_la_11a_de_d_por_el_tope(caso):
    _, _, resumen = caso
    assert resumen.descartes[Descarte.DURACION_INSUFICIENTE] >= 2  # A (29 s) y C (pausa)
    assert resumen.descartes[Descarte.TOPE_DIARIO] == 1  # la 11.ª del escenario D
    assert Descarte.OTRO_MES not in resumen.descartes


def test_pais_nulo_se_cuenta_y_no_se_inventa(caso):
    _, fuentes, resumen = caso
    sin_pais = {u for u, p in fuentes.pais_de_usuario.items() if p is None}
    assert all(r.usuario_id not in sin_pais for r in resumen.liquidables)
    assert resumen.pais == "CO"


def test_bolsa_y_rnf02(caso):
    _, fuentes, resumen = caso
    aprobados = sum(
        (
            p.monto_usd
            for p in fuentes.pagos
            if p.estado == "aprobado" and fuentes.pais_de_usuario[p.usuario_id]
        ),
        Decimal(0),
    )
    bolsa = resumen.resultado.bolsa
    assert bolsa.suscripcion == aprobados * Decimal("0.52")
    assert bolsa.publicidad == Decimal("20000") * Decimal("0.45")
    for componente in Componente:
        assert resumen.resultado.total_usd(componente) <= bolsa.de(componente) + Decimal("0.01")
    # Todas las pagables de CO aparecen en alguna fila.
    assert sum(f.reproducciones_validas for f in resumen.resultado.filas) == len(
        resumen.liquidables
    )


def test_publicidad_float_rechazada(caso):
    eventos, fuentes, _ = caso
    with pytest.raises(TypeError, match="Decimal"):
        liquidar(eventos, fuentes, SEP, 20000.0)  # type: ignore[arg-type]


def test_ajuste_offline_de_agosto_se_liquida_en_septiembre(caso):
    """ADR-0007 §5: un ajuste de la EG-22 entra en la liquidación siguiente con el % de su fecha."""
    eventos, fuentes, _ = caso
    usuario = next(u for u, s in fuentes.suscripciones.items() if s[0].plan == "individual")
    pista = next(iter(fuentes.titular_de_pista))
    base = {
        "schema_version": "1.0",
        "user_id": usuario,
        "device_id": "android-offline",
        "track_id": pista,
        "session_id": "ajuste-agosto",
        "country_playback": "CO",
        "is_offline": True,
        "server_ts": "2026-09-10T12:00:00.000Z",  # sincronizada después del corte del 2-sep
    }
    ajuste = [
        {
            **base,
            "event_id": "a1",
            "event_type": "start",
            "device_ts": "2026-08-28T20:00:00.000Z",
            "position_ms": 0,
        },
        {
            **base,
            "event_id": "a2",
            "event_type": "end",
            "device_ts": "2026-08-28T20:00:40.000Z",
            "position_ms": 40_000,
        },
    ]
    resumen = liquidar([*eventos, *ajuste], fuentes, SEP, Decimal("20000"))
    assert resumen.ajustes == 1
    (rep,) = [r for r in resumen.liquidables if r.reproduccion_id == "ajuste-agosto"]
    assert rep.inicio.date() == date(2026, 8, 28)
    assert sum(f.reproducciones_validas for f in resumen.resultado.filas) == len(
        resumen.liquidables
    )
