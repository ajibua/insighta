"""
Standalone CSV ingestion worker for Insighta Labs+.
Runs independently of the FastAPI app — no HTTP, no Uvicorn.

Usage:
    python worker.py --file profiles_test.csv
    python worker.py --file profiles_test.csv --encoding latin-1
"""
 
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.database import engine                          # noqa: E402
from app.services.csv_ingest import ingest_profiles_csv_stream  # noqa: E402
from app.services.query_cache import invalidate_profiles_cache  # noqa: E402


async def run(file_path: str, encoding: str) -> None:
    path = Path(file_path)

    if not path.exists():
        print(f"[error] File not found: {file_path}")
        sys.exit(1)

    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"\n Insighta Labs+ -- CSV Ingestion Worker")
    print(f" {'-'*40}")
    print(f" File:     {path.name}")
    print(f" Size:     {size_mb:.1f} MB")
    print(f" Encoding: {encoding}")
    print(f" {'-'*40}\n")

    start = time.perf_counter()

    try:
        with open(path, "rb") as f:
            summary = await ingest_profiles_csv_stream(f, encoding=encoding)

        elapsed = time.perf_counter() - start

        try:
            await invalidate_profiles_cache()
            print(" Cache invalidated [OK]")
        except Exception as e:
            print(f" Cache invalidation skipped ({e})")

        rows_per_sec = summary.total_rows / elapsed if elapsed > 0 else 0

        print(f"\n {'-'*40}")
        print(f"  Status:      success")
        print(f"  Total rows:  {summary.total_rows:,}")
        print(f"  Inserted:    {summary.inserted:,}")
        print(f"  Skipped:     {summary.skipped:,}")

        if summary.reasons:
            print(f"\n  Skip reasons:")
            for reason, count in sorted(summary.reasons.items(), key=lambda x: -x[1]):
                print(f"    {reason:<30} {count:,}")

        print(f"\n  Time:        {elapsed:.1f}s")
        print(f"  Throughput:  {rows_per_sec:,.0f} rows/sec")
        print(f" {'-'*40}\n")

    finally:
        await engine.dispose()   # ← inside async, before loop closes

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a CSV file into Insighta Labs+ directly (no HTTP)"
    )
    parser.add_argument(
        "--file", required=True,
        help="Path to the CSV file to ingest"
    )
    parser.add_argument(
        "--encoding", default="utf-8",
        help="CSV file encoding (default: utf-8)"
    )
    args = parser.parse_args()

    asyncio.run(run(args.file, args.encoding))


if __name__ == "__main__":
    main()