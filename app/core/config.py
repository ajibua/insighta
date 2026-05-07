from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str | None = None

    # SQLAlchemy async engine pool (postgresql+asyncpg). Tune per Neon/Railway connection limits.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 15
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 300
    # asyncpg TLS handshake / connect timeout (seconds)
    DB_CONNECT_TIMEOUT: int = 10
    # Use 0 behind pgBouncer transaction pooling if you see prepared-statement errors; leave unset otherwise
    DB_ASYNCPG_STATEMENT_CACHE_SIZE: int | None = None

    # Optional: Redis for query caching (falls back to in-process TTL cache if unset)
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""
    PROFILE_CACHE_TTL_SECONDS: int = 300

    # ── GitHub OAuth ─────────────────────────────────────────────────────
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = ""

    # ── JWT ───────────────────────────────────────────────────────────────
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # ── Frontend / Cookies ───────────────────────────────────────────────
    FRONTEND_URL: str = "http://127.0.0.1:3000"
    CLI_REDIRECT_URI: str = "http://localhost:9876/callback"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "none"

    @model_validator(mode="before")
    @classmethod
    def build_database_url_from_pg_vars(cls, data: dict) -> dict:
        if data.get("DATABASE_URL"):
            return data

        required_vars = ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"]
        missing = [name for name in required_vars if not data.get(name)]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(
                "DATABASE_URL is not set. Provide DATABASE_URL or all of: "
                f"{missing_list}."
            )

        user = quote_plus(str(data["PGUSER"]))
        password = quote_plus(str(data["PGPASSWORD"]))
        host = str(data["PGHOST"]).strip()
        port = str(data["PGPORT"]).strip()
        database = str(data["PGDATABASE"]).strip()

        data["DATABASE_URL"] = (
            f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
        )
        return data

    @model_validator(mode="after")
    def normalize_database_url(self) -> "Settings":
        url = str(self.DATABASE_URL).strip()

        # Railway and other providers often expose postgres:// or postgresql:// URLs.
        # SQLAlchemy async engine needs the asyncpg dialect.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]

        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        self.DATABASE_URL = url
        return self

    class Config:
        env_file = ".env"


settings = Settings()
