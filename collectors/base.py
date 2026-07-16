# NPEDATA - automated data collection framework.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0; see LICENSE/NOTICE.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# A connector fetches raw observations from a source and yields them in the
# platform's tidy shape. normalize() then validates and de-duplicates, reusing
# the same rules the API's ingestion path enforces. Collection is demo-safe by
# default: the runner writes a dated snapshot file for review and only touches
# the live database when explicitly enabled.

from __future__ import annotations

import datetime as _dt


class Connector:
    """Base class for a source connector."""
    name = "base"
    source_label = "Unknown"

    def fetch(self, start_year: int = 2015):
        """Yield dicts: {indicator_id, obs_date (ISO), value (float), source}."""
        raise NotImplementedError


def _valid_date(s: str) -> bool:
    try:
        _dt.date.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


def normalize(rows) -> list[dict]:
    """Validate, coerce and de-duplicate raw rows.

    Rules (mirroring the API's ingestion validation): obs_date must be ISO
    YYYY-MM-DD, value must be a finite number, and (indicator_id, obs_date)
    must be unique - the last write wins, matching the DB's uniqueness rule.
    Rows that fail validation are dropped and counted, never silently kept.
    """
    seen: dict = {}
    dropped = 0
    for row in rows:
        iid = str(row.get("indicator_id", "")).strip()
        date = str(row.get("obs_date", "")).strip()
        try:
            value = float(row.get("value"))
            finite = value == value and value not in (float("inf"), float("-inf"))
        except (TypeError, ValueError):
            finite = False
            value = None
        if not iid or not _valid_date(date) or not finite:
            dropped += 1
            continue
        seen[(iid, date)] = {
            "indicator_id": iid,
            "obs_date": date,
            "value": round(value, 6),
            "source": str(row.get("source", "")).strip() or "Unknown",
        }
    clean = sorted(seen.values(), key=lambda r: (r["indicator_id"], r["obs_date"]))
    return clean, dropped
