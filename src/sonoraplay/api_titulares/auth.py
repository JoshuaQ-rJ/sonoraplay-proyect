"""Autenticación de sellos con JWT HS256 (ADR-0006).

El token identifica a un titular (`sub`). Cualquier fallo es 401 con `WWW-Authenticate: Bearer`;
el aislamiento entre titulares (403) se aplica en el router, antes de consultar la base.
"""

import os
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

VAR_SECRETO = "API_TITULARES_JWT_SECRET"
ALGORITMO = "HS256"
EMISOR = "sonoraplay"
AUDIENCIA = "api-titulares"
# RFC 7518 §3.2: la clave de HS256 debe tener al menos 256 bits.
BYTES_MINIMOS_SECRETO = 32
# Prefijo del valor falso de .env.example: la app se niega a arrancar con él.
PREFIJO_EJEMPLO = "cambia_esto"


class SecretoInvalido(RuntimeError):
    pass


class TokenInvalido(Exception):
    """El mensaje es apto para el cliente: no repite el error interno de PyJWT."""


def cargar_secreto(entorno: Mapping[str, str] = os.environ) -> str:
    """Secreto de firma desde el entorno. Nunca hay un valor por defecto."""
    secreto = entorno.get(VAR_SECRETO, "")
    if not secreto:
        raise SecretoInvalido(
            f"Falta {VAR_SECRETO}. Genera uno con "
            '`uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` '
            "y guárdalo en .env (en AWS sale de SSM Parameter Store, ADR-0017)."
        )
    if secreto.startswith(PREFIJO_EJEMPLO):
        raise SecretoInvalido(f"{VAR_SECRETO} tiene el valor de ejemplo de .env.example.")
    if len(secreto.encode()) < BYTES_MINIMOS_SECRETO:
        raise SecretoInvalido(
            f"{VAR_SECRETO} debe tener al menos {BYTES_MINIMOS_SECRETO} bytes (RFC 7518 §3.2)."
        )
    return secreto


def emitir_token(
    titular_id: uuid.UUID, secreto: str, duracion: timedelta, ahora: datetime | None = None
) -> str:
    ahora = ahora or datetime.now(UTC)
    claims = {
        "sub": str(titular_id),
        "iss": EMISOR,
        "aud": AUDIENCIA,
        "iat": ahora,
        "exp": ahora + duracion,
    }
    return jwt.encode(claims, secreto, algorithm=ALGORITMO)


def validar_token(token: str, secreto: str) -> uuid.UUID:
    """Valida firma, algoritmo, `exp`, `iss` y `aud`, y devuelve `sub` como UUID."""
    try:
        claims = jwt.decode(
            token,
            secreto,
            algorithms=[ALGORITMO],
            audience=AUDIENCIA,
            issuer=EMISOR,
            options={"require": ["sub", "iss", "aud", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise TokenInvalido("El token venció") from None
    except jwt.InvalidTokenError:
        raise TokenInvalido("Token inválido") from None
    try:
        return uuid.UUID(claims["sub"])
    except (TypeError, ValueError):
        raise TokenInvalido("Token inválido") from None


esquema_bearer = HTTPBearer(
    auto_error=False,
    description="JWT HS256 emitido por SonoraPlay para un titular (ADR-0006). "
    "Pega solo el token, sin el prefijo `Bearer`.",
)


def _no_autenticado(mensaje: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, mensaje, headers={"WWW-Authenticate": "Bearer"}
    )


def titular_autenticado(
    request: Request,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema_bearer)],
) -> uuid.UUID:
    """Dependencia de FastAPI: titular del token, o 401."""
    if credenciales is None or credenciales.scheme.lower() != "bearer":
        raise _no_autenticado("Falta el token de acceso")
    try:
        return validar_token(credenciales.credentials, request.app.state.jwt_secreto)
    except TokenInvalido as e:
        raise _no_autenticado(str(e)) from None


TitularAutenticado = Annotated[uuid.UUID, Depends(titular_autenticado)]
