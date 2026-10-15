"""Emite un token de sello para desarrollo y pruebas manuales (ADR-0006).

Uso: `uv run --env-file .env python -m sonoraplay.api_titulares.tokens --titular <uuid> --horas 8`

Solo imprime el token en la salida estándar: no lo guarda en ningún archivo.
"""

import argparse
import uuid
from datetime import timedelta

from sonoraplay.api_titulares.auth import SecretoInvalido, cargar_secreto, emitir_token

HORAS_MAXIMAS = 24 * 90


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--titular", type=uuid.UUID, required=True, help="UUID del titular.")
    parser.add_argument("--horas", type=int, default=8, help="Vigencia en horas (por defecto 8).")
    args = parser.parse_args(argv)
    if not 1 <= args.horas <= HORAS_MAXIMAS:
        parser.error(f"--horas debe estar entre 1 y {HORAS_MAXIMAS}")
    try:
        secreto = cargar_secreto()
    except SecretoInvalido as e:
        raise SystemExit(str(e)) from None
    print(emitir_token(args.titular, secreto, timedelta(hours=args.horas)))


if __name__ == "__main__":
    main()
