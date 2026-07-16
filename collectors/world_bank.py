# NPEDATA - World Bank connector (live, public API, no key required).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# The World Bank Indicators API is genuinely open and machine-readable, so this
# connector is fully automated. It fetches Nigeria (NGA) annual series and maps
# each World Bank indicator code to a namespaced NPEDATA indicator_id (prefixed
# `wb_`) so it never collides with the platform's existing curated series.

from __future__ import annotations

import json
import urllib.request

from .base import Connector

BASE = "https://api.worldbank.org/v2/country/NGA/indicator/{code}?format=json&per_page=200&date={start}:{end}"

# World Bank code -> (npedata indicator_id, human name)
INDICATORS = {
    "NY.GDP.MKTP.CD": ("wb_gdp_usd", "GDP (current US$)"),
    "NY.GDP.MKTP.KD.ZG": ("wb_gdp_growth", "GDP growth (annual %)"),
    "FP.CPI.TOTL.ZG": ("wb_inflation", "Inflation, consumer prices (annual %)"),
    "SL.UEM.TOTL.ZS": ("wb_unemployment", "Unemployment (% of labour force)"),
    "NE.EXP.GNFS.ZS": ("wb_exports_gdp", "Exports of goods and services (% of GDP)"),
    "BX.KLT.DINV.CD.WD": ("wb_fdi_usd", "Foreign direct investment, net inflows (US$)"),
    "SP.POP.TOTL": ("wb_population", "Population, total"),
}


class WorldBankConnector(Connector):
    name = "world_bank"
    source_label = "World Bank"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def _get(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch(self, start_year: int = 2010, end_year: int = 2026):
        for code, (iid, _name) in INDICATORS.items():
            url = BASE.format(code=code, start=start_year, end=end_year)
            try:
                payload = self._get(url)
            except Exception:
                continue  # skip a failing series, keep the rest
            series = payload[1] if isinstance(payload, list) and len(payload) > 1 else None
            for row in series or []:
                if row.get("value") is None:
                    continue
                yield {
                    "indicator_id": iid,
                    "obs_date": f"{row['date']}-01-01",  # annual -> Jan 1
                    "value": row["value"],
                    "source": self.source_label,
                }
