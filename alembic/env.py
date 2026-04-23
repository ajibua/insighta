import asyncio
import os
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

config = context.config


def build_url() -> str:
    """
    Build the SQLAlchemy URL safely.
    Prefers individual PG* vars (handles special chars in passwords).
    Falls back to DATABASE_URL.
    """
    pghost = os.getenv("PGHOST")
    pgpassword = os.getenv("PGPASSWORD")
    pguser = os.getenv("PGUSER", "postgres")
    pgport = os.getenv("PGPORT", "5432")
    pgdatabase = os.getenv("PGDATABASE", "railway")

    if pghost and pgpassword:
        # quote_plus encodes @, #, $, etc. safely
        safe_password = quote_plus(pgpassword)
        return f"postgresql+asyncpg://{pguser}:{safe_password}@{pghost}:{pgport}/{pgdatabase}"

    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("Set DATABASE_URL or PGHOST+PGPASSWORD environment variables.")

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
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
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