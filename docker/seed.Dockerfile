# Seed (EG-25): catálogo F1, seed F3 y seed F4, en ese orden. Trabajo de una sola ejecución.
# Build desde la raíz del repo: docker build -f docker/seed.Dockerfile .
# Necesita DATABASE_URL y el CSV de F1 montado (F1_ENTRADA); escribe en /datos/procesados.
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
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY --chmod=755 docker/seed.sh /usr/local/bin/seed.sh

# El volumen con nombre hereda el dueño de esta carpeta al crearse: así el usuario sin
# privilegios puede escribir los parquet del catálogo.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /datos/procesados \
    && chown app /datos/procesados
USER app

# Sin HEALTHCHECK: es un trabajo que termina solo. Su salud es el código de salida, que compose
# exige con depends_on: condition: service_completed_successfully.
CMD ["seed.sh"]
