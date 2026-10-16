# ADR-0002 — Use UTC to define the business-rule day and month

> **English translation of [ADR-0002 (Spanish)](../0002-zona-horaria-dia-mes.md).** The Spanish ADR remains the decision record. This translation does not alter its status.

| Field | Value |
|---|---|
| Status | Accepted (EG-11 working assumption; subject to revision if the instructor responds differently) |
| Date | 2026-10-02 |
| Originating story | HU 02 · EG-11 |
| Owner | María Clara |
| Reviewed by | María Clara — approved 2026-10-02 |
| References | RN-02, RN-04, RN-05, RN-07, CA-02, CA-04, F2, F6 |

## 1. Context

Several business rules depend on the day or month to which a playback belongs:

- **RN-02:** at most 10 valid plays per track, user, and **day**.
- **RN-04:** offline playback belongs to its actual **month** if synchronized before day 2 at 23:59 **UTC**.
- **RN-05:** the revenue pool is **monthly** and uses the exchange rate for the last day of the month.
- **RN-07:** the applicable contract percentage depends on the playback **date**.

SonoraPlay operates across Latin America, with time zones from UTC−3 to UTC−6. A play at 22:00 in Bogotá on January 31 is already February 1 in UTC. If each rule uses a different time zone, the same play can belong to different months depending on the calculation. The assignment does not specify the governing zone (EG-11 Q4).

## 2. Decision criteria

- **Business:** RN-04 already sets a UTC cutoff; other rules must use a consistent calendar for offline attribution and settlement.
- **Requirement:** RNF-03 (traceability) requires an unambiguous settlement month per play.
- **Requirement:** RNF-01 (settlement in under one hour) favors partitioning the Data Lake by year/month without per-country conversion.
- **Cost:** no additional cost; only code and data are affected.
- **Team:** EG-17 pure functions were already written assuming UTC.

## 3. Options considered

| Option | Advantages | Disadvantages | Approx. USD/month |
|---|---|---|---:|
| A · UTC everywhere | Consistent with RN-04; one calendar; simple partitions; no daylight-saving issues | The user's “day” differs from the local calendar (20:00 in Colombia counts toward the following day) | 0 |
| B · Playback-country time zone | Reflects the listener's local day | Conflicts with RN-04 UTC cutoff; mixes calendars; needs time-zone mappings and daylight-saving handling | 0 |
| C · Billing-country time zone | Aligns with country revenue pools | Same disadvantages as B; a traveling user's day may shift | 0 |

## 4. Decision

**Option A (UTC) was selected**, since RN-04 already defines its cutoff in UTC, it assigns each playback to one day and month (RNF-03), and it simplifies Data Lake partitioning (RNF-01).

Implementation rules:

1. All F2 timestamps are sent and stored in UTC (ISO 8601 ending in `Z`).
2. Corrected device timestamps (RN-04 clock drift) are also in UTC.
3. `day = UTC date` and `month = UTC year-month` for RN-02, RN-04, RN-05, and RN-07.
4. The F6 exchange rate corresponds to the last day of the UTC month.
5. The time zone is configured in `config.py` as `ZONA_HORARIA_REGLAS = "UTC"`, allowing a change if the instructor answers differently.

**Clarification:** the monthly reference date does not mean a quotation must be published on a non-business day; the separate F6 month-end observation policy is tracked in ADR-0021.

## 5. Consequences

- **Positive:** one calendar for all rules, simpler tests, and no daylight-saving mistakes.
- **Trade-off:** for a listener in Colombia (UTC−5), the RN-02 day runs from 19:00 to 18:59 local time. The same cap applies consistently to all users.
- **Risk and mitigation:** if the instructor requires local time, change `config.py`, update EG-17 and EG-22 tests, and mark this ADR as *Superseded*.

## 6. How to verify

- **EG-17:** 11 plays from 23:50 to 23:59 UTC → only 10 valid; six at 23:59 UTC and five at 00:01 UTC on the next day → all 11 valid.
- **EG-22 (CA-04):** playback on the 28th, synchronized on day 2 at 23:59 UTC → original month; at 00:00 UTC on day 3 → next-month adjustment.

## 7. References

- Python datetime: https://docs.python.org/3/library/datetime.html
- PostgreSQL timestamp with time zone: https://www.postgresql.org/docs/16/datatype-datetime.html
- Spark SQL time zone: https://spark.apache.org/docs/latest/configuration.html
- RFC 3339: https://www.rfc-editor.org/rfc/rfc3339
