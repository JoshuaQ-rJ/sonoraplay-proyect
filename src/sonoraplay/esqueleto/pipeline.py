"""Esqueleto de punta a punta (EG-24): eventos F2 → reglas → liquidación de un país → base.

Une lo que ya existe sin reimplementar reglas:

1. Eventos F2 del simulador (EG-19), validados contra el esquema (EG-15).
2. `reconstruir` (EG-19, reloj corregido por la EG-22) y `atribuir_reproduccion` (RN-04).
3. `aplicar_tope_diario` (RN-01, RN-02, EG-17). RN-03 (fraude) no entra: el simulador mínimo no
   genera granjas (EG-51).
4. F1 (pista → titular), F3 (país Q6/RN-10, plan Q8, pagos Q5) y F4 (condiciones RN-07/RN-08/Q7),
   leídos directamente de los archivos y de PostgreSQL.
5. `calcular_bolsa` → `liquidar_pais` → `verificar_invariantes` (EG-23).
6. Carga append-only en `liquidaciones` y `reporte_regalias` en una transacción (ADR-0007).

`liquidar` es pura: recibe los eventos y las fuentes ya leídas. Lo que toca archivos o la base
está en `leer_eventos`, `leer_fuentes`, `publicar` y `ejecutar`. Detalle en docs/esqueleto.md.
"""

import json
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, text

from sonoraplay.config import (
    AtribucionOfflineConfig,
    ReglasLiquidacionConfig,
    ReglasValidezConfig,
    SimuladorConfig,
)
from sonoraplay.reglas.atribucion import ResultadoAtribucion, TipoAtribucion, atribuir_reproduccion
from sonoraplay.reglas.liquidacion import (
    CondicionContrato,
    Incidente,
    Pago,
    ReproduccionLiquidable,
    ResultadoLiquidacion,
    calcular_bolsa,
    indexar_condiciones,
    liquidar_pais,
    paises_facturacion,
    suscripcion_neta_por_pais,
    verificar_invariantes,
)
from sonoraplay.reglas.sesiones import ReproduccionF2, deduplicar, reconstruir
from sonoraplay.reglas.validez import MotivoValidez, aplicar_tope_diario
from sonoraplay.reporte_regalias import Componente
from sonoraplay.simulador.f2_minimo import validador

Evento = Mapping[str, Any]

# Mes de SimuladorConfig.fecha_base: el que el simulador mínimo llena de eventos.
PERIODO_POR_DEFECTO = SimuladorConfig.fecha_base.replace(day=1)
# Provisional hasta que exista F5 (EG-30, Sprint 3): ingresos publicitarios del país en el mes.
PUBLICIDAD_USD_POR_DEFECTO = Decimal("20000")

PLANES_PAGOS = {"individual", "familiar", "estudiante"}
_ATRIBUCION = AtribucionOfflineConfig()
_VALIDEZ = ReglasValidezConfig()
_LIQUIDACION = ReglasLiquidacionConfig()


class Descarte:
    """Por qué una reproducción reconstruida no llega a la liquidación. Se cuentan, no se borran."""

    OTRO_MES = "otro_mes"
    DURACION_INSUFICIENTE = str(MotivoValidez.DURACION_INSUFICIENTE)
    TOPE_DIARIO = str(MotivoValidez.TOPE_DIARIO)
    PISTA_SIN_TITULAR = "pista_sin_titular"
    SIN_PAIS_FACTURACION = "sin_pais_facturacion"  # defecto de F3; se depura en Silver (EG-35)
    SIN_PLAN_VIGENTE = "sin_plan_vigente"


# --- Entradas ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Suscripcion:
    """Un período de F3. `hasta` es **exclusivo**: en un cambio de plan el período viejo termina
    el mismo día en que empieza el nuevo, y ese día ya cuenta el nuevo."""

    usuario_id: str
    plan: str  # planes.codigo
    desde: date
    hasta: date | None

    def vigente_en(self, fecha: date) -> bool:
        return self.desde <= fecha and (self.hasta is None or fecha < self.hasta)


@dataclass(frozen=True)
class FuentesLiquidacion:
    """Lo que el esqueleto lee de F1, F3 y F4, ya en tipos de Python."""

    titular_de_pista: Mapping[str, uuid.UUID]  # F1: catalogo_f1.parquet
    pais_de_usuario: Mapping[str, str | None]  # F3: usuarios.pais_facturacion
    titular_de_familia: Mapping[str, str]  # F3: miembro → titular de su grupo familiar
    suscripciones: Mapping[str, Sequence[Suscripcion]]  # F3: por usuario_id
    pagos: Sequence[Pago]  # F3: pagos del período (aprobados y rechazados)
    condiciones: Sequence[CondicionContrato]  # F4


@dataclass(frozen=True)
class ResumenEsqueleto:
    periodo: date
    pais: str
    publicidad_usd: Decimal
    eventos: int
    reproducciones: int
    ajustes: int  # reproducciones offline de meses anteriores liquidadas en este (RN-04)
    liquidables: tuple[ReproduccionLiquidable, ...]  # de todos los países
    descartes: Mapping[str, int]
    pagos_sin_pais: int
    resultado: ResultadoLiquidacion
    pagables_por_pais: Mapping[str, int] = field(default_factory=dict)

    @property
    def incidentes(self) -> tuple[Incidente, ...]:
        return self.resultado.incidentes


# --- Partes puras -----------------------------------------------------------------------------


def componente_de_plan(plan: str) -> Componente:
    """Q8: el plan gratuito va a la bolsa de publicidad; un plan pago, a la de suscripción."""
    if plan == "free":
        return Componente.PUBLICIDAD
    if plan in PLANES_PAGOS:
        return Componente.SUSCRIPCION
    raise ValueError(f"plan desconocido: {plan!r}")


def seleccionar_periodo(
    reps: Iterable[ReproduccionF2], periodo: date, cfg: AtribucionOfflineConfig
) -> list[tuple[ReproduccionF2, ResultadoAtribucion]]:
    """RN-04: las reproducciones cuyo mes de liquidación es `periodo`, con su atribución.

    Incluye los ajustes: offline de meses anteriores sincronizadas tarde (EG-22, ADR-0007).
    """
    if periodo.day != 1:
        raise ValueError("periodo debe ser el primer día del mes")
    seleccion = []
    for rep in reps:
        r = atribuir_reproduccion(rep.inicio, rep.sincronizado, rep.is_offline, cfg)
        if r.mes_liquidacion == periodo:
            seleccion.append((rep, r))
    return seleccion


def plan_vigente(usuario_id: str, fecha: date, fuentes: FuentesLiquidacion) -> str | None:
    """Plan del usuario en `fecha` (UTC). Un miembro de familia no tiene suscripción propia
    (modelo-f3.md): usa la del titular de su grupo. None si no hay ninguna vigente."""
    for duenio in (usuario_id, fuentes.titular_de_familia.get(usuario_id)):
        if duenio is None:
            continue
        for s in fuentes.suscripciones.get(duenio, ()):
            if s.vigente_en(fecha):
                return s.plan
    return None


def elegir_pais(liquidables: Iterable[ReproduccionLiquidable]) -> str:
    """El país de facturación con más reproducciones pagables; un empate lo gana el primero en
    orden alfabético, para que el resultado no dependa del orden de entrada."""
    conteo = Counter(r.pais_facturacion for r in liquidables)
    if not conteo:
        raise ValueError("no hay reproducciones pagables en el período")
    return min(conteo, key=lambda p: (-conteo[p], p))


def _paises_conocidos(fuentes: FuentesLiquidacion) -> dict[str, str]:
    """Q6 / RN-10 sin los usuarios cuyo titular de familia no tiene país (defecto de F3).

    `paises_facturacion` falla con un país nulo, a propósito (ADR-0008): Silver (EG-35) lo
    depura. El esqueleto no tiene Silver, así que deja fuera a esos usuarios y los cuenta.
    """
    con_pais = {
        u: p
        for u, p in fuentes.pais_de_usuario.items()
        if fuentes.pais_de_usuario.get(fuentes.titular_de_familia.get(u, u)) is not None
    }
    return paises_facturacion(con_pais, fuentes.titular_de_familia)


def _pais_de_reproduccion(eventos: Iterable[Evento]) -> dict[str, str]:
    """`country_playback` de cada sesión, tomado de su `start` (RN-08 y Q7)."""
    paises: dict[str, str] = {}
    for e in eventos:
        if e["event_type"] == "start" or e["session_id"] not in paises:
            paises[e["session_id"]] = e["country_playback"]
    return paises


def liquidar(
    eventos: Sequence[Evento],
    fuentes: FuentesLiquidacion,
    periodo: date,
    publicidad_usd: Decimal,
    pais: str | None = None,
    *,
    atribucion: AtribucionOfflineConfig = _ATRIBUCION,
    validez: ReglasValidezConfig = _VALIDEZ,
    liquidacion: ReglasLiquidacionConfig = _LIQUIDACION,
) -> ResumenEsqueleto:
    """Pasos 2 a 7 del esqueleto, sin E/S. `pais` None = el de más reproducciones pagables."""
    if not isinstance(publicidad_usd, Decimal):
        raise TypeError("publicidad_usd debe ser Decimal (no float: se pierden centavos)")
    descartes: Counter[str] = Counter()

    # 2. Reproducciones del período (reloj corregido y RN-04).
    reps = reconstruir(eventos, atribucion)
    del_periodo = seleccionar_periodo(reps, periodo, atribucion)
    descartes[Descarte.OTRO_MES] = len(reps) - len(del_periodo)
    ajustes = sum(r.tipo == TipoAtribucion.AJUSTE for _, r in del_periodo)

    # 3. RN-01 y RN-02: solo pasan las pagables.
    candidatas = [rep for rep, _ in del_periodo]
    pagables = []
    for rep, res in zip(candidatas, aplicar_tope_diario(candidatas, validez), strict=True):
        if res.pagable:
            pagables.append(rep)
        else:
            descartes[str(res.motivo)] += 1

    # 4. F1 y F3: titular, país de facturación y componente de cada reproducción.
    paises = _paises_conocidos(fuentes)
    pais_reproduccion = _pais_de_reproduccion(deduplicar(eventos))
    liquidables: list[ReproduccionLiquidable] = []
    for rep in pagables:
        titular = fuentes.titular_de_pista.get(rep.track_id)
        plan = plan_vigente(rep.cuenta_id, rep.inicio.date(), fuentes)
        if titular is None:
            descartes[Descarte.PISTA_SIN_TITULAR] += 1
        elif rep.cuenta_id not in paises:
            descartes[Descarte.SIN_PAIS_FACTURACION] += 1
        elif plan is None:
            descartes[Descarte.SIN_PLAN_VIGENTE] += 1
        else:
            liquidables.append(
                ReproduccionLiquidable(
                    reproduccion_id=rep.reproduccion_id,
                    usuario_id=rep.cuenta_id,
                    titular_id=titular,
                    track_id=rep.track_id,
                    inicio=rep.inicio,
                    pais_facturacion=paises[rep.cuenta_id],
                    pais_reproduccion=pais_reproduccion.get(rep.reproduccion_id),
                    componente=componente_de_plan(plan),
                )
            )

    # 6. País a liquidar.
    pais = pais or elegir_pais(liquidables)
    del_pais = [r for r in liquidables if r.pais_facturacion == pais]
    if not del_pais:
        raise ValueError(f"no hay reproducciones pagables con país de facturación {pais}")

    # 4-5. Bolsa: pagos aprobados del mes (Q5) + publicidad provisional (sin F5 hasta la EG-30).
    pagos = [p for p in fuentes.pagos if p.usuario_id in paises]
    neta = suscripcion_neta_por_pais(pagos, paises).get(pais, Decimal(0))
    bolsa = calcular_bolsa(pais, neta, publicidad_usd, liquidacion)

    # 7. Liquidación del país (RN-05 a RN-08, RNF-02).
    pistas = {r.track_id for r in del_pais}
    condiciones = indexar_condiciones(c for c in fuentes.condiciones if c.track_id in pistas)
    resultado = liquidar_pais(periodo, bolsa, del_pais, condiciones)
    verificar_invariantes(resultado)

    return ResumenEsqueleto(
        periodo=periodo,
        pais=pais,
        publicidad_usd=publicidad_usd,
        eventos=len(eventos),
        reproducciones=len(reps),
        ajustes=ajustes,
        liquidables=tuple(liquidables),
        descartes={k: v for k, v in descartes.items() if v},
        pagos_sin_pais=len(fuentes.pagos) - len(pagos),
        resultado=resultado,
        pagables_por_pais=dict(Counter(r.pais_facturacion for r in liquidables)),
    )


# --- Lectura y escritura ----------------------------------------------------------------------


def leer_eventos(ruta: Path) -> list[dict]:
    """JSON Lines del simulador. Cada evento se valida contra el esquema F2 (EG-15)."""
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}. Corre antes: python -m sonoraplay.simulador")
    v = validador()
    eventos = []
    with ruta.open(encoding="utf-8") as f:
        for n, linea in enumerate(f, start=1):
            if not linea.strip():
                continue
            evento = json.loads(linea)
            errores = sorted(err.message for err in v.iter_errors(evento))
            if errores:
                raise ValueError(f"{ruta}:{n} no cumple el esquema F2: {'; '.join(errores)}")
            eventos.append(evento)
    return eventos


def _siguiente_mes(periodo: date) -> date:
    return date(periodo.year + (periodo.month == 12), periodo.month % 12 + 1, 1)


def _texto(valor: str | None) -> str | None:
    """char(n) de PostgreSQL → str sin espacios, o None si queda vacío."""
    return (valor or "").strip() or None


def leer_fuentes(
    engine: Engine, directorio_f1: Path, periodo: date, pistas: Iterable[str]
) -> FuentesLiquidacion:
    """F1 del parquet del catálogo; F3 y F4 directamente de PostgreSQL (no por la API HTTP de
    contratos: es el seguimiento de rendimiento de la EG-20). Solo lee las condiciones F4 de
    `pistas`."""
    ruta = directorio_f1 / "catalogo_f1.parquet"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}. Corre antes: python -m sonoraplay.catalogo")
    catalogo = pd.read_parquet(ruta, columns=["track_id", "titular_id"]).drop_duplicates()
    repetidas = catalogo["track_id"][catalogo["track_id"].duplicated()]
    if not repetidas.empty:
        raise ValueError(f"pistas con más de un titular en F1: {sorted(repetidas)[:5]}")
    titular_de_pista = {
        str(t): uuid.UUID(str(titular)) for t, titular in catalogo.itertuples(index=False)
    }

    with engine.connect() as c:
        usuarios = c.execute(text("SELECT usuario_id::text, pais_facturacion FROM usuarios")).all()
        familias = c.execute(
            text(
                "SELECT m.usuario_id::text, g.titular_id::text FROM miembros_familia m "
                "JOIN grupos_familiares g USING (grupo_id) WHERE m.rol = 'miembro'"
            )
        ).all()
        suscripciones = c.execute(
            text(
                "SELECT s.usuario_id::text, p.codigo, s.fecha_inicio, s.fecha_fin "
                "FROM suscripciones s JOIN planes p USING (plan_id)"
            )
        ).all()
        pagos = c.execute(
            text(
                "SELECT s.usuario_id::text, p.monto_usd, p.estado FROM pagos p "
                "JOIN suscripciones s USING (suscripcion_id) "
                "WHERE p.fecha_pago >= :desde AND p.fecha_pago < :hasta"
            ),
            {"desde": periodo, "hasta": _siguiente_mes(periodo)},
        ).all()
        contratos = c.execute(
            text(
                "SELECT c.contrato_id, c.titular_id, c.track_id, c.porcentaje, c.valido_desde, "
                "c.valido_hasta, c.territorio, "
                "coalesce(array_agg(e.pais) FILTER (WHERE e.pais IS NOT NULL), '{}') "
                "FROM contratos c LEFT JOIN exclusiones_territoriales e USING (contrato_id) "
                "WHERE c.track_id = ANY(:pistas) GROUP BY c.contrato_id"
            ),
            {"pistas": sorted(set(pistas))},
        ).all()

    por_usuario: dict[str, list[Suscripcion]] = defaultdict(list)
    for u, plan, desde, hasta in suscripciones:
        por_usuario[u].append(Suscripcion(u, plan, desde, hasta))
    return FuentesLiquidacion(
        titular_de_pista=titular_de_pista,
        pais_de_usuario={u: _texto(p) for u, p in usuarios},
        titular_de_familia=dict(familias),
        suscripciones=dict(por_usuario),
        pagos=tuple(Pago(u, monto, estado) for u, monto, estado in pagos),
        condiciones=tuple(
            CondicionContrato(
                contrato_id=cid,
                titular_id=tid,
                track_id=track,
                porcentaje=pct,
                valido_desde=desde,
                valido_hasta=hasta,
                territorio=_texto(territorio),
                exclusiones=frozenset(p.strip() for p in excl),
            )
            for cid, tid, track, pct, desde, hasta, territorio, excl in contratos
        ),
    )


def publicar(engine: Engine, resultado: ResultadoLiquidacion) -> uuid.UUID:
    """Carga append-only (ADR-0007, contrato de la EG-21) en **una** transacción.

    Inserta la liquidación sin publicar, sus filas y al final pone `publicada_en`. Cada llamada
    crea una liquidación nueva; nunca modifica una anterior. Si algo falla no queda nada.
    """
    if not resultado.filas:
        raise ValueError("una liquidación sin filas no se publica")
    liquidacion_id = uuid.uuid4()
    filas = [
        {
            "liquidacion_id": liquidacion_id,
            "titular_id": f.titular_id,
            "periodo": f.periodo,
            "pais": f.pais,
            "componente": str(f.componente),
            "reproducciones_validas": f.reproducciones_validas,
            "participacion": f.participacion,
            "porcentaje_contractual": f.porcentaje_contractual,
            "regalia_usd": f.regalia_usd,
        }
        for f in resultado.filas
    ]
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO liquidaciones (liquidacion_id, periodo) VALUES (:id, :periodo)"),
            {"id": liquidacion_id, "periodo": resultado.periodo},
        )
        c.execute(
            text(
                "INSERT INTO reporte_regalias (liquidacion_id, titular_id, periodo, pais, "
                "componente, reproducciones_validas, participacion, porcentaje_contractual, "
                "regalia_usd) VALUES (:liquidacion_id, :titular_id, :periodo, :pais, "
                ":componente, :reproducciones_validas, :participacion, "
                ":porcentaje_contractual, :regalia_usd)"
            ),
            filas,
        )
        c.execute(
            text("UPDATE liquidaciones SET publicada_en = now() WHERE liquidacion_id = :id"),
            {"id": liquidacion_id},
        )
    return liquidacion_id


def ejecutar(
    engine: Engine,
    eventos: Path,
    directorio_f1: Path,
    periodo: date = PERIODO_POR_DEFECTO,
    publicidad_usd: Decimal = PUBLICIDAD_USD_POR_DEFECTO,
    pais: str | None = None,
) -> tuple[uuid.UUID, ResumenEsqueleto]:
    """Todo el esqueleto: lee, liquida y publica. Devuelve el ID de la liquidación nueva."""
    evs = leer_eventos(eventos)
    fuentes = leer_fuentes(engine, directorio_f1, periodo, {e["track_id"] for e in evs})
    resumen = liquidar(evs, fuentes, periodo, publicidad_usd, pais)
    return publicar(engine, resumen.resultado), resumen


# --- Resumen en consola -----------------------------------------------------------------------


def formatear_resumen(liquidacion_id: uuid.UUID, r: ResumenEsqueleto) -> str:
    res = r.resultado
    periodo = f"{r.periodo:%Y-%m}"
    totales: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    repros: dict[uuid.UUID, int] = defaultdict(int)
    for f in res.filas:
        totales[f.titular_id] += f.regalia_usd
        repros[f.titular_id] += f.reproducciones_validas
    mayor = min(totales, key=lambda t: (-totales[t], str(t)))
    pagables_pais = sum(f.reproducciones_validas for f in res.filas)

    lineas = [
        "== Esqueleto EG-24 · liquidación publicada",
        f"ID de liquidación: {liquidacion_id}",
        f"Período: {periodo}   País de facturación: {r.pais}",
        f"Eventos F2: {r.eventos}   Reproducciones: {r.reproducciones}   "
        f"Ajustes de meses anteriores: {r.ajustes}",
        "Descartadas: "
        + (", ".join(f"{k}={v}" for k, v in sorted(r.descartes.items())) or "ninguna"),
        "Pagables por país: "
        + ", ".join(f"{p}={n}" for p, n in sorted(r.pagables_por_pais.items())),
        f"Pagables en {r.pais}: {pagables_pais}",
        "",
        "Bolsa (USD):",
        f"  suscripción  {res.bolsa.suscripcion:.2f}  (52 % de los pagos aprobados del mes)",
        f"  publicidad   {res.bolsa.publicidad:.2f}  (45 % de {r.publicidad_usd} USD, "
        "PROVISIONAL sin F5 hasta la EG-30)",
        f"  repartido    {res.total_usd():.2f}",
        "",
        f"Filas por titular ({len(totales)} titulares, {len(res.filas)} filas):",
    ]
    for t in sorted(totales, key=lambda t: (-totales[t], str(t))):
        lineas.append(f"  {t}  {repros[t]:>3} reproducciones  {totales[t]:>10.2f} USD")
    if r.pagos_sin_pais:
        lineas.append(f"Pagos fuera de la bolsa por país de facturación nulo: {r.pagos_sin_pais}")
    lineas.append("")
    lineas.append(f"Incidentes (RN-08, sin tabla todavía): {len(res.incidentes)}")
    for i in res.incidentes:
        lineas.append(
            f"  {i.tipo}  reproducción {i.reproduccion_id}  pista {i.track_id}  "
            f"país {i.pais_reproduccion}  contrato {i.contrato_id}"
        )
    lineas += [
        "",
        f"Titular con mayor regalía: {mayor} ({totales[mayor]:.2f} USD)",
        "Token del sello (local):",
        f"  uv run --env-file .env python -m sonoraplay.api_titulares.tokens --titular {mayor}",
        "Token del sello (Docker):",
        "  docker compose exec api-titulares python -m sonoraplay.api_titulares.tokens "
        f"--titular {mayor}",
        "Consulta:",
        '  curl -H "Authorization: Bearer <token>" '
        f'"http://localhost:8001/me/reportes?periodo={periodo}"',
    ]
    return "\n".join(lineas)
