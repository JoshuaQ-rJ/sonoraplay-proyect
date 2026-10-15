# ADR-0012 · Propuesta de fuentes y fecha de cierre para F6 / Proposed F6 sources and closing-date policy

| Campo / Field | Valor / Value |
|---|---|
| Estado / Status | **Propuesto / Proposed — NO aprobado / NOT approved** |
| Fecha / Date | 2026-10-15 |
| Historia / Story | EG-30 (F5, F6, F7) |
| Responsable / Owner | María Clara (propuesta para revisión del TL) |
| Revisor / Reviewer | Joshua — pendiente / pending |
| Referencias / References | ADR-0002; `TasaCambio`, `convertir_a_usd` en `reglas/liquidacion.py`; F3 |

## Español

### 1. Contexto
F3 usa CO, MX, BR, AR, CL y PE. F6 debe proporcionar ARS, BRL, CLP, COP, MXN y PEN como **unidades de moneda local por 1 USD**. La integración actual usa Frankfurter **v1** con datos del BCE; según la revisión del TL, no cubre ARS, CLP, COP ni PEN. F6 no puede completarse con esa respuesta. La liquidación exige `TasaCambio.fecha` igual al último día calendario del mes (ADR-0002). Algunos proveedores devuelven una observación del último día hábil, distinta del cierre calendario.

### 2. Criterios
- Cobertura verificable de las seis monedas, sin inventar tasas ni reemplazarlas silenciosamente.
- USD como base y valores positivos convertidos desde texto a `Decimal`.
- Trazabilidad: proveedor, fecha de observación real, fecha de cierre, momento de extracción.
- Compatibilidad con `TasaCambio(moneda, fecha, unidades_por_usd)` y el cierre mensual UTC.
- Preferir costo nulo y uso académico permitido; no incluir credenciales en Git.

### 3. Opciones
| Opción | Ventajas | Riesgos y requisitos | Costo anunciado |
|---|---|---|---|
| A. Frankfurter v2, tasas combinadas | 223 divisas, 104 fuentes oficiales, histórico, sin API key; reutiliza proveedor | La v2 tiene esquema distinto a v1; confirmar las seis monedas y fechas mediante respuestas reales; tasas combinadas son mid-market, no necesariamente TRM oficial de cada país | Gratis |
| B. Open Exchange Rates | Lista ARS/BRL/CLP/COP/MXN/PEN, base USD, histórico diario | Requiere registro y clave; contrastar cobertura histórica, licencia y semántica de las tasas | Plan gratis: 1.000 solicitudes/mes |
| C. Bancos centrales por país | Datos oficiales por jurisdicción | Seis adaptadores y calendarios distintos; algunos exigen tokens; integración más costosa | Variable / normalmente gratuito |
| D. Mantener Frankfurter v1/BCE | Sin cambios de implementación | No cubre monedas obligatorias; bloqueante | Gratis |

### 4. Recomendación **pendiente de aprobación**
**Evaluar primero A (Frankfurter v2)** y usar B como alternativa si la prueba de cobertura, fecha o licencia falla. **No se autoriza todavía cambiar el proveedor ni la regla de cierre.** La documentación oficial de v2 describe fuentes múltiples, filtro por `quotes`, fechas históricas y atribución mediante `expand=providers`. Deben verificarse datos reales para un cierre hábil y otro en fin de semana, y la presencia de PEN.

**Política de cierre propuesta (requiere decisión del TL):** seleccionar la última observación válida **no posterior** al último día calendario del mes; conservar `fecha_observacion` original y `fecha_cierre` calendario por separado; asignar `TasaCambio.fecha = fecha_cierre` solo si el equipo aprueba explícitamente esta regla. Rechazar observaciones futuras, monedas faltantes, valores no positivos y ausencia de datos del mes. No sustituir fechas sin trazabilidad.

**Formato propuesto:** una fila por moneda con `moneda`, `fecha` (cierre), `unidades_por_usd` (decimal como texto), `fecha_observacion`, `proveedor` y `extraido_en_utc`. Los tres primeros campos corresponden al contrato de liquidación; los demás son metadatos auditables. Decidir con EG-24/EG-37 el esquema final de persistencia.

### 5. Consecuencias y validación
- F5 debe incluir Argentina y eliminar la divergencia respecto a F3 mediante configuración compartida (cambio de código aún no implementado).
- Pruebas offline de seis monedas, precisión decimal, fecha real vs. cierre, error de cobertura y prohibición de escritura parcial.
- Pruebas de integración reales: un cierre de día hábil y mayo de 2026 (31 domingo), y evidencia de proveedor/fecha para cada moneda.
- Antes de aceptar: aprobación del TL sobre fuente, semántica mid-market/oficial, licencia, calendario y campos de auditoría.

## English

### 1. Context
F3 covers CO, MX, BR, AR, CL and PE. F6 requires ARS, BRL, CLP, COP, MXN and PEN, expressed as **local currency units per USD**. The current Frankfurter **v1** ECB-backed endpoint lacks several required currencies, according to the TL review. Royalty conversion requires `TasaCambio.fecha` to equal the calendar month-end (ADR-0002), while some source observations use the last business day.

### 2. Decision criteria
Verified coverage of all six currencies; no invented or silent fallback values; USD base; positive rates parsed to `Decimal` from text; provenance and actual observation date; UTC month-end compatibility; low cost and appropriate licensing.

### 3. Alternatives
- **A — Frankfurter v2 combined rates:** 223 currencies, 104 official providers, historical data, no key and free access. Must verify live coverage (especially PEN), date semantics, provider provenance and mid-market suitability.
- **B — Open Exchange Rates:** supports the six listed currencies, USD base and daily history; requires a key and account. Free tier advertises 1,000 requests/month.
- **C — Country-specific central banks:** authoritative per jurisdiction but requires multiple adapters, calendars and potentially credentials.
- **D — Frankfurter v1 ECB:** cannot cover the required currencies; rejected as the sole source.

### 4. Proposed recommendation — NOT YET ACCEPTED
**Validate option A first**, keeping B as fallback if live coverage, date or license checks fail. **Do not change the implementation or month-end policy before approval.** Proposed policy: use the latest valid observation on or before calendar month-end, preserve both `observation_date` and `closing_date`, and populate `TasaCambio.fecha` with the closing date only if explicitly approved. Reject future dates, missing currencies, non-positive values and absent monthly observations.

Proposed normalized output: `moneda`, `fecha`, `unidades_por_usd` (decimal string), `fecha_observacion`, `proveedor`, `extraido_en_utc`. Agree on persistence with EG-24/EG-37.

### 5. Acceptance checks
Offline tests for six currencies, decimal precision, observation-vs-closing dates and failure without partial outputs; live checks for a business-day close and May 2026 (Sunday month-end); TL approval of provenance, license and date policy.

## Fuentes / Sources
- Frankfurter v2 documentation: https://frankfurter.dev/
- Frankfurter providers: https://frankfurter.dev/providers/
- Open Exchange Rates supported currencies: https://docs.openexchangerates.org/reference/supported-currencies
- Open Exchange Rates historical API: https://docs.openexchangerates.org/reference/historical-json
- Open Exchange Rates free plan: https://openexchangerates.org/signup/free
- Central Bank of Chile API: https://si3.bcentral.cl/estadisticas/Principal1/Web_Services/index_API_sec1_es.htm
