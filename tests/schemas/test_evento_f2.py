"""Pruebas del esquema JSON de eventos F2 · EG-15 · ADR-0004.

Válidos e inválidos son un evento por archivo. Cada archivo de defectos trae varios eventos que
deben pasar el esquema: son defectos de negocio, no de formato.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

RAIZ = Path(__file__).resolve().parents[2]
ESQUEMA = RAIZ / "schemas" / "f2_evento.schema.json"
EJEMPLOS = RAIZ / "schemas" / "ejemplos"
MUESTRA_F1 = RAIZ / "data" / "samples" / "f1_muestra.csv"

TIPOS = {"start", "pause", "resume", "skip", "end"}
DEFECTOS = {
    "evento_sin_fin",
    "reloj_desfasado",
    "track_desconocido",
    "duplicado_por_reintento",
    "pais_facturacion_distinto",
}


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _archivos(carpeta: str) -> list[Path]:
    return sorted((EJEMPLOS / carpeta).glob("*.json"))


def _ids(rutas: list[Path]) -> list[str]:
    return [r.stem for r in rutas]


def _ts(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


@pytest.fixture(scope="module")
def validador() -> Draft202012Validator:
    return Draft202012Validator(_leer(ESQUEMA), format_checker=FormatChecker())


# --- El esquema ------------------------------------------------------------------------------


def test_el_esquema_es_draft_2020_12_valido():
    esquema = _leer(ESQUEMA)
    assert esquema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(esquema)


def test_no_admite_campos_extra_y_todos_son_obligatorios():
    esquema = _leer(ESQUEMA)
    assert esquema["additionalProperties"] is False
    assert set(esquema["required"]) == set(esquema["properties"])


def test_format_checker_valida_de_verdad_uuid_y_date_time():
    """Sin rfc3339-validator, jsonschema ignora `date-time` en silencio (ADR-0004)."""
    checker = FormatChecker()
    assert {"uuid", "date-time"} <= set(checker.checkers)
    assert not checker.conforms("2026-02-30T14:00:00Z", "date-time")
    assert not checker.conforms("evento-123", "uuid")


# --- Ejemplos --------------------------------------------------------------------------------


def test_hay_un_valido_por_cada_event_type():
    assert {_leer(r)["event_type"] for r in _archivos("validos")} == TIPOS


@pytest.mark.parametrize("ruta", _archivos("validos"), ids=_ids(_archivos("validos")))
def test_eventos_validos_pasan(validador, ruta):
    errores = [e.message for e in validador.iter_errors(_leer(ruta))]
    assert errores == []


@pytest.mark.parametrize("ruta", _archivos("invalidos"), ids=_ids(_archivos("invalidos")))
def test_eventos_invalidos_fallan(validador, ruta):
    assert not validador.is_valid(_leer(ruta))


def test_cubre_los_invalidos_minimos_de_eg_15():
    nombres = set(_ids(_archivos("invalidos")))
    assert {"sin_event_id", "event_type_desconocido", "position_ms_negativa"} <= nombres


# --- Defectos de negocio ---------------------------------------------------------------------


def test_hay_un_archivo_por_cada_defecto():
    assert {_leer(r)["defecto"] for r in _archivos("defectos")} == DEFECTOS
    assert set(_ids(_archivos("defectos"))) == DEFECTOS


@pytest.mark.parametrize("ruta", _archivos("defectos"), ids=_ids(_archivos("defectos")))
def test_defectos_pasan_el_esquema(validador, ruta):
    caso = _leer(ruta)
    assert caso["eventos"], "un defecto debe traer al menos un evento"
    for evento in caso["eventos"]:
        errores = [e.message for e in validador.iter_errors(evento)]
        assert errores == [], f"{evento['event_id']}: {errores}"


def _eventos(defecto: str) -> list[dict]:
    return _leer(EJEMPLOS / "defectos" / f"{defecto}.json")["eventos"]


def test_defecto_evento_sin_fin_no_tiene_end_ni_skip():
    eventos = _eventos("evento_sin_fin")
    assert eventos[0]["event_type"] == "start"
    assert not {e["event_type"] for e in eventos} & {"end", "skip"}


def test_defecto_reloj_desfasado_es_online_y_se_aleja_del_servidor():
    for e in _eventos("reloj_desfasado"):
        assert e["is_offline"] is False
        assert abs(_ts(e["server_ts"]) - _ts(e["device_ts"])) >= timedelta(hours=1)


def test_defecto_track_desconocido_no_esta_en_la_muestra_f1():
    muestra = MUESTRA_F1.read_text(encoding="utf-8")
    for e in _eventos("track_desconocido"):
        assert e["track_id"] not in muestra


def test_defecto_duplicado_repite_event_id_y_contenido():
    eventos = _eventos("duplicado_por_reintento")
    por_id: dict[str, list[dict]] = {}
    for e in eventos:
        por_id.setdefault(e["event_id"], []).append(e)
    repetidos = [grupo for grupo in por_id.values() if len(grupo) > 1]
    assert len(repetidos) == 1
    original, reintento = repetidos[0]
    # Solo cambia server_ts: deduplicar por el contenido completo no detectaría el reintento.
    assert original["server_ts"] != reintento["server_ts"]
    sin_server = [{k: v for k, v in e.items() if k != "server_ts"} for e in (original, reintento)]
    assert sin_server[0] == sin_server[1]


def test_defecto_pais_facturacion_distinto_del_de_reproduccion():
    caso = _leer(EJEMPLOS / "defectos" / "pais_facturacion_distinto.json")
    for e in caso["eventos"]:
        assert e["user_id"] == caso["contexto"]["user_id"]
        assert e["country_playback"] != caso["contexto"]["pais_facturacion_f3"]
