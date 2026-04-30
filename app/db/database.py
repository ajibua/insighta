import ssl as _ssl

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def build_async_database_url() -> tuple[str, bool]:
    """Returns (url, needs_ssl)."""
    url = settings.DATABASE_URL

    # Handle empty DATABASE_URL (dev/healthcheck mode)
    if not url:
        return "sqlite+aiosqlite:///:memory:", False

    # Check if SSL is required and strip the query param (asyncpg doesn't understand sslmode)
    needs_ssl = False
    if "sslmode=require" in url:
        needs_ssl = True
        url = url.replace("?sslmode=require", "").replace("&sslmode=require", "")

    # Ensure asyncpg dialect
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        if "asyncpg" not in url:
            url = url.replace("://", "+asyncpg://", 1)
    return url, needs_ssl


# Build the URL
db_url, requires_ssl = build_async_database_url()

# Engine kwargs — skip pool settings for SQLite
engine_kwargs = {}
if not db_url.startswith("sqlite"):
    engine_kwargs = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

# Handle SSL for Neon / cloud Postgres
if requires_ssl:
    ssl_ctx = _ssl.create_default_context()
    engine_kwargs["connect_args"] = {"ssl": ssl_ctx}

engine = create_async_engine(
    db_url,
    echo=False,
    **engine_kwargs
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
