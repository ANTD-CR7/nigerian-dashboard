# NPEDATA - CBN Financial Data connector (live, public JSON endpoint).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/rates/FinancialData.html). This is CBN's
# daily banking-system liquidity report -- net Naira flows in/out of the
# banking system each day (opening balances, standing facilities, repo/OMO
# activity, statutory allocations, clearing, NDIC premium, etc.), not
# tracked anywhere else on the platform. Field names below come from the
# page's own Kendo grid series definitions (human-readable names embedded
# in the page's JS), not guessed from the raw field codes.
#
# Deliberately suffixed _flow/_sales/_repayment to avoid colliding with the
# existing *rate* series for related concepts (cbn_standing_lending_rate,
# cbn_repurchase_rate, cbn_reverse_repo_rate): those are policy rates, these
# are net flow amounts -- a different measurement, not a duplicate.
#
# GetAllFinancialData is clean -- verified zero blanks and zero unparseable
# values across all 17 numeric fields over 3,700 rows. 50 rows share an
# exact date with another row; normalize()'s existing last-write-wins
# dedup on (indicator_id, obs_date) handles this the same way it handles
# every other connector's duplicate rows. Dates are "DD/MM/YYYY" -- a
# third CBN date format seen this session, alongside ISO and
# "Month-DD-YYYY".

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllFinancialData"

FIELD_MAP = {
    "opeBal": "cbn_banks_opening_balance",
    "rediscBills": "cbn_rediscounted_bills",
    "slFacility": "cbn_standing_lending_facility_flow",
    "sdFacility": "cbn_standing_deposit_facility_flow",
    "repo": "cbn_repo_flow",
    "revRepo": "cbn_reverse_repo_flow",
    "omoSales": "cbn_omo_sales",
    "omoRepay": "cbn_omo_repayment",
    "pmSales": "cbn_primary_market_sales",
    "pmRepay": "cbn_primary_market_repayment",
    "crr": "cbn_crr_flow",
    "netWdas": "cbn_net_wdas",
    "statAlloc": "cbn_statutory_allocations",
    "jvCash": "cbn_jv_cash_call",
    "netClr": "cbn_net_clearing",
    "ndicPrem": "cbn_ndic_premium",
    "oMajor": "cbn_other_major_flow",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNFinancialDataConnector(Connector):
    name = "cbn_financial_data"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            obs_date = datetime.datetime.strptime(row["recDate"], "%d/%m/%Y").date().isoformat()
            for field, indicator_id in FIELD_MAP.items():
                raw = row.get(field)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    value = float(str(raw).replace(",", "."))
                except ValueError:
                    continue
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "CBN"}
