"""EG-30: captura HTTP reintentable y CSV F5 reproducible y atómico.

Los datos de F6/F7 se obtienen de las APIs oficiales; no se inventan respuestas.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import tempfile
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen

FRANKFURTER = "https://api.frankfurter.dev/v1"
REST_COUNTRIES = "https://restcountries.com/v3.1/all?fields=cca2,name,region,currencies"
MONEDAS = ("BRL", "CLP", "COP", "EUR", "MXN", "PEN")
PAISES = ("BR", "CL", "CO", "MX", "PE")
CAMPOS_F5 = ("mes", "pais", "moneda", "ingresos_publicidad")


def obtener_json(url: str, intentos: int = 3) -> object:
    """Reintenta errores transitorios; falla sin escribir archivos parciales."""
    for intento in range(intentos):
        try:
            with urlopen(Request(url, headers={"User-Agent": "SonoraPlay-EG30/1.0"}), timeout=20) as resp:
                return json.load(resp)
        except (OSError, ValueError):
            if intento == intentos - 1:
                raise
            time.sleep(min(2**intento, 4))
    raise RuntimeError("Sin respuesta")


def ultimo_dia(mes: str) -> date:
    inicio = date.fromisoformat(mes + "-01")
    siguiente = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    return siguiente - timedelta(days=1)


def validar_paises(datos: object) -> list[dict]:
    if not isinstance(datos, list):
        raise ValueError("F7 debe ser una lista")
    resultado = {}
    for item in datos:
        if not isinstance(item, dict):
            raise ValueError("País inválido")
        codigo = item.get("cca2")
        monedas = item.get("currencies")
        if not isinstance(codigo, str) or len(codigo) != 2 or not isinstance(monedas, dict):
            raise ValueError("País sin código ISO-2 o monedas")
        resultado[codigo] = {
            "pais": codigo,
            "region": item.get("region") or "Unknown",
            "monedas": sorted(monedas),
        }
    if len(resultado) < 200:
        raise ValueError(f"F7 incompleta: {len(resultado)} países")
    return [resultado[k] for k in sorted(resultado)]


def validar_tasas(datos: object, monedas: tuple[str, ...] = MONEDAS) -> dict:
    if not isinstance(datos, dict) or not isinstance(datos.get("rates"), dict):
        raise ValueError("Respuesta F6 inválida")
    tasas = datos["rates"]
    faltantes = sorted(set(monedas) - set(tasas))
    if faltantes:
        raise ValueError(f"F6 sin cobertura para: {', '.join(faltantes)}; documentar fallback ADR")
    for moneda in monedas:
        if Decimal(str(tasas[moneda])) <= 0:
            raise ValueError(f"Tasa inválida: {moneda}")
    return datos


def generar_f5(mes: str, paises: list[dict], semilla: int = 2026) -> list[dict]:
    ultimo_dia(mes)
    por_codigo = {p["pais"]: p for p in paises}
    rng = random.Random(f"sonoraplay:f5:{semilla}:{mes}")
    filas = []
    for codigo in PAISES:
        if codigo not in por_codigo:
            raise ValueError(f"F7 no contiene {codigo}")
        monedas = por_codigo[codigo]["monedas"]
        esperada = {"BR": "BRL", "CL": "CLP", "CO": "COP", "MX": "MXN", "PE": "PEN"}[codigo]
        if esperada not in monedas:
            raise ValueError(f"F7 no confirma moneda {esperada} para {codigo}")
        valor = Decimal(rng.randint(100_000, 900_000)) / Decimal(100)
        filas.append(
            {"mes": mes, "pais": codigo, "moneda": esperada, "ingresos_publicidad": f"{valor:.2f}"}
        )
    return filas


def escribir_atomico(destino: Path, contenido: str) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=destino.parent, delete=False
        ) as fh:
            temporal = Path(fh.name)
            fh.write(contenido)
        os.replace(temporal, destino)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def ejecutar(mes: str, salida: Path, semilla: int = 2026) -> None:
    """Valida todas las fuentes antes de reemplazar cualquier salida."""
    import io

    paises = validar_paises(obtener_json(REST_COUNTRIES))
    fecha = ultimo_dia(mes).isoformat()
    # Frankfurter: base USD, rates indica unidades de moneda por USD.
    tasas = validar_tasas(
        obtener_json(f"{FRANKFURTER}/{fecha}?base=USD&symbols={','.join(MONEDAS)}")
    )
    filas = generar_f5(mes, paises, semilla)
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=CAMPOS_F5, lineterminator="\n")
    escritor.writeheader()
    escritor.writerows(filas)
    # Escribe el manifiesto después de validar; la sustitución de cada archivo es atómica.
    escribir_atomico(salida / f"f5_publicidad_{mes}.csv", buffer.getvalue())
    escribir_atomico(
        salida / f"f6_tasas_{fecha}.json", json.dumps(tasas, ensure_ascii=False, indent=2) + "\n"
    )
    escribir_atomico(
        salida / "f7_paises.json", json.dumps(paises, ensure_ascii=False, indent=2) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="EG-30: descargar F6/F7 y generar F5")
    parser.add_argument("--mes", required=True, help="AAAA-MM")
    parser.add_argument("--salida", type=Path, default=Path("data/generated/eg30"))
    parser.add_argument("--semilla", type=int, default=2026)
    args = parser.parse_args()
    try:
        ejecutar(args.mes, args.salida, args.semilla)
    except (OSError, ValueError) as exc:
        print(f"Error EG-30: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"F5/F6/F7 generados en {args.salida}")


if __name__ == "__main__":
    main()
