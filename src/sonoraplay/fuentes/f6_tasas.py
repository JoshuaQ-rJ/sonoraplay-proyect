"""F6: validación y normalización de cotizaciones USD."""

from datetime import date
from decimal import Decimal

from sonoraplay.fuentes.f5_publicidad import PAIS_MONEDA

FRANKFURTER = "https://api.frankfurter.dev/v2/rates"
MONEDAS = tuple(PAIS_MONEDA.values())


def validar_tasas(
    datos: object, monedas: tuple[str, ...] = MONEDAS, cierre: date | None = None
) -> list[dict]:
    """Normaliza Frankfurter v2; conserva fecha real y fecha de cierre UTC."""
    if not isinstance(datos, list):
        raise ValueError("Respuesta F6 inválida: se esperaba lista v2")
    if cierre is None:
        raise ValueError("F6 requiere fecha de cierre")
    por_moneda: dict[str, dict] = {}
    for item in datos:
        if not isinstance(item, dict) or item.get("base") != "USD":
            raise ValueError("F6 exige tasas con base USD")
        moneda = item.get("quote")
        if moneda not in monedas:
            continue
        try:
            observacion = date.fromisoformat(item["date"])
            valor = Decimal(str(item["rate"]))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError(f"F6 inválida para {moneda}") from exc
        if not valor.is_finite() or valor <= 0:
            raise ValueError(f"Tasa inválida: {moneda}")
        if not date(cierre.year, cierre.month, 1) <= observacion <= cierre:
            raise ValueError(f"Fecha de tasa fuera del mes: {moneda} {observacion}")
        anterior = por_moneda.get(moneda)
        if anterior is None or observacion > date.fromisoformat(anterior["fecha_observacion"]):
            por_moneda[moneda] = {
                "moneda": moneda,
                "fecha": cierre.isoformat(),
                "unidades_por_usd": str(valor),
                "fecha_observacion": observacion.isoformat(),
                "proveedor": "Frankfurter v2 (tasas combinadas)",
            }
    faltantes = sorted(set(monedas) - set(por_moneda))
    if faltantes:
        raise ValueError(f"F6 sin cobertura para: {', '.join(faltantes)}")
    return [por_moneda[moneda] for moneda in monedas]
