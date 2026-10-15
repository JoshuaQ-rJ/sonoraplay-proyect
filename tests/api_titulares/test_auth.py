"""Carga del secreto, emisión y validación de tokens (ADR-0006). Sin HTTP."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from sonoraplay.api_titulares import tokens
from sonoraplay.api_titulares.auth import (
    AUDIENCIA,
    EMISOR,
    VAR_SECRETO,
    SecretoInvalido,
    TokenInvalido,
    cargar_secreto,
    emitir_token,
    validar_token,
)
from tests.api_titulares.conftest import SECRETO_PRUEBA, T_A

# --- Secreto ---------------------------------------------------------------------------------


def test_cargar_secreto_valido():
    assert cargar_secreto({VAR_SECRETO: SECRETO_PRUEBA}) == SECRETO_PRUEBA


@pytest.mark.parametrize(
    ("entorno", "mensaje"),
    [
        ({}, "Falta"),
        ({VAR_SECRETO: ""}, "Falta"),
        ({VAR_SECRETO: "corto"}, "32 bytes"),
        ({VAR_SECRETO: "cambia_esto"}, "ejemplo"),
    ],
)
def test_cargar_secreto_rechaza_faltante_corto_o_de_ejemplo(entorno, mensaje):
    with pytest.raises(SecretoInvalido, match=mensaje):
        cargar_secreto(entorno)


def test_el_valor_de_env_example_se_rechaza():
    with open(".env.example", encoding="utf-8") as f:
        valores = dict(
            linea.strip().split("=", 1) for linea in f if "=" in linea and not linea.startswith("#")
        )
    with pytest.raises(SecretoInvalido):
        cargar_secreto({VAR_SECRETO: valores[VAR_SECRETO]})


# --- Tokens ----------------------------------------------------------------------------------


def test_emitir_y_validar_devuelve_el_titular():
    t = emitir_token(T_A, SECRETO_PRUEBA, timedelta(hours=1))
    assert validar_token(t, SECRETO_PRUEBA) == T_A


def test_claims_del_token():
    ahora = datetime(2026, 10, 9, 12, tzinfo=UTC)
    t = emitir_token(T_A, SECRETO_PRUEBA, timedelta(hours=8), ahora=ahora)
    claims = jwt.decode(t, options={"verify_signature": False})
    assert claims == {
        "sub": str(T_A),
        "iss": EMISOR,
        "aud": AUDIENCIA,
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + timedelta(hours=8)).timestamp()),
    }
    assert jwt.get_unverified_header(t)["alg"] == "HS256"


def _claims(**cambios):
    ahora = datetime.now(UTC)
    base = {
        "sub": str(T_A),
        "iss": EMISOR,
        "aud": AUDIENCIA,
        "iat": ahora,
        "exp": ahora + timedelta(hours=1),
    }
    base.update(cambios)
    return {k: v for k, v in base.items() if v is not None}


def test_token_vencido():
    t = emitir_token(
        T_A, SECRETO_PRUEBA, timedelta(hours=1), ahora=datetime.now(UTC) - timedelta(hours=2)
    )
    with pytest.raises(TokenInvalido, match="venció"):
        validar_token(t, SECRETO_PRUEBA)


@pytest.mark.parametrize(
    ("token", "descripcion"),
    [
        (jwt.encode(_claims(), "otro-secreto-" + "y" * 32, "HS256"), "firma inválida"),
        (jwt.encode(_claims(aud="api-contratos"), SECRETO_PRUEBA, "HS256"), "aud incorrecto"),
        (jwt.encode(_claims(iss="otro-emisor"), SECRETO_PRUEBA, "HS256"), "iss incorrecto"),
        (jwt.encode(_claims(sub="sello-a"), SECRETO_PRUEBA, "HS256"), "sub no es UUID"),
        (jwt.encode(_claims(sub=None), SECRETO_PRUEBA, "HS256"), "sin sub"),
        (jwt.encode(_claims(exp=None), SECRETO_PRUEBA, "HS256"), "sin exp"),
        (jwt.encode(_claims(iat=None), SECRETO_PRUEBA, "HS256"), "sin iat"),
        (jwt.encode(_claims(aud=None), SECRETO_PRUEBA, "HS256"), "sin aud"),
        (jwt.encode(_claims(), SECRETO_PRUEBA, "HS384"), "otro algoritmo"),
        (jwt.encode(_claims(), None, "none"), "alg none"),
        ("no.es.un.jwt", "basura"),
    ],
)
def test_tokens_invalidos(token, descripcion):
    with pytest.raises(TokenInvalido, match="Token inválido"):
        validar_token(token, SECRETO_PRUEBA)


# --- Script de desarrollo --------------------------------------------------------------------


def test_script_imprime_un_token_valido(secreto, capsys):
    tokens.main(["--titular", str(T_A), "--horas", "8"])
    salida = capsys.readouterr().out.strip()
    assert validar_token(salida, secreto) == T_A
    claims = jwt.decode(salida, options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 8 * 3600


def test_script_sin_secreto_falla_con_mensaje(monkeypatch):
    monkeypatch.delenv(VAR_SECRETO, raising=False)
    with pytest.raises(SystemExit, match="Falta"):
        tokens.main(["--titular", str(uuid.uuid4())])


@pytest.mark.parametrize(
    "args", [["--titular", "no-uuid"], ["--titular", str(T_A), "--horas", "0"]]
)
def test_script_valida_argumentos(secreto, args):
    with pytest.raises(SystemExit):
        tokens.main(args)
