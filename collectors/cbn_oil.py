# NPEDATA - CBN crude oil connector (live, public JSON endpoint, no key required).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# CBN's Crude Oil Price page (cbn.gov.ng/rates/crudeoil.html) looks
# JavaScript-rendered, but its own inline script calls a plain JSON endpoint
# underneath -- found by reading the raw page source before assuming browser
# automation was needed. One call returns full history (2006 onward) across
# three series: price, domestic production, export volume.

from __future__ import annotations

import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllCrudeOilPrices"

# CBN field -> npedata indicator_id
SERIES = {
    "crudeOilPrice": "cbn_crude_oil_price",
    "domProd": "cbn_oil_domestic_production",
    "crudeOilExp": "cbn_oil_export_volume",
}


class CBNOilConnector(Connector):
    name = "cbn_oil"
    source_label = "CBN"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def _get(self):
        req = urllib.request.Request(URL, headers={"User-Agent": "npedata-collector/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch(self, start_year: int = 2015):
        rows = self._get()
        for row in rows:
            obs_date = f"{int(row['tyear']):04d}-{int(row['tmonth']):02d}-01"
            for field, indicator_id in SERIES.items():
                value = row.get(field)
                if value is None:
                    continue
                yield {
                    "indicator_id": indicator_id,
                    "obs_date": obs_date,
                    "value": float(value),
                    "source": self.source_label,
                }
