# NPEDATA - CBN inflation rates connector (refreshes existing NBS ids).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/rates/inflrates.html, GetAllInflationRates,
# 286 rows, monthly, January 2003 to today, zero messiness). This
# endpoint's 7 non-headline fields were checked earlier this session
# against existing NBS indicators and found to be exact duplicates -- a
# connector built for them as NEW ids was deleted. That was correct for
# avoiding duplicate ids, but no connector was ever built to actually
# refresh the existing 8 ids. Confirmed stale (stuck at 2026-03-01,
# 8 months behind) and same source (exact value match at that date for
# all 8 fields, e.g. inflation=15.38 matches live allItemsYearOn=15.38
# for March 2026). This connector refreshes those 8 existing ids -- no
# new indicators, no new live `indicators` table rows needed.

from __future__ import annotations

import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllInflationRates"

FIELD_MAP = {
    "allItemsYearOn": "inflation",
    "allItemsAverage": "inflation_avg",
    "foodYearOn": "inflation_food",
    "foodAverage": "inflation_food_avg",
    "allItemsLessFrmProdYearOn": "inflation_core",
    "allItemsLessFrmProdAverage": "inflation_core_avg",
    "allItemsLessFrmProdAndEnergyYearOn": "inflation_core_energy",
    "allItemsLessFrmProdAndEnergyAvg": "inflation_core_energy_avg",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNInflationConnector(Connector):
    name = "cbn_inflation"
    source_label = "NBS"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            obs_date = f"{row['tyear']}-{int(row['tmonth']):02d}-01"
            for field, indicator_id in FIELD_MAP.items():
                raw = row.get(field)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    value = float(str(raw).replace(",", "."))
                except ValueError:
                    continue
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "NBS"}
