"""Pruebas de la liquidación (EG-23) · RN-05 a RN-10, Q5 a Q8, RNF-02 · ADR-0002.

Todas son puras: sin base de datos ni reloj del sistema.
"""

import random
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import pytest

from sonoraplay.api_contratos.models import Contrato
from sonoraplay.api_contratos.services import SinCondicionVigente, elegir_condicion
from sonoraplay.config import ReglasLiquidacionConfig
from sonoraplay.reglas.liquidacion import (
    BolsaPais,
    CondicionContrato,
    Pago,
    ReproduccionLiquidable,
    ResultadoLiquidacion,
    TasaCambio,
    TipoIncidente,
    calcular_bolsa,
    convertir_a_usd,
    indexar_condiciones,
    liquidar_pais,
    paises_facturacion,
    porcentaje_aplicable,
    suscripcion_neta_por_pais,
    ultimo_dia_del_mes,
    verificar_invariantes,
)
from sonoraplay.reporte_regalias import CENTAVO, Componente, FilaReporte

CFG = ReglasLiquidacionConfig()
SEPT = date(2026, 9, 1)
BASE = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
BOGOTA = timezone(timedelta(hours=-5))
SUS, PUB = Componente.SUSCRIPCION, Componente.PUBLICIDAD

SELLO_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
SELLO_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")


def D(x: str | int) -> Decimal:
    return Decimal(str(x))


def cond(
    titular: uuid.UUID = SELLO_A,
    pct: str | int = 80,
    desde: date = date(2026, 1, 1),
    hasta: date | None = None,
    track: str = "t1",
    territorio: str | None = None,
    exclusiones: frozenset[str] = frozenset(),
) -> CondicionContrato:
    return CondicionContrato(
        contrato_id=uuid.uuid4(),
        titular_id=titular,
        track_id=track,
        porcentaje=D(pct),
        valido_desde=desde,
        valido_hasta=hasta,
        territorio=territorio,
        exclusiones=exclusiones,
    )


_ids = iter(range(10**9))


def rep(
    titular: uuid.UUID = SELLO_A,
    componente: Componente = SUS,
    inicio: datetime = BASE,
    track: str = "t1",
    usuario: str = "u1",
    pais_facturacion: str = "CO",
    pais_reproduccion: str | None = "CO",
) -> ReproduccionLiquidable:
    return ReproduccionLiquidable(
        reproduccion_id=f"r{next(_ids)}",
        usuario_id=usuario,
        titular_id=titular,
        track_id=track,
        inicio=inicio,
        pais_facturacion=pais_facturacion,
        pais_reproduccion=pais_reproduccion,
        componente=componente,
    )


def reps(n: int, **kw) -> list[ReproduccionLiquidable]:
    return [rep(**kw) for _ in range(n)]


def filas_de(res: ResultadoLiquidacion, titular: uuid.UUID) -> dict:
    return {
        (f.componente, f.porcentaje_contractual): f for f in res.filas if f.titular_id == titular
    }


def bolsa_colombia() -> BolsaPais:
    return calcular_bolsa("CO", D(100_000), D(20_000), CFG)


# --- Bolsa con dos componentes (Q8) y ejemplo de Colombia --------------------------------------


def test_bolsa_colombia_dos_componentes():
    bolsa = bolsa_colombia()
    assert bolsa.suscripcion == D(52_000)
    assert bolsa.publicidad == D(9_000)
    assert bolsa.total == D(61_000)


def _caso_colombia(free_a: int) -> ResultadoLiquidacion:
    """A: 5 de 100 reproducciones pagas y `free_a` de 100 gratuitas, contrato 80 %. B: el resto
    al 50 %."""
    condiciones = indexar_condiciones(
        [cond(SELLO_A, 80, track="ta"), cond(SELLO_B, 50, track="tb")]
    )
    plays = (
        reps(5, titular=SELLO_A, track="ta", componente=SUS)
        + reps(95, titular=SELLO_B, track="tb", componente=SUS)
        + reps(free_a, titular=SELLO_A, track="ta", componente=PUB)
        + reps(100 - free_a, titular=SELLO_B, track="tb", componente=PUB)
    )
    return liquidar_pais(SEPT, bolsa_colombia(), plays, condiciones)


def test_criterio_1_colombia_2800():
    res = _caso_colombia(free_a=10)
    a = filas_de(res, SELLO_A)
    assert a[(SUS, D("80.00"))].regalia_usd == D("2080.00")  # 52.000 × 5 % × 80 %
    assert a[(SUS, D("80.00"))].participacion == D("0.050000")
    assert a[(PUB, D("80.00"))].regalia_usd == D("720.00")  # 9.000 × 10 % × 80 %
    assert a[(PUB, D("80.00"))].participacion == D("0.100000")
    assert res.total_titular(SELLO_A) == D("2800.00")
    assert not res.incidentes


def test_cruce_bolsa_unica_2440():
    """Con 5 % en los dos componentes: (52.000 + 9.000) × 5 % × 80 % = 2.440,00."""
    res = _caso_colombia(free_a=5)
    assert res.total_titular(SELLO_A) == D("2440.00")


def test_denominadores_separados():
    """Las reproducciones gratuitas no diluyen el componente de suscripción (Q8)."""
    condiciones = indexar_condiciones([cond(SELLO_A, 100), cond(SELLO_B, 100, track="tb")])
    pagas = reps(10, titular=SELLO_A)
    solo_pagas = liquidar_pais(SEPT, bolsa_colombia(), pagas, condiciones)
    con_gratis = liquidar_pais(
        SEPT,
        bolsa_colombia(),
        pagas + reps(990, titular=SELLO_B, track="tb", componente=PUB),
        condiciones,
    )
    assert filas_de(solo_pagas, SELLO_A)[(SUS, D("100.00"))].regalia_usd == D("52000.00")
    assert filas_de(con_gratis, SELLO_A)[(SUS, D("100.00"))].regalia_usd == D("52000.00")
    assert filas_de(con_gratis, SELLO_B)[(PUB, D("100.00"))].regalia_usd == D("9000.00")
    assert (PUB, D("100.00")) not in filas_de(con_gratis, SELLO_A)


# --- RN-07: % vigente por fecha de la reproducción --------------------------------------------

CAMBIO = [
    cond(SELLO_A, 50, desde=date(2026, 9, 1), hasta=date(2026, 9, 14)),
    cond(SELLO_A, 40, desde=date(2026, 9, 15)),
]


@pytest.mark.parametrize(
    ("inicio", "esperado"),
    [
        (datetime(2026, 9, 14, 0, 0, tzinfo=UTC), "50"),
        # valido_hasta es inclusivo: todo el día 14 UTC usa el 50 %.
        (datetime(2026, 9, 14, 23, 59, 59, 999999, tzinfo=UTC), "50"),
        # valido_desde es inclusivo: desde las 00:00:00 UTC del 15 se usa el 40 %.
        (datetime(2026, 9, 15, 0, 0, tzinfo=UTC), "40"),
        # El día lo decide la fecha UTC (ADR-0002), no la hora local de Bogotá.
        (datetime(2026, 9, 14, 18, 59, tzinfo=BOGOTA), "50"),  # 23:59 UTC del 14
        (datetime(2026, 9, 14, 19, 0, tzinfo=BOGOTA), "40"),  # 00:00 UTC del 15
    ],
)
def test_limite_del_cambio_de_porcentaje(inicio, esperado):
    pct, elegida, inc = porcentaje_aplicable(rep(inicio=inicio), indexar_condiciones(CAMBIO))
    assert pct == D(esperado)
    assert elegida is not None and elegida.porcentaje == D(esperado)
    assert inc is None


def test_cambio_a_mitad_de_mes_una_fila_por_porcentaje():
    """4 reproducciones al 50 % (hasta el 14) y 3 al 40 % (desde el 15), de 10 pagas en CO."""
    plays = (
        reps(3, inicio=datetime(2026, 9, 10, tzinfo=UTC))
        + reps(1, inicio=datetime(2026, 9, 14, 23, 59, 59, tzinfo=UTC))
        + reps(2, inicio=datetime(2026, 9, 15, tzinfo=UTC))
        + reps(1, inicio=datetime(2026, 9, 14, 22, tzinfo=BOGOTA))  # 15 a las 03:00 UTC
        + reps(3, titular=SELLO_B, track="tb")
    )
    condiciones = indexar_condiciones(CAMBIO + [cond(SELLO_B, 100, track="tb")])
    bolsa = calcular_bolsa("CO", D(1_000), D(0), CFG)  # componente de suscripción: 520
    res = liquidar_pais(SEPT, bolsa, plays, condiciones)

    a = filas_de(res, SELLO_A)
    assert set(a) == {(SUS, D("50.00")), (SUS, D("40.00"))}
    assert a[(SUS, D("50.00"))].reproducciones_validas == 4
    assert a[(SUS, D("50.00"))].regalia_usd == D("104.00")  # 520 × 4/10 × 50 %
    assert a[(SUS, D("40.00"))].reproducciones_validas == 3
    assert a[(SUS, D("40.00"))].regalia_usd == D("62.40")  # 520 × 3/10 × 40 %
    assert res.total_titular(SELLO_A) == D("166.40")  # suma de los dos períodos


def test_condicion_territorial_q7():
    condiciones = indexar_condiciones([cond(pct=80), cond(pct=60, territorio="PE")])
    assert porcentaje_aplicable(rep(pais_reproduccion="PE"), condiciones)[0] == D(60)
    assert porcentaje_aplicable(rep(pais_reproduccion="CO"), condiciones)[0] == D(80)
    assert porcentaje_aplicable(rep(pais_reproduccion=None), condiciones)[0] == D(80)


def test_condiciones_generales_solapadas_lanza_error():
    condiciones = indexar_condiciones([cond(pct=80), cond(pct=50)])
    with pytest.raises(ValueError, match="solapadas"):
        porcentaje_aplicable(rep(), condiciones)


# --- RN-08: territorio excluido -----------------------------------------------------------------


def test_territorio_excluido_paga_cero_y_devuelve_incidente():
    general = cond(SELLO_A, 70, exclusiones=frozenset({"MX"}))
    condiciones = indexar_condiciones([general, cond(SELLO_B, 100, track="tb")])
    excluida = rep(pais_reproduccion="MX")  # cuenta de Colombia escuchando en México
    plays = [excluida] + reps(3, pais_reproduccion="CO") + reps(6, titular=SELLO_B, track="tb")
    res = liquidar_pais(SEPT, calcular_bolsa("CO", D(1_000), D(0), CFG), plays, condiciones)

    assert len(res.incidentes) == 1
    inc = res.incidentes[0]
    assert inc.tipo == TipoIncidente.TERRITORIO_EXCLUIDO
    assert inc.reproduccion_id == excluida.reproduccion_id
    assert inc.contrato_id == general.contrato_id
    assert inc.pais_reproduccion == "MX"
    assert inc.fecha == date(2026, 9, 10)

    a = filas_de(res, SELLO_A)
    cero = a[(SUS, D("0.00"))]
    assert cero.reproducciones_validas == 1
    assert cero.regalia_usd == D("0.00")
    # La excluida cuenta en el denominador (10): su parte no se reparte a otros titulares.
    assert a[(SUS, D("70.00"))].regalia_usd == D("109.20")  # 520 × 3/10 × 70 %
    assert filas_de(res, SELLO_B)[(SUS, D("100.00"))].regalia_usd == D("312.00")  # 520 × 6/10


def test_exclusion_manda_sobre_condicion_territorial():
    condiciones = indexar_condiciones(
        [cond(pct=80, exclusiones=frozenset({"PE"})), cond(pct=60, territorio="PE")]
    )
    pct, _, inc = porcentaje_aplicable(rep(pais_reproduccion="PE"), condiciones)
    assert pct == 0
    assert inc is not None and inc.tipo == TipoIncidente.TERRITORIO_EXCLUIDO


def test_sin_condicion_vigente_paga_cero_y_devuelve_incidente():
    condiciones = indexar_condiciones([cond(pct=80, desde=date(2026, 10, 1))])
    res = liquidar_pais(SEPT, bolsa_colombia(), [rep()], condiciones)
    assert [i.tipo for i in res.incidentes] == [TipoIncidente.SIN_CONDICION_VIGENTE]
    assert res.incidentes[0].contrato_id is None
    assert res.total_usd() == 0


# --- RN-10 y Q6: cuentas familiares -------------------------------------------------------------


def test_familia_un_pago_repartido_entre_todos_los_miembros():
    pais_de_usuario = {"titular": "CO", "m1": "MX", "m2": None, "indiv_mx": "MX"}
    familia = {"m1": "titular", "m2": "titular"}
    paises = paises_facturacion(pais_de_usuario, familia)
    assert paises == {"titular": "CO", "m1": "CO", "m2": "CO", "indiv_mx": "MX"}

    pagos = [
        Pago("titular", D("15.00"), "aprobado"),
        Pago("titular", D("15.00"), "aprobado"),
        Pago("titular", D("15.00"), "rechazado"),  # Q5: no es ingreso
        Pago("indiv_mx", D("10.00"), "aprobado"),
    ]
    neta = suscripcion_neta_por_pais(pagos, paises)
    assert neta == {"CO": D("30.00"), "MX": D("10.00")}  # el pago familiar entra una sola vez

    def de(usuario: str, n: int, titular: uuid.UUID = SELLO_A, pais_rep: str = "CO"):
        return reps(
            n,
            titular=titular,
            track="ta" if titular == SELLO_A else "tb",
            usuario=usuario,
            pais_facturacion=paises[usuario],
            pais_reproduccion=pais_rep,
        )

    plays = de("titular", 2) + de("m1", 3, pais_rep="MX") + de("m2", 1)
    plays += de("indiv_mx", 4, titular=SELLO_B, pais_rep="MX")
    condiciones = indexar_condiciones(
        [cond(SELLO_A, 100, track="ta"), cond(SELLO_B, 100, track="tb")]
    )

    co = liquidar_pais(SEPT, calcular_bolsa("CO", neta["CO"], D(0), CFG), plays, condiciones)
    [fila] = co.filas
    assert fila.titular_id == SELLO_A
    assert fila.reproducciones_validas == 6  # los 3 miembros, aunque m1 escuchó en México
    assert fila.regalia_usd == D("15.60")  # 52 % × 30,00
    mx = liquidar_pais(SEPT, calcular_bolsa("MX", neta["MX"], D(0), CFG), plays, condiciones)
    assert [(f.titular_id, f.reproducciones_validas) for f in mx.filas] == [(SELLO_B, 4)]


def test_familia_con_titular_sin_pais_lanza_error():
    with pytest.raises(ValueError, match="nulo"):
        paises_facturacion({"t": None, "m": "CO"}, {"m": "t"})


# --- RNF-02: invariantes y redondeo -------------------------------------------------------------


def _verificar_rnf02(res: ResultadoLiquidacion) -> None:
    for componente in Componente:
        assert res.total_usd(componente) <= res.bolsa.de(componente) + CENTAVO
    assert res.total_usd() <= res.bolsa.total + CENTAVO


def test_sin_reproducciones_no_hay_filas():
    res = liquidar_pais(SEPT, bolsa_colombia(), [], {})
    assert res.filas == () and res.incidentes == ()
    assert res.total_usd() == 0


def test_un_componente_sin_reproducciones():
    res = liquidar_pais(SEPT, bolsa_colombia(), reps(3), indexar_condiciones([cond(pct=100)]))
    assert res.total_usd(PUB) == 0
    assert res.total_usd(SUS) == D("52000.00")


def test_un_solo_titular_al_100_recibe_la_bolsa_redondeada():
    bolsa = calcular_bolsa("CO", D("100.01"), D("0.03"), CFG)  # 52,0052 y 0,0135
    plays = reps(7) + reps(2, componente=PUB)
    res = liquidar_pais(SEPT, bolsa, plays, indexar_condiciones([cond(pct=100)]))
    assert res.total_usd(SUS) == D("52.01")  # ROUND_HALF_UP de 52,0052
    assert res.total_usd(PUB) == D("0.01")
    _verificar_rnf02(res)


def test_residuos_redondeo_por_fila_se_pasaria_pero_el_reparto_no():
    """Tres titulares con 1/3 cada uno de 100,005: ROUND_HALF_UP por fila daría
    3 × 33,34 = 100,02 (se pasa en 0,015). El mayor residuo da 100,01."""
    titulares = [uuid.UUID(int=i) for i in (1, 2, 3)]
    condiciones = indexar_condiciones([cond(t, 100, track=f"t{t.int}") for t in titulares])
    plays = [rep(t, track=f"t{t.int}") for t in titulares]
    bolsa = BolsaPais("CO", D("100.005"), D(0))

    ingenuo = 3 * (D("100.005") / 3).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    assert ingenuo > bolsa.suscripcion + CENTAVO

    res = liquidar_pais(SEPT, bolsa, plays, condiciones)
    assert sorted(f.regalia_usd for f in res.filas) == [D("33.33"), D("33.34"), D("33.34")]
    assert res.total_usd() == D("100.01")
    # Determinista: los empates de residuo se rompen por titular.
    assert liquidar_pais(SEPT, bolsa, list(reversed(plays)), condiciones).filas == res.filas


def test_siete_titulares_reparten_centavos_sin_perder_ni_crear():
    titulares = [uuid.UUID(int=i) for i in range(1, 8)]
    condiciones = indexar_condiciones([cond(t, 100, track=f"t{t.int}") for t in titulares])
    plays = [rep(t, track=f"t{t.int}") for t in titulares]
    res = liquidar_pais(SEPT, calcular_bolsa("CO", D(100), D(0), CFG), plays, condiciones)
    assert res.total_usd() == D("52.00")  # 52 / 7 = 7,428571… → 6 filas de 7,43 y 1 de 7,42
    assert sorted(f.regalia_usd for f in res.filas) == [D("7.42")] + [D("7.43")] * 6


def test_invariantes_con_muchos_casos_aleatorios():
    """Muchos titulares, conteos y % arbitrarios, bolsas con centavos sueltos (semilla fija)."""
    rng = random.Random(42)
    for _ in range(300):
        n = rng.randint(1, 40)
        titulares = [uuid.UUID(int=i + 1) for i in range(n)]
        condiciones = indexar_condiciones(
            [
                cond(
                    t,
                    D(rng.randint(0, 10_000)) / 100,
                    track=f"t{t.int}",
                    **({"exclusiones": frozenset({"MX"})} if rng.random() < 0.2 else {}),
                )
                for t in titulares
            ]
        )
        plays = [
            rep(
                t,
                componente=rng.choice([SUS, PUB]),
                track=f"t{t.int}",
                pais_reproduccion=rng.choice(["CO", "CO", "MX"]),
            )
            for t in titulares
            for _ in range(rng.randint(0, 30))
        ]
        bolsa = calcular_bolsa(
            "CO", D(rng.randint(0, 10_000_000)) / 100, D(rng.randint(0, 1_000_000)) / 100, CFG
        )
        res = liquidar_pais(SEPT, bolsa, plays, condiciones)
        _verificar_rnf02(res)

        totales = {c: sum(1 for p in plays if p.componente == c) for c in Componente}
        for f in res.filas:
            exacto = (
                bolsa.de(f.componente)
                * f.reproducciones_validas
                * f.porcentaje_contractual
                / (100 * totales[f.componente])
            )
            assert abs(f.regalia_usd - exacto) < CENTAVO  # cada fila a < 1 centavo del exacto
            if f.porcentaje_contractual == 0:
                assert f.regalia_usd == 0  # una excluida nunca recibe un centavo del reparto
        assert sum(f.reproducciones_validas for f in res.filas) == len(plays)


def test_verificar_invariantes_detecta_una_suma_que_se_pasa():
    fila = FilaReporte(
        titular_id=SELLO_A,
        periodo=SEPT,
        pais="CO",
        componente=SUS,
        reproducciones_validas=1,
        participacion=D(1),
        porcentaje_contractual=D(100),
        regalia_usd=D("52000.02"),
    )
    with pytest.raises(ValueError, match="RNF-02"):
        verificar_invariantes(ResultadoLiquidacion(SEPT, bolsa_colombia(), (fila,), ()))


# --- Moneda: tasa del último día del mes --------------------------------------------------------


@pytest.mark.parametrize(
    ("periodo", "ultimo"),
    [
        (date(2026, 9, 1), date(2026, 9, 30)),
        (date(2026, 12, 1), date(2026, 12, 31)),
        (date(2027, 2, 1), date(2027, 2, 28)),
        (date(2028, 2, 1), date(2028, 2, 29)),  # bisiesto
    ],
)
def test_ultimo_dia_del_mes(periodo, ultimo):
    assert ultimo_dia_del_mes(periodo) == ultimo


def test_conversion_con_tasa_de_cierre_de_mes():
    tasa = TasaCambio("COP", date(2026, 9, 30), D(4_000))
    publicidad = convertir_a_usd(D(80_000_000), "COP", tasa, SEPT)
    assert publicidad == D(20_000)
    assert calcular_bolsa("CO", D(100_000), publicidad, CFG).publicidad == D(9_000)


def test_conversion_no_redondea_antes_de_tiempo():
    tasa = TasaCambio("COP", date(2026, 9, 30), D("3999.99"))
    usd = convertir_a_usd(D(1_000), "COP", tasa, SEPT)
    assert usd == D(1_000) / D("3999.99")
    assert usd != usd.quantize(CENTAVO)


@pytest.mark.parametrize(
    ("tasa", "mensaje"),
    [
        (TasaCambio("COP", date(2026, 9, 29), D(4_000)), "último día"),
        (TasaCambio("COP", date(2026, 10, 1), D(4_000)), "último día"),
        (TasaCambio("MXN", date(2026, 9, 30), D(18)), "MXN"),
    ],
)
def test_conversion_rechaza_tasa_de_otra_fecha_o_moneda(tasa, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        convertir_a_usd(D(1_000), "COP", tasa, SEPT)


# --- Entradas inválidas y alcance -------------------------------------------------------------


def test_rechaza_float_en_dinero_y_porcentajes():
    with pytest.raises(TypeError):
        calcular_bolsa("CO", 100_000.0, D(0), CFG)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        CondicionContrato(uuid.uuid4(), SELLO_A, "t1", 80.0, date(2026, 1, 1))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        TasaCambio("COP", date(2026, 9, 30), 4000.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ReglasLiquidacionConfig(fraccion_suscripcion=0.52)  # type: ignore[arg-type]


def test_rechaza_datetime_naive():
    with pytest.raises(ValueError, match="aware"):
        rep(inicio=datetime(2026, 9, 10, 12, 0))


def test_rechaza_reproduccion_repetida():
    r = rep()
    with pytest.raises(ValueError, match="repetido"):
        liquidar_pais(SEPT, bolsa_colombia(), [r, r], indexar_condiciones([cond()]))


def test_solo_cuenta_las_reproducciones_del_pais_de_la_bolsa():
    plays = reps(2) + reps(8, pais_facturacion="MX")
    res = liquidar_pais(SEPT, bolsa_colombia(), plays, indexar_condiciones([cond(pct=100)]))
    [fila] = res.filas
    assert fila.reproducciones_validas == 2
    assert fila.participacion == D(1)


def test_funcion_pura_misma_entrada_misma_salida():
    a, b = _caso_colombia(10), _caso_colombia(10)
    assert [(f.titular_id, f.componente, f.regalia_usd) for f in a.filas] == [
        (f.titular_id, f.componente, f.regalia_usd) for f in b.filas
    ]


# --- Paridad con la API de contratos (EG-20) ----------------------------------------------------


@pytest.mark.parametrize("pais", [None, "CO", "PE", "MX", "AR"])
@pytest.mark.parametrize("dia", [5, 14, 15, 30])
def test_paridad_con_elegir_condicion(pais, dia):
    """La liquidación aplica la misma precedencia que `services.elegir_condicion` (RN-08 > Q7 >
    general), para no tener dos reglas que diverjan."""
    general_1 = cond(pct=50, hasta=date(2026, 9, 14), exclusiones=frozenset({"MX"}))
    general_2 = cond(pct=40, desde=date(2026, 9, 15), exclusiones=frozenset({"AR"}))
    territorial = cond(pct=60, territorio="PE", desde=date(2026, 9, 10))
    nuestras = [general_1, general_2, territorial]
    fecha = date(2026, 9, dia)

    sqlmodel = [
        Contrato(
            contrato_id=c.contrato_id,
            titular_id=c.titular_id,
            track_id=c.track_id,
            porcentaje=c.porcentaje,
            territorio=c.territorio,
            valido_desde=c.valido_desde,
            valido_hasta=c.valido_hasta,
        )
        for c in nuestras
        if c.vigente_en(fecha)
    ]
    exclusiones = {c.contrato_id: sorted(c.exclusiones) for c in nuestras}
    pct, elegida, inc = porcentaje_aplicable(
        rep(inicio=datetime(2026, 9, dia, 12, tzinfo=UTC), pais_reproduccion=pais),
        indexar_condiciones(nuestras),
    )
    try:
        ref = elegir_condicion(sqlmodel, exclusiones, pais)
    except SinCondicionVigente:
        assert elegida is None
        return
    assert elegida is not None and elegida.contrato_id == ref.contrato.contrato_id
    assert (inc is not None) == ref.excluido
    assert pct == (D(0) if ref.excluido else ref.contrato.porcentaje)
