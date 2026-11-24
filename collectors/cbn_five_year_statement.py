# NPEDATA - CBN Five Year Financial Statements connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/rates/5YearBalanceSheet.html,
# GetAllFiveYearStatement, 41 rows, 1972-2012) plus its sibling
# (/rates/5YearBalanceSheet71e.html, GetAllFiveYearStatementPre1972, 11
# rows, 1960-1971) -- together CBN's complete audited balance sheet +
# income statement since its founding, through 2012 (frozen by CBN
# itself since -- confirmed both endpoints' own final entries stop at
# 2012, not a scraping gap). Zero bad values, zero duplicate years in
# either endpoint.
#
# 35 raw fields; "appro" is excluded -- not displayed anywhere on CBN's
# own page (its JS skips it when slicing fields into display tables) and
# blank in all 52 rows across both endpoints.
#
# 5 of the other 34 fields already exist as platform ids (confirmed same
# source via exact value match, all frozen at 2012-12-31 with no active
# connector): cbn_annual_total_assets, cbn_annual_ext_reserve,
# cbn_annual_cin_c, cbn_annual_surplus, cbn_annual_total_income.
#
# Two distinct "total liabilities"-style concepts: subLia (labeled
# "Total Liabilities" -- a balance-sheet subtotal, liabilities only) vs
# totalLia (labeled "Total Liabilities & Equity" -- the grand total,
# parallel to totalAss). Different figures, different ids.
#
# Blanks are genuine historical gaps (e.g. holdingsSDR blank in all 11
# pre-1972 rows -- SDRs didn't apply to CBN's books until later) --
# skipped per-field, not per-row.

from __future__ import annotations

import datetime
import json
import urllib.request

from .base import Connector

URL_MAIN = "https://www.cbn.gov.ng/api/GetAllFiveYearStatement"
URL_PRE1972 = "https://www.cbn.gov.ng/api/GetAllFiveYearStatementPre1972"

FIELD_MAP = {
    "extReserve": "cbn_annual_ext_reserve",
    "holdingsSDR": "cbn_annual_sdr_holdings",
    "fedGovtSec": "cbn_annual_fed_govt_securities",
    "rediscount": "cbn_annual_rediscount_advances",
    "otherAss": "cbn_annual_other_assets",
    "otherSec": "cbn_annual_other_securities",
    "exDiff": "cbn_annual_exchange_diff_promissory_notes",
    "fixedAss": "cbn_annual_fixed_assets",
    "totalAss": "cbn_annual_total_assets",
    "deposit": "cbn_annual_deposits",
    "cbnInst": "cbn_annual_instruments_issued",
    "cinC": "cbn_annual_cin_c",
    "imfsdr": "cbn_annual_imf_sdr_allocation",
    "tradeDebt": "cbn_annual_trade_debt_promissory_notes",
    "otherFore": "cbn_annual_other_foreign_currency_liabilities",
    "otherLia": "cbn_annual_other_financial_liabilities",
    "subLia": "cbn_annual_liabilities_subtotal",
    "shareCap": "cbn_annual_share_capital",
    "genReserve": "cbn_annual_general_reserve_fund",
    "assetsRev": "cbn_annual_assets_revaluation_reserve",
    "foreignC": "cbn_annual_currency_revaluation_reserve",
    "resFundInv": "cbn_annual_reserve_fund_inv_manager",
    "subCapRes": "cbn_annual_total_capital_reserves",
    "totalLia": "cbn_annual_total_liabilities_equity",
    "contingent": "cbn_annual_contingent_liabilities",
    "totalIncome": "cbn_annual_total_income",
    "provisionforDebt": "cbn_annual_provision_bad_debt",
    "operatnExp": "cbn_annual_operating_expenses",
    "provision": "cbn_annual_provisions_net",
    "exceptional": "cbn_annual_exceptional_items",
    "surplus": "cbn_annual_surplus",
    "transfer": "cbn_annual_transfer_general_reserve",
    "surplusFGN": "cbn_annual_surplus_to_fgn",
    "totalAppro": "cbn_annual_total_appropriation",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNFiveYearStatementConnector(Connector):
    name = "cbn_five_year_statement"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        for url in (URL_MAIN, URL_PRE1972):
            for row in _get(url):
                obs_date = datetime.datetime.strptime(row["date"], "%d %B, %Y").date().isoformat()
                for field, indicator_id in FIELD_MAP.items():
                    raw = row.get(field)
                    if raw is None or str(raw).strip() == "":
                        continue
                    try:
                        value = float(str(raw).replace(",", "."))
                    except ValueError:
                        continue
                    yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "CBN"}
