# ADR-0003 — One row per `track_id` in F1, with a primary genre and a genre bridge table

> Complete English translation of [ADR-0003 in Spanish](../0003-duplicados-f1.md). The Spanish record remains authoritative.

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-02 |
| Originating story | HU 03 · EG-12 |
| Owner | María Clara |
| Reviewed by | Approved in PR #7, merged 2026-10-02 |
| References | F1, RN-03, EG-11 Q9 ([ambiguities](../../analisis/ambiguedades-rn.md)) |

## 1. Context

F1 is a public Spotify tracks CSV with 114,000 rows and 21 columns. Exploration in `notebooks/01_exploracion_f1.ipynb` found that **one row does not represent one track**; it represents a track in a genre.

| Observation | Count |
|---|---:|
| Rows | 114,000 |
| Distinct `track_id` | 89,741 |
| IDs appearing at least twice | 16,641 (occupying 40,900 rows) |
| Excess rows | 24,259 |
| Of those, exact duplicates (same track and genre) | 450 |
| Maximum repetitions of one track | 9 genres |
| Fields varying across rows with the same track ID | Only `popularity`, for 720 tracks (maximum difference: 44 points) |
| Repeated tracks tied at maximum popularity | 15,767 of 16,641 |
| (Name, artist) pairs with multiple distinct track IDs | 4,657 pairs / 13,054 tracks; for example Brenda Lee's *Rockin' Around The Christmas Tree* has 45 track IDs |
| Invalid rows | 1 (row 65900: missing artists, album and track name; zero duration) |

Using the catalog unchanged would multiply F2 join rows and royalties for a single playback. EG-11 Q9 assumed one canonical row per `track_id`; this ADR defines the method.

## 2. Decision criteria

- **Business:** each F2 playback must join exactly one track and one rights holder; otherwise royalties are duplicated.
- **RN-03:** fraud signal 2 counts listeners per artist, so the principal artist must be stable and unambiguous.
- **Requirement:** cleaned catalog is reproducible (seed 42) and every track has exactly one `titular_id` (EG-12 criteria 2, 3, 5).
- **Data:** preserve additional genres for reports and dashboards.
- **Cost:** none; code and data only.

## 3. Options considered

| Option | Advantages | Disadvantages | Approx. USD/month |
|---|---|---|---:|
| A · Keep duplicates as distinct tracks | No work; original CSV preserved | `track_id` ceases to be unique; F2 joins multiply plays by up to 9, duplicating royalties; violates EG-12 criterion 1 | 0 |
| B · One row per `track_id`, primary genre plus `track_generos` bridge | Primary key; one-to-one F2 joins; preserves all genres; deterministic | Must choose one primary genre; 15,767 popularity ties use an arbitrary but reproducible alphabetical tie-break | 0 |
| C · Also merge by (track name, artists) | More compact catalog (8,397 fewer rows than B) | F2 identifies tracks by `track_id`; requires a mapping and may merge remasters, live recordings or singles with different owners or durations | 0 |

## 4. Decision

**Option B was selected** to keep `track_id` unique for F2 joins (one playback → one track → one rights holder) while retaining all genres. **Option C was rejected** because F2 uses track IDs, not names; merging distinct IDs might combine recordings with different rights holders.

Implementation in `src/sonoraplay/catalogo/limpiar_f1.py`:

1. Remove redundant index column `Unnamed: 0`, trim whitespace (eight `"Terra "` values), and normalize types.
2. Drop rows missing `track_id`, `artists`, or `track_name`, or with `duration_ms <= 0`.
3. Keep one row per `track_id`. Choose `genero_principal` from the row with highest `popularity`, breaking ties alphabetically. Other columns come from that same selected row.
4. Store all distinct genres in `track_generos(track_id, genero)`.
5. Never merge distinct `track_id` values, even when track name and artist match.
6. Define `artista_principal` as the text in `artists` before the first semicolon. Assign each principal artist to exactly one rights holder via `asignar_titulares.py`, so all of that artist's tracks share a rights holder.

### Full F1 results

| Step | Rows |
|---|---:|
| Input rows | 114,000 |
| Invalid rows dropped | 1 |
| Rows merged (450 exact duplicates + 23,809 extra genre rows) | 24,259 |
| **Final distinct tracks** | **89,740** |
| Tracks with at least two genres | 16,299 |
| Rows in `track_generos` | 113,549 |
| Principal artists | 17,648 |
| Rights holders | 1,500 (all with at least one artist) |
| Largest rights holder | 2,118 artists and 11,405 tracks (median: 4 artists) |

Rights holders are assigned using Zipf-like weights (1/k): the largest ten hold 35% of tracks. This intentional skew supports Spark skew analysis (topic 15, ADR-0016).

## 5. Consequences

- **Positive:** `track_id` is the catalog and future tracks-table primary key; F2 joins do not multiply rows; repeated runs with seed 42 produce identical output, checked with `assert_frame_equal`.
- **Trade-off:** primary genre is chosen alphabetically for 15,767 popularity ties. This affects genre reporting, not royalties. The 13,054 same-name tracks remain distinct and may look duplicated in reports.
- **Primary-genre bias:** alphabetical tie-breaking systematically favors names such as `alt-rock` over `rock`. **Genre analytics must use the `track_generos` bridge**, not `genero_principal`, particularly the EG-31 dimensional model and EG-44 Power BI dashboards. The primary genre is only a display label.
- **Popularity:** among 720 tracks whose popularity differs between rows, the highest value is retained; lower values are discarded.
- **Risks:** if F2 contains an unknown `track_id` (including one discarded as invalid), flag it in EG-15 validation rather than silently dropping the playback. If the instructor changes Q9, mark this ADR *Superseded*.

## 6. How to verify

`tests/catalogo/test_catalogo_f1.py` uses `data/samples/f1_muestra.csv` (200 rows deliberately covering edge cases):

- Unique `track_id` after cleaning (criterion 1).
- Correct primary genre with and without ties; bridge retains all genres.
- Invalid row dropped; same-name tracks with distinct IDs remain separate.
- Exactly one rights holder per track; all tracks by the same artist share one rights holder; 1,500 distinct nonempty holders (criteria 2 and 5).
- Two runs yield identical DataFrames (criterion 3).

## 7. Sources

- Spotify Tracks Dataset (Kaggle): https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset
- pandas `drop_duplicates`: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.drop_duplicates.html
- Python `uuid.uuid5`: https://docs.python.org/3/library/uuid.html#uuid.uuid5
- Python `random.Random`: https://docs.python.org/3/library/random.html
