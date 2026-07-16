# NPEDATA - collection runner.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Runs the connectors, normalises the result, and writes a dated JSON snapshot
# for review. It only writes to the live database when NPE_COLLECT_WRITE=true
# AND Supabase credentials are present - demo-safe by default, exactly like the
# API's ingestion path.
#
#   python -m collectors.runner            # collect -> data/collected/*.json
#   python -m collectors.runner --write    # also upsert into Supabase

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path

from .base import normalize
from .world_bank import WorldBankConnector
from .sources_scaffold import CBNConnector, NBSConnector

DEFAULT_CONNECTORS = [WorldBankConnector(), CBNConnector(), NBSConnector()]


def run(connectors=None, out_dir="data/collected", write_db=False, stamp=None):
    connectors = connectors or DEFAULT_CONNECTORS
    raw = []
    per_source = {}
    for c in connectors:
        rows = list(c.fetch())
        per_source[c.name] = len(rows)
        raw.extend(rows)

    clean, dropped = normalize(raw)
    stamp = stamp or datetime.date.today().isoformat()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"collected_{stamp}.json"
    snapshot = {
        "collected_at": stamp,
        "rows": len(clean),
        "dropped_invalid": dropped,
        "per_source": per_source,
        "observations": clean,
    }
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    written = 0
    if write_db:
        written = _upsert(clean)

    summary = {
        "rows": len(clean),
        "dropped": dropped,
        "per_source": per_source,
        "snapshot": str(path),
        "written_to_db": written,
    }
    return summary


def _upsert(rows) -> int:
    """Upsert observations into Supabase. Guarded twice: requires the explicit
    flag AND credentials; otherwise it is a no-op."""
    if os.environ.get("NPE_COLLECT_WRITE", "").lower() != "true":
        return 0
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return 0
    try:
        from supabase import create_client
    except ImportError:
        return 0
    client = create_client(url, key)
    client.table("observations").upsert(rows, on_conflict="indicator_id,obs_date").execute()
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Collect NPEDATA source data.")
    ap.add_argument("--write", action="store_true", help="also upsert into Supabase (needs NPE_COLLECT_WRITE=true + creds)")
    ap.add_argument("--out", default="data/collected", help="snapshot output directory")
    args = ap.parse_args()
    summary = run(write_db=args.write, out_dir=args.out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
