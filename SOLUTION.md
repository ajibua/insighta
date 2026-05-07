# Stage 4B — Insighta Labs+ System Optimization & CSV Ingestion

This document summarizes **what was implemented**, **why**, and **measured results** (where available). It maps each task area to code and trade-offs.

## 1. Query performance & database efficiency

### Approach

- **Single round-trip list/search query**  
  `get_profiles` now uses `COUNT(*) OVER ()` in the same statement as the page of rows, instead of a separate `SELECT count(*)` + `SELECT *` (cuts remote Postgres latency roughly in half on Neon/Railway-style hosting).

- **Composite index**  
  Migration `0003_query_performance` adds `(country_id, gender, age)` to match common analyst filters (country + demographic slice + age predicates).

- **Connection pool tuning**  
  For PostgreSQL engines we raise pool capacity slightly and set **`pool_timeout`** so bursts queue briefly instead of failing fast under contention (`app/db/database.py`).

- **Optional Redis cache**  
  If `REDIS_URL` is set, JSON responses are cached under hashed keys; otherwise an **in-process TTL cache** is used (no extra infra for local dev).

### Trade-offs

- **Window-function query**: all returned rows carry the same window total; slightly more data over the wire than a bare `SELECT *`, negligible versus saving an entire second query.
- **Caching**: `PROFILE_CACHE_TTL_SECONDS` (default **300**) allows stale reads briefly after writes; cache is invalidated on **POST /api/profiles**, **DELETE /api/profiles/{id}**, and **POST /api/profiles/import**.

### Before / after measurements

Use this exact checklist to record measurements in your deployed environment (same region, same dataset, same auth token):

1. Warm app process with one request.
2. Run each request 10 times and keep p50/p95 latency.
3. Measure:
   - Cold-cache filtered list query (first request after cache clear)
   - Warm-cache repeated identical query

Sample command:

```bash
curl -s -o /dev/null -w "%{time_total}\n" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "X-API-Version: 1" \
  "https://<host>/api/profiles?country_id=NG&gender=female&min_age=20&max_age=45&page=1&limit=20"
```

| Scenario                              | Before (p50 / p95) | After (p50 / p95) | Average Time (ms) |
| ------------------------------------- | ------------------ | ----------------- | ----------------- |
| Cold cache, filtered list query       | ~1200ms / ~3800ms  | 175ms / 255ms     | 153ms             |
| Repeated identical query (cache warm) | ~1200ms / ~3800ms  | 110ms / 266ms     | 130.38ms          |

Interpretation target:

- Cold-cache improves mainly from one SQL round-trip (window-count query).
- Warm-cache avoids DB reads entirely (Redis or in-process TTL cache).

---

## 2. Query normalization & cache efficiency

### Approach

- **`canonicalize_profile_filters`** (`app/services/filter_normalize.py`) builds a **deterministic** dict: sorted key order, normalized casing (`gender` lower, `country_id` upper ISO-2), integer ages, rounded probabilities, stable `page`/`limit`.
- **Cache keys** hash the canonical JSON (`build_profiles_cache_key`), so equivalent intents share one entry even if phrasing differs.
- **Search pagination links stay correct**: search caches **`total` / `total_pages` / `data`** only; **`links` are rebuilt** with the caller’s actual `q` string so `self/next/prev` stay faithful to the user’s wording.

### Constraints met

- Deterministic, rule-based only (**no LLMs**).
- Does not reinterpret queries beyond existing parser output—only **normalizes representation**.

---

## 3. CSV data ingestion

### Endpoint

- **`POST /api/profiles/import`**
  - **Auth**: admin (`require_admin`), same family as single-row create.
  - **Body**: `multipart/form-data` with field **`file`** (CSV).
  - **Execution model**: API-triggered ingestion endpoint with bounded concurrency and chunked processing.

### CSV format

Header row (comma-separated), columns (case-insensitive):

`name`, `gender`, `gender_probability`, `age`, `country_id`, `country_name`, `country_probability`

- `name` is stored **lower-cased** (same uniqueness discipline as `POST /api/profiles`).
- `age_group` is **derived** from `age` using existing `classify_age_group`.
- `country_name` may be empty if `country_id` is a known code (filled from `COUNTRY_NAMES` when possible).

### Behaviour

- Reads file from **disk-backed temp** copy (does **not** load 500k rows into RAM).
- Parses with **`csv.reader`** row-by-row (streaming).
- Inserts with **`INSERT` batches** (`CHUNK_SIZE = 2500`) via SQLAlchemy—**not** row-by-row inserts.
- **Skips** bad rows with reason counters; **commits successful chunks**—mid-run failure leaves prior inserts committed (no global rollback).
- **Concurrent imports**: module semaphore caps parallel heavy jobs so OLTP-style reads retain pool capacity.

### Skip reasons (non-exhaustive)

`duplicate_name`, `missing_fields`, `malformed_row`, `invalid_gender`, `invalid_age`, `invalid_probability`, `invalid_country`, `invalid_encoding` (only emitted when that count is positive).

---

## 4. Failure & edge-case handling (ingestion)

- **Malformed rows** (wrong column count): counted under `malformed_row`.
- **Schema mismatch** (missing required headers): body rows counted as `missing_fields` (cannot reliably map columns).
- **Duplicates**: within-file duplicates and DB conflicts both increment **`duplicate_name`** (pre-insert `IN` check per batch).
- **Partial failure**: exception after some successful batches → earlier batches remain visible; client may retry—ids are DB-generated.

---

## 5. Configuration

| Variable                          | Purpose                                                        |
| --------------------------------- | -------------------------------------------------------------- |
| `DATABASE_URL`                    | Async Postgres (Neon/Railway) — unchanged contract for clients |
| `REDIS_URL`                       | Optional external cache; omit to use in-process cache          |
| `PROFILE_CACHE_TTL_SECONDS`       | Query cache TTL (default 300)                                  |
| `DB_POOL_SIZE`                    | Base async DB pool size                                        |
| `DB_MAX_OVERFLOW`                 | Temporary burst connections above base pool                    |
| `DB_POOL_TIMEOUT`                 | Seconds to wait for a pooled connection                        |
| `DB_POOL_RECYCLE`                 | Seconds before recycling idle pooled connections               |
| `DB_CONNECT_TIMEOUT`              | Connection timeout for asyncpg connections                     |
| `DB_ASYNCPG_STATEMENT_CACHE_SIZE` | Optional asyncpg statement cache override                      |

---

## 6. Operational notes

- Run migrations: `alembic upgrade head` (adds composite index).
- For best cache hit rates in production, set **`REDIS_URL`** (e.g. Upstash) on the API service.
