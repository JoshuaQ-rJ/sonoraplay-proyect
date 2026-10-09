# API de sellos (EG-21). Pública: en AWS corre en Fargate ARM64 detrás del ALB con HTTPS (ADR-0006).
# Build desde la raíz del repo: docker build -f docker/api-titulares.Dockerfile .
# Necesita API_TITULARES_JWT_SECRET en el entorno (en AWS, desde SSM); sin ella no arranca.
FROM python:3.12-slim

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

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000

# La imagen slim no trae curl: el health check usa Python.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status != 200)"]

CMD ["uvicorn", "sonoraplay.api_titulares.main:app", "--host", "0.0.0.0", "--port", "8000"]
