import asyncio
import os
import ssl as _ssl
from logging.config import fileConfig
from urllib.parse import quote_plus

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from dotenv import load_dotenv

load_dotenv()

from app.db.database import Base
from app.models.profile import Profile  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.oauth_state import OAuthState  # noqa: F401
from app.models.oauth_token import OAuthToken  # noqa: F401

config = context.config

# Track whether SSL is needed
_needs_ssl = False


def build_url() -> str:
    """
    Build the SQLAlchemy URL safely.
    Prefers individual PG* vars (handles special chars in passwords).
    Falls back to DATABASE_URL.
    """
    global _needs_ssl

    pghost = os.getenv("PGHOST")
    pgpassword = os.getenv("PGPASSWORD")
    pguser = os.getenv("PGUSER", "postgres")
    pgport = os.getenv("PGPORT", "5432")
    pgdatabase = os.getenv("PGDATABASE", "railway")

    if pghost and pgpassword:
        safe_password = quote_plus(pgpassword)
        return f"postgresql+asyncpg://{pguser}:{safe_password}@{pghost}:{pgport}/{pgdatabase}"

    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("Set DATABASE_URL or PGHOST+PGPASSWORD environment variables.")

    # Strip sslmode param (asyncpg doesn't understand it)
    if "sslmode=require" in url:
        _needs_ssl = True
        url = url.replace("?sslmode=require", "").replace("&sslmode=require", "")

    if "postgresql://" in url and "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")

    return url


config.set_main_option("sqlalchemy.url", build_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine_kwargs = {}
    if _needs_ssl:
        ssl_ctx = _ssl.create_default_context()
        engine_kwargs["connect_args"] = {"ssl": ssl_ctx}

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        **engine_kwargs,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()