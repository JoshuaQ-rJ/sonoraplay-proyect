"""Pruebas de aceptación de la HU 04 (EG-13): un test (o más) por criterio."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sonoraplay.config import SeedConfig, database_url
from sonoraplay.seed.f3_suscripciones import ejecutar

TABLAS = [
    "planes",
    "usuarios",
    "grupos_familiares",
    "miembros_familia",
    "suscripciones",
    "pagos",
    "seed_defectos",
]


def cfg(**cambios) -> SeedConfig:
    return SeedConfig(**{"semilla": 42, "usuarios": 2_000, "tasa_defectos": 0.05, **cambios})


def huella(engine) -> dict[str, tuple]:
    """Conteo + checksum MD5 del contenido completo de cada tabla."""
    sql = "SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {} x"
    with engine.connect() as c:
        return {t: tuple(c.execute(text(sql.format(t))).one()) for t in TABLAS}


def conteos(engine) -> dict[str, int]:
    return {t: n for t, (n, _) in huella(engine).items()}


def valor(engine, sql: str):
    with engine.connect() as c:
        return c.scalar(text(sql))


# Criterio 1 — semilla fija
def test_misma_semilla_mismos_datos(db_vacia, recrear):
    ejecutar(db_vacia, cfg())
    primera = huella(db_vacia)
    recrear(db_vacia)
    ejecutar(db_vacia, cfg())
    assert huella(db_vacia) == primera


def test_otra_semilla_otros_datos(db_vacia, recrear):
    ejecutar(db_vacia, cfg())
    con_42 = huella(db_vacia)
    recrear(db_vacia)
    ejecutar(db_vacia, cfg(semilla=7))
    assert huella(db_vacia)["usuarios"] != con_42["usuarios"]


# Criterio 2 — idempotencia
def test_reejecutar_no_aumenta_conteos(db_vacia):
    ejecutar(db_vacia, cfg())
    antes = conteos(db_vacia)
    ejecutar(db_vacia, cfg())
    assert conteos(db_vacia) == antes


# Criterio 3 — volumen parametrizable (y dev es prefijo de completo)
def test_volumen_parametrizable(db_vacia):
    ejecutar(db_vacia, cfg(usuarios=1_000))
    assert 1_000 <= conteos(db_vacia)["usuarios"] <= 1_005
    ejecutar(db_vacia, cfg(usuarios=2_000))
    assert 2_000 <= conteos(db_vacia)["usuarios"] <= 2_005
    assert (
        valor(
            db_vacia,
            """SELECT count(*) FROM grupos_familiares g WHERE NOT EXISTS
                              (SELECT 1 FROM suscripciones s WHERE s.grupo_id = g.grupo_id)""",
        )
        == 0
    )


# Criterio 4 — integridad referencial
def test_sin_huerfanos(db_vacia):
    ejecutar(db_vacia, cfg())
    assert (
        valor(
            db_vacia,
            """
        SELECT (SELECT count(*) FROM suscripciones s LEFT JOIN usuarios u USING (usuario_id)
                WHERE u.usuario_id IS NULL)
             + (SELECT count(*) FROM suscripciones s LEFT JOIN planes p USING (plan_id)
                WHERE p.plan_id IS NULL)
             + (SELECT count(*) FROM pagos p LEFT JOIN suscripciones s USING (suscripcion_id)
                WHERE s.suscripcion_id IS NULL)
             + (SELECT count(*) FROM miembros_familia m LEFT JOIN usuarios u USING (usuario_id)
                WHERE u.usuario_id IS NULL)
    """,
        )
        == 0
    )


def test_fk_rechaza_pago_huerfano(db_vacia):
    with pytest.raises(IntegrityError), db_vacia.begin() as c:
        c.execute(
            text(
                "INSERT INTO pagos VALUES"
                " (gen_random_uuid(), gen_random_uuid(), '2026-01-01', 5.99, 'aprobado')"
            )
        )


# Criterio 5 — reglas de dominio
def test_reglas_de_dominio(db_vacia):
    ejecutar(db_vacia, cfg())
    assert set(valor(db_vacia, "SELECT array_agg(codigo) FROM planes")) == {
        "free",
        "individual",
        "familiar",
        "estudiante",
    }
    assert (
        valor(
            db_vacia,
            "SELECT min(n) FROM (SELECT count(*) n FROM miembros_familia GROUP BY grupo_id) g",
        )
        >= 2
    )
    assert (
        valor(
            db_vacia,
            "SELECT max(n) FROM (SELECT count(*) n FROM miembros_familia GROUP BY grupo_id) g",
        )
        <= 6
    )
    assert (
        valor(db_vacia, "SELECT count(*) FROM suscripciones WHERE motivo_fin = 'cambio_plan'") > 0
    )


NUEVO_USUARIO = text("""INSERT INTO usuarios
                        (usuario_id, nombre, email, pais_facturacion, fecha_alta)
                        VALUES (gen_random_uuid(), 'Prueba', 'prueba@example.com', 'CO', now())
                        RETURNING usuario_id""")
NUEVO_MIEMBRO = text("INSERT INTO miembros_familia VALUES (:g, :u, 'miembro', now())")


def test_trigger_bloquea_septimo_miembro(db_vacia):
    ejecutar(db_vacia, cfg())
    with db_vacia.begin() as c:
        grupo, n = c.execute(
            text("SELECT grupo_id, count(*) FROM miembros_familia GROUP BY grupo_id LIMIT 1")
        ).one()
        for _ in range(6 - n):  # completar hasta 6: debe funcionar
            c.execute(NUEVO_MIEMBRO, {"g": grupo, "u": c.scalar(NUEVO_USUARIO)})
    with pytest.raises(IntegrityError), db_vacia.begin() as c:  # el séptimo: debe fallar
        c.execute(NUEVO_MIEMBRO, {"g": grupo, "u": c.scalar(NUEVO_USUARIO)})


# Criterio 6 — defectos configurables
def test_tasa_cero_sin_defectos(db_vacia):
    ejecutar(db_vacia, cfg(tasa_defectos=0))
    assert valor(db_vacia, "SELECT count(*) FROM seed_defectos") == 0
    assert valor(db_vacia, "SELECT count(*) FROM usuarios WHERE pais_facturacion IS NULL") == 0
    assert (
        valor(
            db_vacia,
            "SELECT count(*) FROM"
            " (SELECT email FROM usuarios GROUP BY email HAVING count(*) > 1) d",
        )
        == 0
    )


def test_tasa_de_defectos_configurable(db_vacia):
    ejecutar(db_vacia, cfg(tasa_defectos=0.10))
    tasa = valor(
        db_vacia,
        "SELECT (SELECT count(*) FROM seed_defectos)::float / (SELECT count(*) FROM usuarios)",
    )
    assert 0.07 <= tasa <= 0.13
    assert valor(db_vacia, "SELECT count(*) FROM usuarios WHERE pais_facturacion IS NULL") == valor(
        db_vacia, "SELECT count(*) FROM seed_defectos WHERE tipo = 'pais_facturacion_nulo'"
    )


# Criterio 7 — la conexión sale de DATABASE_URL
def test_url_desde_entorno(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@rds.ejemplo:5432/sonoraplay")
    assert database_url().endswith("@rds.ejemplo:5432/sonoraplay")
