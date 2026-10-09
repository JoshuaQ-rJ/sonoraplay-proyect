"""Reglas de `services.elegir_condicion` (Q7 y RN-08). Pruebas puras, sin base de datos."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from sonoraplay.api_contratos.models import Contrato
from sonoraplay.api_contratos.services import SinCondicionVigente, elegir_condicion

TITULAR = uuid.uuid4()


def contrato(pct: int, territorio: str | None = None) -> Contrato:
    return Contrato(
        contrato_id=uuid.uuid4(),
        titular_id=TITULAR,
        track_id="A" * 22,
        porcentaje=Decimal(pct),
        territorio=territorio,
        valido_desde=date(2026, 9, 1),
    )


def test_sin_pais_usa_la_general():
    general, co = contrato(60), contrato(45, "CO")
    eleccion = elegir_condicion([general, co], {}, None)
    assert eleccion.contrato is general and not eleccion.excluido


def test_q7_pais_con_condicion_territorial_usa_la_territorial():
    general, co = contrato(60), contrato(45, "CO")
    assert elegir_condicion([general, co], {}, "CO").contrato is co


def test_q7_pais_sin_condicion_territorial_usa_la_general():
    general, co = contrato(60), contrato(45, "CO")
    assert elegir_condicion([general, co], {}, "MX").contrato is general


def test_rn08_pais_excluido_en_la_general():
    general = contrato(35)
    eleccion = elegir_condicion([general], {general.contrato_id: ["MX"]}, "MX")
    assert eleccion.contrato is general and eleccion.excluido


def test_rn08_la_exclusion_manda_sobre_la_territorial():
    # modelo-f4: la condición territorial no sustituye las exclusiones de RN-08.
    general, mx = contrato(35), contrato(55, "MX")
    eleccion = elegir_condicion([general, mx], {general.contrato_id: ["MX"]}, "MX")
    assert eleccion.excluido and eleccion.contrato is general


def test_exclusion_de_otro_pais_no_afecta():
    general = contrato(35)
    assert not elegir_condicion([general], {general.contrato_id: ["MX"]}, "CO").excluido


def test_solo_territorial_vigente_sirve_para_su_pais():
    co = contrato(45, "CO")
    assert elegir_condicion([co], {}, "CO").contrato is co


@pytest.mark.parametrize("pais", [None, "MX"])
def test_sin_condicion_aplicable_falla(pais):
    with pytest.raises(SinCondicionVigente):
        elegir_condicion([contrato(45, "CO")], {}, pais)


def test_sin_condiciones_falla():
    with pytest.raises(SinCondicionVigente):
        elegir_condicion([], {}, None)
