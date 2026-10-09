"""Aplicación FastAPI de sellos (EG-21). Única API pública: va detrás del ALB con HTTPS.

Uso local:
`uv run --env-file .env python -m uvicorn sonoraplay.api_titulares.main:app --port 8001`
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI

from sonoraplay.api_titulares.auth import cargar_secreto
from sonoraplay.api_titulares.routers import reportes, salud

DESCRIPCION = """
API **pública** de sellos, distribuidoras y sociedades de gestión (RF-05). En AWS va detrás del
ALB, que solo acepta HTTPS.

**Autenticación (ADR-0006):** `Authorization: Bearer <token>`, un JWT HS256 que identifica a un
titular. Usa el botón **Authorize** y pega solo el token.

- **RN-11 / CA-08:** cada titular ve solo su reporte. Pedir otro titular da **403** con el mismo
  mensaje exista o no. Sin token, o con uno vencido o inválido, **401**.
- **Recomendado:** `GET /me/reportes`, que toma el titular del token.
- Se muestra la **última liquidación publicada** de cada mes (re-liquidaciones, ADR-0007).
- **Dinero y decimales como string** (`"2800.00"`): un número JSON se lee como float y puede perder
  centavos (RNF-02). `regalia_usd` y `porcentaje_contractual` llevan 2 decimales;
  `participacion`, 6.
"""


@asynccontextmanager
async def _ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    # Sin secreto válido la app no arranca (ADR-0006). Se lee aquí y no al importar, para que
    # el módulo se pueda importar sin la variable.
    app.state.jwt_secreto = cargar_secreto()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="SonoraPlay · API de sellos",
        version=version("sonoraplay"),
        description=DESCRIPCION,
        lifespan=_ciclo_de_vida,
    )
    app.include_router(salud.router)
    app.include_router(reportes.router)
    return app


app = create_app()
