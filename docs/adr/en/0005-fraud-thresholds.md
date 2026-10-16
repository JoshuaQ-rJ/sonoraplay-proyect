# ADR-0005 — Streaming-farm thresholds and full-month exclusion

> English translation of [ADR-0005 in Spanish](../0005-umbrales-granjas.md). Accepted on 2026-10-02 for HU 09 / EG-18; PR #8 merged on 2026-10-05. Owner: María Clara. References: RN-03, CA-03, CA-10, EG-11 Q2–Q4, ADR-0002, ADR-0007.

## 1. Context

RN-03 flags a listening account if **any** of three conditions holds: over 20 listening hours in 24 hours; over 70% of its plays target one artist with fewer than 1,000 listeners; or the account uses a device shared by more than five accounts. Plays from a flagged account are excluded from the revenue pool and held for review. The assignment leaves the 24-hour window, artist-listener counting period, and exclusion duration ambiguous. These decisions affect payments and false positives. CA-10 requires at least 95% detection with less than 2% false positives. Pure functions live in `src/sonoraplay/reglas/fraude.py`; settings are in `ReglasFraudeConfig`.

## 2. Decision criteria

Business rules require strict thresholds and full-month review of suspicious accounts. EG-11 Q2 assumes monthly unique artist listeners; Q3 assumes exclusion of the entire settlement month; Q4 and ADR-0002 use UTC. EG-43 must measure CA-10 and report which signals triggered. The logic adds no separate infrastructure cost and must be configurable without code changes.

## 3. Options considered

**3.1 Measuring 20 hours in 24 hours:** A rolling 24-hour window detects listening split across two calendar days, at a somewhat higher calculation cost (two pointers over sorted plays). A UTC calendar day is simpler but lets farms avoid detection by crossing midnight. A playback crossing a window boundary contributes only the overlapping part.

**3.2 Shared device:** Marking **more than five accounts** follows RN-03 but can flag a six-member family sharing one device. A threshold of more than six protects that family but contradicts RN-03. Exempting members of the same F3 family avoids that false positive but creates an F3 dependency and a possible evasion technique.

**3.3 Exclusion period:** Excluding the **entire settlement month** prevents fraudulent payment and aligns with monthly signals, but delays legitimate payments after a false positive. Excluding only the signal day is less punitive but fails for a monthly signal and lets other fraudulent plays be paid.

## 4. Decision

Options **3.1-A, 3.2-A, and 3.3-A** were selected.

| `ReglasFraudeConfig` setting | Value | Flag condition |
|---|---:|---|
| `horas_max_24h` | 20 | Listening time **>20 hours** in any rolling 24-hour window |
| `porcentaje_max_artista` | 0.70 | Share of monthly plays to top artist **>70%** |
| `oyentes_min_artista` | 1,000 | That artist has **<1,000** unique listeners in the UTC month |
| `cuentas_max_dispositivo` | 5 | Any device used by the account has **>5** accounts in the month |
| `periodo_exclusion` | `"mes"` | All plays in the flagged account's month become `en_revision` |

Exactly 20 hours, 70%, 1,000 listeners, or five accounts **do not trigger** their respective strict comparisons. Artist share counts **plays**, not listening milliseconds. `marcar_exclusion` retains records and returns `en_revision` or `valida_para_fraude`; it never deletes them. When manual review clears an account, its plays are released and paid as an adjustment in a later append-only settlement under ADR-0007.

## 5. Consequences

Pure functions have boundary tests, expose triggered `senales`, and allow recalibration in `config.py`. A six-member family on one device and a legitimate listener exceeding 20 hours can be flagged. Signals are evaluated by UTC month, so rolling windows crossing a month boundary are split across monthly evaluations. If false positives exceed 2%, EG-43 recalibrates thresholds and this ADR must be superseded. Farms staying just below thresholds are outside RN-03's stated detection rules; EG-43 should report near-threshold accounts. EG-35 Silver reconciles the F2 event schema with the fraud-playback record.

## 6. Verification

`tests/reglas/test_fraude.py` covers positive, legitimate, and exact-boundary cases for each signal; cross-day rolling windows; boundary-overlapping plays; multiple signals; month-wide exclusion; and rejection of naive datetimes. The source reports 100% coverage of `sonoraplay.reglas`. For CA-10, EG-43 uses labeled F2 simulator accounts and a confusion matrix: detection = TP/(TP+FN) **>=95%**, false-positive rate = FP/(FP+TN) **<2%**. Recalibrate and rerun if targets are missed; report performance by signal.

## 7. References

- Project requirements RN-03, CA-03, CA-10.
- [EG-11 assumptions](../../analisis/ambiguedades-rn.md), Q2–Q4.
- [ADR-0002](0002-utc-day-month.md) — UTC calendar.
- Python datetime: https://docs.python.org/3/library/datetime.html
- Confusion matrix: https://en.wikipedia.org/wiki/Confusion_matrix
