"""Conexión a PostgreSQL. El engine se crea al primer uso, no al importar el módulo.

Así la app se puede construir sin DATABASE_URL (las pruebas sobrescriben `get_session`).
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from sonoraplay.config import database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # pool_pre_ping: tras un reinicio de RDS la API descarta conexiones muertas sin fallar.
    return create_engine(database_url(), pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    with Session(get_engine()) as session:
        yield session
