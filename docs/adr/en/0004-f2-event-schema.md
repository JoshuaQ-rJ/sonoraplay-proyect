# ADR-0004 — F2 JSON event schema with `event_id` deduplication

> Complete English translation of [the Spanish ADR](../0004-esquema-eventos-f2.md). No changes to the original decision.

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-07 |
| Originating story | HU 06 · EG-15 |
| Owner | Andrea |
| Reviewed by | María Clara |
| References | F2, RNF-04, RN-01–RN-04, RN-08, EG-11 Q1/Q4/Q6, ADR-0002, ADR-0005, ADR-0008, ADR-0013 |

## 1. Context

F2 consists of playback events sent by the app (`start`, `pause`, `resume`, `skip`, `end`). They are used for RN-01/RN-02 validity (EG-17), RN-03 streaming-farm signals (EG-18), and RN-04 offline attribution (EG-22). Lost or double-counted events affect money.

RabbitMQ (ADR-0013) delivers messages **at least once**. An app may resend when it does not receive ingestion acknowledgment, and a queue may redeliver when a consumer crashes before acknowledging. RNF-04 requires idempotency. The F2 simulator injects five business defects that the schema must **represent**, leaving detection to downstream processing: missing end, incorrect device clock, unknown track, retry duplicate, and playback country differing from billing country.

The decision must establish the event contract (fields, types, timestamps) and duplicate identification.

## 2. Decision criteria

- **RNF-04:** retries must not create additional plays or listened milliseconds.
- **RN-01 / EG-11 Q1:** reconstruct **continuous segments**; a pause or seek restarts the count.
- **RN-02/RN-04:** UTC day/month (ADR-0002); `device_ts` records listening time and `server_ts` synchronization time.
- **RN-03:** identify account, device, and track (artist resolved through F1) and map to the `Reproduccion` model (ADR-0005).
- **Quality:** five injected business defects must pass schema validation; malformed formats must fail before reaching the Data Lake.
- **Cost:** none; `jsonschema` is already a dependency.
- **Team:** schema evolution must not break future sprint consumers.

## 3. Options considered

### 3.1 Duplicate identification

| Option | Advantages | Disadvantages | Approx. USD/month |
|---|---|---|---:|
| A · **Device-generated UUID `event_id`**, deduplicated in the consumer and Silver | Retry retains the same ID; unique and inexpensive to index via primary key / `ON CONFLICT DO NOTHING` / Spark `dropDuplicates(["event_id"])`; independent of payload | A buggy app generating a new ID per retry escapes this check; seen IDs must be stored | 0 |
| B · Natural-key hash of user, device, session, event type, device timestamp, position | No new field; catches regenerated IDs | Distinct legitimate events may collide (two pause taps in one millisecond); schema changes alter key; hashing is more expensive in Spark | 0 |
| C · Full-event hash | Simple | **Fails:** the ingestion API sets a new `server_ts` on every receipt, so retry hashes differ | 0 |
| D · Trust exactly-once queue delivery | No code | RabbitMQ does not guarantee end-to-end exactly-once; app retries occur independently of queue delivery | 0 |

### 3.2 Timestamp format

| Option | Advantages | Disadvantages |
|---|---|---|
| A · **`format: date-time` plus regex requiring `Z`** | Enforces ADR-0002; regex still checks UTC if `rfc3339-validator` is absent | Rejects valid offset timestamps such as `-05:00`, which the app must normalize |
| B · `format: date-time` only | Standard | Allows any zone; without `rfc3339-validator`, `jsonschema` may silently skip format checking |

### 3.3 Schema evolution

| Option | Advantages | Disadvantages |
|---|---|---|
| A · **`additionalProperties: false` and fixed `schema_version`** | Misspelled or unexpected fields fail ingestion; consumers know the version | Adding a field requires version `1.1`/`2.0` and temporary multi-version consumer support |
| B · Allow extra fields | App can add fields without coordination | Typos pass silently; contract stops describing reality |

## 4. Decision

**Options 3.1-A, 3.2-A, and 3.3-A were selected.**

1. **Deduplicate by `event_id` (RNF-04).** The device generates a UUID per event and retains it across retries. The queue consumer uses `INSERT … ON CONFLICT (event_id) DO NOTHING` or equivalent. Silver deduplicates by `event_id` in the current **and previous** month partitions because offline events can arrive through day 2 of the following month. Keep the earliest `server_ts` for duplicates. Option B remains a **quality check**: events with different IDs but the same natural key are reported as a possible app bug, not automatically deleted.
2. **UTC timestamps ending in `Z`.** `device_ts` is device playback time and `server_ts` is ingestion API receipt time. Both are mandatory in the **already ingested** event schema. The app payload does not contain `server_ts`; the API adds it before publishing to the queue.
3. **Closed, versioned contract.** `additionalProperties: false`, all fields mandatory, `schema_version: "1.0"`, and validation with `FormatChecker`.

Changes from fields originally proposed in the story:

- No **duration** field: listened milliseconds are reconstructed from `position_ms` and timestamps; `position_ms >= 0` handles negative positions.
- No `seek` event type: the app sends `pause` then `resume` at the new position, restarting the continuous segment as EG-11 Q1 requires.
- `device_id` is opaque text, not a UUID, because no master source defines it. `track_id` must match the F1 22-character base62 format, but its **existence** is checked against the catalog downstream (unknown-track defect).
- Billing country is **not** duplicated in events: F3 supplies it through `user_id` (EG-11 Q6, ADR-0008); duplicating it would permit contradictions.

## 5. Consequences

- **Positive:** app and queue retries do not duplicate plays or milliseconds (RNF-04). All five injected defects pass schema validation and are detected by session reconstruction and F1/F3 joins as appropriate. Bad types, time zones, and unexpected fields are rejected before the Data Lake.
- **Trade-offs:** maintain a unique ingestion index and Spark partition deduplication. A buggy regenerated `event_id` may look distinct until natural-key quality checks. New fields require a schema version.
- **Risk — format validator:** `rfc3339-validator` may only be present in dev via Jupyter. The `Z` pattern enforces UTC, and `test_format_checker_valida_de_verdad_uuid_y_date_time` checks actual format validation. If production validation uses this module, add `jsonschema[format-nongpl]` to runtime dependencies; this remains a team decision.
- **Risk — naming mismatch:** F2 `user_id`/`device_id` differ from `Reproduccion` `cuenta_id`/`dispositivo_id`; artist is a name rather than a stable ID. The mapping is documented in `docs/datos/eventos-f2.md`. EG-17 added `track_id` and `ms_continuos_max` to `ReproduccionValidez`; Silver (EG-35) assembles the combined record.

## 6. How to verify

- **EG-15:** `tests/schemas/test_evento_f2.py` checks the schema, one valid sample for each event type, 15 invalid examples, and all five injected business defects. The retry example repeats `event_id` and differs only in `server_ts`.
- **HU 20 / EG-29:** restarting a consumer mid-load and resending events neither loses nor duplicates them; distinct `event_id` counts remain unchanged.
- **Silver / EG-35:** publish monthly counts of duplicate IDs removed alongside metrics for the other four defects.

## 7. Sources

- JSON Schema draft 2020-12: https://json-schema.org/draft/2020-12/json-schema-validation
- Python jsonschema format validation: https://python-jsonschema.readthedocs.io/en/stable/validate/#validating-formats
- RFC 3339: https://www.rfc-editor.org/rfc/rfc3339
- RFC 9562 UUID: https://www.rfc-editor.org/rfc/rfc9562
- RabbitMQ reliability: https://www.rabbitmq.com/docs/reliability
- [ADR-0002](0002-utc-day-month.md), [ADR-0005](../0005-umbrales-granjas.md), [business-rule assumptions](../../analisis/ambiguedades-rn.md).
