# NPEDATA - CBN International Payments connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/IntOps/payments.html, GetAllIntPayments,
# 376 rows, monthly, 2003-10-12 to today). 4 fields confirmed via the
# page's own Kendo series labels: loc (Letters of Credit), remit (Total
# Direct Remittances), debt (Debt Service/Payments), total (Total).
#
# Investigated total's relationship to the other 3 before assuming it's
# a simple sum: in recent data (2025-2026), total == loc + remit + debt
# exactly (ratio 1.0), but in older data (2003-2006) the ratio varies
# wildly (2x-13x) -- CBN's own definition of "total" clearly broadened/
# narrowed over the dataset's history, not a bug. No identity-based
# correction is applied (unlike cbn_nominal_gdp.py/cbn_real_gdp.py):
# there's no fixed accounting rule to validate against across the whole
# series, so all 4 fields are captured as independently-reported values.
#
# One real data-quality issue: 12 rows (all in 2021) have total == 0
# exactly while loc/remit/debt are substantial and nonzero that same
# month -- a genuine reporting gap, not a true zero. Confirmed this
# isn't a blanket "0 means missing" situation: loc/remit/debt are each
# legitimately zero in some rows (13/2/58 respectively -- most plausibly
# genuine "no debt service due that month" etc.) and are NOT dropped for
# being zero. Only total == 0 while its own components are nonzero is
# implausible and treated as missing.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllIntPayments"

FIELD_MAP = {
    "loc": "cbn_letters_of_credit",
    "remit": "cbn_total_direct_remittances",
    "debt": "cbn_debt_service_payments",
    "total": "cbn_int_payments_total",
}


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


class CBNIntPaymentsConnector(Connector):
    name = "cbn_int_payments"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            obs_date = datetime.datetime.strptime(row["payDate"], "%d/%m/%Y").date().isoformat()
            values = {f: _num(row.get(f)) for f in ("loc", "remit", "debt", "total")}
            skip_total = values["total"] == 0.0 and any(
                v not in (None, 0.0) for k, v in values.items() if k != "total"
            )
            for field, indicator_id in FIELD_MAP.items():
                if field == "total" and skip_total:
                    continue
                value = values[field]
                if value is None:
                    continue
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "CBN"}
