# EG-30 · Fuentes F5, F6 y F7 / Data sources F5, F6 and F7

## Español

**Estado:** implementación inicial para revisión; no equivale a despliegue público ni a cumplimiento completo de EG-30.

- **F5:** CSV mensual de ingresos publicitarios simulados por país. Semilla fija y formato decimal con dos posiciones. Países BR, CL, CO, MX y PE; menos de 1.000 filas.
- **F6:** Frankfurter, tasas históricas con USD como moneda base. Se solicitan BRL, CLP, COP, EUR, MXN y PEN para el último día del mes. Si faltan monedas, la ejecución falla: **no se inventan tasas**. Queda pendiente investigar y documentar una fuente alternativa en un ADR.
- **F7:** REST Countries, países ISO-2, región y monedas. Se exige cobertura mínima de 200 países.
- **Reintentos:** tres intentos con espera; si falla una API o la validación, no se escriben salidas nuevas.
- **Idempotencia de archivos:** misma semilla y mes generan el mismo CSV y sobrescriben el mismo destino, sin anexar filas.
- **Pendiente:** carga transaccional e idempotente a PostgreSQL, fallback F6, pruebas contra servicios reales, verificación de cobertura por cada día del mes y repositorios separados según el TL.

Ejecución (con conexión a internet):

```bash
uv run python -m sonoraplay.fuentes.eg30 --mes 2026-09 --salida data/generated/eg30
uv run pytest tests/fuentes/test_eg30.py
```

**No subir datos sin verificar licencias ni secretos.** Los archivos generados son resultados locales, no evidencia de despliegue.

## English

**Status:** initial implementation for review; this is not a public deployment or full EG-30 acceptance.

- **F5:** deterministic monthly simulated advertising-revenue CSV by country, using a fixed seed and two-decimal amounts. Countries BR, CL, CO, MX and PE; fewer than 1,000 rows.
- **F6:** Frankfurter historical rates with USD as base. Request BRL, CLP, COP, EUR, MXN and PEN for the month's last day. Missing currencies cause failure; **no rates are fabricated**. A fallback source and ADR remain pending.
- **F7:** REST Countries ISO-2 country codes, regions and currencies, requiring at least 200 countries.
- **Retries:** three attempts with backoff; API or validation failure does not write new outputs.
- **File idempotency:** the same seed and month produce the same CSV, replacing the output rather than appending rows.
- **Remaining:** transactional and idempotent PostgreSQL loading, F6 fallback, live service checks, daily rate coverage, and source-specific repositories as required by the TL.

Run with internet access:

```bash
uv run python -m sonoraplay.fuentes.eg30 --mes 2026-09 --salida data/generated/eg30
uv run pytest tests/fuentes/test_eg30.py
```

**Do not commit data before checking licensing and secrets.** Generated files are local outputs, not proof of deployment.
