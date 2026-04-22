#!/usr/bin/env python3
"""
Seed the database with profiles from a JSON file.
Run: python seed.py profiles.json

Re-running is safe — duplicate names are skipped via ON CONFLICT DO NOTHING.
UUID v7 is generated per-record using the uuid_utils library.
"""

import asyncio
import json
import sys
from datetime import timezone

import asyncpg
import uuid_utils as uuid

from app.core.config import settings


def classify_age_group(age: int) -> str:
    if age < 13:
        return "child"
    elif age < 20:
        return "teenager"
    elif age < 65:
        return "adult"
    else:
        return "senior"


def clean_db_url(url: str) -> str:
    """Convert SQLAlchemy async URL to plain asyncpg URL."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


def load_profiles(filepath: str) -> list[dict]:
    """Load profiles from either a top-level list or a {'profiles': [...]} object."""
    with open(filepath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        profiles = payload
    elif isinstance(payload, dict) and isinstance(payload.get("profiles"), list):
        profiles = payload["profiles"]
    else:
        raise ValueError(
            "Invalid JSON format. Expected a list or an object with a 'profiles' list."
        )

    for i, item in enumerate(profiles):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid profile at index {i}: expected an object.")

    return profiles


async def seed(filepath: str):
    profiles = load_profiles(filepath)

    conn = await asyncpg.connect(clean_db_url(settings.DATABASE_URL))

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

    print(f"Seed complete: {inserted} inserted, {skipped} skipped (duplicates).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python seed.py seed_profiles.json")
        sys.exit(1)

    asyncio.run(seed(sys.argv[1]))
