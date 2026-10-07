import os
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

DDL_DIR = Path(__file__).resolve().parents[1] / "db" / "ddl"


def _recrear_esquema(engine: Engine) -> None:
    # Se usa el cursor nativo de psycopg sin parámetros: con exec_driver_sql, el '%' del
    # RAISE EXCEPTION del trigger se interpreta como placeholder y la carga del DDL falla.
    with engine.begin() as c:
        cur = c.connection.driver_connection.cursor()
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        for ddl in sorted(DDL_DIR.glob("*.sql")):
            cur.execute(ddl.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def engine():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        if not c.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}):
            c.exec_driver_sql(f'CREATE DATABASE "{url.database}"')
    admin.dispose()
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def recrear():
    return _recrear_esquema


@pytest.fixture
def db_vacia(engine, recrear):
    recrear(engine)
    return engine
