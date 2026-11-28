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
from datetime import date, datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from supabase import create_client, Client
from typing import Optional

import forecasting
import ai_assistant

app = FastAPI(
    title="Nigerian Public Economic Data API",
    description=("A free, open economic data API for Nigeria. 122 indicators from CBN, NBS and the "
                 "World Bank, with Holt-Winters forecasting, seasonal decomposition, lead/lag analysis, "
                 "a grounded AI assistant, and full HATEOAS. No authentication required by default."),
    version="1.1.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


# --- Optional API-key auth + per-IP rate limiting (opt-in via env) --------- #
# Both are OFF by default: with NPE_API_KEYS unset the API stays fully open, as
# it is today. Set a comma-separated NPE_API_KEYS to require an X-API-Key header
# on /api/v1 routes. NPE_RATE_LIMIT_PER_MIN caps requests per IP per minute.
#
# _rate_state only ever grew before this fix -- no eviction, no cap. Combined
# with the old --forwarded-allow-ips="*" (removed; see render.yaml/Procfile),
# a caller could claim a fresh fake IP on every request, turning this into an
# unbounded-memory primitive rather than just a bypassed limit. Even with
# that spoofing vector closed, many genuinely distinct real clients can
# still grow this dict over the life of a long-running process, so it's
# bounded unconditionally: a periodic sweep drops stale entries, and a hard
# cap resets the whole table as a last resort if growth ever outpaces the
# sweep (a brief false reset of everyone's count, not a memory leak).
_rate_state: dict = {}
_rate_lock = threading.Lock()
_rate_last_sweep = 0.0
_RATE_SWEEP_INTERVAL = 60.0   # how often to look for stale entries
_RATE_STALE_AFTER = 120.0    # 2x the rate-limit window
_RATE_STATE_MAX_ENTRIES = 50_000  # last-resort safety valve between sweeps


def _sweep_rate_state(now: float) -> None:
    global _rate_last_sweep
    if len(_rate_state) > _RATE_STATE_MAX_ENTRIES:
        _rate_state.clear()
        _rate_last_sweep = now
        return
    if now - _rate_last_sweep < _RATE_SWEEP_INTERVAL:
        return
    for ip in [k for k, (window_start, _) in _rate_state.items() if now - window_start > _RATE_STALE_AFTER]:
        del _rate_state[ip]
    _rate_last_sweep = now


def _allowed_keys() -> set:
    return {k.strip() for k in os.environ.get("NPE_API_KEYS", "").split(",") if k.strip()}


def _rate_limit_per_min() -> int:
    try:
        return int(os.environ.get("NPE_RATE_LIMIT_PER_MIN", "120") or 0)
    except ValueError:
        return 120


# CSV upload endpoints (validate/ingest) call `await file.read()` with no
# size cap. Starlette's multipart form parser buffers the *entire* body
# into the UploadFile (spooling to disk past its internal threshold)
# before our handler ever runs, so bounding what we read afterward doesn't
# stop an attacker from first making the process spool an arbitrarily
# large body. The only point early enough to reject an oversized upload is
# before Starlette parses the body at all -- i.e. here, from the
# declared Content-Length, in middleware.
_MAX_CSV_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MiB: generous for an observations CSV
_CSV_UPLOAD_PATHS = {"/api/v1/validate/csv", "/api/v1/ingest/csv"}


@app.middleware("http")
async def gate(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/v1"):
        limit = _rate_limit_per_min()
        if limit > 0:
            ip = request.client.host if request.client else "?"
            now = time.time()
            with _rate_lock:
                _sweep_rate_state(now)
                window_start, count = _rate_state.get(ip, (now, 0))
                if now - window_start >= 60:
                    window_start, count = now, 0
                count += 1
                _rate_state[ip] = (window_start, count)
            if count > limit:
                return JSONResponse(status_code=429,
                                    content={"detail": "Rate limit exceeded. Please slow down and retry shortly."})
        keys = _allowed_keys()
        if keys and request.headers.get("x-api-key") not in keys:
            return JSONResponse(status_code=401,
                                content={"detail": "Missing or invalid API key. Send it in the X-API-Key header."})
        if path in _CSV_UPLOAD_PATHS:
            content_length = request.headers.get("content-length")
            try:
                too_big = content_length is None or int(content_length) > _MAX_CSV_UPLOAD_BYTES
            except ValueError:
                too_big = True
            if too_big:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Upload too large or missing Content-Length. "
                                        f"Limit is {_MAX_CSV_UPLOAD_BYTES} bytes."},
                )
        # Validate date params up front so a malformed value returns a clean 422
        # instead of reaching the database and surfacing a 500.
        for param in ("start", "end"):
            val = request.query_params.get(param)
            if val is not None:
                try:
                    date.fromisoformat(val)
                except ValueError:
                    return JSONResponse(status_code=422,
                                        content={"detail": f"Invalid '{param}' date. Use ISO format YYYY-MM-DD."})
    response = await call_next(request)
    # Let browsers and CDNs cache successful GET reads briefly - cheap protection
    # for the free tier under traffic. Data refreshes at most a few times a day.
    if request.method == "GET" and path.startswith("/api/v1") and response.status_code == 200:
        response.headers.setdefault("Cache-Control", "public, max-age=300")
    return response

# Credentials read from the environment (Render dashboard / local .env). No
# hardcoded fallback: audit finding #1/#107 found this exact anon key
# hardcoded in 20+ files with RLS disabled on the tables it could write to.
# RLS is now on (see project/database/setup.sql's LOCKDOWN section) and this
# key is read-only going forward -- a missing env var should fail loudly,
# not silently resurrect a since-rotated key.
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
# Demo-safe by default: ingestion endpoints validate and normalize but do not
# write to the live database unless this is explicitly enabled.
ALLOW_DATA_WRITES = os.environ.get("ALLOW_DATA_WRITES", "false").lower() == "true"
# The service-role key: the only credential allowed to write (see
# store_observation() below). Bypasses RLS/GRANTs entirely by design, so it
# is never the same key as SUPABASE_KEY above and never has a hardcoded
# fallback. Writes are silently disabled (demo-safe) if this isn't set, even
# when ALLOW_DATA_WRITES=true.
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase_write: Client | None = (
    create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_SERVICE_KEY else None
)
# What store_observation() actually does, not just what was asked for: a
# truthful status flag for the endpoints below that report it externally.
# ALLOW_DATA_WRITES=true with no service key configured is still demo-safe
# in practice, and callers checking this flag deserve to know that.
WRITES_ACTUALLY_ENABLED = ALLOW_DATA_WRITES and supabase_write is not None

# Metadata for the indicators exposed as single time series through the
# analytics/export/ingestion endpoints below.
INDICATORS = {
    "gdp_growth": {"name": "GDP Growth Rate", "unit": "Percent (%)", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_usd": {"name": "Nominal GDP", "unit": "USD Billions", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "inflation": {"name": "Headline Inflation Rate", "unit": "Percent (%)", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "exchange_rate": {"name": "Exchange Rate", "unit": "Naira per USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "mpr": {"name": "Monetary Policy Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "fx_reserves": {"name": "FX Reserves (Gross)", "unit": "USD Billions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "reserves_liquid": {"name": "FX Reserves (Liquid)", "unit": "USD Billions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "reserves_blocked": {"name": "FX Reserves (Blocked)", "unit": "USD Billions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "reserves_block_pct": {"name": "FX Reserves Blocked (%)", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_closing": {"name": "NFEM Closing Rate", "unit": "Naira per USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_highest": {"name": "NFEM Highest Rate", "unit": "Naira per USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_lowest": {"name": "NFEM Lowest Rate", "unit": "Naira per USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_weighted_avg": {"name": "NFEM Weighted Average Rate", "unit": "Naira per USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_simple_avg": {"name": "NFEM Simple Average Rate", "unit": "Naira per USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_deals_count": {"name": "NFEM Number of Deals", "unit": "Count", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_deals_count_interbank": {"name": "NFEM Number of Interbank Deals", "unit": "Count", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_total_turnover": {"name": "NFEM Total Turnover", "unit": "USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "nfem_interbank_turnover": {"name": "NFEM Interbank Turnover", "unit": "USD", "source": "CBN", "frequency": "daily", "period_months": 1},
    "currency_circulation_full": {"name": "Currency in Circulation", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_assets": {"name": "CBN Total Assets", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_liabilities": {"name": "CBN Total Liabilities", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_annual_total_assets": {"name": "CBN Total Assets (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    # CBN Five Year Financial Statements (frozen source, 1960-2012).
    # cbn_annual_ext_reserve/cbn_annual_cin_c/cbn_annual_surplus/
    # cbn_annual_total_income had live data from the original ETL but
    # no INDICATORS entry at all (same gap pattern found repeatedly
    # this session). The other 29 are genuinely new.
    "cbn_annual_ext_reserve": {"name": "CBN External Reserves (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_sdr_holdings": {"name": "Holdings of Special Drawing Rights (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_fed_govt_securities": {"name": "Fed Govt. Securities (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_rediscount_advances": {"name": "Rediscount & Loans/Advances (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_other_assets": {"name": "Other Assets (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_other_securities": {"name": "Other Securities / Investments (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_exchange_diff_promissory_notes": {"name": "Exchange Difference on Promissory Notes (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_fixed_assets": {"name": "Fixed Assets (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_deposits": {"name": "Deposits (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_instruments_issued": {"name": "CBN Instruments Issued (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_cin_c": {"name": "CBN Currency in Circulation (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_imf_sdr_allocation": {"name": "IMF Allocation for SDR (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_trade_debt_promissory_notes": {"name": "Trade Debt Promissory Notes (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_other_foreign_currency_liabilities": {"name": "Other Foreign Currency Liabilities (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_other_financial_liabilities": {"name": "Other Financial Liabilities (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_liabilities_subtotal": {"name": "Total Liabilities (Annual, Subtotal)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_share_capital": {"name": "Share Capital (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_general_reserve_fund": {"name": "General Reserve Fund (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_assets_revaluation_reserve": {"name": "Assets Revaluation Reserve (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_currency_revaluation_reserve": {"name": "Currency Revaluation Reserve (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_reserve_fund_inv_manager": {"name": "Reserve Fund Inv. Manager (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_total_capital_reserves": {"name": "Total Capital & Reserves (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_total_liabilities_equity": {"name": "Total Liabilities & Equity (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_contingent_liabilities": {"name": "Contingent Liabilities (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_total_income": {"name": "CBN Annual Total Income", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_provision_bad_debt": {"name": "Provision for Bad Debt (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_operating_expenses": {"name": "Operating Expenses (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_provisions_net": {"name": "Provisions, Net (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_exceptional_items": {"name": "Exceptional Items (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_surplus": {"name": "CBN Annual Surplus", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_transfer_general_reserve": {"name": "Transfer to General Reserve (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_surplus_to_fgn": {"name": "Surplus Available to F.G.N. (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    "cbn_annual_total_appropriation": {"name": "Total Appropriation (Annual)", "unit": "Naira Millions", "source": "CBN", "frequency": "annual", "period_months": 12},
    # CBN Statement of Assets & Liabilities (frozen source, Jan 2005 -
    # Nov 2023). cbn_gold/cbn_currency_issued had live data from the
    # original ETL but no INDICATORS entry at all (same gap pattern
    # found repeatedly this session).
    #
    # Unit for this whole block (and cbn_total_assets/cbn_total_liabilities
    # above) was "Naira" -- wrong by a factor of 1000, cross-validated 3
    # ways against the live data: cbn_total_assets ~N81tn (matches CBN's
    # real ~N87tn total assets); cbn_currency_issued ~N3.348tn in Nov 2023
    # matches currency_circulation_full's independently-sourced N3,347,716
    # million for the same month to within 0.01%; cbn_capital_subscribed is
    # a constant 5,000,000 which is exactly CBN's statutory N5,000,000,000
    # authorised capital (CBN Act 2007 s.9) read as thousands. The
    # /api/v1/cbn-balance-sheet endpoint already said "Naira Thousands" for
    # the same 4 series -- this INDICATORS block disagreed with its own
    # endpoint (#5/#40/#79/#111/#135).
    "cbn_gold": {"name": "Gold", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_convertible_currencies": {"name": "Convertible Currencies", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_imf_gold_tranche": {"name": "IMF Gold Tranche", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_sdr_holdings": {"name": "Special Drawing Rights (Holdings)", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_external_reserve": {"name": "Total External Reserve", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_fed_govt_securities": {"name": "Federal Government Securities (Holdings)", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_other_securities": {"name": "Other Securities", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_rediscount_advances": {"name": "Rediscount & Advances", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_other_assets": {"name": "Other Assets", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_fixed_assets": {"name": "Fixed Assets", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_capital_subscribed": {"name": "Capital Subscribed", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_general_reserves": {"name": "General Reserves", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_other_reserves": {"name": "Other Reserves", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_capitalization": {"name": "Total Capitalization", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_instruments_outstanding": {"name": "CBN Instruments (Outstanding)", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_currency_issued": {"name": "Currency In Circulation", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_govt_deposits": {"name": "Federal & State Govts. Deposits", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_bankers_deposits": {"name": "Bankers Deposits", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_other_deposits": {"name": "Other Deposits", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_deposits": {"name": "Total Deposits", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_other_liabilities": {"name": "Other Liabilities", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "wb_inflation": {"name": "Inflation, Consumer Prices (World Bank)", "unit": "Percent (%)", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "wb_gdp_growth": {"name": "GDP Growth, Annual (World Bank)", "unit": "Percent (%)", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "wb_gdp_usd": {"name": "GDP (current US$), World Bank", "unit": "USD", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "wb_unemployment": {"name": "Unemployment, World Bank", "unit": "Percent (%) of labour force", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "wb_exports_gdp": {"name": "Exports of Goods and Services (% of GDP)", "unit": "Percent (%) of GDP", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "wb_fdi_usd": {"name": "Foreign Direct Investment, Net Inflows", "unit": "USD", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "wb_population": {"name": "Population, Total (World Bank)", "unit": "Count", "source": "World Bank", "frequency": "annual", "period_months": 12},
    "imf_inflation": {"name": "Inflation, Average Consumer Prices (IMF)", "unit": "Percent (%)", "source": "IMF", "frequency": "annual", "period_months": 12},
    "imf_gdp_growth": {"name": "GDP Growth, Annual (IMF)", "unit": "Percent (%)", "source": "IMF", "frequency": "annual", "period_months": 12},
    "cbn_crude_oil_price": {"name": "Crude Oil Price (Bonny Light)", "unit": "USD per Barrel", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_oil_domestic_production": {"name": "Crude Oil Domestic Production", "unit": "Million Barrels Per Day", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_oil_export_volume": {"name": "Crude Oil Export Volume", "unit": "Million Barrels Per Day", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_crude_oil_price_daily": {"name": "Crude Oil Price (Daily)", "unit": "USD per Barrel", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_min_rediscount_rate": {"name": "Minimum Rediscount Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_121_150d": {"name": "Repo Rate (121-150 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_123_152d": {"name": "Repo Rate (123-152 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_151_181d": {"name": "Repo Rate (151-181 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_153_182d": {"name": "Repo Rate (153-182 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_183_212d": {"name": "Repo Rate (183-212 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_1_7d": {"name": "Repo Rate (1-7 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_213_242d": {"name": "Repo Rate (213-242 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_243_272d": {"name": "Repo Rate (243-272 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_273_302d": {"name": "Repo Rate (273-302 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_303_332d": {"name": "Repo Rate (303-332 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_31_60d": {"name": "Repo Rate (31-60 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_333_363d": {"name": "Repo Rate (333-363 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_33_62d": {"name": "Repo Rate (33-62 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_61_90d": {"name": "Repo Rate (61-90 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_63_92d": {"name": "Repo Rate (63-92 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_8_30d": {"name": "Repo Rate (8-30 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_8_32d": {"name": "Repo Rate (8-32 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_91_120d": {"name": "Repo Rate (91-120 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_91_180d": {"name": "Repo Rate (91-180 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repo_rate_93_122d": {"name": "Repo Rate (93-122 Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_repurchase_rate": {"name": "Repurchase (Repo) Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_reverse_repo_rate": {"name": "Reverse Repo Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_standing_deposit_rate": {"name": "Standing Deposit Facility Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_standing_lending_rate": {"name": "Standing Lending Facility Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_money_supply_m3": {"name": "Money Supply (M3)", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_bills_outstanding": {"name": "CBN Bills Outstanding", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_money_supply_m2": {"name": "Money Supply (M2)", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_quasi_money": {"name": "Quasi Money", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_narrow_money": {"name": "Narrow Money (M1)", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_currency_outside_banks": {"name": "Currency Outside Banks", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_demand_deposits": {"name": "Demand Deposits", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_net_foreign_assets": {"name": "Net Foreign Assets", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_net_domestic_assets": {"name": "Net Domestic Assets", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_net_domestic_credit": {"name": "Net Domestic Credit", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_credit_to_government": {"name": "Credit to Government", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_credit_to_government_federal": {"name": "Credit to Federal Government", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_mirror_accounts": {"name": "Mirror Accounts", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_credit_to_private_sector": {"name": "Credit to Private Sector", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_other_assets_net": {"name": "Other Assets (Net)", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_base_money": {"name": "Base Money", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_bank_reserves": {"name": "Bank Reserves", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_special_intervention_reserves": {"name": "Special Intervention Reserves", "unit": "Naira Millions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_interbank_call_rate": {"name": "Interbank Call Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_treasury_bill_rate": {"name": "Treasury Bill Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_savings_deposit_rate": {"name": "Savings Deposit Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_deposit_rate_1m": {"name": "Deposit Rate (1-Month)", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_deposit_rate_3m": {"name": "Deposit Rate (3-Month)", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_deposit_rate_6m": {"name": "Deposit Rate (6-Month)", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_deposit_rate_12m": {"name": "Deposit Rate (12-Month)", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_prime_lending_rate": {"name": "Prime Lending Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_max_lending_rate": {"name": "Maximum Lending Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_ntb_91d": {"name": "Treasury Bill Rate (91-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_ntb_182d": {"name": "Treasury Bill Rate (182-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_ntb_364d": {"name": "Treasury Bill Rate (364-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_fgn_bond_5y": {"name": "FGN Bond Rate (5-Year)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_fgn_bond_7y": {"name": "FGN Bond Rate (7-Year)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_fgn_bond_10y": {"name": "FGN Bond Rate (10-Year)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_fgn_bond_15y": {"name": "FGN Bond Rate (15-Year)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_fgn_bond_20y": {"name": "FGN Bond Rate (20-Year)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_fgn_bond_25y": {"name": "FGN Bond Rate (25-Year)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_fgn_bond_30y": {"name": "FGN Bond Rate (30-Year)", "unit": "Percent (%)", "source": "CBN", "frequency": "policy decision", "period_months": 2},
    "cbn_nofr": {"name": "Nigerian Overnight Financing Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_nofr_volume": {"name": "NOFR Daily Volume", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_nofr_min_rate": {"name": "NOFR Minimum Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_nofr_max_rate": {"name": "NOFR Maximum Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_nofr_variation_range": {"name": "NOFR Daily Variation Range", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_nofri": {"name": "Nigerian Overnight Financing Rate Index (NOFRI)", "unit": "Index (base 1.0)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_nofr_30d_term": {"name": "NOFR 30-Day Compounded Term Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_nofr_90d_term": {"name": "NOFR 90-Day Compounded Term Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_nofr_180d_term": {"name": "NOFR 180-Day Compounded Term Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_obb_rate": {"name": "Open Buy Back (OBB) Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_interbank_call_rate_daily": {"name": "Interbank Call Rate (Daily)", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_interbank_rate_7d": {"name": "Interbank Rate (7-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_interbank_rate_30d": {"name": "Interbank Rate (30-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_interbank_rate_60d": {"name": "Interbank Rate (60-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_interbank_rate_90d": {"name": "Interbank Rate (90-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_interbank_rate_180d": {"name": "Interbank Rate (180-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_interbank_rate_360d": {"name": "Interbank Rate (360-Day)", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    # CBN Financial Data (daily banking-system liquidity flows). Net Naira
    # flow amounts, distinct from the policy rates above (cbn_standing_
    # lending_rate, cbn_repurchase_rate, cbn_reverse_repo_rate etc.).
    "cbn_banks_opening_balance": {"name": "Opening Balances of Banks/Discount Houses", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_rediscounted_bills": {"name": "Rediscounted Bills", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_standing_lending_facility_flow": {"name": "Standing Lending Facility (Net Flow)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_standing_deposit_facility_flow": {"name": "Standing Deposit Facility (Net Flow)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_repo_flow": {"name": "Repo (Net Flow)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_reverse_repo_flow": {"name": "Reverse Repo (Net Flow)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_omo_sales": {"name": "OMO Sales/Under-Writing by MMDs", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_omo_repayment": {"name": "OMO Repayment", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_primary_market_sales": {"name": "Primary Market Sales (NTBs, FGN Bonds)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_primary_market_repayment": {"name": "Primary Market Repayment", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_crr_flow": {"name": "CRR (Debit/Credit)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_net_wdas": {"name": "Net Foreign Exchange Auction (WDAS)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_statutory_allocations": {"name": "Statutory Allocations (FAAC, VAT, etc.)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_jv_cash_call": {"name": "Joint Venture Cash Call Payment", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_net_clearing": {"name": "Net Clearing (Lagos/Abuja)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_ndic_premium": {"name": "NDIC Premium (Debit/Credit)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_other_major_flow": {"name": "Other Major (Debit/Credit)", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    # CBN OMO auctions, aggregated per auction date (tenor field is too
    # continuous/messy for a fixed-bucket scheme like NTB's 91/182/364).
    "cbn_omo_rate_avg": {"name": "OMO Average Rate", "unit": "Percent (%)", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_omo_total_subscription": {"name": "OMO Total Subscription", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_omo_total_successful": {"name": "OMO Total Successful Bids", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_omo_amt_offered": {"name": "OMO Amount Offered", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_omo_total_repaid": {"name": "OMO Total Repaid", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cbn_omo_net_value": {"name": "OMO Net Value", "unit": "Naira Millions", "source": "CBN", "frequency": "daily", "period_months": 1},
    # Nominal GDP at current basic prices (full sector/sub-sector detail,
    # CBN GetAllNominalGDP). gdp_cp_* avoids collision with the existing
    # gdp_agriculture/etc ids, which are at constant prices -- a different
    # basis, and themselves a stale ETL leftover with no active connector.
    "gdp_cp_agriculture": {"name": "Agriculture (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_crop_production": {"name": "Crop Production (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_livestock": {"name": "Livestock (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_forestry": {"name": "Forestry (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_fishing": {"name": "Fishing (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_industry": {"name": "Industry (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_mining_and_quarrying": {"name": "Mining and Quarrying (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_crude_petroleum_and_natural_gas": {"name": "Crude Petroleum and Natural Gas (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_coal_mining": {"name": "Coal Mining (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_metal_ores": {"name": "Metal Ores (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_quarrying_and_other_minerals": {"name": "Quarrying and Other Minerals (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_manufacturing": {"name": "Manufacturing (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_oil_refining": {"name": "Oil Refining (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_cement": {"name": "Cement (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_food_beverage_and_tobacco": {"name": "Food, Beverage and Tobacco (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_textile_apparel_and_footwear": {"name": "Textile, Apparel and Footwear (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_wood_and_wood_products": {"name": "Wood and Wood Products (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_pulp_paper_and_paper_products": {"name": "Pulp, Paper and Paper Products (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_chemical_and_pharmaceutical_products": {"name": "Chemical and Pharmaceutical Products (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_non_metallic_products": {"name": "Non-Metallic Products (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_plastic_and_rubber_products": {"name": "Plastic and Rubber Products (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_electrical_and_electronics": {"name": "Electrical and Electronics (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_basic_metal_iron_and_steel": {"name": "Basic Metal, Iron and Steel (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_motor_vehicles_and_assembly": {"name": "Motor Vehicles and Assembly (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_other_manufacturing": {"name": "Other Manufacturing (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_electricity_gas_steam_and_air_con": {"name": "Electricity, Gas, Steam and Air Conditioning (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_water_supply_sewage_waste": {"name": "Water Supply, Sewage and Waste (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_construction": {"name": "Construction (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_services": {"name": "Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_trade": {"name": "Trade (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_accommodation_and_food_services": {"name": "Accommodation and Food Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_transportation_and_storage": {"name": "Transportation and Storage (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_road_transport": {"name": "Road Transport (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_rail_transport_and_pipelines": {"name": "Rail Transport and Pipelines (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_water_transport": {"name": "Water Transport (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_air_transport": {"name": "Air Transport (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_transport_services": {"name": "Transport Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_post_and_courier_services": {"name": "Post and Courier Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_information_and_communication": {"name": "Information and Communication (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_telecommunications_and_information_services": {"name": "Telecommunications and Information Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_publishing": {"name": "Publishing (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_motion_pictures_recording_music": {"name": "Motion Pictures, Sound Recording and Music Production (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_broadcasting": {"name": "Broadcasting (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_arts_entertainment_and_recreation": {"name": "Arts, Entertainment and Recreation (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_finance_and_insurance": {"name": "Finance and Insurance (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_financial_institutions": {"name": "Financial Institutions (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_insurance": {"name": "Insurance (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_real_estate": {"name": "Real Estate (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_professional_sci_and_tech_services": {"name": "Professional, Scientific and Technical Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_admin_and_support_services": {"name": "Administrative and Support Services; Business Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_public_administration": {"name": "Public Administration (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_education": {"name": "Education (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_human_health_and_social_services": {"name": "Human Health and Social Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_other_services": {"name": "Other Services (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_basic_prices": {"name": "GDP at Current Basic Prices", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_net_taxes_on_products": {"name": "Net Taxes on Products (Current Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_cp_market_prices": {"name": "GDP at Current Market Prices", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    # Real GDP at constant basic prices (full sector/sub-sector detail,
    # CBN GetAllRealGDP). 7 of these ids (gdp_agriculture, gdp_industry,
    # gdp_manufacturing, gdp_construction, gdp_trade, gdp_services,
    # gdp_telecommunicationsAndInformationServices) are pre-existing --
    # they had live observation data but no INDICATORS entry at all (same
    # gap pattern as the multicurrency/wb_* ids found earlier this
    # session). The other 50 use gdp_real_* (parallel to gdp_cp_*).
    "gdp_agriculture": {"name": "Agriculture (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_crop_production": {"name": "Crop Production (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_livestock": {"name": "Livestock (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_forestry": {"name": "Forestry (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_fishing": {"name": "Fishing (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_industry": {"name": "Industry (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_mining_and_quarrying": {"name": "Mining and Quarrying (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_crude_petroleum_and_natural_gas": {"name": "Crude Petroleum and Natural Gas (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_coal_mining": {"name": "Coal Mining (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_metal_ores": {"name": "Metal Ores (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_quarrying_and_other_minerals": {"name": "Quarrying and Other Minerals (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_manufacturing": {"name": "Manufacturing (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_oil_refining": {"name": "Oil Refining (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_cement": {"name": "Cement (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_food_beverage_and_tobacco": {"name": "Food, Beverage and Tobacco (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_textile_apparel_and_footwear": {"name": "Textile, Apparel and Footwear (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_wood_and_wood_products": {"name": "Wood and Wood Products (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_pulp_paper_and_paper_products": {"name": "Pulp, Paper and Paper Products (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_chemical_and_pharmaceutical_products": {"name": "Chemical and Pharmaceutical Products (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_non_metallic_products": {"name": "Non-Metallic Products (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_plastic_and_rubber_products": {"name": "Plastic and Rubber Products (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_electrical_and_electronics": {"name": "Electrical and Electronics (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_basic_metal_iron_and_steel": {"name": "Basic Metal, Iron and Steel (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_motor_vehicles_and_assembly": {"name": "Motor Vehicles and Assembly (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_other_manufacturing": {"name": "Other Manufacturing (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_electricity_gas_steam_and_air_con": {"name": "Electricity, Gas, Steam and Air Conditioning (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_water_supply_sewage_waste": {"name": "Water Supply, Sewage and Waste (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_construction": {"name": "Construction (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_services": {"name": "Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_trade": {"name": "Trade (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_accommodation_and_food_services": {"name": "Accommodation and Food Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_transportation_and_storage": {"name": "Transportation and Storage (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_road_transport": {"name": "Road Transport (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_rail_transport_and_pipelines": {"name": "Rail Transport and Pipelines (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_water_transport": {"name": "Water Transport (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_air_transport": {"name": "Air Transport (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_transport_services": {"name": "Transport Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_post_and_courier_services": {"name": "Post and Courier Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_information_and_communication": {"name": "Information and Communication (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_telecommunicationsAndInformationServices": {"name": "Telecommunications and Information Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_publishing": {"name": "Publishing (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_motion_pictures_recording_music": {"name": "Motion Pictures, Sound Recording and Music Production (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_broadcasting": {"name": "Broadcasting (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_arts_entertainment_and_recreation": {"name": "Arts, Entertainment and Recreation (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_finance_and_insurance": {"name": "Finance and Insurance (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_financial_institutions": {"name": "Financial Institutions (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_insurance": {"name": "Insurance (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_real_estate": {"name": "Real Estate (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_professional_sci_and_tech_services": {"name": "Professional, Scientific and Technical Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_admin_and_support_services": {"name": "Administrative and Support Services; Business Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_public_administration": {"name": "Public Administration (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_education": {"name": "Education (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_human_health_and_social_services": {"name": "Human Health and Social Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_other_services": {"name": "Other Services (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_basic_prices": {"name": "GDP at Constant Basic Prices", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_net_taxes_on_products": {"name": "Net Taxes on Products (Constant Prices)", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    "gdp_real_market_prices": {"name": "GDP at Constant Market Prices", "unit": "Naira Billions", "source": "NBS", "frequency": "quarterly", "period_months": 3},
    # CBN International Payments (monthly). "total" meant something
    # broader pre-~2007 than loc+remit+debt; captured as-is, not corrected.
    "cbn_letters_of_credit": {"name": "Letters of Credit", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_direct_remittances": {"name": "Total Direct Remittances", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_debt_service_payments": {"name": "Debt Service/Payments", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_int_payments_total": {"name": "International Payments Total", "unit": "Naira Thousands", "source": "CBN", "frequency": "monthly", "period_months": 1},
    # CBN Monthly Average Exchange Rates of the Naira (frozen source,
    # Jan 2004 - Apr 2021). cbn_usd_bdc_rate is the parallel/black-market
    # rate, not captured anywhere else on the platform.
    "cbn_usd_wdas_rate": {"name": "USD Rate (Official/WDAS, Monthly Avg)", "unit": "NGN", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_usd_ifem_rate": {"name": "USD Rate (Interbank/IFEM, Monthly Avg)", "unit": "NGN", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_usd_bdc_rate": {"name": "USD Rate (Bureau-de-Change/Parallel Market, Monthly Avg)", "unit": "NGN", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_gbp_monthly_avg": {"name": "GBP Rate (Monthly Avg)", "unit": "NGN", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_eur_monthly_avg": {"name": "EUR Rate (Monthly Avg)", "unit": "NGN", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_cfa_monthly_avg": {"name": "CFA Rate (Monthly Avg)", "unit": "NGN", "source": "CBN", "frequency": "monthly", "period_months": 1},
    # Multicurrency cross rates (CBN GetAllExchangeRates). These 33 ids already
    # existed in the live `indicators` table and had observation data from the
    # original one-time ETL, but had no INDICATORS entry here -- meaning
    # /api/v1/analytics/usd_buying 404'd as "Unknown indicator" even though the
    # data existed. dkk_* and jpy_* (Danish Krone, Yen) are genuinely new.
    "aed_buying": {"name": "UAE DIRHAM Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "aed_central": {"name": "UAE DIRHAM Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "aed_selling": {"name": "UAE DIRHAM Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cfa_buying": {"name": "CFA Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cfa_central": {"name": "CFA Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cfa_selling": {"name": "CFA Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "chf_buying": {"name": "SWISS FRANC Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "chf_central": {"name": "SWISS FRANC Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "chf_selling": {"name": "SWISS FRANC Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cny_buying": {"name": "YUAN/RENMINBI Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cny_central": {"name": "YUAN/RENMINBI Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "cny_selling": {"name": "YUAN/RENMINBI Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "dkk_buying": {"name": "DANISH KRONA Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "dkk_central": {"name": "DANISH KRONA Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "dkk_selling": {"name": "DANISH KRONA Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "eur_buying": {"name": "EURO Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "eur_central": {"name": "EURO Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "eur_selling": {"name": "EURO Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "gbp_buying": {"name": "POUNDS STERLING Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "gbp_central": {"name": "POUNDS STERLING Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "gbp_selling": {"name": "POUNDS STERLING Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "jpy_buying": {"name": "YEN Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "jpy_central": {"name": "YEN Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "jpy_selling": {"name": "YEN Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "sar_buying": {"name": "RIYAL Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "sar_central": {"name": "RIYAL Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "sar_selling": {"name": "RIYAL Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "sdr_buying": {"name": "SDR Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "sdr_central": {"name": "SDR Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "sdr_selling": {"name": "SDR Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "usd_buying": {"name": "US DOLLAR Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "usd_central": {"name": "US DOLLAR Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "usd_selling": {"name": "US DOLLAR Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "waua_buying": {"name": "WAUA Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "waua_central": {"name": "WAUA Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "waua_selling": {"name": "WAUA Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "zar_buying": {"name": "SOUTH AFRICAN RAND Buying Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "zar_central": {"name": "SOUTH AFRICAN RAND Central Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    "zar_selling": {"name": "SOUTH AFRICAN RAND Selling Rate", "unit": "NGN", "source": "CBN", "frequency": "daily", "period_months": 1},
    # NBS state-level CPI (pilot). Table-5 of NBS's monthly CPI Excel
    # reports -- 37 states (36 + FCT), Food and All-Items index each.
    # Not retroactively rebased: values jump discontinuously at NBS's
    # Nov 2024 CPI rebasing boundary, same as CBN's own inflation indices.
    "nbs_cpi_abia_food": {"name": "Abia CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_abia_all": {"name": "Abia CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_adamawa_food": {"name": "Adamawa CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_adamawa_all": {"name": "Adamawa CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_akwa_ibom_food": {"name": "Akwa Ibom CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_akwa_ibom_all": {"name": "Akwa Ibom CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_anambra_food": {"name": "Anambra CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_anambra_all": {"name": "Anambra CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_bauchi_food": {"name": "Bauchi CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_bauchi_all": {"name": "Bauchi CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_bayelsa_food": {"name": "Bayelsa CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_bayelsa_all": {"name": "Bayelsa CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_benue_food": {"name": "Benue CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_benue_all": {"name": "Benue CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_borno_food": {"name": "Borno CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_borno_all": {"name": "Borno CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_cross_river_food": {"name": "Cross River CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_cross_river_all": {"name": "Cross River CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_delta_food": {"name": "Delta CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_delta_all": {"name": "Delta CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_ebonyi_food": {"name": "Ebonyi CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_ebonyi_all": {"name": "Ebonyi CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_edo_food": {"name": "Edo CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_edo_all": {"name": "Edo CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_ekiti_food": {"name": "Ekiti CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_ekiti_all": {"name": "Ekiti CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_enugu_food": {"name": "Enugu CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_enugu_all": {"name": "Enugu CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_fct_abuja_food": {"name": "Abuja (FCT) CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_fct_abuja_all": {"name": "Abuja (FCT) CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_gombe_food": {"name": "Gombe CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_gombe_all": {"name": "Gombe CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_imo_food": {"name": "Imo CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_imo_all": {"name": "Imo CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_jigawa_food": {"name": "Jigawa CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_jigawa_all": {"name": "Jigawa CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kaduna_food": {"name": "Kaduna CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kaduna_all": {"name": "Kaduna CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kano_food": {"name": "Kano CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kano_all": {"name": "Kano CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_katsina_food": {"name": "Katsina CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_katsina_all": {"name": "Katsina CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kebbi_food": {"name": "Kebbi CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kebbi_all": {"name": "Kebbi CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kogi_food": {"name": "Kogi CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kogi_all": {"name": "Kogi CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kwara_food": {"name": "Kwara CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_kwara_all": {"name": "Kwara CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_lagos_food": {"name": "Lagos CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_lagos_all": {"name": "Lagos CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_nasarawa_food": {"name": "Nasarawa CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_nasarawa_all": {"name": "Nasarawa CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_niger_food": {"name": "Niger CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_niger_all": {"name": "Niger CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_ogun_food": {"name": "Ogun CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_ogun_all": {"name": "Ogun CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_ondo_food": {"name": "Ondo CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_ondo_all": {"name": "Ondo CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_osun_food": {"name": "Osun CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_osun_all": {"name": "Osun CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_oyo_food": {"name": "Oyo CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_oyo_all": {"name": "Oyo CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_plateau_food": {"name": "Plateau CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_plateau_all": {"name": "Plateau CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_rivers_food": {"name": "Rivers CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_rivers_all": {"name": "Rivers CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_sokoto_food": {"name": "Sokoto CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_sokoto_all": {"name": "Sokoto CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_taraba_food": {"name": "Taraba CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_taraba_all": {"name": "Taraba CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_yobe_food": {"name": "Yobe CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_yobe_all": {"name": "Yobe CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_zamfara_food": {"name": "Zamfara CPI (Food)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    "nbs_cpi_zamfara_all": {"name": "Zamfara CPI (All Items)", "unit": "Index", "source": "NBS", "frequency": "monthly", "period_months": 1},
    # DMO Total Public Debt (quarterly, back to 2012). External+Domestic
    # should sum to the Total; a document that doesn't reconcile is
    # dropped entirely by the connector rather than guessed.
    "dmo_total_external_debt_usd": {"name": "Total External Debt (USD)", "unit": "USD Millions", "source": "DMO", "frequency": "quarterly", "period_months": 3},
    "dmo_total_external_debt_ngn": {"name": "Total External Debt (NGN)", "unit": "Naira Millions", "source": "DMO", "frequency": "quarterly", "period_months": 3},
    "dmo_total_domestic_debt_usd": {"name": "Total Domestic Debt (USD)", "unit": "USD Millions", "source": "DMO", "frequency": "quarterly", "period_months": 3},
    "dmo_total_domestic_debt_ngn": {"name": "Total Domestic Debt (NGN)", "unit": "Naira Millions", "source": "DMO", "frequency": "quarterly", "period_months": 3},
    "dmo_total_public_debt_usd": {"name": "Total Public Debt (USD)", "unit": "USD Millions", "source": "DMO", "frequency": "quarterly", "period_months": 3},
    "dmo_total_public_debt_ngn": {"name": "Total Public Debt (NGN)", "unit": "Naira Millions", "source": "DMO", "frequency": "quarterly", "period_months": 3},
    # FMDQ NIBOR (Nigerian Interbank Offered Rate), daily, back to Feb
    # 2022. Confirmed distinct from CBN's own interbank-rate ids (FMDQ is
    # NIBOR's actual benchmark administrator; different values, different
    # tenors).
    "fmdq_nibor_on": {"name": "NIBOR (Overnight)", "unit": "Percent (%)", "source": "FMDQ", "frequency": "daily", "period_months": 1},
    "fmdq_nibor_1m": {"name": "NIBOR (1 Month)", "unit": "Percent (%)", "source": "FMDQ", "frequency": "daily", "period_months": 1},
    "fmdq_nibor_3m": {"name": "NIBOR (3 Month)", "unit": "Percent (%)", "source": "FMDQ", "frequency": "daily", "period_months": 1},
    "fmdq_nibor_6m": {"name": "NIBOR (6 Month)", "unit": "Percent (%)", "source": "FMDQ", "frequency": "daily", "period_months": 1},
    # Budget Office of the Federation, quarterly, back to 2009. Only
    # Revenue and Fiscal Deficit -- the two headline figures robust
    # against this report's row-label drift across years (confirmed by
    # direct inspection of 2018/2021/2026 samples before scoping down
    # from a 5-metric pilot to these 2).
    "budgetoffice_revenue_actual": {"name": "FGN Revenue (Actual, Quarterly)", "unit": "Naira Billions", "source": "Budget Office", "frequency": "quarterly", "period_months": 3},
    "budgetoffice_fiscal_deficit_actual": {"name": "FGN Fiscal Deficit (Actual, Quarterly)", "unit": "Naira Billions", "source": "Budget Office", "frequency": "quarterly", "period_months": 3},
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


_PAGE_SIZE = 1000


def _paginate(make_request, page_size: int = _PAGE_SIZE):
    """Accumulate every row from a paginated query/RPC call. This Supabase
    project caps a single response at page_size rows regardless of how the
    query is built -- confirmed live: a 3,997-row indicator (the daily oil
    series) was silently truncated to 1,000, with `latest` landing on a
    2024 date because the cutoff happens after ascending sort, dropping the
    newest rows, not the oldest. `make_request` must return a FRESH
    query/RPC builder each call (e.g. a lambda), since .range() is applied
    to -- and consumes -- one builder per page."""
    rows = []
    offset = 0
    while True:
        page = make_request().range(offset, offset + page_size - 1).execute().data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def _resolve_end(end):
    """None means "through today" -- never a hardcoded date that goes
    stale. (#37: ~20 endpoints used to default end to a literal
    2026-12-31, silently truncating data added after that date.)"""
    return end if end is not None else date.today().isoformat()


def fetch(indicator_id, start="2020-01-01", end=None):
    end = _resolve_end(end)
    key = ("series", indicator_id, start, end)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    data = _paginate(lambda: supabase.table("observations").select("obs_date,value,source")
                      .eq("indicator_id", indicator_id).gte("obs_date", start).lte("obs_date", end).order("obs_date"))
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


def fetch_as_of(indicator_id, as_of: Optional[datetime] = None):
    """The Rater's input: an indicator's full history reconstructed from the
    Ledger as it stood at `as_of` (default: now). Always the indicator's whole
    lifetime, not a caller-chosen start/end window -- percentile rank and
    move-significance are statements about where a value sits in its own full
    track record, not about an arbitrary slice of it."""
    as_of = as_of or datetime.now(timezone.utc)
    key = ("vintage", indicator_id, as_of.strftime("%Y-%m-%dT%H:%M"))
    cached = _cache_get(key)
    if cached is not None:
        return cached
    rpc_rows = _paginate(lambda: supabase.rpc("observations_as_of", {
        "p_indicator_id": indicator_id,
        "p_as_of": as_of.isoformat(),
    }))
    data = [{"obs_date": str(r["obs_date"]), "value": float(r["value"])} for r in rpc_rows]
    _cache_put(key, data)
    return data


def require_indicator(indicator_id: str):
    if indicator_id not in INDICATORS:
        allowed = ", ".join(INDICATORS.keys())
        raise HTTPException(status_code=404, detail=f"Unknown indicator. Use one of: {allowed}")
    return INDICATORS[indicator_id]


def require_concept(concept: str):
    """The Reconciler: indicators from different institutions, hand-tagged as
    describing the same real-world concept via indicators.concept. Manually
    curated, never inferred -- ambiguity tolerance here is zero."""
    rows = supabase.table("indicators").select("id,name,source").eq("concept", concept).execute().data
    if not rows:
        known_rows = supabase.table("indicators").select("concept").execute().data
        known = sorted({r["concept"] for r in known_rows if r["concept"]})
        raise HTTPException(status_code=404, detail=f"Unknown concept. Use one of: {', '.join(known)}")
    return rows


def reconcile_concept(concept: str):
    """For a concept, fetch every member indicator's full vintage-correct
    history, align by exact obs_date, and report the disagreement at each
    shared date -- never a winner, never an average."""
    members = require_concept(concept)
    series = {m["id"]: {r["obs_date"]: r["value"] for r in fetch_as_of(m["id"])} for m in members}
    common = sorted(set.intersection(*(set(s) for s in series.values())))
    if not common:
        ids = ", ".join(series)
        raise HTTPException(status_code=422, detail=f"No overlapping obs_date values between: {ids}")

    rows = []
    for d in common:
        values = {iid: series[iid][d] for iid in series}
        vals = list(values.values())
        rows.append({
            "obs_date": d,
            "values": values,
            "spread": {
                "max_minus_min": round(max(vals) - min(vals), 4),
                # Only well-defined for exactly two sources -- |a-b| is ambiguous
                # (which minus which?) once a third source joins the concept.
                "absolute": round(abs(vals[0] - vals[1]), 4) if len(vals) == 2 else None,
            },
        })
    return members, rows


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

    if not commit or not ALLOW_DATA_WRITES or supabase_write is None:
        row["action"] = "validated"
        row["committed"] = False
        row["note"] = "Demo-safe mode: row normalized but not written to the live database."
        return row

    # The Ledger: record this value as a permanent vintage *before* touching
    # observations. If this insert fails, the exception propagates and
    # observations is never written -- the two tables never drift apart.
    # Uses supabase_write (service-role key), not the read-only anon client --
    # anon has no write grant on either table as of the LOCKDOWN migration.
    supabase_write.table("observation_vintages").insert({
        "indicator_id": row["indicator_id"],
        "obs_date": row["obs_date"],
        "value": row["value"],
        "source": row["source"],
    }).execute()

    existing = (
        supabase_write.table("observations")
        .select("id")
        .eq("indicator_id", row["indicator_id"])
        .eq("obs_date", row["obs_date"])
        .limit(1)
        .execute()
    )

    if existing.data:
        supabase_write.table("observations").update({
            "value": row["value"],
            "source": row["source"],
        }).eq("indicator_id", row["indicator_id"]).eq("obs_date", row["obs_date"]).execute()
        row["action"] = "updated"
    else:
        supabase_write.table("observations").insert(row).execute()
        row["action"] = "inserted"

    row["committed"] = True
    return row


def _rater_context(indicator_id: str) -> dict:
    """The Rater: disclosed statistics on the indicator's full vintage-correct
    history (never the requested start/end window - percentile rank and
    move-significance describe where a value sits in its whole track record,
    not an arbitrary slice of it, and this must hold even when that window
    has no data of its own -- several historical CBN series added this
    session have their entire real history outside the default 2020-2026
    window). Isolated in its own try/except: a Ledger/RPC hiccup must
    degrade this one field, not take down trend/forecast/anything else."""
    try:
        vintage_values = [p["value"] for p in fetch_as_of(indicator_id)]
        refusal = forecasting.insufficient_history(len(vintage_values))
        return refusal if refusal else {
            "percentile_rank": forecasting.percentile_rank(vintage_values),
            "z_score": forecasting.z_score(vintage_values),
            "move_significance": forecasting.move_significance(vintage_values),
        }
    except Exception:
        return {"error": "context temporarily unavailable"}


def analytics_for(indicator_id: str, start: str, end: Optional[str], periods: int):
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
            "context": _rater_context(indicator_id),
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

    context = _rater_context(indicator_id)

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
        "context": context,
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
    end = _resolve_end(end)
    def _one(ind):
        key = ("series", ind, start, end)
        cached = _cache_get(key)
        if cached is not None:
            return ind, cached
        client = _thread_client()
        data = _paginate(lambda: client.table("observations").select("obs_date,value,source")
                          .eq("indicator_id", ind).gte("obs_date", start).lte("obs_date", end).order("obs_date"))
        _cache_put(key, data)
        return ind, data
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
    "gdp_current_prices": "/api/v1/gdp-current-prices",
    "gdp_real": "/api/v1/gdp-real",
    "cbn_balance_sheet": "/api/v1/cbn-balance-sheet",
    "analytics": "/api/v1/analytics",
    "leadlag": "/api/v1/leadlag?x=exchange_rate&y=inflation",
    "coverage": "/api/v1/coverage",
    "reconcile_index": "/api/v1/reconcile",
}


def _base_url(request: Request) -> str:
    """The request's own base URL, with the scheme corrected for display.

    Render terminates TLS at its own edge and forwards to this app over
    plain HTTP, so request.base_url's scheme would show "http://" unless
    something restores "https://". That used to be uvicorn's own
    --proxy-headers/--forwarded-allow-ips="*" (trusting X-Forwarded-Proto
    at the ASGI layer) -- but that flag ALSO rewrites request.client.host
    from the same trust, which the rate limiter then used as a per-IP key.
    Render appends to (doesn't replace) a client-supplied X-Forwarded-For,
    and MDN's own guidance is that no part of that header is trustworthy
    for security purposes without a verified, fixed hop count -- which
    Render doesn't document. So the two concerns are split instead: this
    reads X-Forwarded-Proto directly, for display only, and nothing in
    this codebase trusts it (or X-Forwarded-For) for identity or access
    control.
    """
    base = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto", "").lower() == "https" and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return base


def _link(request: Request, path: str) -> dict:
    return {"href": _base_url(request) + path}


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
            "/api/v1/coverage", "/api/v1/export/{indicator_id}", "/api/v1/reconcile",
            "/api/v1/reconcile/{concept}",
        ],
        "data_writes_enabled": WRITES_ACTUALLY_ENABLED,
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
cross-correlation), /reconcile (which concepts have more than one institution's figure tracked),
/reconcile/{concept} (where two institutions disagree on the same concept, at every shared date --
never a winner, never an average), /coverage, /export/{indicator_id} (CSV).
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
def get_gdp(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    return {"gdp_growth": fetch("gdp_growth", start, end), "gdp_usd": fetch("gdp_usd", start, end), "unit": "Percent and USD Billions", "source": "NBS and World Bank",
            "_links": hypermedia(request, "/api/v1/gdp", indicator="gdp_growth", related=["summary", "gdp_sectors", "coverage"])}


@app.get("/api/v1/inflation")
def get_inflation(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    return {"headline": fetch("inflation", start, end), "food": fetch("inflation_food", start, end), "core": fetch("inflation_core", start, end), "unit": "Percent year-on-year", "source": "NBS CPI Report",
            "_links": hypermedia(request, "/api/v1/inflation", indicator="inflation", related=["summary", "coverage"])}


@app.get("/api/v1/exchange-rate")
def get_exchange_rate(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    return {"data": fetch("exchange_rate", start, end), "unit": "Naira per USD", "source": "CBN Official Rate",
            "_links": hypermedia(request, "/api/v1/exchange-rate", indicator="exchange_rate", related=["summary", "nfem", "multicurrency", "coverage"])}


@app.get("/api/v1/interest-rate")
def get_interest_rate(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    return {"data": fetch("mpr", start, end), "unit": "Percent", "source": "CBN Monetary Policy Committee",
            "_links": hypermedia(request, "/api/v1/interest-rate", indicator="mpr", related=["summary", "coverage"])}


@app.get("/api/v1/fx-reserves")
def get_fx_reserves(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    return {"gross": fetch("fx_reserves", start, end), "liquid": fetch("reserves_liquid", start, end), "blocked": fetch("reserves_blocked", start, end), "block_pct": fetch("reserves_block_pct", start, end), "unit": "USD Billions", "source": "CBN",
            "_links": hypermedia(request, "/api/v1/fx-reserves", indicator="fx_reserves", related=["summary", "cbn_balance_sheet", "coverage"])}


@app.get("/api/v1/currency-circulation")
def get_currency_circulation(request: Request, start: Optional[str] = Query(default="2002-01-01"), end: Optional[str] = Query(default=None)):
    return {"data": fetch("currency_circulation_full", start, end), "unit": "Naira Millions", "source": "CBN Statistical Bulletin",
            "_links": hypermedia(request, "/api/v1/currency-circulation", indicator="currency_circulation_full", related=["summary", "cbn_balance_sheet", "coverage"])}


@app.get("/api/v1/nfem")
def get_nfem(request: Request, start: Optional[str] = Query(default="2024-12-01"), end: Optional[str] = Query(default=None)):
    fields = {
        "closing": "nfem_closing", "highest": "nfem_highest", "lowest": "nfem_lowest",
        "weighted_avg": "nfem_weighted_avg", "simple_avg": "nfem_simple_avg",
        "deals_count": "nfem_deals_count", "deals_count_interbank": "nfem_deals_count_interbank",
        "total_turnover": "nfem_total_turnover", "interbank_turnover": "nfem_interbank_turnover",
    }
    fetched = fetch_parallel(list(fields.values()), start, end)
    return {**{k: fetched[v] for k, v in fields.items()}, "unit": "NGN per USD", "source": "CBN NFEM",
            "_links": hypermedia(request, "/api/v1/nfem", indicator="nfem_closing", related=["exchange_rate", "multicurrency", "coverage"])}


@app.get("/api/v1/multicurrency")
def get_multicurrency(request: Request, currency: Optional[str] = Query(default=None), start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    currencies = ["usd", "gbp", "eur", "cny", "chf", "zar", "aed", "sar", "sdr", "cfa", "waua", "dkk", "jpy"]
    if currency and currency.lower() in currencies:
        currencies = [currency.lower()]
    rates = ["buying", "central", "selling"]
    fetched = fetch_parallel([f"{c}_{r}" for c in currencies for r in rates], start, end)
    return {"data": {c: {r: fetched[f"{c}_{r}"] for r in rates} for c in currencies}, "unit": "Naira per foreign currency unit", "source": "CBN",
            "_links": hypermedia(request, "/api/v1/multicurrency", related=["exchange_rate", "nfem", "coverage"])}


@app.get("/api/v1/gdp-sectors")
def get_gdp_sectors(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    sectors = ["gdp_agriculture", "gdp_industry", "gdp_services", "gdp_manufacturing", "gdp_telecommunicationsAndInformationServices", "gdp_construction", "gdp_trade"]
    return {"data": {s: fetch(s, start, end) for s in sectors}, "unit": "Naira Billions constant prices", "source": "NBS GDP Report",
            "_links": hypermedia(request, "/api/v1/gdp-sectors", related=["gdp", "coverage"])}


@app.get("/api/v1/gdp-current-prices")
def get_gdp_current_prices(request: Request, start: Optional[str] = Query(default="2010-01-01"), end: Optional[str] = Query(default=None)):
    """Full GDP-by-sector breakdown at current (nominal) basic prices --
    distinct from /gdp-sectors, which is at constant prices."""
    ids = ["gdp_cp_agriculture", "gdp_cp_crop_production", "gdp_cp_livestock", "gdp_cp_forestry", "gdp_cp_fishing", "gdp_cp_industry", "gdp_cp_mining_and_quarrying", "gdp_cp_crude_petroleum_and_natural_gas", "gdp_cp_coal_mining", "gdp_cp_metal_ores", "gdp_cp_quarrying_and_other_minerals", "gdp_cp_manufacturing", "gdp_cp_oil_refining", "gdp_cp_cement", "gdp_cp_food_beverage_and_tobacco", "gdp_cp_textile_apparel_and_footwear", "gdp_cp_wood_and_wood_products", "gdp_cp_pulp_paper_and_paper_products", "gdp_cp_chemical_and_pharmaceutical_products", "gdp_cp_non_metallic_products", "gdp_cp_plastic_and_rubber_products", "gdp_cp_electrical_and_electronics", "gdp_cp_basic_metal_iron_and_steel", "gdp_cp_motor_vehicles_and_assembly", "gdp_cp_other_manufacturing", "gdp_cp_electricity_gas_steam_and_air_con", "gdp_cp_water_supply_sewage_waste", "gdp_cp_construction", "gdp_cp_services", "gdp_cp_trade", "gdp_cp_accommodation_and_food_services", "gdp_cp_transportation_and_storage", "gdp_cp_road_transport", "gdp_cp_rail_transport_and_pipelines", "gdp_cp_water_transport", "gdp_cp_air_transport", "gdp_cp_transport_services", "gdp_cp_post_and_courier_services", "gdp_cp_information_and_communication", "gdp_cp_telecommunications_and_information_services", "gdp_cp_publishing", "gdp_cp_motion_pictures_recording_music", "gdp_cp_broadcasting", "gdp_cp_arts_entertainment_and_recreation", "gdp_cp_finance_and_insurance", "gdp_cp_financial_institutions", "gdp_cp_insurance", "gdp_cp_real_estate", "gdp_cp_professional_sci_and_tech_services", "gdp_cp_admin_and_support_services", "gdp_cp_public_administration", "gdp_cp_education", "gdp_cp_human_health_and_social_services", "gdp_cp_other_services", "gdp_cp_basic_prices", "gdp_cp_net_taxes_on_products", "gdp_cp_market_prices"]
    fetched = fetch_parallel(ids, start, end)
    return {"headline": {"basic_prices": fetched["gdp_cp_basic_prices"], "net_taxes_on_products": fetched["gdp_cp_net_taxes_on_products"], "market_prices": fetched["gdp_cp_market_prices"]},
            "data": {i: fetched[i] for i in ids if i not in ("gdp_cp_basic_prices", "gdp_cp_net_taxes_on_products", "gdp_cp_market_prices")},
            "unit": "Naira Billions, current prices", "source": "NBS (via CBN GetAllNominalGDP)",
            "_links": hypermedia(request, "/api/v1/gdp-current-prices", indicator="gdp_cp_basic_prices", related=["gdp", "gdp_sectors", "coverage"])}


@app.get("/api/v1/gdp-real")
def get_gdp_real(request: Request, start: Optional[str] = Query(default="2010-01-01"), end: Optional[str] = Query(default=None)):
    """Full GDP-by-sector breakdown at constant (real) basic prices --
    supersedes the partial, stale /gdp-sectors with the live source those
    7 ids were originally one-time-seeded from."""
    ids = ["gdp_agriculture", "gdp_real_crop_production", "gdp_real_livestock", "gdp_real_forestry", "gdp_real_fishing", "gdp_industry", "gdp_real_mining_and_quarrying", "gdp_real_crude_petroleum_and_natural_gas", "gdp_real_coal_mining", "gdp_real_metal_ores", "gdp_real_quarrying_and_other_minerals", "gdp_manufacturing", "gdp_real_oil_refining", "gdp_real_cement", "gdp_real_food_beverage_and_tobacco", "gdp_real_textile_apparel_and_footwear", "gdp_real_wood_and_wood_products", "gdp_real_pulp_paper_and_paper_products", "gdp_real_chemical_and_pharmaceutical_products", "gdp_real_non_metallic_products", "gdp_real_plastic_and_rubber_products", "gdp_real_electrical_and_electronics", "gdp_real_basic_metal_iron_and_steel", "gdp_real_motor_vehicles_and_assembly", "gdp_real_other_manufacturing", "gdp_real_electricity_gas_steam_and_air_con", "gdp_real_water_supply_sewage_waste", "gdp_construction", "gdp_services", "gdp_trade", "gdp_real_accommodation_and_food_services", "gdp_real_transportation_and_storage", "gdp_real_road_transport", "gdp_real_rail_transport_and_pipelines", "gdp_real_water_transport", "gdp_real_air_transport", "gdp_real_transport_services", "gdp_real_post_and_courier_services", "gdp_real_information_and_communication", "gdp_telecommunicationsAndInformationServices", "gdp_real_publishing", "gdp_real_motion_pictures_recording_music", "gdp_real_broadcasting", "gdp_real_arts_entertainment_and_recreation", "gdp_real_finance_and_insurance", "gdp_real_financial_institutions", "gdp_real_insurance", "gdp_real_real_estate", "gdp_real_professional_sci_and_tech_services", "gdp_real_admin_and_support_services", "gdp_real_public_administration", "gdp_real_education", "gdp_real_human_health_and_social_services", "gdp_real_other_services", "gdp_real_basic_prices", "gdp_real_net_taxes_on_products", "gdp_real_market_prices"]
    fetched = fetch_parallel(ids, start, end)
    return {"headline": {"basic_prices": fetched["gdp_real_basic_prices"], "net_taxes_on_products": fetched["gdp_real_net_taxes_on_products"], "market_prices": fetched["gdp_real_market_prices"]},
            "data": {i: fetched[i] for i in ids if i not in ("gdp_real_basic_prices", "gdp_real_net_taxes_on_products", "gdp_real_market_prices")},
            "unit": "Naira Billions, constant prices", "source": "NBS (via CBN GetAllRealGDP)",
            "_links": hypermedia(request, "/api/v1/gdp-real", indicator="gdp_real_basic_prices", related=["gdp", "gdp_sectors", "gdp_current_prices", "coverage"])}


@app.get("/api/v1/cbn-balance-sheet")
def get_cbn_balance_sheet(request: Request, start: Optional[str] = Query(default="2005-01-01"), end: Optional[str] = Query(default=None)):
    return {"total_assets": fetch("cbn_total_assets", start, end), "total_liabilities": fetch("cbn_total_liabilities", start, end), "gold": fetch("cbn_gold", start, end), "currency_issued": fetch("cbn_currency_issued", start, end), "unit": "Naira Thousands", "source": "CBN Balance Sheet",
            "_links": hypermedia(request, "/api/v1/cbn-balance-sheet", indicator="cbn_total_assets", related=["fx_reserves", "currency_circulation", "coverage"])}


@app.get("/api/v1/analytics")
def get_analytics(request: Request):
    inf_data = fetch("inflation", "2020-01-01", None)
    fx_data = fetch("exchange_rate", "2020-01-01", None)
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
    end: Optional[str] = Query(default=None),
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
    end: Optional[str] = Query(default=None),
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
    end: Optional[str] = Query(default=None),
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
    end: Optional[str] = Query(default=None),
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


@app.get("/api/v1/reconcile")
def list_concepts(request: Request):
    """The Reconciler's index: which concepts have more than one institution's
    figure tracked, and who tracks each one."""
    rows = supabase.table("indicators").select("concept,id,name").execute().data
    grouped: dict = {}
    for r in rows:
        if r["concept"]:
            grouped.setdefault(r["concept"], []).append({"id": r["id"], "name": r["name"]})
    return {
        "concepts": [{"concept": c, "indicators": members} for c, members in grouped.items()],
        "_links": hypermedia(request, "/api/v1/reconcile"),
    }


@app.get("/api/v1/reconcile/{concept}")
def reconcile(request: Request, concept: str):
    """The Reconciler: where two institutions report the same concept, this
    is their disagreement at every date both published a value -- never a
    winner, never an average."""
    members, rows = reconcile_concept(concept)
    return {
        "concept": concept,
        "indicators": members,
        "n": len(rows),
        "period": f"{rows[0]['obs_date']} to {rows[-1]['obs_date']}",
        "observations": rows,
        "source": ", ".join(sorted({m["source"] for m in members})),
        "_links": hypermedia(request, f"/api/v1/reconcile/{concept}", related=["reconcile_index"]),
    }


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
        a = analytics_for(iid, "2020-01-01", None, 3)
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
def get_coverage(request: Request, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    end = _resolve_end(end)  # echoed in the response below -- must be the resolved date, not None
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
def export_indicator_csv(request: Request, indicator_id: str, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default=None)):
    require_indicator(indicator_id)
    rows = fetch(indicator_id, start, end)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["indicator_id", "obs_date", "value", "source"])
    writer.writeheader()
    for row in rows:
        writer.writerow({"indicator_id": indicator_id, "obs_date": row["obs_date"], "value": row["value"], "source": row.get("source", "")})

    # A CSV body carries no JSON `_links`; hypermedia for non-JSON representations
    # goes in the RFC 8288 Link header instead, keeping the API Level 3 end to end.
    base = _base_url(request)
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
    return {"message": "Observation normalized successfully.", "write_enabled": WRITES_ACTUALLY_ENABLED, "observation": stored,
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
        "write_enabled": WRITES_ACTUALLY_ENABLED,
        "indicator_id": indicator_id,
        "rows_processed": len(stored),
        "rows_committed": sum(1 for row in stored if row.get("committed")),
        "rows": stored,
        "_links": hypermedia(request, "/api/v1/ingest/csv", indicator=indicator_id, related=["coverage"]),
    }
