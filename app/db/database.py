import ssl as _ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_pre_ping": True,
        "pool_recycle": settings.DB_POOL_RECYCLE,
    }
    connect_args = {"timeout": settings.DB_CONNECT_TIMEOUT}
    if settings.DB_ASYNCPG_STATEMENT_CACHE_SIZE is not None:
        connect_args["statement_cache_size"] = settings.DB_ASYNCPG_STATEMENT_CACHE_SIZE
    engine_kwargs["connect_args"] = connect_args

# Handle SSL for Neon / cloud Postgres
if requires_ssl:
    ssl_ctx = _ssl.create_default_context()
    connect_args = engine_kwargs.setdefault("connect_args", {})
    connect_args["ssl"] = ssl_ctx

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
