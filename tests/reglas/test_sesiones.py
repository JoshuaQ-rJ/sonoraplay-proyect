"""Reconstrucción de reproducciones desde eventos F2 · EG-19 · docs/datos/eventos-f2.md."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sonoraplay.reglas.sesiones import deduplicar, reconstruir, tramos

EJEMPLOS = Path(__file__).resolve().parents[2] / "schemas" / "ejemplos"


def _validos() -> list[dict]:
    return [
        json.loads((EJEMPLOS / "validos" / f"{t}.json").read_text(encoding="utf-8"))
        for t in ("start", "pause", "resume", "end", "skip")
    ]


def _defecto(nombre: str) -> list[dict]:
    datos = json.loads((EJEMPLOS / "defectos" / f"{nombre}.json").read_text(encoding="utf-8"))
    return datos["eventos"]


def ev(tipo: str, seg: float, pos_ms: int, n: int = 0, sesion: str = "s1") -> dict:
    """Evento mínimo: lo que usa reconstruir, con device_ts a `seg` segundos de las 12:00 UTC."""
    ts = datetime(2026, 9, 15, 12, 0, tzinfo=UTC).timestamp() + seg
    iso = datetime.fromtimestamp(ts, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "event_id": f"{sesion}-{n}",
        "event_type": tipo,
        "user_id": "u1",
        "track_id": "t1",
        "session_id": sesion,
        "device_ts": iso,
        "server_ts": iso,
        "position_ms": pos_ms,
    }


def test_ejemplo_del_documento_da_los_dos_tramos():
    """La sesión de validos/ (start, pause, resume, end) del ejemplo de eventos-f2.md."""
    sesion = [e for e in _validos() if e["event_type"] != "skip"]
    assert tramos(sesion) == [45_000, 165_760]
    (rep,) = reconstruir(sesion)
    assert rep.reproduccion_id == sesion[0]["session_id"]
    assert rep.cuenta_id == sesion[0]["user_id"]
    assert rep.track_id == "23Mcmg5O8rBKAOzxvrTjnD"
    assert rep.inicio == datetime(2026, 9, 15, 14, 0, tzinfo=UTC)
    assert rep.ms_continuos_max == 165_760


def test_el_orden_de_entrada_no_importa():
    sesion = [e for e in _validos() if e["event_type"] != "skip"]
    assert reconstruir(list(reversed(sesion))) == reconstruir(sesion)


def test_sesion_sin_start_no_produce_reproduccion():
    """skip.json es de otra sesión y viene solo: no hay start desde el cual contar."""
    reps = reconstruir(_validos())
    assert len(reps) == 1


def test_evento_sin_fin_cuenta_cero_el_tramo_abierto():
    eventos = _defecto("evento_sin_fin")
    assert tramos(eventos) == [40_000, 0]
    (rep,) = reconstruir(eventos)
    assert rep.ms_continuos_max == 40_000


def test_duplicado_por_reintento_conserva_el_menor_server_ts():
    eventos = _defecto("duplicado_por_reintento")
    unicos = deduplicar(eventos)
    assert len(unicos) == len(eventos) - 1
    start = next(e for e in unicos if e["event_type"] == "start")
    assert start["server_ts"] == min(e["server_ts"] for e in eventos if e["event_type"] == "start")
    (rep,) = reconstruir(eventos)
    assert rep.ms_continuos_max == 210_760


def test_la_pausa_reinicia_el_tramo():
    """EG-11 Q1: 15 s + 20 s no suman 30 s continuos."""
    sesion = [ev("start", 0, 0, 0), ev("pause", 15, 15_000, 1)]
    sesion += [ev("resume", 40, 15_000, 2), ev("skip", 60, 35_000, 3)]
    assert tramos(sesion) == [15_000, 20_000]
    assert reconstruir(sesion)[0].ms_continuos_max == 20_000


@pytest.mark.parametrize(
    ("pos_fin", "seg_fin", "esperado"),
    [
        (90_000, 30, 30_000),  # avanza más que el tiempo transcurrido: manda el reloj
        (20_000, 60, 20_000),  # tiempo de sobra: manda la posición
        (0, 10, 0),  # posición hacia atrás: nunca negativo
    ],
)
def test_tramo_inconsistente_cuenta_el_minimo(pos_fin, seg_fin, esperado):
    sesion = [ev("start", 0, 5_000 if pos_fin == 0 else 0, 0), ev("end", seg_fin, pos_fin, 1)]
    assert tramos(sesion) == [esperado]


def test_eventos_fuera_de_orden_y_despues_del_cierre_se_ignoran():
    sesion = [
        ev("pause", 0, 0, 0),  # pause sin tramo abierto
        ev("resume", 1, 0, 1),  # resume antes del start
        ev("start", 2, 0, 2),
        ev("start", 3, 1_000, 3),  # segundo start: no abre otro tramo
        ev("skip", 42, 40_000, 4),
        ev("resume", 50, 40_000, 5),  # después del cierre
        ev("end", 200, 190_000, 6),
    ]
    assert tramos(sesion) == [40_000]


def test_varias_sesiones_ordenadas_por_inicio():
    a = [ev("start", 100, 0, 0, "a"), ev("end", 160, 60_000, 1, "a")]
    b = [ev("start", 0, 0, 0, "b"), ev("skip", 10, 10_000, 1, "b")]
    reps = reconstruir(a + b)
    assert [r.reproduccion_id for r in reps] == ["b", "a"]
    assert [r.ms_continuos_max for r in reps] == [10_000, 60_000]
