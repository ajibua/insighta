# Insighta Labs+ — Intelligence Query Engine API

A FastAPI backend for demographic profile querying with advanced filtering, sorting, pagination, natural language search, GitHub OAuth authentication, and role-based access control.

---

## Stack

- **FastAPI** — async web framework
- **PostgreSQL** — primary database
- **SQLAlchemy (async)** — ORM and query building
- **asyncpg** — async PostgreSQL driver
- **Alembic** — database migrations
- **python-jose** — JWT token creation/validation
- **httpx** — async HTTP client for GitHub OAuth
- **slowapi** — rate limiting
- **uuid_utils** — UUID v7 generation

---

## Architecture

```
app/
├── main.py                    # FastAPI entry point, middleware stack
├── core/
│   ├── config.py              # Pydantic settings (env vars)
│   ├── security.py            # JWT creation/decode, token hashing
│   ├── dependencies.py        # Auth & RBAC dependency injection
│   └── rate_limit.py          # SlowAPI limiter instance
├── api/routes/
│   ├── auth.py                # OAuth endpoints (CLI + Web flows)
│   └── profiles.py            # Profile CRUD, search, export
├── models/
│   ├── profile.py             # Profile SQLAlchemy model
│   ├── user.py                # User model (GitHub identity, role)
│   ├── refresh_token.py       # Hashed refresh tokens
│   ├── oauth_state.py         # Pending OAuth states (PKCE)
│   └── oauth_token.py         # Temporary CLI polling tokens
├── schemas/
│   └── profile.py             # Pydantic response schemas
├── services/
│   ├── profile_service.py     # Query builder with filters
│   ├── nl_parser.py           # Rule-based NL search
│   ├── auth_service.py        # User upsert, token rotation
│   └── github_oauth.py        # PKCE, GitHub API client
├── middleware/
│   └── logging.py             # Request logging middleware
└── db/
    └── database.py            # Async engine + session factory
```

---

## Authentication

### GitHub OAuth + PKCE

Two flows are supported:

#### CLI Flow
1. CLI generates PKCE values (S256) and opens browser to `GET /auth/github?code_challenge=...&state=...&code_verifier=...`
2. Backend stores state + verifier in DB, redirects to GitHub
3. GitHub redirects back to `GET /auth/github/callback?code=...&state=...`
4. Backend exchanges code + verifier for GitHub token, creates/updates user
5. Backend stores JWT tokens in DB keyed by `state`
6. CLI polls `GET /auth/cli/token?state=...` until tokens are returned

#### Web Flow
1. Browser navigates to `GET /auth/github/web`
2. Backend generates PKCE pair server-side, stores in DB, redirects to GitHub
3. After callback, backend sets HTTP-only cookies with tokens and redirects to frontend

### Token Management

| Token | Expiry | Storage |
|---|---|---|
| Access (JWT) | 15 minutes | Bearer header (CLI) / HTTP-only cookie (Web) |
| Refresh | 7 days | Request body (CLI) / HTTP-only cookie (Web) |

- Refresh tokens are **SHA-256 hashed** before storage
- Token **rotation** on every refresh (old token revoked, new pair issued)

---

## Role-Based Access Control

| Role | Permissions |
|---|---|
| `admin` | Full access: read, create, export profiles |
| `analyst` | Read-only: list, search, export profiles |

Roles are enforced via FastAPI dependency injection on every endpoint.

---

## API Endpoints

### Auth (`/auth/`)

| Method | Path | Description | Rate Limit |
|---|---|---|---|
| `GET` | `/auth/github` | Start CLI OAuth flow | 10/min |
| `GET` | `/auth/github/web` | Start web OAuth flow | 10/min |
| `GET` | `/auth/github/callback` | GitHub OAuth callback | 10/min |
| `GET` | `/auth/cli/token` | CLI polls for tokens | 10/min |
| `POST` | `/auth/refresh` | Rotate tokens | 10/min |
| `POST` | `/auth/logout` | Revoke + clear cookies | 10/min |
| `GET` | `/auth/me` | Current user info | 30/min |

### Profiles (`/api/profiles`)

**All profile endpoints require:**
- Authentication (Bearer token or cookie)
- `X-API-Version: 1` header

| Method | Path | Description | Role |
|---|---|---|---|
| `GET` | `/api/profiles` | List with filters, pagination | analyst+ |
| `GET` | `/api/profiles/search?q=...` | Natural language search | analyst+ |
| `GET` | `/api/profiles/export?format=csv` | Export as CSV | analyst+ |
| `POST` | `/api/profiles` | Create via external APIs | admin |

### Pagination Shape

```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 150,
  "total_pages": 15,
  "links": {
    "self": "/api/profiles?page=1&limit=10",
    "next": "/api/profiles?page=2&limit=10",
    "prev": null
  },
  "data": [...]
}
```

---

## Security

### CSRF Protection
- **Double-submit cookie pattern** for web portal
- Non-HTTP-only `csrf_token` cookie sent alongside HTTP-only auth cookies
- Web portal reads the cookie and sends it as `X-CSRF-Token` header
- Middleware only enforces CSRF for cookie-based auth (not Bearer)
- Safe methods (GET, HEAD, OPTIONS) are exempt

### Rate Limiting
- Auth endpoints: **10 requests/minute** per IP
- Profile endpoints: **60 requests/minute** per IP
- Returns `429 Too Many Requests` when exceeded

### Request Logging
- Every request is logged with: method, path, status code, duration (ms)

---

## Natural Language Parsing Approach

The parser (`app/services/nl_parser.py`) is **entirely rule-based** — no AI, no LLMs. It runs a series of regex and keyword checks against the lowercased query string and builds a filter dict that is passed directly to the same query builder used by `GET /api/profiles`.

### How it works

The query is checked independently for four categories of filter. All recognised filters are combined (AND logic).

#### 1. Gender detection

| Words matched | Filter applied |
|---|---|
| `male`, `males`, `men`, `man` | `gender=male` |
| `female`, `females`, `women`, `woman`, `girl`, `girls` | `gender=female` |
| Both male AND female words present | No gender filter (ambiguous) |

#### 2. Age group detection

| Words matched | Filter applied |
|---|---|
| `teenager`, `teenagers`, `teen`, `teens` | `age_group=teenager` |
| `adult`, `adults` | `age_group=adult` |
| `senior`, `seniors`, `elderly`, `elder` | `age_group=senior` |
| `child`, `children`, `kid`, `kids` | `age_group=child` |

#### 3. Age bound extraction

| Pattern in query | Filter applied |
|---|---|
| `young` | `min_age=16`, `max_age=24` |
| `above N`, `over N`, `older than N`, `at least N` | `min_age=N` |
| `below N`, `under N`, `younger than N`, `at most N` | `max_age=N` |
| `between N and M` | `min_age=N`, `max_age=M` |

#### 4. Country detection

~60 country names → ISO-2 codes covering all of Africa plus common global countries.

---

## Error Responses

All errors follow this structure:

```json
{ "status": "error", "message": "<description>" }
```

| HTTP Code | Meaning |
|---|---|
| 400 | Missing or empty required parameter |
| 401 | Not authenticated / invalid token |
| 403 | Insufficient permissions (RBAC) / CSRF failure |
| 404 | Profile not found |
| 422 | Invalid parameter type or value |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## Environment Variables

```env
DATABASE_URL=postgresql://...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_REDIRECT_URI=https://your-backend.up.railway.app/auth/github/callback
JWT_SECRET=...
FRONTEND_URL=https://your-portal.vercel.app
COOKIE_SECURE=true
COOKIE_SAMESITE=none
```

---

## Database Schema

```sql
-- Stage 2 table (preserved)
CREATE TABLE profiles (...);

-- Stage 3 tables
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    github_id VARCHAR NOT NULL UNIQUE,
    username VARCHAR NOT NULL,
    email VARCHAR,
    avatar_url VARCHAR,
    role VARCHAR NOT NULL DEFAULT 'analyst',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE refresh_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR NOT NULL UNIQUE,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE oauth_states (
    state VARCHAR PRIMARY KEY,
    code_verifier VARCHAR NOT NULL,
    cli_callback VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE oauth_tokens (
    state VARCHAR PRIMARY KEY,
    access_token VARCHAR NOT NULL,
    refresh_token VARCHAR NOT NULL,
    username VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

All IDs are **UUID v7** (generated in application code via `uuid_utils`).
All timestamps are stored and returned in **UTC ISO 8601** format.
