"""Corrección del reloj por sesión · RN-04 · paso 3 de docs/datos/eventos-f2.md (EG-22)."""

import json
from pathlib import Path

from sonoraplay.config import AtribucionOfflineConfig
from sonoraplay.reglas.atribucion import corregir_reloj_sesion
from sonoraplay.reglas.sesiones import tramos

CFG = AtribucionOfflineConfig()
DEFECTOS = Path(__file__).resolve().parents[2] / "schemas" / "ejemplos" / "defectos"


def _defecto(nombre: str) -> list[dict]:
    return json.loads((DEFECTOS / f"{nombre}.json").read_text(encoding="utf-8"))["eventos"]


def test_reloj_desfasado_3_h_se_corre_con_un_solo_desfase():
    originales = _defecto("reloj_desfasado")
    corregidos = corregir_reloj_sesion(originales, CFG)
    assert [e["device_ts"] for e in corregidos] == [
        "2026-09-17T14:00:00.250Z",
        "2026-09-17T14:03:31.010Z",
    ]
    # El mismo desfase en toda la sesión: la duración del tramo no cambia.
    assert tramos(corregidos) == tramos(originales) == [210_760]


def test_no_modifica_los_eventos_de_entrada():
    originales = _defecto("reloj_desfasado")
    copia = json.loads(json.dumps(originales))
    corregir_reloj_sesion(originales, CFG)
    assert originales == copia


def test_dentro_de_la_tolerancia_no_se_toca():
    eventos = _defecto("duplicado_por_reintento")
    assert corregir_reloj_sesion(eventos, CFG) == eventos


def test_sesion_offline_no_se_toca():
    """Su server_ts es la sincronización: corregir con él movería la escucha de mes."""
    eventos = [{**e, "is_offline": True} for e in _defecto("reloj_desfasado")]
    assert corregir_reloj_sesion(eventos, CFG) == eventos


def test_la_mediana_ignora_un_evento_atipico():
    """Un evento con un server_ts muy tardío (reintento) no arrastra a los demás."""
    eventos = _defecto("reloj_desfasado")
    atipico = {**eventos[1], "event_id": "x", "server_ts": "2026-09-18T14:00:00.000Z"}
    corregidos = corregir_reloj_sesion([*eventos, atipico], CFG)
    assert corregidos[0]["device_ts"] == "2026-09-17T14:00:00.250Z"


def test_sesion_vacia():
    assert corregir_reloj_sesion([], CFG) == []
