# ADR-0008 — Billing country determines the pool; two components use separate denominators

> English translation of [Spanish ADR-0008](../0008-pais-bolsa-dos-componentes.md). Accepted 2026-10-13 for HU 14 / EG-23; owners Andrea Zárate and María Clara Manjarrés; reviewed by Joshua. The Q8 assumption still requires instructor confirmation.

## 1. Context

RN-05 defines a **country revenue pool** consisting of 52% of net subscriptions and 45% of advertising revenue. RN-06 allocates it among rights holders based on valid-play share multiplied by contract percentage. Two ambiguities directly affect payments: whether a play belongs to the F3 **billing country** or F2 **playback country**, especially for travelers and family plans (RN-10, Q6); and whether free-plan plays belong in the paid-subscription denominator (Q8).

Implementation is in `src/sonoraplay/reglas/liquidacion.py`. `ReglasLiquidacionConfig` sets `fraccion_suscripcion=0.52` and `fraccion_publicidad=0.45` as Decimal values. The EG-21 reporting contract already includes `pais` and `componente`.

## 2. Decision criteria

- RN-05: 52% of approved net subscription payments plus 45% of advertising; Q5 defines net subscriptions as approved `pagos.monto_usd`.
- RN-06 and Q7: pool × share × contract percentage; territory-specific contract terms only when explicitly defined.
- RN-10 and Q6: one family payment, one family billing country.
- RN-08: retain playback country to enforce territorial exclusions.
- RNF-02: royalties must not exceed each country pool beyond USD 0.01.
- RF-05: report by country and component. Pure functions introduce no new infrastructure cost and can be changed in one module if the instructor revises Q6 or Q8.

## 3. Options considered

### 3.1 Country of the pool

| Option | Advantages | Disadvantages | Approx. USD/month |
|---|---|---|---:|
| A · **Billing country** | Revenue and playback denominator align; family payment stays in one country; stable despite travel/VPN | A Colombian account playing in Mexico is paid from Colombia's pool; playback-country analytics and royalties differ | 0 |
| B · Playback country | Reflects where music was heard | Traveling users dilute pools in countries that received no subscription payment; family payments would require an invented cross-country split; playback country can be null | 0 |

### 3.2 Pool structure

| Option | Advantages | Disadvantages | Approx. USD/month |
|---|---|---|---:|
| A · Single pool | Literal reading of RN-05/RN-06; one share per holder/country | Subscription money is distributed using free plays and advertising using paid plays | 0 |
| B · **Two components, separate denominators** | Each revenue stream is allocated among plays that generated it; coincides with A when the holder's share is equal in both streams | Departs from the literal formula; instructor confirmation needed; two report rows per holder/country | 0 |

**Colombia example, September 2026:** USD 100,000 net subscriptions → USD 52,000 subscription pool; USD 20,000 advertising → USD 9,000 advertising pool; total USD 61,000. A holder with 5% of paid plays, 10% of free plays, and an 80% contract receives **USD 2,800** under B (52,000 × 5% × 80% + 9,000 × 10% × 80% = 2,080 + 720). At 5% share in both components the result is **USD 2,440**. Under A with 100 paid and 100 free plays and 15 of 200 total plays, the result is **USD 3,660** (61,000 × 7.5% × 80%). The divergence is precisely why Q8 matters.

## 4. Decision

**Options 3.1-A and 3.2-B were selected.**

**Billing country:** `paises_facturacion` assigns each user to a pool. Family members inherit the family holder's billing country even when they live elsewhere. A null billing country is an F3 defect: Silver should clean it and the function raises `ValueError` rather than inventing one. `suscripcion_neta_por_pais` counts each approved payment once; a family holder pays once for all members. `liquidar_pais` includes only plays whose billing country matches the pool. Playback country remains available for RN-08 exclusions and Q7 territorial terms. Contract precedence is **exclusion > territorial term > general term**, consistent with `api_contratos.services.elegir_condicion`.

**Two components:** `calcular_bolsa` computes 52% of net subscriptions and 45% of advertising. `convertir_a_usd` converts advertising at the month-end exchange rate without premature rounding. Subscription uses valid plays from individual, family, and student plans; advertising uses valid free-plan plays. Holder royalty equals (subscription component × paid-play share + advertising component × free-play share) × contractual percentage. Reporting creates rows by holder, component, and percentage, with rounding governed by ADR-0007.

**Instructor validation pending:** Q8 differs from the literal single-pool reading of RN-05/RN-06 and has substantial monetary impact. If the instructor requires a single pool, `liquidar_pais` must use one denominator across both play types, and this ADR must be superseded. Pool calculation, billing-country choice, and rounding need not change.

## 5. Consequences

- **Positive:** revenue and plays align by billing country; family payments are not duplicated; each income stream is allocated to its generating audience; existing EG-21 DDL already supports country and component.
- **Trade-offs:** billing-country royalty reports differ from playback-country analytics; foreign-resident family members use the holder's billing country; a territorially excluded play stays in the billing-country denominator but pays zero, leaving its share undistributed (ADR-0007); a component with no eligible plays is not distributed.
- **Risks:** instructor revises Q8 → update `liquidar_pais` and the Colombia tests; missing F3 billing country → fail and clean in Silver; Spark applies another country rule → EG-37 must reuse `paises_facturacion` and `liquidar_pais`.

## 6. Verification

`tests/reglas/test_liquidacion.py` includes `test_bolsa_colombia_dos_componentes` (52,000 + 9,000), `test_criterio_1_colombia_2800`, `test_cruce_bolsa_unica_2440`, and `test_denominadores_separados` (990 free plays do not affect subscription royalties). Family tests verify country inheritance, rejection of unapproved payments, one USD 30 family payment producing USD 15.60 subscription component, and six plays allocated to Colombia even if heard in Mexico. Tests reject missing billing countries and nonmatching pool countries. Currency tests cover month-end date, no early rounding, wrong date/currency, and leap years. `test_paridad_con_elegir_condicion` covers 20 country/date combinations. EG-24 manually recalculates royalties from 100 simulated events against PostgreSQL with a USD 0.01 tolerance. After the instructor answers Q8, update the ambiguity log and this ADR if necessary.

## 7. References

- Project rules RN-05, RN-06, RN-08, RN-10, RNF-02.
- [Business assumptions](../../analisis/ambiguedades-rn.md) Q5–Q8.
- [Rights-holder API](../../servicios/api-titulares.md) and `db/ddl/003_reportes_regalias.sql`.
- [ADR-0002](0002-utc-day-month.md); [ADR-0007](../0007-cierre-mes-ajustes-reliquidacion.md).
- ISO country codes: https://www.iso.org/iso-3166-country-codes.html
- Python decimal: https://docs.python.org/3/library/decimal.html
