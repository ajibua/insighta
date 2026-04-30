from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str | None = None
    RAILWAY_ENVIRONMENT: str | None = None
    PGHOST: str | None = None
    PGPORT: int | None = None
    PGUSER: str | None = None
    PGPASSWORD: str | None = None
    PGDATABASE: str | None = None

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
    FRONTEND_URL: str = "http://localhost:3000"
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

    @model_validator(mode="after")
    def validate_railway_database_host(self) -> "Settings":
        if self.RAILWAY_ENVIRONMENT and any(
            marker in self.DATABASE_URL
            for marker in ("@localhost", "@127.0.0.1", "@[::1]")
        ):
            raise ValueError(
                "DATABASE_URL points to localhost while running on Railway. "
                "Set DATABASE_URL to your Railway Postgres connection URL."
            )
        return self

    class Config:
        env_file = ".env"


settings = Settings()
