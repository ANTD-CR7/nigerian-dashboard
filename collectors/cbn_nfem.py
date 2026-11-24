# NPEDATA - CBN NFEM (Nigerian Foreign Exchange Market) rates connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's exchange rate page. Uses GetAllNFEM_Rates (the full
# endpoint, 495 rows, 2024-12-02 to today) rather than
# GetAllNFEM_RatesGRAPH, which only returns a recent window for charting.
#
# main.py's /api/v1/nfem endpoint already references nfem_highest,
# nfem_lowest and nfem_weighted_avg as indicator ids -- they've been dead
# fields until now because nothing ever populated them. This connector
# also adds simple-average, deal-count and turnover fields that weren't
# tracked anywhere on the platform before.
#
# noOfDeals_InterBank, nfeM_Total_Turnover and interBank_Total_Turnover
# are blank for 320 of 495 rows (CBN only started publishing the
# interbank breakdown partway through NFEM's history) -- skipped per
# field, not per row, so the other 6 fields for that date still get
# written. 6 dates have 2 conflicting rows; normalize()'s existing
# last-write-wins dedup on (indicator_id, obs_date) handles this the same
# way it handles every other connector's duplicate rows.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllNFEM_Rates"

FIELD_MAP = {
    "closingrate": "nfem_closing",
    "highestrate": "nfem_highest",
    "lowestrate": "nfem_lowest",
    "weightedAvgRate": "nfem_weighted_avg",
    "simpleAvgRate": "nfem_simple_avg",
    "noOfDeals": "nfem_deals_count",
    "noOfDeals_InterBank": "nfem_deals_count_interbank",
    "nfeM_Total_Turnover": "nfem_total_turnover",
    "interBank_Total_Turnover": "nfem_interbank_turnover",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNNFEMConnector(Connector):
    name = "cbn_nfem"
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
