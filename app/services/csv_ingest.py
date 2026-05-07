"""
Streamed CSV ingestion: chunked bulk INSERT, per-row validation, partial success semantics.
"""

from __future__ import annotations

import asyncio
import csv
import sys
from dataclasses import dataclass, field
from io import TextIOWrapper
from typing import BinaryIO, Dict, List, Set

import uuid_utils as uuid
from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.database import AsyncSessionLocal          
from app.models.profile import Profile
from app.services.profile_service import COUNTRY_NAMES, VALID_GENDERS, classify_age_group


csv.field_size_limit(min(sys.maxsize, 10_000_000))


REQUIRED_HEADERS = {
    "name",
    "gender",
    "gender_probability",
    "age",
    "country_id",
    "country_name",
    "country_probability",
}

CHUNK_SIZE = 2_500


def _norm_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_")


def _parse_float(val: str | None) -> float | None:
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(str(val).strip())
    except ValueError:
        return None


def _parse_int(val: str | None) -> int | None:
    if val is None or str(val).strip() == "":
        return None
    try:
        return int(str(val).strip())
    except ValueError:
        return None


@dataclass
class IngestSummary:
    total_rows: int = 0
    inserted: int = 0
    skipped: int = 0
    reasons: Dict[str, int] = field(default_factory=dict)

    def bump(self, reason: str, n: int = 1) -> None:
        self.skipped += n
        self.reasons[reason] = self.reasons.get(reason, 0) + n


async def ingest_profiles_csv_stream(
    binary_stream: BinaryIO,              
    encoding: str = "utf-8",
) -> IngestSummary:
    """
    Read CSV from a binary stream without loading the whole file into memory.
    Valid rows are inserted in bulk batches using short-lived sessions per chunk.
    Duplicate names are handled atomically via ON CONFLICT DO NOTHING —
    no race window, no batch abort on unique constraint violation.
    """
    summary = IngestSummary()
    seen_lower_names: Set[str] = set()   # in-process dedup within this upload
    pending: List[dict] = []

    # ── flush_batch ──────────────────────────────────────────────────────────
    # Opens a fresh session per chunk and releases it immediately after commit.
    # This means the DB connection is held for milliseconds per batch, not for
    # the entire upload — read queries are never starved of pool connections.
    async def flush_batch(batch: List[dict]) -> None:
        if not batch:                          
            return

        async with AsyncSessionLocal() as db:  
            stmt = (
                pg_insert(Profile)
                .values(batch)
                .on_conflict_do_nothing(index_elements=["name"])
            )
            result = await db.execute(stmt)
            await db.commit()

        inserted_count = result.rowcount
        skipped_count = len(batch) - inserted_count
        summary.inserted += inserted_count
        if skipped_count > 0:
            summary.bump("duplicate_name", skipped_count)

    # ── CSV parsing ──────────────────────────────────────────────────────────
    wrapper = TextIOWrapper(binary_stream, encoding=encoding, newline="", errors="replace")
    reader = csv.reader(wrapper)

    # Parse header row
    try:
        header_row = next(reader)
    except StopIteration:
        return summary
    except UnicodeDecodeError:
        summary.bump("invalid_encoding", 1)
        return summary

    headers = [_norm_header(h) for h in header_row]

    # Duplicate header columns → whole file is malformed
    if len(set(headers)) != len(headers):
        for _ in reader:
            summary.total_rows += 1
            summary.bump("malformed_row", 1)
        return summary

    # Required columns missing → whole file is unusable
    missing_req = REQUIRED_HEADERS - set(headers)
    if missing_req:
        for _ in reader:
            summary.total_rows += 1
            summary.bump("missing_fields", 1)
        return summary

    idx_range = range(len(headers))

    # ── Row iteration ────────────────────────────────────────────────────────
    try:
        for raw in reader:
            summary.total_rows += 1

            # Wrong column count → malformed row
            if len(raw) != len(headers):
                summary.bump("malformed_row", 1)
                continue

            # Encoding replacement characters present → bad encoding
            if any("\ufffd" in (cell or "") for cell in raw):
                summary.bump("invalid_encoding", 1)
                continue

            row_map = {headers[i]: (raw[i] or "").strip() for i in idx_range}

            # Extract fields
            name_raw  = row_map.get("name", "")
            g_raw     = row_map.get("gender", "")
            age_raw   = row_map.get("age", "")
            cid_raw   = row_map.get("country_id", "")
            cname_raw = row_map.get("country_name", "")
            gp_raw    = row_map.get("gender_probability", "")
            cp_raw    = row_map.get("country_probability", "")

            # Required field presence check
            if not name_raw or not g_raw or age_raw == "" or not cid_raw:
                summary.bump("missing_fields", 1)
                continue

            # In-process duplicate check (within this upload)
            # The DB-level ON CONFLICT handles cross-upload / concurrent duplicates
            name_l = name_raw.lower()
            if name_l in seen_lower_names:
                summary.bump("duplicate_name", 1)
                continue

            # Gender validation
            g = g_raw.lower()
            if g not in VALID_GENDERS:
                summary.bump("invalid_gender", 1)
                continue

            # Age validation
            age = _parse_int(age_raw)
            if age is None or age < 0 or age > 130:
                summary.bump("invalid_age", 1)
                continue

            # Probability validation
            gp = _parse_float(gp_raw)
            cp = _parse_float(cp_raw)
            if gp is None or cp is None:
                summary.bump("missing_fields", 1)
                continue
            if not (0.0 <= gp <= 1.0) or not (0.0 <= cp <= 1.0):
                summary.bump("invalid_probability", 1)
                continue

            # Country ID validation
            cid = cid_raw.strip().upper()
            if len(cid) != 2:
                summary.bump("invalid_country", 1)
                continue

            cname = cname_raw.strip() or COUNTRY_NAMES.get(cid, cid)

            rec = {
                "id":                  str(uuid.uuid7()),
                "name":                name_l,
                "gender":              g,
                "gender_probability":  gp,
                "age":                 age,
                "age_group":           classify_age_group(age),
                "country_id":          cid,
                "country_name":        cname,
                "country_probability": cp,
            }

            seen_lower_names.add(name_l)
            pending.append(rec)

            # Flush when chunk is full
            if len(pending) >= CHUNK_SIZE:
                await flush_batch(pending)
                pending.clear()
                await asyncio.sleep(0)   # yield to event loop — keeps read queries responsive

    except UnicodeDecodeError:
        summary.bump("invalid_encoding", 1)

    # Flush any remaining rows
    await flush_batch(pending)

    # Remove zero-count reasons from summary
    summary.reasons = {k: v for k, v in summary.reasons.items() if v > 0}
    return summary