"""EG-24 · criterios 2, 3 y 4 contra PostgreSQL: cálculo a mano, API de sellos y append-only.

F3 pequeño, catálogo de muestra (50 titulares), F4, 100 eventos del simulador y el pipeline
completo. La regalía esperada se calcula aquí con la fórmula escrita a mano, sin `liquidar_pais`:
`(bolsa_componente × reproducciones_del_titular / reproducciones_del_componente) × % / 100`.
"""

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from sonoraplay.api_titulares.auth import VAR_SECRETO, emitir_token
from sonoraplay.api_titulares.db import get_session
from sonoraplay.api_titulares.main import create_app
from sonoraplay.catalogo import __main__ as catalogo_cli
from sonoraplay.config import ContratosConfig, SeedConfig, SimuladorConfig
from sonoraplay.esqueleto import __main__ as esqueleto_cli
from sonoraplay.esqueleto.pipeline import PERIODO_POR_DEFECTO, ejecutar
from sonoraplay.seed import f3_suscripciones, f4_contratos
from sonoraplay.simulador.f2_minimo import ejecutar as simular

MUESTRA_F1 = Path(__file__).resolve().parents[2] / "data" / "samples" / "f1_muestra.csv"
PUBLICIDAD = Decimal("20000")
SECRETO_PRUEBA = "solo-para-pruebas-" + "x" * 32
CENTAVO = Decimal("0.01")


@pytest.fixture
def entorno(db_vacia, tmp_path):
    """Base con F3, F1 y F4 cargados y 100 eventos F2 en disco, como deja `seed` + `simulador`."""
    f3_suscripciones.ejecutar(db_vacia, SeedConfig(usuarios=50))
    f1 = tmp_path / "f1"
    catalogo_cli.main(["--entrada", str(MUESTRA_F1), "--salida", str(f1), "--titulares", "50"])
    f4_contratos.ejecutar(db_vacia, f1, ContratosConfig())
    eventos = tmp_path / "eventos_f2.jsonl"
    assert simular(db_vacia, f1, eventos, SimuladorConfig()) == 100
    return db_vacia, eventos, f1


@pytest.fixture
def corrida(entorno):
    engine, eventos, f1 = entorno
    liquidacion_id, resumen = ejecutar(engine, eventos, f1, publicidad_usd=PUBLICIDAD)
    return engine, liquidacion_id, resumen


def _filas_db(conn, liquidacion_id):
    return conn.execute(
        text(
            "SELECT titular_id, componente, reproducciones_validas, porcentaje_contractual, "
            "regalia_usd FROM reporte_regalias WHERE liquidacion_id = :id"
        ),
        {"id": liquidacion_id},
    ).all()


def _bolsa_a_mano(conn, pais: str) -> dict[str, Decimal]:
    """Q5/Q8 a mano: 52 % de los pagos aprobados de septiembre del país y 45 % de la publicidad.

    Paga el dueño de la suscripción (el titular de la familia), así que su país es el de la bolsa.
    """
    pagos = conn.scalar(
        text(
            "SELECT coalesce(sum(p.monto_usd), 0) FROM pagos p "
            "JOIN suscripciones s USING (suscripcion_id) JOIN usuarios u USING (usuario_id) "
            "WHERE p.estado = 'aprobado' AND p.fecha_pago >= '2026-09-01' "
            "AND p.fecha_pago < '2026-10-01' AND u.pais_facturacion = :pais"
        ),
        {"pais": pais},
    )
    return {"suscripcion": pagos * Decimal("0.52"), "publicidad": PUBLICIDAD * Decimal("0.45")}


def _porcentaje_a_mano(conn, rep) -> Decimal:
    """RN-07, RN-08 y Q7 leyendo F4 directo: exclusión > condición territorial > general."""
    vigentes = conn.execute(
        text(
            "SELECT contrato_id, porcentaje, territorio FROM contratos "
            "WHERE titular_id = :t AND track_id = :k AND valido_desde <= :d "
            "AND (valido_hasta IS NULL OR valido_hasta >= :d)"
        ),
        {"t": rep.titular_id, "k": rep.track_id, "d": rep.fecha},
    ).all()
    general = [v for v in vigentes if v.territorio is None]
    if general and conn.scalar(
        text("SELECT 1 FROM exclusiones_territoriales WHERE contrato_id = :c AND pais = :p"),
        {"c": general[0].contrato_id, "p": rep.pais_reproduccion},
    ):
        return Decimal(0)
    territorial = [v for v in vigentes if v.territorio == rep.pais_reproduccion]
    elegida = territorial or general
    return elegida[0].porcentaje if elegida else Decimal(0)


# --- Criterio 1 y 3 ------------------------------------------------------------------------------


def test_cien_eventos_pasan_por_las_reglas_y_quedan_en_la_base(corrida):
    engine, liquidacion_id, resumen = corrida
    assert resumen.eventos == 100
    assert resumen.descartes["duracion_insuficiente"] >= 2  # escenarios A y C
    assert resumen.descartes["tope_diario"] == 1  # 11.ª del escenario D
    with engine.connect() as c:
        publicada = c.scalar(
            text("SELECT publicada_en FROM liquidaciones WHERE liquidacion_id = :id"),
            {"id": liquidacion_id},
        )
        assert publicada is not None
        assert len(_filas_db(c, liquidacion_id)) == len(resumen.resultado.filas) > 0


def test_regalia_coincide_con_el_calculo_a_mano(corrida):
    engine, liquidacion_id, resumen = corrida
    pais = resumen.pais
    del_pais = [r for r in resumen.liquidables if r.pais_facturacion == pais]
    with engine.connect() as c:
        filas = _filas_db(c, liquidacion_id)
        bolsa = _bolsa_a_mano(c, pais)
        por_componente = Counter(str(r.componente) for r in del_pais)

        # El titular con mayor regalía en la base.
        totales = defaultdict(Decimal)
        for f in filas:
            totales[f.titular_id] += f.regalia_usd
        titular = max(totales, key=lambda t: (totales[t], str(t)))

        # Sus reproducciones agrupadas a mano por (componente, %).
        conteo = Counter(
            (str(r.componente), _porcentaje_a_mano(c, r).quantize(CENTAVO))
            for r in del_pais
            if r.titular_id == titular
        )

    esperadas = {
        (comp, pct): bolsa[comp] * n / por_componente[comp] * pct / 100
        for (comp, pct), n in conteo.items()
    }
    reales = {
        (f.componente, f.porcentaje_contractual): (f.reproducciones_validas, f.regalia_usd)
        for f in filas
        if f.titular_id == titular
    }
    assert reales.keys() == esperadas.keys()
    for clave, esperada in esperadas.items():
        repro, regalia = reales[clave]
        assert repro == conteo[clave]  # RNF-03: las reproducciones que respaldan la fila
        assert abs(regalia - esperada) <= CENTAVO, (clave, regalia, esperada)

    # Los denominadores a mano son los mismos que quedaron en la base.
    for comp, n in por_componente.items():
        assert sum(f.reproducciones_validas for f in filas if f.componente == comp) == n


# --- Criterios 2 y 4: la API de sellos ------------------------------------------------------------


@pytest.fixture
def cliente(monkeypatch, corrida):
    monkeypatch.setenv(VAR_SECRETO, SECRETO_PRUEBA)
    engine = corrida[0]
    app = create_app()

    def _sesion():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _sesion
    with TestClient(app) as c:
        yield c


def _reporte(cliente, titular):
    token = emitir_token(titular, SECRETO_PRUEBA, timedelta(hours=1))
    r = cliente.get(
        "/me/reportes",
        params={"periodo": f"{PERIODO_POR_DEFECTO:%Y-%m}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _mayor_titular(resumen):
    totales = defaultdict(Decimal)
    for f in resumen.resultado.filas:
        totales[f.titular_id] += f.regalia_usd
    return max(totales, key=lambda t: (totales[t], str(t))), totales


def test_sello_consulta_su_regalia_con_id_y_reproducciones(cliente, corrida):
    _, liquidacion_id, resumen = corrida
    titular, totales = _mayor_titular(resumen)
    cuerpo = _reporte(cliente, titular)
    filas = [f for f in resumen.resultado.filas if f.titular_id == titular]

    assert cuerpo["titular_id"] == str(titular)
    assert len(cuerpo["filas"]) == len(filas)
    for f in cuerpo["filas"]:
        assert f["liquidacion_id"] == str(liquidacion_id)  # RNF-03
        assert f["reproducciones_validas"] > 0  # RNF-03
        assert f["pais"] == resumen.pais
    (total,) = cuerpo["totales"]
    assert total["liquidacion_id"] == str(liquidacion_id)
    assert Decimal(total["regalia_usd"]) == totales[titular] > 0
    assert total["reproducciones_validas"] == sum(f.reproducciones_validas for f in filas)


# --- Append-only (ADR-0007) ----------------------------------------------------------------------


def test_segunda_corrida_crea_otra_liquidacion_y_la_primera_queda_intacta(
    cliente, corrida, entorno
):
    engine, primera, resumen = corrida
    _, eventos, f1 = entorno
    with engine.connect() as c:
        antes = sorted(_filas_db(c, primera))
        publicada_antes = c.scalar(
            text("SELECT publicada_en FROM liquidaciones WHERE liquidacion_id = :id"),
            {"id": primera},
        )

    segunda, _ = ejecutar(engine, eventos, f1, publicidad_usd=PUBLICIDAD)

    assert segunda != primera
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM liquidaciones")) == 2
        assert sorted(_filas_db(c, primera)) == antes
        assert (
            c.scalar(
                text("SELECT publicada_en FROM liquidaciones WHERE liquidacion_id = :id"),
                {"id": primera},
            )
            == publicada_antes
        )
    titular, _ = _mayor_titular(resumen)
    cuerpo = _reporte(cliente, titular)
    assert {f["liquidacion_id"] for f in cuerpo["filas"]} == {str(segunda)}


def test_la_cli_imprime_el_resumen_con_token_y_curl(entorno, monkeypatch, capsys):
    engine, eventos, f1 = entorno
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    esqueleto_cli.main(["--eventos", str(eventos), "--datos-f1", str(f1)])
    salida = capsys.readouterr().out
    assert "ID de liquidación:" in salida
    assert "python -m sonoraplay.api_titulares.tokens --titular " in salida
    assert "http://localhost:8001/me/reportes?periodo=2026-09" in salida
    assert "PROVISIONAL" in salida
