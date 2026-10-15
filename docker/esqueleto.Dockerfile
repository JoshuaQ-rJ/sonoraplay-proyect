# Esqueleto de punta a punta (EG-24): eventos F2 -> reglas -> liquidación -> reporte_regalias.
# Build desde la raíz del repo: docker build -f docker/esqueleto.Dockerfile .
# Necesita DATABASE_URL (F3 y F4 cargados), el catálogo F1 y los eventos del simulador en
# /datos/procesados (los dejan seed y simulador). Trabajo de una sola ejecución.
FROM python:3.12.15-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Capa 1: solo dependencias, para que un cambio de código no las reinstale.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Capa 2: el paquete sonoraplay. uv_build necesita README y LICENSE.
COPY README.md LICENSE ./
COPY src ./src
# El esqueleto valida cada evento contra el esquema F2 (EG-15), que busca en /app/schemas.
COPY schemas/f2_evento.schema.json ./schemas/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 app
USER app

# Sin HEALTHCHECK: es un trabajo que termina solo; su resultado es el código de salida.
# Período, país y publicidad se cambian con `docker compose run esqueleto ... --pais CO`.
ENTRYPOINT ["python", "-m", "sonoraplay.esqueleto", \
            "--eventos", "/datos/procesados/eventos_f2.jsonl", "--datos-f1", "/datos/procesados"]
