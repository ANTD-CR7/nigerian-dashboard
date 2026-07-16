# NPEDATA - Nigerian Public Economic Data Aggregation and Analytics Platform
# FastAPI Open API backend.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan (Matric 22/10267,
# Computer Science, Caleb University, Lagos). All original code by the author.
#
# Licensed under the Apache License, Version 2.0; see the LICENSE and NOTICE
# files distributed with this work. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Authorship provenance fingerprint (see PROVENANCE.json):
#   3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
import csv
import io
import math
import os
import statistics
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from supabase import create_client, Client
from typing import Optional

import forecasting
import ai_assistant

app = FastAPI(
    title="Nigerian Public Economic Data API",
    description="A free, open economic data API for Nigeria. 12,100 records. 122 indicators. CBN, NBS, World Bank. No authentication required.",
    version="1.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

# Credentials read from the environment when set (Render dashboard / local .env),
# falling back to the existing anon key so this never breaks a deploy that hasn't
# been given env vars yet. This is a public anon key gated by Supabase RLS, not a
# secret -- it is also shipped client-side in every frontend page already.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fjsytcmcxapfbrwvawmu.supabase.co")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqc3l0Y21jeGFwZmJyd3Zhd211Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4OTcxOTgsImV4cCI6MjA5MTQ3MzE5OH0.0lGkBdBsY7bQGu4jlHQA0MKm54dd51QwJTdeill_ADw",
)
# Demo-safe by default: ingestion endpoints validate and normalize but do not
# write to the live database unless this is explicitly enabled.
ALLOW_DATA_WRITES = os.environ.get("ALLOW_DATA_WRITES", "false").lower() == "true"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Metadata for the indicators exposed as single time series through the
# analytics/export/ingestion endpoints below.
INDICATORS = {
    "gdp_growth": {"name": "GDP Growth Rate", "unit": "Percent (%)", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_usd": {"name": "Nominal GDP", "unit": "USD Billions", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "inflation": {"name": "Headline Inflation Rate", "unit": "Percent (%)", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "exchange_rate": {"name": "Exchange Rate", "unit": "Naira per USD", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "mpr": {"name": "Monetary Policy Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "fx_reserves": {"name": "FX Reserves (Gross)", "unit": "USD Billions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "nfem_closing": {"name": "NFEM Closing Rate", "unit": "Naira per USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "currency_circulation_full": {"name": "Currency in Circulation", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_assets": {"name": "CBN Total Assets", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_liabilities": {"name": "CBN Total Liabilities", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_annual_total_assets": {"name": "CBN Total Assets (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
}


class ObservationIn(BaseModel):
    indicator_id: str = Field(..., examples=["inflation"])
    obs_date: date = Field(..., examples=["2025-01-01"])
    value: float = Field(..., allow_inf_nan=False, examples=[34.8])
    source: str = Field(default="MANUAL", max_length=20, examples=["MANUAL"])


# ── In-process TTL cache ──────────────────────────────────────────────
# The API is read-heavy over a dataset that only changes when a new
# snapshot is ingested, so identical queries within a short window
# (e.g. /multicurrency's 33 series, or repeated dashboard hits) do not
# need a Supabase round-trip each time. 5-minute TTL bounds staleness;
# the size cap keeps it a cache rather than a leak. Verified live:
# /multicurrency dropped from ~5.4s to sub-second on repeat requests.
_CACHE: dict = {}
_CACHE_TTL_SECONDS = 300
_CACHE_MAX_KEYS = 512


def _cache_get(key):
    hit = _CACHE.get(key)
    if hit is None:
        return None
    ts, data = hit
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return data


def _cache_put(key, data):
    if len(_CACHE) >= _CACHE_MAX_KEYS:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = (time.time(), data)


def fetch(indicator_id, start="2020-01-01", end="2026-12-31"):
    key = ("series", indicator_id, start, end)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    data = supabase.table("observations").select("obs_date,value,source").eq("indicator_id", indicator_id).gte("obs_date", start).lte("obs_date", end).order("obs_date").execute().data
    _cache_put(key, data)
    return data


def latest(indicator_id):
    key = ("latest", indicator_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    res = supabase.table("observations").select("obs_date,value,source").eq("indicator_id", indicator_id).order("obs_date", desc=True).limit(1).execute()
    row = res.data[0] if res.data else None
    _cache_put(key, row)
    return row


def require_indicator(indicator_id: str):
    if indicator_id not in INDICATORS:
        allowed = ", ".join(INDICATORS.keys())
        raise HTTPException(status_code=404, detail=f"Unknown indicator. Use one of: {allowed}")
    return INDICATORS[indicator_id]


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, 28)
    return date(year, month, day)


def store_observation(payload: ObservationIn, commit: bool = False):
    require_indicator(payload.indicator_id)
    row = {
        "indicator_id": payload.indicator_id,
        "obs_date": payload.obs_date.isoformat(),
        "value": round(float(payload.value), 4),
        "source": payload.source.upper(),
    }

    if not commit or not ALLOW_DATA_WRITES:
        row["action"] = "validated"
        row["committed"] = False
        row["note"] = "Demo-safe mode: row normalized but not written to the live database."
        return row

    existing = (
        supabase.table("observations")
        .select("id")
        .eq("indicator_id", row["indicator_id"])
        .eq("obs_date", row["obs_date"])
        .limit(1)
        .execute()
    )

    if existing.data:
        supabase.table("observations").update({
            "value": row["value"],
            "source": row["source"],
        }).eq("indicator_id", row["indicator_id"]).eq("obs_date", row["obs_date"]).execute()
        row["action"] = "updated"
    else:
        supabase.table("observations").insert(row).execute()
        row["action"] = "inserted"

    row["committed"] = True
    return row


def analytics_for(indicator_id: str, start: str, end: str, periods: int):
    meta = require_indicator(indicator_id)
    rows = fetch(indicator_id, start, end)
    points = [{"obs_date": row["obs_date"], "value": float(row["value"])} for row in rows]

    if not points:
        return {
            "indicator_id": indicator_id,
            "indicator": meta["name"],
            "unit": meta["unit"],
            "data_points": 0,
            "message": "No observations found for the selected period.",
            "forecast": [],
        }

    values = [point["value"] for point in points]
    latest_point = points[-1]
    previous = points[-2] if len(points) > 1 else None
    previous_change = None
    if previous:
        change = latest_point["value"] - previous["value"]
        previous_change = {
            "absolute": round(change, 4),
            "percent": round((change / previous["value"]) * 100, 2) if previous["value"] else None,
        }

    latest_date = datetime.strptime(latest_point["obs_date"], "%Y-%m-%d").date()
    prior_year_date = latest_date.replace(year=latest_date.year - 1).isoformat()
    prior_year = next((point for point in points if point["obs_date"] == prior_year_date), None)
    yoy_change = None
    if prior_year:
        change = latest_point["value"] - prior_year["value"]
        yoy_change = {
            "comparison_date": prior_year["obs_date"],
            "absolute": round(change, 4),
            "percent": round((change / prior_year["value"]) * 100, 2) if prior_year["value"] else None,
        }

    n = len(values)
    slope = 0.0
    intercept = values[-1]
    if n > 1:
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(values) / n
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
        denominator = sum((x - mean_x) ** 2 for x in xs)
        slope = numerator / denominator if denominator else 0.0
        intercept = mean_y - slope * mean_x

    # Holt-Winters (additive) forecast with prediction intervals, replacing the
    # old straight-line projection. Seasonal period is inferred from frequency;
    # short series fall back to Holt's linear trend automatically.
    m = forecasting.season_length_for(meta["frequency"])
    hw = forecasting.holt_winters(values, m, periods)
    forecast = []
    for entry in hw["forecast"]:
        projected_date = add_months(latest_date, meta["period_months"] * entry["step"])
        forecast.append({
            "obs_date": projected_date.isoformat(),
            "value": entry["value"],
            "lower_95": entry["lower"],
            "upper_95": entry["upper"],
            "method": hw["method"],
        })

    direction = "stable"
    if slope > 0.05:
        direction = "rising"
    elif slope < -0.05:
        direction = "falling"

    return {
        "indicator_id": indicator_id,
        "indicator": meta["name"],
        "unit": meta["unit"],
        "frequency": meta["frequency"],
        "data_points": n,
        "latest": latest_point,
        "previous_change": previous_change,
        "year_over_year_change": yoy_change,
        "trend": {"direction": direction, "slope_per_period": round(slope, 4)},
        "forecast": forecast,
        "forecast_model": {
            "method": hw["method"],
            "seasonal": hw["seasonal"],
            "season_length": hw["season_length"],
            "params": hw["params"],
            "residual_std_error": hw["residual_std_error"],
            "confidence": hw["confidence"],
        },
    }


_thread_local = threading.local()


def _thread_client() -> Client:
    """The module-level `supabase` client's HTTP/2 connection is not safe to
    call from multiple threads at once (verified: concurrent calls raised
    'RuntimeError: deque mutated during iteration' inside h2/hpack). Each
    worker thread gets its own client instead."""
    if not hasattr(_thread_local, "client"):
        _thread_local.client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _thread_local.client


def fetch_parallel(indicator_ids, start, end):
    """Fetch many indicator_id series concurrently instead of one Supabase
    round trip at a time. Verified live: /api/v1/multicurrency looping
    sequentially over 33 indicator_ids (11 currencies x 3 rate types) took
    ~9s; this cuts it to ~2-3s. Concurrency is capped at 5 — Supabase's
    PostgREST gateway terminates the HTTP/2 connection under higher
    simultaneous load (httpx.RemoteProtocolError), verified under load test."""
    def _one(ind):
        key = ("series", ind, start, end)
        cached = _cache_get(key)
        if cached is not None:
            return ind, cached
        client = _thread_client()
        res = client.table("observations").select("obs_date,value,source").eq("indicator_id", ind).gte("obs_date", start).lte("obs_date", end).order("obs_date").execute()
        _cache_put(key, res.data)
        return ind, res.data
    with ThreadPoolExecutor(max_workers=min(len(indicator_ids), 5)) as executor:
        return dict(executor.map(_one, indicator_ids))


# ============================================================
# HATEOAS hypermedia controls (Richardson Maturity Model Level 3)
# Every JSON response carries a `_links` block describing the
# available next actions, so a client can navigate the whole API
# from the root without hardcoding any URL but the base.
# ============================================================
API_LINKS = {
    "summary": "/api/v1/summary",
    "gdp": "/api/v1/gdp",
    "inflation": "/api/v1/inflation",
    "exchange_rate": "/api/v1/exchange-rate",
    "interest_rate": "/api/v1/interest-rate",
    "fx_reserves": "/api/v1/fx-reserves",
    "currency_circulation": "/api/v1/currency-circulation",
    "nfem": "/api/v1/nfem",
    "multicurrency": "/api/v1/multicurrency",
    "gdp_sectors": "/api/v1/gdp-sectors",
    "cbn_balance_sheet": "/api/v1/cbn-balance-sheet",
    "analytics": "/api/v1/analytics",
    "leadlag": "/api/v1/leadlag?x=exchange_rate&y=inflation",
    "coverage": "/api/v1/coverage",
}


def _link(request: Request, path: str) -> dict:
    return {"href": str(request.base_url).rstrip("/") + path}


def hypermedia(request: Request, self_path: str, related=None, indicator: str = None, extra: dict = None) -> dict:
    """Build a `_links` block: self + index + docs, plus any related
    collection endpoints, plus per-indicator next actions (analytics/export)."""
    out = {"self": _link(request, self_path)}
    if self_path != "/":
        out["index"] = _link(request, "/")
    out["docs"] = _link(request, "/docs")
    if indicator:
        out["analytics"] = _link(request, f"/api/v1/analytics/{indicator}")
        out["export_csv"] = _link(request, f"/api/v1/export/{indicator}")
    for name in (related or []):
        out[name] = _link(request, API_LINKS[name])
    for rel, path in (extra or {}).items():
        out[rel] = _link(request, path)
    return out


@app.get("/")
@app.head("/")
def root(request: Request):
    return {
        "name": "Nigerian Public Economic Data API",
        "version": "1.0.0",
        "docs": "/docs",
        "dashboard": "https://antd-cr7.github.io/nigerian-dashboard",
        "endpoints": [
            "/api/v1/summary", "/api/v1/gdp", "/api/v1/inflation", "/api/v1/exchange-rate",
            "/api/v1/interest-rate", "/api/v1/fx-reserves", "/api/v1/currency-circulation",
            "/api/v1/nfem", "/api/v1/multicurrency", "/api/v1/gdp-sectors",
            "/api/v1/cbn-balance-sheet", "/api/v1/analytics", "/api/v1/analytics/{indicator_id}",
            "/api/v1/coverage", "/api/v1/export/{indicator_id}",
        ],
        "data_writes_enabled": ALLOW_DATA_WRITES,
        "_links": hypermedia(request, "/", related=list(API_LINKS)),
    }


LLMS_TXT = """# NPEDATA — Nigerian Public Economic Data Aggregation and Analytics Platform with Open API

## Summary
NPEDATA aggregates Nigerian public economic data from the Central Bank of Nigeria (CBN), the National
Bureau of Statistics (NBS), and the World Bank into one interactive dashboard, with a free, open,
no-authentication REST API for programmatic and AI-agent access. Final Year Project, Department of
Computer Science, Caleb University, Imota, Lagos, Nigeria (2026). Author: Taoheed Abdulmanan Olaosebikan.

Scope is strictly Nigeria — no other countries' data is included.

## Links
- Live dashboard (primary): https://antd-cr7.github.io/nigerian-dashboard
- Live dashboard (mirror, Cloudflare Pages): https://npedata.pages.dev
- Open API base URL: https://npedata-api.onrender.com
- Source code: https://github.com/ANTD-CR7/nigerian-dashboard
- API status / data freshness: https://antd-cr7.github.io/nigerian-dashboard/status.html

## Open API
Base URL: https://npedata-api.onrender.com
Auth: none. CORS: open. Format: JSON. Every JSON response includes a HATEOAS `_links` block
(Richardson Maturity Model Level 3) so the whole API is navigable from the root.

Read endpoints (GET, all under /api/v1/): /summary, /gdp, /inflation, /exchange-rate, /interest-rate,
/fx-reserves, /currency-circulation, /nfem, /multicurrency, /gdp-sectors, /cbn-balance-sheet, /analytics,
/analytics/{indicator_id} (trend + Holt-Winters forecast), /forecast/{indicator_id} (Holt-Winters with
95% prediction intervals), /decompose/{indicator_id} (seasonal decomposition), /leadlag (lead/lag
cross-correlation), /coverage, /export/{indicator_id} (CSV).
Most accept optional start/end date query params (ISO 8601). Interactive docs at /docs.

A demo-safe data-ingestion path also exists (POST /api/v1/observations, /api/v1/ingest/csv) for the
Data Validation Layer of the FYP: rows are always validated and normalized, but only written to the
live database when the server-side ALLOW_DATA_WRITES flag is enabled (disabled by default).

## AI Agent Access
A Model Context Protocol (MCP) server is available at /mcp-server in the source repository, exposing
every endpoint above as a read-only tool for Claude Desktop, Cursor, and other MCP-compatible clients.

## License / Usage
Free for research, academic, and development use. Informational and educational purposes only —
not financial advice. For official figures, refer directly to the CBN, NBS, and World Bank.
"""


@app.get("/llms.txt", response_class=PlainTextResponse)
def llms_txt():
    return LLMS_TXT


@app.get("/api/v1/summary")
def get_summary(request: Request):
    return {"gdp_growth": latest("gdp_growth"), "inflation": latest("inflation"), "exchange_rate": latest("exchange_rate"), "mpr": latest("mpr"), "fx_reserves": latest("fx_reserves"), "source": "CBN, NBS, World Bank",
            "_links": hypermedia(request, "/api/v1/summary", related=["gdp", "inflation", "exchange_rate", "interest_rate", "fx_reserves", "coverage"])}


@app.get("/api/v1/gdp")
def get_gdp(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"gdp_growth": fetch("gdp_growth", start, end), "gdp_usd": fetch("gdp_usd", start, end), "unit": "Percent and USD Billions", "source": "NBS and World Bank",
            "_links": hypermedia(request, "/api/v1/gdp", indicator="gdp_growth", related=["summary", "gdp_sectors", "coverage"])}


@app.get("/api/v1/inflation")
def get_inflation(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"headline": fetch("inflation", start, end), "food": fetch("inflation_food", start, end), "core": fetch("inflation_core", start, end), "unit": "Percent year-on-year", "source": "NBS CPI Report",
            "_links": hypermedia(request, "/api/v1/inflation", indicator="inflation", related=["summary", "coverage"])}


@app.get("/api/v1/exchange-rate")
def get_exchange_rate(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"data": fetch("exchange_rate", start, end), "unit": "Naira per USD", "source": "CBN Official Rate",
            "_links": hypermedia(request, "/api/v1/exchange-rate", indicator="exchange_rate", related=["summary", "nfem", "multicurrency", "coverage"])}


@app.get("/api/v1/interest-rate")
def get_interest_rate(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"data": fetch("mpr", start, end), "unit": "Percent", "source": "CBN Monetary Policy Committee",
            "_links": hypermedia(request, "/api/v1/interest-rate", indicator="mpr", related=["summary", "coverage"])}


@app.get("/api/v1/fx-reserves")
def get_fx_reserves(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"gross": fetch("fx_reserves", start, end), "liquid": fetch("reserves_liquid", start, end), "blocked": fetch("reserves_blocked", start, end), "block_pct": fetch("reserves_block_pct", start, end), "unit": "USD Billions", "source": "CBN",
            "_links": hypermedia(request, "/api/v1/fx-reserves", indicator="fx_reserves", related=["summary", "cbn_balance_sheet", "coverage"])}


@app.get("/api/v1/currency-circulation")
def get_currency_circulation(request: Request, start: Optional[str] = Query(default="2002-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"data": fetch("currency_circulation_full", start, end), "unit": "Naira Millions", "source": "CBN Statistical Bulletin",
            "_links": hypermedia(request, "/api/v1/currency-circulation", indicator="currency_circulation_full", related=["summary", "cbn_balance_sheet", "coverage"])}


@app.get("/api/v1/nfem")
def get_nfem(request: Request, start: Optional[str] = Query(default="2024-12-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"closing": fetch("nfem_closing", start, end), "highest": fetch("nfem_highest", start, end), "lowest": fetch("nfem_lowest", start, end), "weighted_avg": fetch("nfem_weighted_avg", start, end), "unit": "NGN per USD", "source": "CBN NFEM", "coverage": "December 2024 to April 2026",
            "_links": hypermedia(request, "/api/v1/nfem", indicator="nfem_closing", related=["exchange_rate", "multicurrency", "coverage"])}


@app.get("/api/v1/multicurrency")
def get_multicurrency(request: Request, currency: Optional[str] = Query(default=None), start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    currencies = ["usd", "gbp", "eur", "cny", "chf", "zar", "aed", "sar", "sdr", "cfa", "waua"]
    if currency and currency.lower() in currencies:
        currencies = [currency.lower()]
    rates = ["buying", "central", "selling"]
    fetched = fetch_parallel([f"{c}_{r}" for c in currencies for r in rates], start, end)
    return {"data": {c: {r: fetched[f"{c}_{r}"] for r in rates} for c in currencies}, "unit": "Naira per foreign currency unit", "source": "CBN",
            "_links": hypermedia(request, "/api/v1/multicurrency", related=["exchange_rate", "nfem", "coverage"])}


@app.get("/api/v1/gdp-sectors")
def get_gdp_sectors(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    sectors = ["gdp_agriculture", "gdp_industry", "gdp_services", "gdp_manufacturing", "gdp_telecommunicationsAndInformationServices", "gdp_construction", "gdp_trade"]
    return {"data": {s: fetch(s, start, end) for s in sectors}, "unit": "Naira Billions constant prices", "source": "NBS GDP Report",
            "_links": hypermedia(request, "/api/v1/gdp-sectors", related=["gdp", "coverage"])}


@app.get("/api/v1/cbn-balance-sheet")
def get_cbn_balance_sheet(request: Request, start: Optional[str] = Query(default="2005-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"total_assets": fetch("cbn_total_assets", start, end), "total_liabilities": fetch("cbn_total_liabilities", start, end), "gold": fetch("cbn_gold", start, end), "currency_issued": fetch("cbn_currency_issued", start, end), "unit": "Naira Thousands", "source": "CBN Balance Sheet",
            "_links": hypermedia(request, "/api/v1/cbn-balance-sheet", indicator="cbn_total_assets", related=["fx_reserves", "currency_circulation", "coverage"])}


@app.get("/api/v1/analytics")
def get_analytics(request: Request):
    inf_data = fetch("inflation", "2020-01-01", "2026-12-31")
    fx_data = fetch("exchange_rate", "2020-01-01", "2026-12-31")
    inf_map = {d["obs_date"]: d["value"] for d in inf_data}
    fx_map = {d["obs_date"]: d["value"] for d in fx_data}
    common = sorted(set(inf_map) & set(fx_map))
    inf_vals = [inf_map[d] for d in common]
    fx_vals = [fx_map[d] for d in common]
    r = 0.0
    if len(common) > 1:
        mi = statistics.mean(inf_vals)
        mf = statistics.mean(fx_vals)
        num = sum((a - mi) * (b - mf) for a, b in zip(inf_vals, fx_vals))
        den = (sum((a - mi) ** 2 for a in inf_vals) * sum((b - mf) ** 2 for b in fx_vals)) ** 0.5
        r = round(num / den, 4) if den else 0.0
    return {
        "pearson_correlation": {
            "r": r,
            "variables": ["headline_inflation", "ngn_usd_exchange_rate"],
            "period": f"{common[0]} to {common[-1]}" if common else "N/A",
            "n": len(common),
            "interpretation": f"A Pearson r of {r} indicates a strong positive association between headline inflation and the NGN/USD rate over this period, consistent with the June 2023 FX reform coinciding with the 2023-2024 inflation surge. Correlation does not by itself establish causation.",
        },
        "inflation_peak": {"value": max(inf_vals), "date": common[inf_vals.index(max(inf_vals))]},
        "exchange_rate_peak": {"value": max(fx_vals), "date": common[fx_vals.index(max(fx_vals))]},
        "source": "CBN, NBS",
        "_links": hypermedia(request, "/api/v1/analytics", related=["inflation", "exchange_rate", "coverage"]),
    }


@app.get("/api/v1/analytics/{indicator_id}")
def get_indicator_analytics(
    request: Request,
    indicator_id: str,
    start: Optional[str] = Query(default="2020-01-01"),
    end: Optional[str] = Query(default="2026-12-31"),
    forecast_periods: int = Query(default=3, ge=1, le=12),
):
    result = analytics_for(indicator_id, start, end, forecast_periods)
    result["_links"] = hypermedia(
        request, f"/api/v1/analytics/{indicator_id}", related=["coverage"],
        extra={"export_csv": f"/api/v1/export/{indicator_id}", "analytics_correlation": "/api/v1/analytics"},
    )
    return result


@app.get("/api/v1/forecast/{indicator_id}")
def get_forecast(
    request: Request,
    indicator_id: str,
    start: Optional[str] = Query(default="2020-01-01"),
    end: Optional[str] = Query(default="2026-12-31"),
    periods: int = Query(default=6, ge=1, le=24),
    confidence: float = Query(default=0.95, ge=0.5, le=0.99),
):
    """Holt-Winters forecast with prediction intervals. Seasonal period is
    inferred from the indicator's frequency; short series fall back to Holt's
    linear trend. Every smoothing parameter is reported (no black box)."""
    meta = require_indicator(indicator_id)
    rows = fetch(indicator_id, start, end)
    values = [float(r["value"]) for r in rows]
    if len(values) < 3:
        raise HTTPException(status_code=422, detail="Need at least 3 observations to forecast.")

    last_date = datetime.strptime(rows[-1]["obs_date"], "%Y-%m-%d").date()
    m = forecasting.season_length_for(meta["frequency"])
    hw = forecasting.holt_winters(values, m, periods, ci=confidence)
    for entry in hw["forecast"]:
        entry["obs_date"] = add_months(last_date, meta["period_months"] * entry["step"]).isoformat()

    return {
        "indicator_id": indicator_id,
        "indicator": meta["name"],
        "unit": meta["unit"],
        "frequency": meta["frequency"],
        "history_points": len(values),
        "last_observed": {"obs_date": rows[-1]["obs_date"], "value": values[-1]},
        "model": {
            "method": hw["method"], "seasonal": hw["seasonal"], "season_length": hw["season_length"],
            "params": hw["params"], "residual_std_error": hw["residual_std_error"],
        },
        "confidence": hw["confidence"],
        "forecast": hw["forecast"],
        "source": meta["source"],
        "_links": hypermedia(
            request, f"/api/v1/forecast/{indicator_id}", related=["coverage"],
            extra={"analytics": f"/api/v1/analytics/{indicator_id}",
                   "decompose": f"/api/v1/decompose/{indicator_id}",
                   "export_csv": f"/api/v1/export/{indicator_id}"},
        ),
    }


@app.get("/api/v1/decompose/{indicator_id}")
def get_decompose(
    request: Request,
    indicator_id: str,
    start: Optional[str] = Query(default="2020-01-01"),
    end: Optional[str] = Query(default="2026-12-31"),
):
    """Classical additive seasonal decomposition: value = trend + seasonal +
    residual, with a 0-1 seasonal-strength score."""
    meta = require_indicator(indicator_id)
    rows = fetch(indicator_id, start, end)
    values = [float(r["value"]) for r in rows]
    dates = [r["obs_date"] for r in rows]
    m = forecasting.season_length_for(meta["frequency"])
    decomp = forecasting.seasonal_decompose(values, m)
    return {
        "indicator_id": indicator_id,
        "indicator": meta["name"],
        "unit": meta["unit"],
        "frequency": meta["frequency"],
        "dates": dates,
        "observed": [round(v, 4) for v in values],
        **decomp,
        "source": meta["source"],
        "_links": hypermedia(
            request, f"/api/v1/decompose/{indicator_id}", related=["coverage"],
            extra={"forecast": f"/api/v1/forecast/{indicator_id}",
                   "analytics": f"/api/v1/analytics/{indicator_id}"},
        ),
    }


@app.get("/api/v1/leadlag")
def get_leadlag(
    request: Request,
    x: str = Query(..., description="Leading indicator id"),
    y: str = Query(..., description="Lagging indicator id"),
    start: Optional[str] = Query(default="2020-01-01"),
    end: Optional[str] = Query(default="2026-12-31"),
    max_lag: int = Query(default=12, ge=1, le=36),
):
    """Lead/lag cross-correlation between two indicators. A positive best lag
    means x leads y (x's past co-moves with y's present)."""
    require_indicator(x)
    require_indicator(y)
    xr = {r["obs_date"]: float(r["value"]) for r in fetch(x, start, end)}
    yr = {r["obs_date"]: float(r["value"]) for r in fetch(y, start, end)}
    common = sorted(set(xr) & set(yr))
    if len(common) < 4:
        raise HTTPException(status_code=422, detail="Need at least 4 overlapping observations.")
    xs = [xr[d] for d in common]
    ys = [yr[d] for d in common]
    cc = forecasting.cross_correlation(xs, ys, max_lag)
    return {
        "x": x, "y": y, "n": len(common),
        "period": f"{common[0]} to {common[-1]}",
        **cc,
        "interpretation": _leadlag_text(x, y, cc),
        "source": "CBN, NBS, World Bank",
        "_links": hypermedia(request, "/api/v1/leadlag", related=["analytics", "coverage"]),
    }


def _leadlag_text(x, y, cc):
    best = cc["best"]
    lag, r = best["lag"], best["r"]
    if cc["relationship"] == "x_leads_y":
        return f"{x} appears to lead {y} by {lag} period(s) (r={r}). Movements in {x} precede similar movements in {y}. This is association, not proven causation."
    if cc["relationship"] == "y_leads_x":
        return f"{y} appears to lead {x} by {abs(lag)} period(s) (r={r}). This is association, not proven causation."
    return f"{x} and {y} co-move contemporaneously (r={r}, no lead detected). Association, not proven causation."


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


@app.post("/api/v1/ask")
def ask_the_data(request: Request, body: AskRequest):
    """Natural-language questions answered strictly from real platform figures.
    Retrieves the relevant indicators, hands the figures to the model, and
    instructs it to answer only from them and cite each one. Returns 503 if no
    ANTHROPIC_API_KEY is configured, so the rest of the API is unaffected."""
    if not ai_assistant.key_configured():
        raise HTTPException(status_code=503, detail="AI assistant not configured (set ANTHROPIC_API_KEY).")

    ids = ai_assistant.match_indicators(body.question, INDICATORS)
    if not ids:
        ids = [i for i in ("inflation", "exchange_rate", "gdp", "fx_reserves", "interest_rate")
               if i in INDICATORS]

    context = {"available_indicator_count": len(INDICATORS), "indicators": {}}
    for iid in ids:
        a = analytics_for(iid, "2020-01-01", "2026-12-31", 3)
        if a.get("data_points"):
            context["indicators"][iid] = {
                "name": a.get("indicator"), "unit": a.get("unit"),
                "latest": a.get("latest"),
                "previous_change": a.get("previous_change"),
                "year_over_year_change": a.get("year_over_year_change"),
                "trend": a.get("trend"),
                "forecast_next": (a.get("forecast") or [None])[0],
            }

    try:
        result = ai_assistant.call_anthropic(
            ai_assistant.build_user_message(body.question, context),
            api_key=os.environ["ANTHROPIC_API_KEY"],
        )
    except Exception as exc:  # network / API error
        raise HTTPException(status_code=502, detail=f"AI request failed: {exc}")

    return {
        "question": body.question,
        "answer": result["text"],
        "model": result.get("model"),
        "data_used": context,
        "disclaimer": "Generated from the figures shown in data_used. Correlation is not causation. Not financial advice.",
        "_links": hypermedia(request, "/api/v1/ask", related=["analytics", "coverage"]),
    }


@app.get("/api/v1/coverage")
def get_coverage(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    indicators = []
    total_observations = 0
    sources = set()

    for indicator_id, meta in INDICATORS.items():
        rows = fetch(indicator_id, start, end)
        values = [float(row["value"]) for row in rows]
        dates = [row["obs_date"] for row in rows]
        row_sources = sorted({row["source"] for row in rows if row.get("source")})
        sources.update(row_sources)
        total_observations += len(rows)
        indicators.append({
            "indicator_id": indicator_id,
            "name": meta["name"],
            "frequency": meta["frequency"],
            "unit": meta["unit"],
            "source": meta["source"],
            "observations": len(rows),
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "minimum": round(min(values), 4) if values else None,
            "maximum": round(max(values), 4) if values else None,
            "database_sources": row_sources,
        })

    return {
        "start": start,
        "end": end,
        "total_observations": total_observations,
        "indicator_count": len(indicators),
        "source_count": len(sources),
        "sources": sorted(sources),
        "indicators": indicators,
        "_links": hypermedia(request, "/api/v1/coverage", related=list(API_LINKS)),
    }


@app.get("/api/v1/export/{indicator_id}")
def export_indicator_csv(request: Request, indicator_id: str, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    require_indicator(indicator_id)
    rows = fetch(indicator_id, start, end)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["indicator_id", "obs_date", "value", "source"])
    writer.writeheader()
    for row in rows:
        writer.writerow({"indicator_id": indicator_id, "obs_date": row["obs_date"], "value": row["value"], "source": row.get("source", "")})

    # A CSV body carries no JSON `_links`; hypermedia for non-JSON representations
    # goes in the RFC 8288 Link header instead, keeping the API Level 3 end to end.
    base = str(request.base_url).rstrip("/")
    link_header = (
        f'<{base}/api/v1/export/{indicator_id}>; rel="self", '
        f'<{base}/api/v1/analytics/{indicator_id}>; rel="analytics", '
        f'<{base}/>; rel="index"'
    )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{indicator_id}_{start}_{end}.csv"',
            "Link": link_header,
        },
    )


@app.post("/api/v1/observations")
def append_observation(request: Request, payload: ObservationIn, commit: bool = Query(default=False)):
    stored = store_observation(payload, commit=commit)
    return {"message": "Observation normalized successfully.", "write_enabled": ALLOW_DATA_WRITES, "observation": stored,
            "_links": hypermedia(request, "/api/v1/observations", indicator=payload.indicator_id, related=["coverage"])}


@app.post("/api/v1/validate/csv")
async def validate_csv(
    request: Request,
    indicator_id: str = Form(...),
    file: UploadFile = File(...),
):
    """The platform's Validation Layer exposed as a service: returns a
    per-row verdict report (valid / rejected + reasons) for any uploaded
    CSV and NEVER writes — unlike /ingest/csv it does not stop at the
    first bad row, so callers see everything wrong with a file at once."""
    require_indicator(indicator_id)
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "obs_date" not in reader.fieldnames or "value" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must contain obs_date and value columns.")

    rows, seen_dates, valid_count = [], set(), 0
    for row_number, row in enumerate(reader, start=2):
        raw_date = (row.get("obs_date") or "").strip()
        raw_value = str(row.get("value") or "").strip().replace(",", "")
        problems = []
        obs_date = None
        value = None
        try:
            obs_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            problems.append("obs_date must be an ISO date (YYYY-MM-DD)")
        try:
            value = float(raw_value)
            if not math.isfinite(value):
                value = None
                problems.append("value must be a finite number (NaN/Infinity rejected)")
        except ValueError:
            problems.append("value must be numeric")
        if obs_date:
            if obs_date > date.today():
                problems.append("obs_date is in the future")
            if obs_date.isoformat() in seen_dates:
                problems.append("duplicate obs_date within this file")
            seen_dates.add(obs_date.isoformat())
        if problems:
            rows.append({"row": row_number, "status": "rejected", "reasons": problems,
                         "input": {"obs_date": raw_date, "value": raw_value}})
        else:
            valid_count += 1
            rows.append({"row": row_number, "status": "valid",
                         "normalized": {"indicator_id": indicator_id, "obs_date": obs_date.isoformat(),
                                        "value": round(value, 4)}})

    return {
        "indicator_id": indicator_id,
        "rows_total": len(rows),
        "rows_valid": valid_count,
        "rows_rejected": len(rows) - valid_count,
        "written_to_database": False,
        "note": "Validation report only — this endpoint never writes to the live database.",
        "rows": rows,
        "_links": hypermedia(request, "/api/v1/validate/csv", indicator=indicator_id, related=["coverage"]),
    }


@app.post("/api/v1/ingest/csv")
async def ingest_csv(
    request: Request,
    indicator_id: str = Form(...),
    source: str = Form(default="UPLOAD"),
    commit: bool = Form(default=False),
    file: UploadFile = File(...),
):
    require_indicator(indicator_id)
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "obs_date" not in reader.fieldnames or "value" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must contain obs_date and value columns.")

    stored = []
    for row_number, row in enumerate(reader, start=2):
        try:
            payload = ObservationIn(
                indicator_id=indicator_id,
                obs_date=datetime.strptime(row["obs_date"].strip(), "%Y-%m-%d").date(),
                value=float(str(row["value"]).replace(",", "").strip()),
                source=(row.get("source") or source).strip()[:20],
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid row {row_number}: {row}") from exc
        stored.append(store_observation(payload, commit=commit))

    return {
        "message": "CSV file normalized successfully.",
        "write_enabled": ALLOW_DATA_WRITES,
        "indicator_id": indicator_id,
        "rows_processed": len(stored),
        "rows_committed": sum(1 for row in stored if row.get("committed")),
        "rows": stored,
        "_links": hypermedia(request, "/api/v1/ingest/csv", indicator=indicator_id, related=["coverage"]),
    }
