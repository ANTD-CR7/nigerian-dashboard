"""
FILE: project/database/seed/load_seed.py

PURPOSE:
    Reproduces the full dataset (3 data sources, 122 indicators, 12,100
    observations) from the CSV snapshot in this folder into Supabase.
    This is the single source of truth for "how does the data get into
    the database" -- it replaces the old load_data.py / load_gdp.py /
    load_other_indicators.py scripts, which only ever covered 5 of the
    122 indicators now in use.

    The CSV snapshot was generated from the live database on 2026-06-28.
    Re-running this script is always safe: every table uses an upsert
    keyed on its primary/unique key, so existing rows are updated in
    place rather than duplicated.

HOW TO RUN:
    pip install supabase
    set SUPABASE_URL and SUPABASE_KEY as environment variables, then:
        python project/database/seed/load_seed.py

    Run project/database/setup.sql first if the tables don't exist yet.
"""

import csv
import os
from pathlib import Path

from supabase import create_client, Client

SEED_DIR = Path(__file__).parent

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fjsytcmcxapfbrwvawmu.supabase.co")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqc3l0Y21jeGFwZmJyd3Zhd211Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4OTcxOTgsImV4cCI6MjA5MTQ3MzE5OH0.0lGkBdBsY7bQGu4jlHQA0MKm54dd51QwJTdeill_ADw",
)


def read_csv(name):
    with open(SEED_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def chunked(rows, size=500):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def main():
    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    data_sources = read_csv("data_sources.csv")
    client.table("data_sources").upsert(data_sources, on_conflict="code").execute()
    print(f"data_sources: upserted {len(data_sources)} rows")

    indicators = read_csv("indicators.csv")
    client.table("indicators").upsert(indicators, on_conflict="id").execute()
    print(f"indicators: upserted {len(indicators)} rows")

    observations = read_csv("observations.csv")
    total = 0
    for batch in chunked(observations):
        client.table("observations").upsert(batch, on_conflict="indicator_id,obs_date").execute()
        total += len(batch)
        print(f"  observations: upserted {total}/{len(observations)}")

    print("Seed load complete.")


if __name__ == "__main__":
    main()
