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
    set SUPABASE_URL and SUPABASE_SERVICE_KEY as environment variables, then:
        python project/database/seed/load_seed.py

    Run project/database/setup.sql first if the tables don't exist yet.
    SUPABASE_SERVICE_KEY is the service-role key (Supabase dashboard ->
    Settings -> API), never the anon key -- anon is read-only as of the
    LOCKDOWN migration in setup.sql (audit finding #1/#107).
"""

import csv
import os
from pathlib import Path

from supabase import create_client, Client

SEED_DIR = Path(__file__).parent

# No hardcoded fallback: this used to default to the anon key, which was
# hardcoded here with RLS disabled on every table it could write to (audit
# finding #1/#107). A missing env var should fail loudly instead.
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]


def read_csv(name):
    with open(SEED_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def chunked(rows, size=500):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def main():
    client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    data_sources = read_csv("data_sources.csv")
    client.table("data_sources").upsert(data_sources, on_conflict="code").execute()
    print(f"data_sources: upserted {len(data_sources)} rows")

    indicators = read_csv("indicators.csv")
    # csv.DictReader gives "" for a blank concept cell, not None -- left as "",
    # the Reconciler's /api/v1/reconcile index (which filters "concept IS NOT
    # NULL") would treat every untagged indicator as one bogus "" concept.
    for row in indicators:
        row["concept"] = row.get("concept") or None
    client.table("indicators").upsert(indicators, on_conflict="id").execute()
    print(f"indicators: upserted {len(indicators)} rows")

    observations = read_csv("observations.csv")
    total = 0
    for batch in chunked(observations):
        client.table("observations").upsert(batch, on_conflict="indicator_id,obs_date").execute()
        total += len(batch)
        print(f"  observations: upserted {total}/{len(observations)}")

    print("Seed load complete.")
    print(
        "Note: this script intentionally does NOT write to observation_vintages "
        "(the Ledger) -- re-running it to reproduce a snapshot is not a real "
        "revision, and writing one here on every reseed would record fake "
        "history. If vintages need to catch up after seeding a fresh database, "
        "re-run the backfill block in project/database/setup.sql -- it's "
        "idempotent (guarded by WHERE NOT EXISTS) and safe to run anytime."
    )


if __name__ == "__main__":
    main()
