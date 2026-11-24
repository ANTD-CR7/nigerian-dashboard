# NPEDATA - CBN Statement of Assets & Liabilities connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/rates/Assets.html, GetAllAssetsLiabilities,
# 229 rows, monthly, January 2005 to November 2023 -- frozen by CBN
# itself, confirmed that's the feed's own final entry, not a scraping
# gap). 23 fields confirmed via the page's own static labels tables
# (<table id="labels"> through labels4), cross-verified against the
# page's JS data-slicing logic (data1/data2/data3/data4 groups of 6
# fields map exactly to the 4 label tables in order).
#
# 4 of these 23 fields already exist as platform ids (cbn_total_assets,
# cbn_total_liabilities, cbn_gold, cbn_currency_issued) -- confirmed
# same source via exact value match against the live feed. No active
# connector existed for any of them: a one-time manual-ETL seed happened
# to capture through Nov 2023, the same month CBN itself stopped
# publishing. This connector captures the other 19 genuinely new fields
# too, and will auto-resume if CBN ever republishes.
#
# cbnInstruments is blank for 166/229 rows -- introduced partway through
# the dataset's history (same regime-gap pattern as elsewhere this
# session), skipped per-field. 4 duplicate-date rows -- same
# last-write-wins handling as every other connector.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllAssetsLiabilities"

FIELD_MAP = {
    "gold": "cbn_gold",
    "convertible": "cbn_convertible_currencies",
    "imfGold": "cbn_imf_gold_tranche",
    "sdr": "cbn_sdr_holdings",
    "ter": "cbn_total_external_reserve",
    "fgs": "cbn_fed_govt_securities",
    "osec": "cbn_other_securities",
    "redAdv": "cbn_rediscount_advances",
    "otherAss": "cbn_other_assets",
    "fixAss": "cbn_fixed_assets",
    "totalAss": "cbn_total_assets",
    "liaCap": "cbn_capital_subscribed",
    "genRes": "cbn_general_reserves",
    "otherRes": "cbn_other_reserves",
    "totalCap": "cbn_total_capitalization",
    "cbnInstruments": "cbn_instruments_outstanding",
    "cinC": "cbn_currency_issued",
    "govtDep": "cbn_govt_deposits",
    "bankers": "cbn_bankers_deposits",
    "others": "cbn_other_deposits",
    "totalDep": "cbn_total_deposits",
    "otherLia": "cbn_other_liabilities",
    "totalLia": "cbn_total_liabilities",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNAssetsLiabilitiesConnector(Connector):
    name = "cbn_assets_liabilities"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            obs_date = datetime.datetime.strptime(row["payDate"], "%d/%m/%Y").date().isoformat()
            for field, indicator_id in FIELD_MAP.items():
                raw = row.get(field)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    value = float(str(raw).replace(",", "."))
                except ValueError:
                    continue
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "CBN"}
