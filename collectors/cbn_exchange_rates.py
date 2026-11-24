# NPEDATA - CBN exchange rates connector (live, public JSON endpoint).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's exchange rate page (/rates/ExchRateByCurrency.html) --
# a genuine daily JSON feed (62,735 rows, 2001-12-10 to today) replacing
# what was previously a one-time manual seed (project/load_data.py) that
# stalled at 2026-04-01 and was never hooked into this pipeline.
#
# Currency labels are messy across 25 years of data: whitespace/tab
# variants ("CFA ", "EURO\t"), a naming change partway through
# ("DANISH KRONER" pre-2012 -> "DANISH KRONA" after), singular/plural
# drift ("POUND STERLING" vs "POUNDS STERLING"), and an alternate full
# name ("JAPANESE YEN" vs "YEN"). All normalized into CURRENCY_MAP below.
# Two labels are noise, not real currencies: "NAIRA" (8 rows, NGN vs NGN
# makes no sense as a cross rate) and "POESO" (3 rows, unclear/vanishingly
# rare) -- excluded, same precedent as other off-pattern exclusions this
# session (e.g. "4-7 Days"/"8-35 Days" in the interbank connector).
#
# The numeric fields themselves are clean -- verified zero unparseable
# values across all 62,735 rows -- so the try/except here is defensive,
# not working around a known pattern. 80 rows share an exact (currency,
# date) key with a conflicting value; normalize()'s existing last-write-
# wins dedup on (indicator_id, obs_date) handles this the same way it
# handles every other connector's duplicate rows.

from __future__ import annotations

import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllExchangeRates"

CURRENCY_MAP = {
    "CFA": "cfa",
    "YUAN/RENMINBI": "cny",
    "DANISH KRONA": "dkk",
    "DANISH KRONER": "dkk",
    "EURO": "eur",
    "YEN": "jpy",
    "JAPANESE YEN": "jpy",
    "RIYAL": "sar",
    "SOUTH AFRICAN RAND": "zar",
    "SDR": "sdr",
    "SWISS FRANC": "chf",
    "POUNDS STERLING": "gbp",
    "POUND STERLING": "gbp",
    "US DOLLAR": "usd",
    "WAUA": "waua",
    "UAE DIRHAM": "aed",
}

_FIELDS = (("buyingrate", "buying"), ("centralrate", "central"), ("sellingrate", "selling"))


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNExchangeRatesConnector(Connector):
    name = "cbn_exchange_rates"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            code = CURRENCY_MAP.get((row.get("currency") or "").strip().upper())
            if code is None:
                continue
            obs_date = row["ratedate"]
            for field, suffix in _FIELDS:
                try:
                    value = float(str(row.get(field)).replace(",", "."))
                except (TypeError, ValueError):
                    continue
                yield {"indicator_id": f"{code}_{suffix}", "obs_date": obs_date, "value": value, "source": "CBN"}
                # "exchange_rate" is the legacy id used by /api/v1/exchange-rate,
                # /summary and /leadlag -- confirmed to be a plain alias of
                # usd_central (identical values at every date checked against
                # the live DB), not a separate series. Kept alive here instead
                # of leaving it stale while usd_central refreshes.
                if code == "usd" and suffix == "central":
                    yield {"indicator_id": "exchange_rate", "obs_date": obs_date, "value": value, "source": "CBN"}
