# NPEDATA - CBN Movement in Foreign Reserves connector (refreshes
# existing fx_reserves/reserves_* ids).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (../IntOps/Reserve.html, "Movement in
# Foreign Reserves", sibling to International Payments), backed by
# GetAllReserves: 4,993 rows, daily, 2006-04-03 to today, zero messiness.
#
# 4 fields map exactly to 4 EXISTING ids already referenced in
# /api/v1/fx-reserves: fx_reserves, reserves_liquid, reserves_blocked,
# reserves_block_pct -- all stale at 2026-04-01 (monthly placeholder
# dates from the original one-time ETL). Only fx_reserves had a
# main.py INDICATORS entry; the other 3 were missing one entirely (same
# gap pattern found repeatedly this session).
#
# Unit conversion: existing fx_reserves/reserves_liquid/reserves_blocked
# values are in USD BILLIONS (e.g. 48.6692), but this feed's gross/
# liquid/blocked fields are raw USD (e.g. 54358521234.28 ~= $54.36B) --
# divided by 1e9 here. blockPercent needs no conversion (already a plain
# percent on both sides).

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllReserves"

# (raw field, npedata indicator_id, divisor)
FIELD_MAP = (
    ("gross", "fx_reserves", 1e9),
    ("liquid", "reserves_liquid", 1e9),
    ("blocked", "reserves_blocked", 1e9),
    ("blockPercent", "reserves_block_pct", 1.0),
)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNReservesConnector(Connector):
    name = "cbn_reserves"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            obs_date = datetime.datetime.strptime(row["moveDate"], "%d/%m/%Y").date().isoformat()
            for raw_field, indicator_id, scale in FIELD_MAP:
                raw = row.get(raw_field)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    value = float(str(raw).replace(",", ".")) / scale
                except ValueError:
                    continue
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "CBN"}
