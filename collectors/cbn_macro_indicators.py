# NPEDATA - CBN macro indicators connectors (live, public JSON endpoints, no key required).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# CBN's "Economic/Macro Indicators" page bundles several endpoints. Two are
# usable time series here; two others (GetSecurities_NTB_TOP,
# GetTopInterbankCallRate) only ever return the single latest row -- no
# history, out of scope for this project's time-series model. A third,
# GetAllInflationRates, was investigated and dropped entirely: every one of
# its 8 fields turned out to duplicate an indicator already in the live
# `indicators` table under NBS source (inflation_avg, inflation_core,
# inflation_core_avg, inflation_core_energy, inflation_core_energy_avg,
# inflation_food, inflation_food_avg) -- confirmed exact value matches, not
# just similar names. The lesson that caused this: checking a new field
# against `main.py`'s INDICATORS dict (which only lists indicators actually
# reachable through the analytics endpoints) is not the same as checking
# the full live `indicators` table, which holds ~155+ rows including many
# from the original seed data never added to that dict.
#
# Each field map below excludes fields confirmed live to duplicate an
# existing indicator, or deliberately excluded for a documented reason --
# see the comment above each map.

from __future__ import annotations

import json
import urllib.request

from .base import Connector

MONEY_CREDIT_URL = "https://www.cbn.gov.ng/api/GetAllMoneyAndCreditStats"
MONEY_MARKET_URL = "https://www.cbn.gov.ng/api/GetAllMoneyMarketIndicators"

# currencyInCirculation deliberately excluded -- exact duplicate of the
# existing "currency_circulation_full" indicator, confirmed live.
MONEY_CREDIT_FIELDS = {
    "moneySupply_M3": "cbn_money_supply_m3",
    "cbnBills": "cbn_bills_outstanding",
    "moneySupply_M2": "cbn_money_supply_m2",
    "quasiMoney": "cbn_quasi_money",
    "narrowMoney": "cbn_narrow_money",
    "currencyOutsideBanks": "cbn_currency_outside_banks",
    "demandDeposits": "cbn_demand_deposits",
    "netForeignAssets": "cbn_net_foreign_assets",
    "netDomesticAssets": "cbn_net_domestic_assets",
    "netDomesticCredit": "cbn_net_domestic_credit",
    "creditToGovernment": "cbn_credit_to_government",
    "creditToGovernmentFed": "cbn_credit_to_government_federal",
    "mirrorAccounts": "cbn_mirror_accounts",
    "creditToPrivateSector": "cbn_credit_to_private_sector",
    "otherAssetsNet": "cbn_other_assets_net",
    "baseMoney": "cbn_base_money",
    "bankReserves": "cbn_bank_reserves",
    "specialInterventionReserves": "cbn_special_intervention_reserves",
}

# mrr excluded (238/249 null -- cbn_min_rediscount_rate already covers this
# rate with far better coverage). mpr excluded deliberately, not just as a
# duplicate: this endpoint's monthly snapshot disagrees with the existing
# decision-dated mpr series (checked live, November 2025: 27.00 here vs
# 26.25 there) -- a different measurement convention, not safe to merge
# into one indicator_id.
MONEY_MARKET_FIELDS = {
    "interBankCallRate": "cbn_interbank_call_rate",
    "treasuryBill": "cbn_treasury_bill_rate",
    "savingsDeposit": "cbn_savings_deposit_rate",
    "oneMonthDeposit": "cbn_deposit_rate_1m",
    "threeMonthsDeposit": "cbn_deposit_rate_3m",
    "sixMonthsDeposit": "cbn_deposit_rate_6m",
    "twelveMonthsDeposit": "cbn_deposit_rate_12m",
    "primeLending": "cbn_prime_lending_rate",
    "maxLending": "cbn_max_lending_rate",
}


def _monthly_obs_date(row):
    return f"{int(row['tyear']):04d}-{int(row['tmonth']):02d}-01"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_field_mapped(rows, field_map, obs_date_fn):
    for row in rows:
        obs_date = obs_date_fn(row)
        for field, indicator_id in field_map.items():
            value = row.get(field)
            if value in (None, ""):
                continue
            yield {
                "indicator_id": indicator_id,
                "obs_date": obs_date,
                "value": float(value),
                "source": "CBN",
            }


class CBNMoneyAndCreditConnector(Connector):
    """CBN reuses tmonth to hold the year again (tmonth == tyear) for 33
    annual-only historical rows (1960-1992) -- treated as annual, using the
    `-12-31` convention this dataset's other annual CBN series already use
    (e.g. cbn_annual_total_assets), not naively parsed as a month."""
    name = "cbn_money_and_credit"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        def _obs_date(row):
            tmonth = int(row["tmonth"])
            if 1 <= tmonth <= 12:
                return f"{int(row['tyear']):04d}-{tmonth:02d}-01"
            return f"{int(row['tyear']):04d}-12-31"
        yield from _fetch_field_mapped(_get(MONEY_CREDIT_URL), MONEY_CREDIT_FIELDS, _obs_date)


class CBNMoneyMarketConnector(Connector):
    name = "cbn_money_market"
    source_label = "CBN"

    def fetch(self, start_year: int = 2015):
        yield from _fetch_field_mapped(_get(MONEY_MARKET_URL), MONEY_MARKET_FIELDS, _monthly_obs_date)
