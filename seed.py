#!/usr/bin/env python3
"""
Seed the database with profiles from a JSON file.
Run: python seed.py profiles.json
"""

import asyncio
import json
import os
import ssl
import sys

import asyncpg
import uuid_utils as uuid
from dotenv import load_dotenv

load_dotenv()


def classify_age_group(age: int) -> str:
    if age < 13:
        return "child"
    elif age < 20:
        return "teenager"
    elif age < 65:
        return "adult"
    else:
        return "senior"


def get_connection_kwargs() -> dict:
    pghost = os.getenv("PGHOST", "localhost")
    pgpassword = os.getenv("PGPASSWORD")
    pgport = int(os.getenv("PGPORT", "5432"))
    pguser = os.getenv("PGUSER", "postgres")
    pgdatabase = os.getenv("PGDATABASE", "railway")
    sslmode = os.getenv("PGSSLMODE", "")

    # Auto-enable SSL for remote hosts unless explicitly disabled
    is_remote = pghost not in ("localhost", "127.0.0.1", "::1")
    use_ssl = sslmode != "disable" and is_remote

    ssl_ctx = None
    if use_ssl:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

    kwargs = dict(
        host=pghost,
        port=pgport,
        user=pguser,
        database=pgdatabase,
    )
    if pgpassword:
        kwargs["password"] = pgpassword
    if ssl_ctx:
        kwargs["ssl"] = ssl_ctx

    return kwargs


async def seed(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        profiles = data["profiles"] if isinstance(data, dict) else data

    print("Connecting to database...")
    conn_kwargs = get_connection_kwargs()

    print(f"  host: {conn_kwargs['host']}")
    print(f"  port: {conn_kwargs['port']}")
    print(f"  user: {conn_kwargs['user']}")
    print(f"  db:   {conn_kwargs['database']}")
    print(f"  ssl:  {'yes' if conn_kwargs.get('ssl') else 'no'}")

    try:
        conn = await asyncpg.connect(**conn_kwargs)
    except Exception as e:
        print(f"\nERROR: Could not connect.\n{e}")
        print("\nMake sure you set all vars IN THE SAME cmd window before running:")
        print("  set PGHOST=your-railway-host.proxy.rlwy.net")
        print("  set PGPORT=54321")
        print("  set PGUSER=postgres")
        print("  set PGPASSWORD=yourpassword")
        print("  set PGDATABASE=railway")
        print("  python seed.py seed_profiles.json")
        sys.exit(1)

    print(f"Connected! Seeding {len(profiles)} profiles...")

    inserted = 0
    skipped = 0

    try:
        for p in profiles:
            age = int(p.get("age", 0))
            record_id = str(uuid.uuid7())

            result = await conn.execute(
                """
                INSERT INTO profiles (
                    id, name, gender, gender_probability,
                    age, age_group,
                    country_id, country_name, country_probability,
                    created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                ON CONFLICT (name) DO NOTHING
                """,
                record_id,
                str(p["name"]).lower(),
                str(p.get("gender", "")).lower(),
                float(p.get("gender_probability", 0.0)),
                age,
                classify_age_group(age),
                str(p.get("country_id", "")).upper(),
                str(p.get("country_name", "")),
                float(p.get("country_probability", 0.0)),
            )
            if result == "INSERT 0 1":
                inserted += 1
            else:
                skipped += 1

    finally:
        await conn.close()

    print(f"\nSeed complete: {inserted} inserted, {skipped} skipped (duplicates).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python seed.py <path-to-profiles.json>")
        sys.exit(1)

    asyncio.run(seed(sys.argv[1]))