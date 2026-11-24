# NPEDATA - CBN Nigerian Overnight Financing Rate Index (NOFRI) connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found alongside NOFR on CBN's rates page (/rates/NOF_Rates.html),
# backed by GetAllNOFR_Index -- a SOFR-Index-style cumulative compounding
# index of the overnight NOFR rate, 225 rows, April 13 2026 to today,
# zero bad values, zero duplicate dates.
#
# 4 fields captured: nofrIndex (the compounding index itself, starting
# at 1.0), thirtyDay_NOFR/ninetyDay_NOFR/oneEightyDay_NOFR (30/90/180-day
# compounded term rates -- reference-rate benchmarks for floating-rate
# pricing, nothing like them exists on the platform). A 5th field
# ("nofr") duplicates cbn_nofr exactly and is not mapped here. The term-
# rate fields are blank for exactly 30/90/180 rows respectively -- a
# genuine "not enough days accumulated yet" ramp-up (confirmed: each
# field's blank count matches its own window length exactly), not
# corruption -- skipped per-field, not per-row.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllNOFR_Index"

FIELD_MAP = {
    "nofrIndex": "cbn_nofri",
    "thirtyDay_NOFR": "cbn_nofr_30d_term",
    "ninetyDay_NOFR": "cbn_nofr_90d_term",
    "oneEightyDay_NOFR": "cbn_nofr_180d_term",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNNOFRIConnector(Connector):
    name = "cbn_nofri"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            obs_date = datetime.datetime.strptime(row["ratedate"], "%B-%d-%Y").date().isoformat()
            for field, indicator_id in FIELD_MAP.items():
                raw = row.get(field)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    value = float(str(raw).replace(",", "."))
                except ValueError:
                    continue
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "CBN"}
