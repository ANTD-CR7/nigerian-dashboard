# NPEDATA - CBN government securities connectors (live, public JSON endpoints, no key required).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's homepage ticker (/rates/GovtSecurities.html) rather than
# assuming what existed. This data is structurally different from every
# other connector in this package: auction records with a `tenor` field,
# not a simple one-value-per-date series, and CBN's own data has real
# messiness that must be handled explicitly:
#
# - NTB tenor strings have ~30 spelling variants of just 3 real tenors
#   (91/182/364-day): "91", "91DAY", "91 DAY", "91Day", etc. Normalized by
#   extracting the leading number and snapping to the nearest standard
#   bucket within a small tolerance (CBN's own near-misses like 90/363/365
#   are clearly the same tenor, not different ones).
# - GetAllSecuritiesFGNBond is contaminated with OMO auction rows (bare
#   numeric tenor, e.g. "49", auction type "OMO") mixed in alongside real
#   bond auctions ("10 Year", "10YEAR", "10-Year", etc.). Requiring the
#   tenor string to explicitly contain "year" cleanly excludes every
#   contaminated row without checking the `auction` field separately.
# - Both endpoints report up to 3 rows per (date, tenor) under different
#   rateDescription conventions (Issue / Maginal [CBN's own typo for
#   Marginal] / Slop-Stop) -- not duplicates, but three different rate
#   conventions for the same auction. Filtered to "Issue" only, the
#   dominant and standard convention, since using all three would silently
#   overwrite one auction's result with another's under the same date.
#
# OMO is deliberately excluded entirely: its tenor field is a continuous
# day-count (594 distinct values across 2,435 rows, genuinely one-off per
# auction), not a small set of standard buckets -- doesn't fit this
# project's one-series-per-concept model without inventing arbitrary
# bucket boundaries. CBN Bills are also excluded: only 10 rows total,
# last active 2003, effectively dead.

from __future__ import annotations

import datetime
import json
import re
import urllib.request

from .base import Connector

NTB_URL = "https://www.cbn.gov.ng/api/GetAllSecuritiesNTB"
FGN_BOND_URL = "https://www.cbn.gov.ng/api/GetAllSecuritiesFGNBond"

NTB_TENOR_BUCKETS = {91: "cbn_ntb_91d", 182: "cbn_ntb_182d", 364: "cbn_ntb_364d"}
FGN_BOND_TENOR_BUCKETS = {
    5: "cbn_fgn_bond_5y", 7: "cbn_fgn_bond_7y", 10: "cbn_fgn_bond_10y",
    15: "cbn_fgn_bond_15y", 20: "cbn_fgn_bond_20y", 25: "cbn_fgn_bond_25y",
    30: "cbn_fgn_bond_30y",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _auction_obs_date(auction_date_str):
    return datetime.datetime.strptime(auction_date_str, "%B-%d-%Y").date().isoformat()


def _nearest_bucket(n, buckets):
    """Snap a parsed tenor number to the nearest standard bucket, within a
    tolerance -- CBN's own data has near-misses (90 vs 91, 363/365 vs 364)
    that are clearly the same tenor, not genuinely different ones."""
    closest = min(buckets, key=lambda b: abs(b - n))
    return closest if abs(closest - n) <= 2 else None


class CBNNTBConnector(Connector):
    name = "cbn_ntb"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(NTB_URL):
            if row.get("rateDescription") != "Issue":
                continue
            m = re.match(r"\s*(\d+)", row.get("tenor", ""))
            if not m:
                continue
            bucket = _nearest_bucket(int(m.group(1)), NTB_TENOR_BUCKETS)
            if bucket is None:
                continue
            rate = row.get("rate")
            if not rate or float(rate) == 0.0:
                continue
            yield {
                "indicator_id": NTB_TENOR_BUCKETS[bucket],
                "obs_date": _auction_obs_date(row["auctionDate"]),
                "value": float(rate),
                "source": "CBN",
            }


class CBNFGNBondConnector(Connector):
    name = "cbn_fgn_bond"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(FGN_BOND_URL):
            tenor_str = row.get("tenor", "")
            if not re.search(r"year", tenor_str, re.I):
                continue
            if row.get("rateDescription") != "Issue":
                continue
            m = re.match(r"\s*(\d+)", tenor_str)
            if not m:
                continue
            bucket = _nearest_bucket(int(m.group(1)), FGN_BOND_TENOR_BUCKETS)
            if bucket is None:
                continue
            rate = row.get("rate")
            if not rate or float(rate) == 0.0:
                continue
            yield {
                "indicator_id": FGN_BOND_TENOR_BUCKETS[bucket],
                "obs_date": _auction_obs_date(row["auctionDate"]),
                "value": float(rate),
                "source": "CBN",
            }
