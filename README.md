# Insighta Labs — Intelligence Query Engine API

A FastAPI backend for demographic profile querying with advanced filtering, sorting, pagination, and a rule-based natural language search endpoint.

---

## Stack

- **FastAPI** — async web framework
- **PostgreSQL** — primary database
- **SQLAlchemy (async)** — ORM and query building
- **asyncpg** — async PostgreSQL driver
- **Alembic** — database migrations
- **uuid_utils** — UUID v7 generation

## Natural Language Parsing Approach

The parser (`app/services/nl_parser.py`) is **entirely rule-based** — no AI, no LLMs. It runs a series of regex and keyword checks against the lowercased query string and builds a filter dict that is passed directly to the same query builder used by `GET /api/profiles`.

### How it works

The query is checked independently for four categories of filter. All recognised filters are combined (AND logic).

#### 1. Gender detection

Scans for gender-specific words:

| Words matched                          | Filter applied        |
|----------------------------------------|-----------------------|
| `male`, `males`, `men`, `man`          | `gender=male`         |
| `female`, `females`, `women`, `woman`, `girl`, `girls` | `gender=female` |
| Both male AND female words present     | No gender filter (ambiguous) |

#### 2. Age group detection

Exact keyword matching:

| Words matched                          | Filter applied           |
|----------------------------------------|--------------------------|
| `teenager`, `teenagers`, `teen`, `teens` | `age_group=teenager`   |
| `adult`, `adults`                      | `age_group=adult`        |
| `senior`, `seniors`, `elderly`, `elder`| `age_group=senior`       |
| `child`, `children`, `kid`, `kids`    | `age_group=child`        |

#### 3. Age bound extraction

Uses regex patterns to extract numeric bounds:

| Pattern in query                            | Filter applied                  |
|---------------------------------------------|---------------------------------|
| `young`                                     | `min_age=16`, `max_age=24`      |
| `above N`, `over N`, `older than N`, `at least N` | `min_age=N`             |
| `below N`, `under N`, `younger than N`, `at most N` | `max_age=N`           |
| `between N and M`                           | `min_age=N`, `max_age=M`        |

**Note:** `young` maps to ages 16–24 for parsing purposes only. It is **not** a stored `age_group` value.

If both `young` and an explicit `above N` are in the same query, the explicit `above N` wins for `min_age` (parsed after `young` sets it, overwriting it).

#### 4. Country detection

Maintains a lookup table of ~60 country names → ISO-2 codes covering all of Africa plus common global countries. Multi-word names (e.g. "south africa") are tried before single-word names (longest match wins) to avoid partial matches.

Examples:
```
"nigeria"      → NG
"south africa" → ZA
"kenya"        → KE
"angola"       → AO
"ghana"        → GH
```

#### Unrecognised queries

If parsing produces **zero** filters (no gender, no age group, no age bounds, no country), the endpoint returns:

```json
{ "status": "error", "message": "Unable to interpret query" }
```
### Endpoints

GET `/api/profiles`
GET `/api/profiles/search?q=young%20males%20from%20nigeria`
---

## Parser Limitations

These are known gaps in the current rule-based implementation:

1. **No fuzzy matching** — "Nigria" or "Kennya" (typos) won't be recognised. The query must exactly match a name in the country lookup table.

2. **No ISO code input** — You can't query `from NG`; you must use the full country name (`from nigeria`).

3. **No negation** — Queries like "not from nigeria" or "excluding females" are not handled. The negation word is ignored and the rest may still match a positive filter.

4. **No combined country queries** — "from nigeria or kenya" will only match whichever country appears first in the longest-match pass.

5. **No relative age phrases beyond the defined set** — Phrases like "middle-aged", "in their 30s", "30-something", or "born in 1990" are not handled.

6. **`young` + explicit `above N` conflict** — If a query says "young males above 20", `young` first sets `min_age=16, max_age=24`, then `above 20` overwrites `min_age` to 20. This is consistent but may not match user intent if they meant only young people.

7. **No probability filters in NL search** — Phrases like "high confidence" or "above 90% confidence" are not parsed into `min_gender_probability` or `min_country_probability`. Use `GET /api/profiles` directly for probability filtering.

8. **Order sensitivity for some patterns** — The regex engine processes patterns left-to-right. Unusual word orders ("30 above males") may not be caught by patterns expecting the number after the keyword.

9. **No stemming or lemmatisation** — "Men" and "man" are handled explicitly, but uncommon synonyms (e.g. "gentlemen", "ladies") are not.

10. **Single language only** — English only. French, Yoruba, Hausa, Swahili, etc. are not supported.

---

## Error Responses

All errors follow this structure:

```json
{ "status": "error", "message": "<description>" }
```

| HTTP Code | Meaning                                       |
|-----------|-----------------------------------------------|
| 400       | Missing or empty required parameter           |
| 422       | Invalid parameter type or value               |
| 404       | Profile not found                             |
| 500       | Internal server error                         |

---

## Database Schema

```sql
CREATE TABLE profiles (
    id               VARCHAR(36) PRIMARY KEY,
    name             VARCHAR     NOT NULL UNIQUE,
    gender           VARCHAR     NOT NULL,
    gender_probability FLOAT     NOT NULL,
    age              INTEGER     NOT NULL,
    age_group        VARCHAR     NOT NULL,
    country_id       VARCHAR(2)  NOT NULL,
    country_name     VARCHAR     NOT NULL,
    country_probability FLOAT    NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX idx_profiles_gender           ON profiles(gender);
CREATE INDEX idx_profiles_age_group        ON profiles(age_group);
CREATE INDEX idx_profiles_country_id       ON profiles(country_id);
CREATE INDEX idx_profiles_age              ON profiles(age);
CREATE INDEX idx_profiles_created_at       ON profiles(created_at);
CREATE INDEX idx_profiles_gender_probability ON profiles(gender_probability);
```

All IDs are **UUID v7** (generated in application code via `uuid_utils`).  
All timestamps are stored and returned in **UTC ISO 8601** format.
