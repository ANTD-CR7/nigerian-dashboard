# NPEDATA - CBN Nigerian Overnight Financing Rate connector (live, public JSON endpoint).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's homepage ticker (/rates/NOF_Rates.html). Kept in its own
# file rather than bundled with cbn_securities.py: different source page,
# no tenor complexity, matches the "group by source page" convention
# already used for the oil/discount-window connectors.
#
# NOFR is a genuinely new CBN rate -- only ~18 days of history exist at the
# time this connector was written, so it will correctly show the Rater's
# insufficient_history refusal today. That's expected, not a bug: it
# accumulates daily and will clear the 30-minimum threshold naturally
# within a few weeks.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

NOFR_URL = "https://www.cbn.gov.ng/api/GetAllNOF_RatesGRAPH"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNNOFRConnector(Connector):
    name = "cbn_nofr"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for row in _get(NOFR_URL):
            value = row.get("nofr")
            if not value:
                continue
            obs_date = datetime.datetime.strptime(row["ratedate"], "%B-%d-%Y").date().isoformat()
            yield {"indicator_id": "cbn_nofr", "obs_date": obs_date, "value": float(value), "source": "CBN"}
