# NPEDATA - CBN Nigerian Overnight Financing Rate connector (live, public JSON endpoint).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's homepage ticker (/rates/NOF_Rates.html). Kept in its own
# file rather than bundled with cbn_securities.py: different source page,
# no tenor complexity, matches the "group by source page" convention
# already used for the oil/discount-window connectors.
#
# FIXED: originally used GetAllNOF_RatesGRAPH, CBN's limited recent-window
# endpoint (only ~18 days returned) -- not because NOFR itself was new,
# but because the GRAPH variant is windowed by design. The full endpoint
# (no GRAPH suffix) has 157 rows, April 13 2026 to today; switching to it
# recovers ~139 days of real history this connector was silently dropping
# every day it ran. Also adds 4 richer fields from the same feed never
# captured before: dailyVolume, minimumRate, maximumRate,
# dailyVariationRange -- real market-depth signals. 2 rows share an exact
# date (confirmed live); normalize()'s existing last-write-wins dedup on
# (indicator_id, obs_date) handles this the same way it handles every
# other connector's duplicate rows.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

NOFR_URL = "https://www.cbn.gov.ng/api/GetAllNOF_Rates"

FIELD_MAP = {
    "nofr": "cbn_nofr",
    "dailyVolume": "cbn_nofr_volume",
    "minimumRate": "cbn_nofr_min_rate",
    "maximumRate": "cbn_nofr_max_rate",
    "dailyVariationRange": "cbn_nofr_variation_range",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNNOFRConnector(Connector):
    name = "cbn_nofr"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(NOFR_URL):
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
