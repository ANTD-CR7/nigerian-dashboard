# NPEDATA - CBN OMO (Open Market Operations) auctions connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's Government Securities pages (GovtSecurities.html /
# GovtSecuritiesDrillDown.html), which list exactly 4 instrument types:
# NTB and FGN Bond (already built), CBN Bill (10 rows total, 2001-2003,
# genuinely dead -- excluded), and OMO -- previously assumed negligible,
# which turned out wrong: 2,435 rows, 2002-01-04 to today.
#
# OMO's tenor field is NOT like NTB's clean 91/182/364-day structure: 594
# distinct raw labels, and even after extracting the numeric day-count,
# 299 distinct values spread continuously across 7-370+ days with no
# small natural cluster. A fixed-bucket scheme would either explode into
# hundreds of near-empty series or arbitrarily discard most of the data.
# So this aggregates PER AUCTION DATE across whatever tenors were offered
# that day, rather than one series per tenor -- loses tenor granularity
# but gives a clean, analyzable OMO activity signal. This is auction-level
# detail (rates, subscription, offered amounts), genuinely complementary
# to -- not a duplicate of -- the cbn_omo_sales/cbn_omo_repayment daily
# *flow* fields already built from CBN's Financial Data feed (a different
# source, a different angle).
#
# Filtered to rateDescription == "Issue" (same precedent as NTB/FGN Bond,
# avoids Marginal/Slop/Stop/"Issue Rates" duplicate rows): 2,136 of 2,435
# rows, spanning 1,202 distinct auction dates (~1.78 tenors/date on
# average -- aggregation is meaningful, not degenerate).
#
# Numeric fields are clean -- zero unparseable values. Some are blank
# (amtOffered 454/2136, totalAmtRepaid 48, netValue 42) -- treated as a 0
# contribution to that date's sum (that tenor didn't offer this amount
# that day), not as corrupted data. rate is 0.0000 for 124/2136 rows
# (~5.8%) vs genuine values like 17.4400 for the rest -- 0 isn't a
# plausible real OMO rate, so it's excluded from the per-date average
# rather than dragging it toward zero.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllSecuritiesOMO"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _num(raw):
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(str(raw).replace(",", "."))
    except ValueError:
        return None


class CBNOMOConnector(Connector):
    name = "cbn_omo"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        by_date: dict = {}
        for row in _get(URL):
            if row.get("rateDescription") != "Issue":
                continue
            obs_date = datetime.datetime.strptime(row["auctionDate"], "%B-%d-%Y").date().isoformat()
            acc = by_date.setdefault(obs_date, {
                "subscription": 0.0, "successful": 0.0, "offered": 0.0,
                "repaid": 0.0, "net_value": 0.0, "rates": [],
            })
            acc["subscription"] += _num(row.get("totalSubscription")) or 0.0
            acc["successful"] += _num(row.get("totalSuccessful")) or 0.0
            acc["offered"] += _num(row.get("amtOffered")) or 0.0
            acc["repaid"] += _num(row.get("totalAmtRepaid")) or 0.0
            acc["net_value"] += _num(row.get("netValue")) or 0.0
            rate = _num(row.get("rate"))
            if rate:  # excludes both None and 0.0 -- 0 isn't a real OMO rate
                acc["rates"].append(rate)

        for obs_date, acc in by_date.items():
            yield {"indicator_id": "cbn_omo_total_subscription", "obs_date": obs_date, "value": acc["subscription"], "source": "CBN"}
            yield {"indicator_id": "cbn_omo_total_successful", "obs_date": obs_date, "value": acc["successful"], "source": "CBN"}
            yield {"indicator_id": "cbn_omo_amt_offered", "obs_date": obs_date, "value": acc["offered"], "source": "CBN"}
            yield {"indicator_id": "cbn_omo_total_repaid", "obs_date": obs_date, "value": acc["repaid"], "source": "CBN"}
            yield {"indicator_id": "cbn_omo_net_value", "obs_date": obs_date, "value": acc["net_value"], "source": "CBN"}
            if acc["rates"]:
                yield {"indicator_id": "cbn_omo_rate_avg", "obs_date": obs_date, "value": sum(acc["rates"]) / len(acc["rates"]), "source": "CBN"}
