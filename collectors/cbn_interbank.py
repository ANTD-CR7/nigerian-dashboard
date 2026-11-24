# NPEDATA - CBN daily interbank rates connector (live, public JSON endpoint).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/rates/interbankrates.html) -- a page
# distinct from Money Market Indicators, which already has a single monthly
# interbank call rate field. This daily feed is confirmed richer, not a
# duplicate: the existing monthly cbn_interbank_call_rate is stale (stuck
# at September 2026), while this daily feed has real data through the
# current date. Kept as a separate indicator (cbn_interbank_call_rate_daily),
# same precedent as the monthly/daily crude oil split already in this
# codebase.
#
# A handful of exact-duplicate (ratetype, date) rows exist in CBN's own
# data (same weightedaverage reported twice) -- no special handling needed,
# normalize()'s existing last-write-wins dedup on (indicator_id, obs_date)
# already collapses these correctly.
#
# weightedaverage itself is genuinely messy across 18,084 rows: 3,558 rows
# use "NIL" for missing data, 1,099 use a bare "-", a handful use "N"/"NL"
# typos, 1,778 have a trailing "%", 3 use a comma decimal separator, and a
# long tail of under 10 rows have one-off corruption (a literal range
# string where a single value belongs, values split across a line break).
# Handled by explicit rules for the known, meaningful patterns (missing-data
# markers, percent suffix, comma decimal) plus a catch-all that skips any
# row that still doesn't parse -- the same resilience already used
# elsewhere in this codebase (drop invalid rows, never crash the whole run
# over a handful of bad ones).
#
# A further 8 rows parse fine as numbers but are transcription errors --
# e.g. "222.19" on May-03-2002, a stray leading "2" with every neighbouring
# day and CBN's own reported `range` field agreeing the real value is near
# 22.19. CBN's `range` field (min-max for that day, separate from
# weightedaverage) is corroborating evidence, not a guess: when
# weightedaverage lands more than 3x outside the row's own range, it's
# dropped rather than "corrected" by guesswork -- same drop-don't-guess
# philosophy as the rest of this file. Verified this doesn't also flag
# genuine triple-digit crisis-period spikes (CBN interbank rates really did
# hit 100-300% in 2016-2018): those rows' weightedaverage sits inside (or
# very close to) their own reported range, so they pass the check untouched.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllInterbankRates"

_NO_DATA_MARKERS = {"nil", "nl", "n", "-", ""}

# CBN ratetype -> npedata indicator_id. "OBB" (1 stray row) merges into
# "OBB Rate". "4-7 Days"/"8-35 Days" (22 rows combined) don't cleanly match
# any of the 8 standard tenors -- excluded as noise, not mapped here.
RATE_TYPE_MAP = {
    "OBB Rate": "cbn_obb_rate",
    "OBB": "cbn_obb_rate",
    "Call Rate": "cbn_interbank_call_rate_daily",
    "7-Day": "cbn_interbank_rate_7d",
    "30-Day": "cbn_interbank_rate_30d",
    "60-Day": "cbn_interbank_rate_60d",
    "90-Day": "cbn_interbank_rate_90d",
    "180-Day": "cbn_interbank_rate_180d",
    "360-Day": "cbn_interbank_rate_360d",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_rate(raw) -> float | None:
    """None for a missing-data marker or anything that still doesn't parse
    as a plain number after normalization -- never raises, so one corrupted
    row can't crash the whole connector."""
    s = str(raw).strip().replace(",", ".")
    if s.endswith("%"):
        s = s[:-1].strip()
    if s.lower() in _NO_DATA_MARKERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _range_bounds(raw) -> tuple[float, float] | None:
    """CBN's own reported (low, high) for the row, used only as corroborating
    evidence to catch a corrupted weightedaverage -- None if it doesn't
    parse as a clean two-sided range."""
    if not raw:
        return None
    parts = str(raw).replace("%", "").strip().split("-")
    if len(parts) != 2:
        return None
    try:
        lo, hi = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    return (min(lo, hi), max(lo, hi))


def _consistent_with_range(value: float, range_raw) -> bool:
    """True unless CBN's own range field for the same row corroborates that
    weightedaverage is a transcription error (more than 3x outside it).
    Rates genuinely swung into triple digits during 2016-2018 liquidity
    crises -- those rows' value sits inside/near their own range, so this
    only catches the rarer case where weightedaverage itself is garbled."""
    bounds = _range_bounds(range_raw)
    if bounds is None:
        return True
    lo, hi = bounds
    if lo <= 0:
        return True
    return lo / 3 <= value <= hi * 3


class CBNInterbankRatesConnector(Connector):
    name = "cbn_interbank"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            indicator_id = RATE_TYPE_MAP.get(row.get("ratetype"))
            if indicator_id is None:
                continue
            value = _parse_rate(row.get("weightedaverage"))
            if value is None:
                continue
            if not _consistent_with_range(value, row.get("range")):
                continue
            obs_date = datetime.datetime.strptime(row["ratedate"], "%B-%d-%Y").date().isoformat()
            yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "CBN"}
