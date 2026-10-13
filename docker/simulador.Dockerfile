# Simulador F2 mínimo (EG-19) en contenedor (EG-25). Trabajo de una sola ejecución.
# Build desde la raíz del repo: docker build -f docker/simulador.Dockerfile .
# Necesita DATABASE_URL (F3 y F4 cargados) y el catálogo F1 en /datos/procesados (lo deja el seed).
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
# El simulador valida cada evento contra el esquema F2 (EG-15), que busca en /app/schemas.
COPY schemas/f2_evento.schema.json ./schemas/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# El volumen con nombre hereda el dueño de esta carpeta al crearse.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /datos/procesados \
    && chown app /datos/procesados
USER app

# Sin HEALTHCHECK: es un trabajo que termina solo. Su salud es el código de salida, que compose
# exige con depends_on: condition: service_completed_successfully.
CMD ["python", "-m", "sonoraplay.simulador", "--eventos", "100", "--semilla", "42", \
     "--salida", "/datos/procesados/eventos_f2.jsonl", "--datos-f1", "/datos/procesados"]
