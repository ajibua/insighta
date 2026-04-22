from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    RAILWAY_ENVIRONMENT: str | None = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        url = str(value).strip()

        # Railway and other providers often expose postgres:// or postgresql:// URLs.
        # SQLAlchemy async engine needs the asyncpg dialect.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]

        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        return url

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
