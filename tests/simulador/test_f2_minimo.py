"""Pruebas de aceptación de EG-19 · simulador F2 mínimo (criterios 2, 3 y 4)."""

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from sonoraplay.catalogo import __main__ as catalogo_cli
from sonoraplay.config import ContratosConfig, SeedConfig, SimuladorConfig
from sonoraplay.reglas.sesiones import reconstruir, tramos
from sonoraplay.reglas.validez import MotivoValidez, aplicar_tope_diario, dia_utc
from sonoraplay.seed import f3_suscripciones, f4_contratos
from sonoraplay.simulador import __main__ as simulador_cli
from sonoraplay.simulador.f2_minimo import (
    CAMPOS,
    ESQUEMA_F2,
    FuentesSimulador,
    Pista,
    Usuario,
    ejecutar,
    generar,
    leer_fuentes,
    validador,
)

MUESTRA_F1 = Path(__file__).resolve().parents[2] / "data" / "samples" / "f1_muestra.csv"
CFG = SimuladorConfig()
UMBRAL = CFG.reglas.segundos_min_validez * 1_000


@pytest.fixture(scope="module")
def fuentes() -> FuentesSimulador:
    usuarios = tuple(
        Usuario(f"00000000-0000-4000-8000-{i:012d}", None if i % 4 == 0 else "CO")
        for i in range(20)
    )
    # 22 caracteres base62 y duraciones de 4 s a ~11 min: hay pistas cortas, límite y largas.
    pistas = tuple(Pista(f"{i:02d}" + "x" * 20, 4_000 + i * 17_000) for i in range(40))
    return FuentesSimulador(usuarios, pistas)


@pytest.fixture(scope="module")
def eventos(fuentes) -> list[dict]:
    return generar(fuentes, CFG)


def _por_sesion(eventos: list[dict]) -> dict[str, list[dict]]:
    sesiones = defaultdict(list)
    for e in eventos:
        sesiones[e["session_id"]].append(e)
    return sesiones


def _ts(e: dict) -> datetime:
    return datetime.fromisoformat(e["device_ts"])


# --- Volumen y esquema (criterios 1 y 2) -----------------------------------------------------


def test_genera_exactamente_cfg_eventos(eventos):
    assert len(eventos) == CFG.eventos


@pytest.mark.parametrize("n", [30, 31, 32, 33, 57])
def test_cualquier_volumen_desde_el_minimo_cuadra_exacto(fuentes, n):
    evs = generar(fuentes, SimuladorConfig(eventos=n))
    assert len(evs) == n
    for sesion in _por_sesion(evs).values():
        assert sesion[-1]["event_type"] in {"end", "skip"}


def test_todos_validan_contra_el_esquema_con_format_checker(eventos):
    v = validador()
    assert v.format_checker is not None
    errores = [(e["event_id"], err.message) for e in eventos for err in v.iter_errors(e)]
    assert errores == []


def test_claves_en_el_orden_del_esquema(eventos):
    requeridos = json.loads(ESQUEMA_F2.read_text(encoding="utf-8"))["required"]
    assert list(CAMPOS) == requeridos
    assert all(list(e) == requeridos for e in eventos)


def test_usuarios_y_pistas_salen_de_las_fuentes(fuentes, eventos):
    assert {e["user_id"] for e in eventos} <= {u.usuario_id for u in fuentes.usuarios}
    assert {e["track_id"] for e in eventos} <= {p.track_id for p in fuentes.pistas}


# --- Determinismo (criterio 3) ---------------------------------------------------------------


def test_misma_semilla_misma_lista(fuentes, eventos):
    assert generar(fuentes, CFG) == eventos


def test_otra_semilla_otra_lista(fuentes, eventos):
    assert generar(fuentes, SimuladorConfig(semilla=7)) != eventos


# --- Reglas de cada sesión (docs/datos/eventos-f2.md) ----------------------------------------


def test_cada_sesion_empieza_con_start_y_cierra_con_end_o_skip(eventos):
    for sesion in _por_sesion(eventos).values():
        tipos = [e["event_type"] for e in sesion]
        assert tipos[0] == "start" and sesion[0]["position_ms"] == 0
        assert tipos[-1] in {"end", "skip"}
        assert not {"end", "skip"} & set(tipos[:-1])  # nada después del cierre
        assert len({(e["user_id"], e["device_id"], e["track_id"]) for e in sesion}) == 1


def test_position_ms_avanza_con_el_reloj_y_se_congela_en_pausa(eventos):
    for sesion in _por_sesion(eventos).values():
        for antes, despues in zip(sesion, sesion[1:], strict=False):
            d_pos = despues["position_ms"] - antes["position_ms"]
            d_ts = (_ts(despues) - _ts(antes)) // timedelta(milliseconds=1)
            if antes["event_type"] in {"start", "resume"}:
                assert d_pos == d_ts > 0
            else:  # pause: el reloj avanza y la posición no
                assert antes["event_type"] == "pause"
                assert d_pos == 0 and d_ts > 0


def test_end_solo_al_final_de_la_pista(fuentes, eventos):
    duracion = {p.track_id: p.duration_ms for p in fuentes.pistas}
    for e in eventos:
        assert e["position_ms"] <= duracion[e["track_id"]]
        if e["event_type"] == "end":
            assert e["position_ms"] == duracion[e["track_id"]]
        if e["event_type"] == "skip":
            assert e["position_ms"] < duracion[e["track_id"]]


def test_timestamps_online_y_pais_de_facturacion(fuentes, eventos):
    pais = {u.usuario_id: u.pais_facturacion for u in fuentes.usuarios}
    for e in eventos:
        assert e["device_ts"].endswith("Z") and len(e["device_ts"]) == 24  # con milisegundos
        latencia = datetime.fromisoformat(e["server_ts"]) - _ts(e)
        assert timedelta(milliseconds=100) <= latencia <= timedelta(milliseconds=500)
        assert e["is_offline"] is False
        assert e["country_playback"] == (pais[e["user_id"]] or e["country_playback"])
    # Un usuario sin país de facturación reproduce siempre desde el mismo país.
    paises = defaultdict(set)
    for e in eventos:
        paises[e["user_id"]].add(e["country_playback"])
    assert all(len(p) == 1 for p in paises.values())


def test_todo_en_la_fecha_base_y_ordenado(eventos):
    assert all(_ts(e).date() == CFG.fecha_base for e in eventos)
    assert [e["device_ts"] for e in eventos] == sorted(e["device_ts"] for e in eventos)


def test_un_usuario_no_tiene_sesiones_solapadas(eventos):
    por_usuario = defaultdict(list)
    for sesion in _por_sesion(eventos).values():
        por_usuario[sesion[0]["user_id"]].append((_ts(sesion[0]), _ts(sesion[-1])))
    for intervalos in por_usuario.values():
        intervalos.sort()
        for (_, fin), (inicio, _) in zip(intervalos, intervalos[1:], strict=False):
            assert fin < inicio


# --- Escenarios RN-01 y RN-02 (criterio 4) ---------------------------------------------------


@pytest.fixture(scope="module")
def resultados(eventos):
    reps = reconstruir(eventos)
    return reps, {r.reproduccion_id: r for r in aplicar_tope_diario(reps, CFG.reglas)}


def test_a_menos_de_30_s_no_es_valida(resultados):
    reps, res = resultados
    a = [r for r in reps if r.ms_continuos_max == UMBRAL - 1_000]
    assert a
    assert all(res[r.reproduccion_id].motivo == MotivoValidez.DURACION_INSUFICIENTE for r in a)


def test_b_exactamente_30_s_es_valida(resultados):
    reps, res = resultados
    b = [r for r in reps if r.ms_continuos_max == UMBRAL]
    assert b
    assert all(res[r.reproduccion_id].valida_rn01 for r in b)


def test_c_la_pausa_reinicia_el_conteo(eventos, resultados):
    _, res = resultados
    c = [
        sid
        for sid, sesion in _por_sesion(eventos).items()
        if tramos(sesion) == [UMBRAL // 2, UMBRAL * 2 // 3]
    ]
    assert c
    assert all(res[sid].motivo == MotivoValidez.DURACION_INSUFICIENTE for sid in c)


def test_d_11_validas_mismo_usuario_pista_y_dia_con_un_solo_tope(resultados):
    reps, res = resultados
    grupos = defaultdict(list)
    for r in reps:
        if res[r.reproduccion_id].valida_rn01:
            grupos[(r.cuenta_id, r.track_id, dia_utc(r))].append(r)
    tope = CFG.reglas.max_reproducciones_dia
    d = [g for g in grupos.values() if len(g) > tope]
    assert len(d) == 1 and len(d[0]) == tope + 1
    assert all(r.ms_continuos_max >= 60_000 for r in d[0])
    motivos = Counter(res[r.reproduccion_id].motivo for r in d[0])
    assert motivos == {MotivoValidez.PAGABLE: tope, MotivoValidez.TOPE_DIARIO: 1}
    assert Counter(x.motivo for x in res.values())[MotivoValidez.TOPE_DIARIO] == 1


@pytest.mark.parametrize("semilla", range(10))
def test_los_escenarios_aparecen_con_cualquier_semilla(fuentes, semilla):
    evs = generar(fuentes, SimuladorConfig(semilla=semilla, eventos=31))
    reps = reconstruir(evs)
    res = Counter(r.motivo for r in aplicar_tope_diario(reps, CFG.reglas))
    assert res[MotivoValidez.TOPE_DIARIO] == 1
    ms = Counter(r.ms_continuos_max for r in reps)
    assert ms[UMBRAL - 1_000] >= 1 and ms[UMBRAL] >= 1


# --- Configuración ---------------------------------------------------------------------------


def test_pocos_eventos_para_los_escenarios_lanza_value_error():
    with pytest.raises(ValueError, match="al menos 30"):
        SimuladorConfig(eventos=5)


def test_la_cli_rechaza_pocos_eventos():
    with pytest.raises(SystemExit):
        simulador_cli.main(["--eventos", "5"])


def test_sin_fuentes_lanza_error(fuentes):
    with pytest.raises(ValueError, match="al menos un usuario"):
        generar(FuentesSimulador((), fuentes.pistas), CFG)


def test_sin_pistas_largas_para_los_escenarios_lanza_error(fuentes):
    cortas = tuple(p for p in fuentes.pistas if p.duration_ms < UMBRAL)
    with pytest.raises(ValueError, match="no hay pistas"):
        generar(FuentesSimulador(fuentes.usuarios, cortas), CFG)


# --- Integración con PostgreSQL y el catálogo F1 de muestra ----------------------------------


def test_base_vacia_dice_que_seed_correr(db_vacia, tmp_path):
    with pytest.raises(ValueError, match="sonoraplay.seed"):
        leer_fuentes(db_vacia, tmp_path, CFG.fecha_base)


def test_extremo_a_extremo_con_f1_f3_y_f4(db_vacia, tmp_path, monkeypatch):
    f3_suscripciones.ejecutar(db_vacia, SeedConfig(usuarios=50))
    f1 = tmp_path / "f1"
    catalogo_cli.main(["--entrada", str(MUESTRA_F1), "--salida", str(f1), "--titulares", "50"])
    f4_contratos.ejecutar(db_vacia, f1, ContratosConfig())

    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    assert ejecutar(db_vacia, f1, a, CFG) == CFG.eventos
    # La segunda corrida usa la CLI, con DATABASE_URL apuntando a la base de pruebas.
    monkeypatch.setenv("DATABASE_URL", db_vacia.url.render_as_string(hide_password=False))
    simulador_cli.main(["--salida", str(b), "--datos-f1", str(f1)])

    contenido = a.read_bytes()
    assert contenido == b.read_bytes()  # criterio 3: byte por byte
    assert b"\r\n" not in contenido and contenido.endswith(b"\n")
    evs = [json.loads(linea) for linea in contenido.decode("utf-8").splitlines()]
    assert len(evs) == CFG.eventos

    with db_vacia.connect() as conn:
        usuarios = set(conn.scalars(text("SELECT usuario_id::text FROM usuarios")))
        generales = set(
            conn.execute(
                text("SELECT track_id, titular_id::text FROM contratos WHERE territorio IS NULL")
            ).all()
        )
    titular = {
        str(t): str(tid)
        for t, tid in f4_contratos.leer_fuentes(f1).catalogo[["track_id", "titular_id"]].values
    }
    assert {e["user_id"] for e in evs} <= usuarios
    assert all(e["track_id"] in titular for e in evs)  # existe en F1
    assert all((e["track_id"], titular[e["track_id"]]) in generales for e in evs)  # y en F4
