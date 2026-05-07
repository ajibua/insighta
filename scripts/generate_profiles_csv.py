from __future__ import annotations

import argparse
import csv
import random
import string
from pathlib import Path


COUNTRIES = [
    ("NG", "Nigeria"),
    ("GH", "Ghana"),
    ("KE", "Kenya"),
    ("ZA", "South Africa"),
    ("EG", "Egypt"),
    ("US", "United States"),
    ("GB", "United Kingdom"),
    ("IN", "India"),
    ("FR", "France"),
    ("DE", "Germany"),
]


def _rand_name(rng: random.Random, i: int) -> str:
    first = rng.choice(
        [
            "Aisha",
            "Chidi",
            "Kofi",
            "Zara",
            "Vikram",
            "Ngozi",
            "Luis",
            "Fatima",
            "Ola",
            "Amara",
            "Hassan",
            "Valentina",
        ]
    )
    last = rng.choice(
        [
            "Okafor",
            "Kumar",
            "Mensah",
            "Adeyemi",
            "Miller",
            "Patel",
            "Diallo",
            "Thomas",
            "Suleiman",
            "Oliveira",
            "Kamara",
        ]
    )
    suffix = "".join(rng.choices(string.digits, k=6))
    return f"{first} {last} {i}{suffix}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a CSV for /api/profiles/import")
    ap.add_argument("--rows", type=int, default=10_000, help="Number of rows to generate")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("sample_profiles.csv"),
        help="Output CSV path",
    )
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for determinism")
    ap.add_argument(
        "--bad-rate",
        type=float,
        default=0.02,
        help="Fraction of intentionally bad rows (0..1) to test skipping logic",
    )
    args = ap.parse_args()

    rng = random.Random(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "name",
                "gender",
                "gender_probability",
                "age",
                "country_id",
                "country_name",
                "country_probability",
            ]
        )

        for i in range(args.rows):
            cid, cname = rng.choice(COUNTRIES)
            gender = rng.choice(["male", "female"])
            age = rng.randint(0, 90)
            gp = round(rng.uniform(0.6, 0.99), 4)
            cp = round(rng.uniform(0.55, 0.99), 4)
            name = _rand_name(rng, i)

            # Inject a small number of bad rows to exercise skip reasons
            if args.bad_rate > 0 and rng.random() < args.bad_rate:
                kind = rng.choice(["missing_fields", "invalid_age", "invalid_probability", "invalid_country"])
                if kind == "missing_fields":
                    name = ""
                elif kind == "invalid_age":
                    age = -5
                elif kind == "invalid_probability":
                    gp = 1.5
                elif kind == "invalid_country":
                    cid, cname = "XXX", "XXX"

            w.writerow([name, gender, gp, age, cid, cname, cp])

    print(f"Wrote {args.rows} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

