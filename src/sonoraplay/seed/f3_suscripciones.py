"""Seed F3 · suscripciones. Determinista, idempotente y con volumen parametrizable.

HU 04 · EG-13. Ver docs/datos/modelo-f3.md.
"""

from __future__ import annotations

import random
import unicodedata
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from faker import Faker
from sqlalchemy import Engine, MetaData, Table, func, select
from sqlalchemy.dialects.postgresql import insert

from sonoraplay.config import SeedConfig

# Fijo para siempre: cambiarlo cambia todos los IDs
NAMESPACE = uuid.UUID("6f1c2a52-8d3b-4c1e-9a77-50a0b0c0f308")

PLANES = [
    {
        "plan_id": 1,
        "codigo": "free",
        "nombre": "Gratuito con anuncios",
        "precio_usd": Decimal("0.00"),
        "max_miembros": 1,
    },
    {
        "plan_id": 2,
        "codigo": "individual",
        "nombre": "Individual",
        "precio_usd": Decimal("5.99"),
        "max_miembros": 1,
    },
    {
        "plan_id": 3,
        "codigo": "familiar",
        "nombre": "Familiar",
        "precio_usd": Decimal("9.99"),
        "max_miembros": 6,
    },
    {
        "plan_id": 4,
        "codigo": "estudiante",
        "nombre": "Estudiante",
        "precio_usd": Decimal("2.99"),
        "max_miembros": 1,
    },
]
PLAN = {p["codigo"]: p for p in PLANES}
PESOS_PLAN = {"free": 45, "individual": 30, "familiar": 10, "estudiante": 15}
CAMBIOS = {"free": "individual", "individual": "estudiante", "estudiante": "individual"}
PAISES = ["CO", "MX", "BR", "AR", "CL", "PE"]
ORDEN_CARGA = [
    "usuarios",
    "grupos_familiares",
    "miembros_familia",
    "suscripciones",
    "pagos",
    "seed_defectos",
]  # padres antes que hijos (FK)


def det_uuid(semilla: int, entidad: str, *partes: object) -> uuid.UUID:
    """UUID determinista: misma entrada, mismo UUID (RFC 9562, versión 5)."""
    return uuid.uuid5(NAMESPACE, ":".join(str(x) for x in (semilla, entidad, *partes)))


def _slug(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower().replace(" ", "")


def _ts(d: date, rng: random.Random) -> datetime:
    return datetime.combine(d, time(rng.randint(0, 23), rng.randint(0, 59)), tzinfo=UTC)


def _mensual(desde: date, hasta: date) -> Iterator[date]:
    d = desde.replace(day=min(desde.day, 28))  # el día 28 existe en todos los meses
    while d < hasta:
        yield d
        d = (d.replace(day=1) + timedelta(days=32)).replace(day=d.day)


@dataclass
class Lote:
    usuarios: list[dict] = field(default_factory=list)
    grupos_familiares: list[dict] = field(default_factory=list)
    miembros_familia: list[dict] = field(default_factory=list)
    suscripciones: list[dict] = field(default_factory=list)
    pagos: list[dict] = field(default_factory=list)
    seed_defectos: list[dict] = field(default_factory=list)

    def tamano(self) -> int:
        return sum(len(getattr(self, f.name)) for f in fields(self))


class GeneradorF3:
    def __init__(self, cfg: SeedConfig) -> None:
        self.cfg = cfg
        fake = Faker("es_CO")
        fake.seed_instance(cfg.semilla)
        # Pools pequeños: Faker se llama 1.000 veces, no 900.000
        self.nombres = [fake.first_name() for _ in range(500)]
        self.apellidos = [fake.last_name() for _ in range(500)]
        self.dias_historia = (cfg.fecha_referencia - cfg.fecha_inicio_historia).days
        self._ultimo_email: str | None = None

    def lotes(self) -> Iterator[Lote]:
        lote, i = Lote(), 0
        while i < self.cfg.usuarios:
            i = self._slot(i, lote)
            if lote.tamano() >= self.cfg.tamano_lote:
                yield lote
                lote = Lote()
        if lote.tamano():
            yield lote

    def _slot(self, i: int, lote: Lote) -> int:
        """Un usuario independiente o una familia completa. Devuelve el siguiente índice libre."""
        s = self.cfg.semilla
        rng = random.Random(f"{s}:slot:{i}")  # semilla str: determinista (usa SHA-512)
        plan = rng.choices(list(PESOS_PLAN), weights=list(PESOS_PLAN.values()))[0]
        tamano = rng.randint(2, 6) if plan == "familiar" else 1
        alta = self.cfg.fecha_inicio_historia + timedelta(
            days=rng.randint(0, self.dias_historia - 1)
        )
        titular = self._usuario(i, rng, alta, lote)

        grupo_id = None
        if plan == "familiar":
            grupo_id = det_uuid(s, "grupo", i)
            lote.grupos_familiares.append(
                {
                    "grupo_id": grupo_id,
                    "titular_id": titular["usuario_id"],
                    "creado_en": titular["fecha_alta"],
                }
            )
            lote.miembros_familia.append(
                {
                    "grupo_id": grupo_id,
                    "usuario_id": titular["usuario_id"],
                    "rol": "titular",
                    "fecha_union": titular["fecha_alta"],
                }
            )
            for j in range(i + 1, i + tamano):
                union = min(alta + timedelta(days=rng.randint(0, 60)), self.cfg.fecha_referencia)
                miembro = self._usuario(j, rng, union, lote)
                lote.miembros_familia.append(
                    {
                        "grupo_id": grupo_id,
                        "usuario_id": miembro["usuario_id"],
                        "rol": "miembro",
                        "fecha_union": miembro["fecha_alta"],
                    }
                )

        self._historial(i, rng, titular, plan, alta, grupo_id, lote)
        return i + tamano

    def _usuario(self, j: int, rng: random.Random, alta: date, lote: Lote) -> dict:
        nombre, apellido = rng.choice(self.nombres), rng.choice(self.apellidos)
        u = {
            "usuario_id": det_uuid(self.cfg.semilla, "usuario", j),
            "nombre": f"{nombre} {apellido}",
            "email": f"{_slug(nombre)}.{_slug(apellido)}.{j}@example.com",
            "pais_facturacion": rng.choice(PAISES),
            "fecha_alta": _ts(alta, rng),
            "fecha_baja": None,
        }
        self._inyectar_defecto(j, u, lote)
        self._ultimo_email = u["email"]
        lote.usuarios.append(u)
        return u

    def _inyectar_defecto(self, j: int, u: dict, lote: Lote) -> None:
        # Generador propio: cambiar la tasa no altera el resto de los datos
        rng_d = random.Random(f"{self.cfg.semilla}:defecto:{j}")
        if rng_d.random() >= self.cfg.tasa_defectos:
            return
        tipo = rng_d.choice(["email_duplicado", "pais_facturacion_nulo"])
        if tipo == "email_duplicado" and self._ultimo_email:
            u["email"] = self._ultimo_email
        else:
            tipo, u["pais_facturacion"] = "pais_facturacion_nulo", None
        lote.seed_defectos.append(
            {"entidad": "usuarios", "entidad_id": u["usuario_id"], "tipo": tipo}
        )

    def _historial(self, i, rng, titular, plan, alta, grupo_id, lote) -> None:
        """Períodos de suscripción (con cambios de plan y bajas) y sus pagos mensuales."""
        ref, s = self.cfg.fecha_referencia, self.cfg.semilla
        periodos: list[tuple[str, date, date | None, str | None]] = []
        actual, desde = plan, alta

        dias = (ref - desde).days
        if plan != "familiar" and dias > 60 and rng.random() < 0.15:  # cambio de plan
            corte = desde + timedelta(days=rng.randint(30, dias - 30))
            periodos.append((actual, desde, corte, "cambio_plan"))
            actual, desde = CAMBIOS[actual], corte

        dias = (ref - desde).days
        prob_baja = 0.10 if actual == "free" else 0.25
        if dias > 30 and rng.random() < prob_baja:  # churn
            fin = desde + timedelta(days=rng.randint(30, dias))
            motivo = "cancelacion" if rng.random() < 0.6 else "no_renovacion"
            periodos.append((actual, desde, fin, motivo))
            titular["fecha_baja"] = _ts(fin, rng)
        else:
            periodos.append((actual, desde, None, None))

        for k, (p, ini, fin, motivo) in enumerate(periodos):
            sid = det_uuid(s, "suscripcion", i, k)
            lote.suscripciones.append(
                {
                    "suscripcion_id": sid,
                    "usuario_id": titular["usuario_id"],
                    "plan_id": PLAN[p]["plan_id"],
                    "grupo_id": grupo_id if p == "familiar" else None,
                    "fecha_inicio": ini,
                    "fecha_fin": fin,
                    "motivo_fin": motivo,
                }
            )
            precio = PLAN[p]["precio_usd"]
            if precio == 0:
                continue  # el plan gratuito no genera pagos
            for n, f in enumerate(_mensual(ini, fin or ref)):
                lote.pagos.append(
                    {
                        "pago_id": det_uuid(s, "pago", i, k, n),
                        "suscripcion_id": sid,
                        "fecha_pago": f,
                        "monto_usd": precio,
                        "estado": "aprobado",
                    }
                )
            if motivo == "no_renovacion":  # el último cobro falla
                lote.pagos.append(
                    {
                        "pago_id": det_uuid(s, "pago", i, k, "rechazado"),
                        "suscripcion_id": sid,
                        "fecha_pago": fin,
                        "monto_usd": precio,
                        "estado": "rechazado",
                    }
                )


def ejecutar(engine: Engine, cfg: SeedConfig) -> dict[str, int]:
    """Carga idempotente: ON CONFLICT DO NOTHING + IDs deterministas. Devuelve conteos por tabla."""
    md = MetaData()
    tablas = {
        n: Table(n, md, autoload_with=engine) for n in ["planes", *ORDEN_CARGA]
    }  # el DDL manda

    with engine.begin() as conn:
        conn.execute(insert(tablas["planes"]).on_conflict_do_nothing(), PLANES)

    for lote in GeneradorF3(cfg).lotes():
        with engine.begin() as conn:  # una transacción por lote
            for nombre in ORDEN_CARGA:
                if filas := getattr(lote, nombre):
                    conn.execute(insert(tablas[nombre]).on_conflict_do_nothing(), filas)

    with engine.connect() as conn:
        return {n: conn.scalar(select(func.count()).select_from(t)) for n, t in tablas.items()}
