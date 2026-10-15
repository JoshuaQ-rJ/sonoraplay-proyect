"""Aplicación FastAPI de contratos F4 (EG-20).

Uso local: `uv run --env-file .env python -m uvicorn sonoraplay.api_contratos.main:app --port 8000`
"""

from importlib.metadata import version

from fastapi import FastAPI

from sonoraplay.api_contratos.routers import contratos, salud

DESCRIPCION = """
API **interna** de contratos F4. Spark la consulta por DNS privado para obtener el % vigente de
un titular en la fecha de cada reproducción. No pasa por el ALB.

- **RN-07:** un período está vigente si `valido_desde <= fecha <= valido_hasta`
  (`valido_hasta` inclusivo; null = sin fin).
- **Q7:** si hay una condición territorial vigente para el país, se usa; si no, la general.
- **RN-08:** si el país está excluido en la condición general, `excluido = true` y `porcentaje = 0`.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="SonoraPlay · API de contratos F4",
        version=version("sonoraplay"),
        description=DESCRIPCION,
    )
    app.include_router(salud.router)
    app.include_router(contratos.router)
    return app


app = create_app()
