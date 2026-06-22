"""
Nigerian Public Economic Data Aggregation and Analytics Platform
Open API v1.0 — FastAPI + Supabase
Docs: /docs
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from typing import Optional
import statistics

app = FastAPI(
    title="Nigerian Public Economic Data API",
    description="""
## Nigeria's First Free Open Economic Data API

Aggregates 13,535+ records across 122 indicators from **CBN**, **NBS**, and **World Bank**.

### No authentication required. No rate limits. No payment.

Built as Final Year Project — Caleb University Lagos — Computer Science 2026.
    """,
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SUPABASE_URL = "https://fjsytcmcxapfbrwvawmu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqc3l0Y21jeGFwZmJyd3Zhd211Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4OTcxOTgsImV4cCI6MjA5MTQ3MzE5OH0.0lGkBdBsY7bQGu4jlHQA0MKm54dd51QwJTdeill_ADw"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch(indicator_id: str, start: str = "2020-01-01", end: str = "2026-12-31"):
    res = (
        supabase.table("observations")
        .select("obs_date,value,source")
        .eq("indicator_id", indicator_id)
        .gte("obs_date", start)
        .lte("obs_date", end)
        .order("obs_date")
        .execute()
    )
    return res.data


def latest(indicator_id: str):
    res = (
        supabase.table("observations")
        .select("obs_date,value,source")
        .eq("indicator_id", indicator_id)
        .order("obs_date", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def fetch_multi(ids: list, start: str, end: str):
    return {ind_id: fetch(ind_id, start, end) for ind_id in ids}


@app.get("/", tags=["Info"])
@app.head("/")
def root():
    return {
        "name": "Nigerian Public Economic Data API",
        "version": "1.0.0",
        "description": "Nigeria's first free open economic data API. No authentication required.",
        "docs": "/docs",
        "dashboard": "https://antd-cr7.github.io/nigerian-dashboard",
        "source_code": "https://github.com/ANTD-CR7/nigerian-dashboard",
        "endpoints": [
            "/api/v1/summary",
            "/api/v1/gdp",
            "/api/v1/inflation",
            "/api/v1/exchange-rate",
            "/api/v1/interest-rate",
            "/api/v1/fx-reserves",
            "/api/v1/currency-circulation",
            "/api/v1/nfem",
            "/api/v1/multicurrency",
            "/api/v1/gdp-sectors",
            "/api/v1/cbn-balance-sheet",
            "/api/v1/analytics",
        ]
    }


@app.get("/api/v1/summary", tags=["Dashboard"])
def get_summary():
    """Returns the latest value for all five headline indicators."""
    return {
        "gdp_growth":    latest("gdp_growth"),
        "inflation":     latest("inflation"),
        "exchange_rate": latest("exchange_rate"),
        "mpr":           latest("mpr"),
        "fx_reserves":   latest("fx_reserves"),
        "source":        "CBN, NBS, World Bank",
    }


@app.get("/api/v1/gdp", tags=["Economy"])
def get_gdp(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """Quarterly real GDP growth rate and annual nominal GDP in USD billions."""
    return {
        "gdp_growth": fetch("gdp_growth", start, end),
        "gdp_usd":    fetch("gdp_usd",    start, end),
        "units": {"gdp_growth": "Percent (%)", "gdp_usd": "USD Billions"},
        "frequency": "Quarterly (growth), Annual (USD)",
        "source":    "NBS (growth), World Bank (USD)"
    }


@app.get("/api/v1/inflation", tags=["Economy"])
def get_inflation(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """Monthly headline, food, and core inflation rates from NBS."""
    return {
        "headline":  fetch("inflation",       start, end),
        "food":      fetch("inflation_food",  start, end),
        "core":      fetch("inflation_core",  start, end),
        "unit":      "Percent (%) year-on-year",
        "frequency": "Monthly",
        "source":    "NBS Consumer Price Index Report"
    }


@app.get("/api/v1/exchange-rate", tags=["Currency"])
def get_exchange_rate(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """Monthly average official NGN/USD exchange rate from CBN."""
    return {
        "data":      fetch("exchange_rate", start, end),
        "unit":      "Naira per 1 US Dollar",
        "frequency": "Monthly average",
        "source":    "CBN Official Rate",
        "note":      "June 2023 FX unification reform caused a major step-change in this series."
    }


@app.get("/api/v1/interest-rate", tags=["Economy"])
def get_interest_rate(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """CBN Monetary Policy Rate decisions from the MPC."""
    return {
        "data":      fetch("mpr", start, end),
        "unit":      "Percent (%)",
        "frequency": "As decided by CBN Monetary Policy Committee",
        "source":    "Central Bank of Nigeria",
        "note":      "MPR rose from 11.5% in 2022 to 27.5% by 2024 as CBN fought inflation."
    }


@app.get("/api/v1/fx-reserves", tags=["CBN Data"])
def get_fx_reserves(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """Nigeria gross, liquid, and blocked foreign exchange reserves."""
    return {
        "gross":     fetch("fx_reserves",        start, end),
        "liquid":    fetch("reserves_liquid",    start, end),
        "blocked":   fetch("reserves_blocked",   start, end),
        "block_pct": fetch("reserves_block_pct", start, end),
        "unit":      "USD Billions",
        "frequency": "Monthly",
        "source":    "Central Bank of Nigeria"
    }


@app.get("/api/v1/currency-circulation", tags=["CBN Data"])
def get_currency_circulation(
    start: Optional[str] = Query(default="2002-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """Total Naira currency in circulation from 2002 to 2024."""
    return {
        "data":      fetch("currency_circulation_full", start, end),
        "unit":      "Naira Billions",
        "frequency": "Monthly",
        "source":    "CBN Statistical Bulletin"
    }


@app.get("/api/v1/nfem", tags=["Currency"])
def get_nfem(
    start: Optional[str] = Query(default="2024-12-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """Daily Nigerian Foreign Exchange Market rates."""
    return {
        "closing":         fetch("nfem_closing",        start, end),
        "highest":         fetch("nfem_highest",        start, end),
        "lowest":          fetch("nfem_lowest",         start, end),
        "weighted_avg":    fetch("nfem_weighted_avg",   start, end),
        "simple_avg":      fetch("nfem_simple_avg",     start, end),
        "deals":           fetch("nfem_deals",          start, end),
        "interbank_deals": fetch("nfem_interbank_deals",start, end),
        "unit":            "NGN per USD",
        "frequency":       "Daily trading days",
        "source":          "CBN NFEM Market Data",
        "coverage":        "December 2024 to April 2026"
    }


@app.get("/api/v1/multicurrency", tags=["Currency"])
def get_multicurrency(
    currency: Optional[str] = Query(default=None, description="Filter: usd, gbp, eur, cny, jpy, chf, zar, aed, sar"),
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """CBN buying, central, and selling rates for 12 currencies."""
    currencies = ["usd","gbp","eur","cny","jpy","chf","zar","aed","sar","sdr","cfa","waua"]
    if currency and currency.lower() in currencies:
        currencies = [currency.lower()]
    result = {}
    for c in currencies:
        result[c] = {
            "buying":  fetch(f"{c}_buying",  start, end),
            "central": fetch(f"{c}_central", start, end),
            "selling": fetch(f"{c}_selling", start, end),
        }
    return {
        "data":      result,
        "unit":      "Naira per foreign currency unit",
        "frequency": "Monthly average",
        "source":    "CBN Foreign Exchange Rates"
    }


@app.get("/api/v1/gdp-sectors", tags=["Economy"])
def get_gdp_sectors(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """Real GDP by sector — Agriculture, Industry, Services and sub-sectors."""
    sectors = [
        "gdp_agriculture","gdp_industry","gdp_services",
        "gdp_manufacturing","gdp_telecoms","gdp_construction","gdp_trade"
    ]
    return {
        "data":      fetch_multi(sectors, start, end),
        "unit":      "Naira Billions (constant basic prices)",
        "frequency": "Quarterly",
        "source":    "NBS GDP Report"
    }


@app.get("/api/v1/cbn-balance-sheet", tags=["CBN Data"])
def get_cbn_balance_sheet(
    start: Optional[str] = Query(default="2005-01-01"),
    end:   Optional[str] = Query(default="2026-12-31")
):
    """CBN Assets and Liabilities from the CBN balance sheet."""
    return {
        "total_assets":      fetch("cbn_total_assets",      start, end),
        "total_liabilities": fetch("cbn_total_liabilities", start, end),
        "gold":              fetch("cbn_gold",              start, end),
        "currency_issued":   fetch("cbn_currency_issued",   start, end),
        "govt_deposits":     fetch("cbn_govt_deposits",     start, end),
        "bankers_deposits":  fetch("cbn_bankers_deposits",  start, end),
        "unit":      "Naira Billions",
        "frequency": "Monthly",
        "source":    "CBN Assets and Liabilities Statement",
        "coverage":  "2005 to 2023"
    }


@app.get("/api/v1/analytics", tags=["Analytics"])
def get_analytics():
    """
    Pearson correlation between inflation and exchange rate.
    Confirms the June 2023 FX reform as the primary driver
    of Nigeria's 2023-2024 inflation surge.
    """
    inf_data = fetch("inflation",     "2020-01-01", "2026-12-31")
    fx_data  = fetch("exchange_rate", "2020-01-01", "2026-12-31")

    inf_map = {d["obs_date"]: d["value"] for d in inf_data}
    fx_map  = {d["obs_date"]: d["value"] for d in fx_data}
    common  = sorted(set(inf_map) & set(fx_map))

    inf_vals = [inf_map[d] for d in common]
    fx_vals  = [fx_map[d]  for d in common]

    r = 0.0
    if len(common) > 1:
        mean_i = statistics.mean(inf_vals)
        mean_f = statistics.mean(fx_vals)
        num = sum((a - mean_i) * (b - mean_f) for a, b in zip(inf_vals, fx_vals))
        den = (sum((a - mean_i)**2 for a in inf_vals) * sum((b - mean_f)**2 for b in fx_vals)) ** 0.5
        r = round(num / den, 4) if den else 0.0

    return {
        "pearson_correlation": {
            "r": r,
            "interpretation": "Very strong positive" if r > 0.9 else "Strong" if r > 0.7 else "Moderate",
            "variables": ["headline_inflation", "ngn_usd_exchange_rate"],
            "period": f"{common[0]} to {common[-1]}" if common else "N/A",
            "n": len(common),
            "conclusion": f"r = {r} confirms the June 2023 CBN FX unification reform is the primary driver of Nigeria's 2023-2024 inflation surge."
        },
        "headline_figures": {
            "inflation_peak":       {"value": max(inf_vals), "date": common[inf_vals.index(max(inf_vals))]},
            "inflation_latest":     {"value": inf_vals[-1],  "date": common[-1]},
            "exchange_rate_peak":   {"value": max(fx_vals),  "date": common[fx_vals.index(max(fx_vals))]},
            "exchange_rate_latest": {"value": fx_vals[-1],   "date": common[-1]},
        },
        "source": "CBN, NBS — computed by NPEDATA Analytics Layer"
    }
