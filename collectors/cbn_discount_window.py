# NPEDATA - CBN discount window connector (live, public JSON endpoint, no key required).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# CBN's Discount Window page bundles ~20 distinct money-market rate series
# (standing facilities, repo tenors, historical MPR) under one endpoint, found
# the same way as the oil connectors: reading the raw page source rather than
# assuming browser automation was needed. The data has inconsistent `ratetype`
# naming across two historical eras -- e.g. "Standing Lending Rate" (pre-2013)
# vs "Standing LendingRate" (2013+, missing space) are the same series;
# "1-7 Day" vs "1-7 Days" are the same bucket, just pluralization. Those are
# merged below. Day ranges that genuinely shifted between eras (e.g.
# "121-150 Day" vs "123-152 Days") are NOT merged -- they're different tenors.
#
# "Monetary Policy Rate" backfills the existing "mpr" indicator directly:
# confirmed no date collision with its current 2020-2025 data (this source
# covers 2007-2020), and the one near-boundary value (2020-05-28, 12.5)
# matches the existing month-snapped equivalent (2020-05-01, 12.5) exactly.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllDiscountRates"

# Raw CBN `ratetype` string -> canonical npedata indicator_id.
RATE_TYPE_MAP = {
    "Monetary Policy Rate": "mpr",
    "Standing Lending Rate": "cbn_standing_lending_rate",
    "Standing LendingRate": "cbn_standing_lending_rate",
    "Standing Deposit Rate": "cbn_standing_deposit_rate",
    "Min. Rediscount": "cbn_min_rediscount_rate",
    "Re-Purchase": "cbn_repurchase_rate",
    "Reverse Rate": "cbn_reverse_repo_rate",
    "1-7 Day": "cbn_repo_rate_1_7d", "1-7 Days": "cbn_repo_rate_1_7d",
    "8-30 Day": "cbn_repo_rate_8_30d",
    "8-32 Days": "cbn_repo_rate_8_32d",
    "31-60 Day": "cbn_repo_rate_31_60d",
    "33-62 Days": "cbn_repo_rate_33_62d",
    "61-90 Day": "cbn_repo_rate_61_90d",
    "63-92 Days": "cbn_repo_rate_63_92d",
    "91-120 Day": "cbn_repo_rate_91_120d",
    "93-122 Days": "cbn_repo_rate_93_122d",
    "91-180 Day": "cbn_repo_rate_91_180d",
    "121-150 Day": "cbn_repo_rate_121_150d",
    "123-152 Days": "cbn_repo_rate_123_152d",
    "151-181 Day": "cbn_repo_rate_151_181d",
    "153-182 Days": "cbn_repo_rate_153_182d",
    "183-212 Days": "cbn_repo_rate_183_212d",
    "213-242 Days": "cbn_repo_rate_213_242d",
    "243-272 Days": "cbn_repo_rate_243_272d",
    "273-302 Days": "cbn_repo_rate_273_302d",
    "303-332 Days": "cbn_repo_rate_303_332d",
    "333-363 Days": "cbn_repo_rate_333_363d",
}


class CBNDiscountWindowConnector(Connector):
    name = "cbn_discount_window"
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
            indicator_id = RATE_TYPE_MAP.get(row.get("ratetype"))
            if indicator_id is None:
                continue  # an unmapped ratetype (e.g. a new one CBN adds later) -- skip, don't guess
            amount = row.get("amount")
            if amount is None:
                continue
            obs_date = datetime.datetime.strptime(row["ratedate"], "%d/%m/%Y").date().isoformat()
            yield {
                "indicator_id": indicator_id,
                "obs_date": obs_date,
                "value": float(amount),
                "source": self.source_label,
            }
