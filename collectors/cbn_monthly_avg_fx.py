# NPEDATA - CBN Monthly Average Exchange Rates of the Naira connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/rates/exrate.html, GetAllMonthlyAvgExchRates,
# 208 rows, monthly, January 2004 -> April 2021). Frozen/discontinued by
# CBN, not a scraping gap -- the most recent entry in the live feed
# itself is April 2021.
#
# 6 fields: daswdasDollar (official/WDAS rate), ifemDollar (Interbank/
# IFEM rate), bdcDollar (bureau-de-change -- the parallel/black-market
# rate, not captured anywhere else on the platform), pounds/euro/cfaFr
# (monthly averages of currencies already tracked daily via
# gbp_central/eur_central/cfa_central -- kept as CBN's own published
# averages, not approximated from the daily feed).
#
# Zero bad values, zero duplicate dates; blanks are genuine historical
# regime gaps (daswdasDollar blank for 74/208 rows -- WDAS wasn't the
# prevailing mechanism for that whole window; ifemDollar blank for 1).

from __future__ import annotations

import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllMonthlyAvgExchRates"

FIELD_MAP = {
    "daswdasDollar": "cbn_usd_wdas_rate",
    "ifemDollar": "cbn_usd_ifem_rate",
    "bdcDollar": "cbn_usd_bdc_rate",
    "pounds": "cbn_gbp_monthly_avg",
    "euro": "cbn_eur_monthly_avg",
    "cfaFr": "cbn_cfa_monthly_avg",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNMonthlyAvgFXConnector(Connector):
    name = "cbn_monthly_avg_fx"
    source_label = "CBN"

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
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "CBN"}
