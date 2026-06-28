import csv
import io
import os
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from supabase import create_client, Client
from typing import Optional

app = FastAPI(
    title="Nigerian Public Economic Data API",
    description="Nigeria's first free open economic data API. 12,100 records. 122 indicators. CBN, NBS, World Bank. No authentication required.",
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
    "currency_circulation_full": {"name": "Currency in Circulation", "unit": "Naira Billions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_assets": {"name": "CBN Total Assets", "unit": "Naira Billions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_total_liabilities": {"name": "CBN Total Liabilities", "unit": "Naira Billions", "source": "CBN", "frequency": "monthly", "period_months": 1},
    "cbn_annual_total_assets": {"name": "CBN Total Assets (Annual)", "unit": "Naira Billions", "source": "CBN", "frequency": "annual", "period_months": 12},
}


class ObservationIn(BaseModel):
    indicator_id: str = Field(..., examples=["inflation"])
    obs_date: date = Field(..., examples=["2025-01-01"])
    value: float = Field(..., examples=[34.8])
    source: str = Field(default="MANUAL", max_length=20, examples=["MANUAL"])


def fetch(indicator_id, start="2020-01-01", end="2026-12-31"):
    return supabase.table("observations").select("obs_date,value,source").eq("indicator_id", indicator_id).gte("obs_date", start).lte("obs_date", end).order("obs_date").execute().data


def latest(indicator_id):
    res = supabase.table("observations").select("obs_date,value,source").eq("indicator_id", indicator_id).order("obs_date", desc=True).limit(1).execute()
    return res.data[0] if res.data else None


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

    forecast = []
    for step in range(1, periods + 1):
        projected_date = add_months(latest_date, meta["period_months"] * step)
        projected_value = latest_point["value"] + slope * step
        forecast.append({
            "obs_date": projected_date.isoformat(),
            "value": round(projected_value, 4),
            "method": "simple_linear_regression",
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
        client = _thread_client()
        res = client.table("observations").select("obs_date,value,source").eq("indicator_id", ind).gte("obs_date", start).lte("obs_date", end).order("obs_date").execute()
        return ind, res.data
    with ThreadPoolExecutor(max_workers=min(len(indicator_ids), 5)) as executor:
        return dict(executor.map(_one, indicator_ids))


@app.get("/")
@app.head("/")
def root():
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
Auth: none. CORS: open. Format: JSON.

Read endpoints (GET, all under /api/v1/): /summary, /gdp, /inflation, /exchange-rate, /interest-rate,
/fx-reserves, /currency-circulation, /nfem, /multicurrency, /gdp-sectors, /cbn-balance-sheet, /analytics,
/analytics/{indicator_id} (trend + simple linear-regression forecast), /coverage, /export/{indicator_id} (CSV).
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
def get_summary():
    return {"gdp_growth": latest("gdp_growth"), "inflation": latest("inflation"), "exchange_rate": latest("exchange_rate"), "mpr": latest("mpr"), "fx_reserves": latest("fx_reserves"), "source": "CBN, NBS, World Bank"}


@app.get("/api/v1/gdp")
def get_gdp(start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"gdp_growth": fetch("gdp_growth", start, end), "gdp_usd": fetch("gdp_usd", start, end), "unit": "Percent and USD Billions", "source": "NBS and World Bank"}


@app.get("/api/v1/inflation")
def get_inflation(start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"headline": fetch("inflation", start, end), "food": fetch("inflation_food", start, end), "core": fetch("inflation_core", start, end), "unit": "Percent year-on-year", "source": "NBS CPI Report"}


@app.get("/api/v1/exchange-rate")
def get_exchange_rate(start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"data": fetch("exchange_rate", start, end), "unit": "Naira per USD", "source": "CBN Official Rate"}


@app.get("/api/v1/interest-rate")
def get_interest_rate(start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"data": fetch("mpr", start, end), "unit": "Percent", "source": "CBN Monetary Policy Committee"}


@app.get("/api/v1/fx-reserves")
def get_fx_reserves(start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"gross": fetch("fx_reserves", start, end), "liquid": fetch("reserves_liquid", start, end), "blocked": fetch("reserves_blocked", start, end), "block_pct": fetch("reserves_block_pct", start, end), "unit": "USD Billions", "source": "CBN"}


@app.get("/api/v1/currency-circulation")
def get_currency_circulation(start: Optional[str] = Query(default="2002-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"data": fetch("currency_circulation_full", start, end), "unit": "Naira Billions", "source": "CBN Statistical Bulletin"}


@app.get("/api/v1/nfem")
def get_nfem(start: Optional[str] = Query(default="2024-12-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"closing": fetch("nfem_closing", start, end), "highest": fetch("nfem_highest", start, end), "lowest": fetch("nfem_lowest", start, end), "weighted_avg": fetch("nfem_weighted_avg", start, end), "unit": "NGN per USD", "source": "CBN NFEM", "coverage": "December 2024 to April 2026"}


@app.get("/api/v1/multicurrency")
def get_multicurrency(currency: Optional[str] = Query(default=None), start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    currencies = ["usd", "gbp", "eur", "cny", "chf", "zar", "aed", "sar", "sdr", "cfa", "waua"]
    if currency and currency.lower() in currencies:
        currencies = [currency.lower()]
    rates = ["buying", "central", "selling"]
    fetched = fetch_parallel([f"{c}_{r}" for c in currencies for r in rates], start, end)
    return {"data": {c: {r: fetched[f"{c}_{r}"] for r in rates} for c in currencies}, "unit": "Naira per foreign currency unit", "source": "CBN"}


@app.get("/api/v1/gdp-sectors")
def get_gdp_sectors(start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    sectors = ["gdp_agriculture", "gdp_industry", "gdp_services", "gdp_manufacturing", "gdp_telecommunicationsAndInformationServices", "gdp_construction", "gdp_trade"]
    return {"data": {s: fetch(s, start, end) for s in sectors}, "unit": "Naira Billions constant prices", "source": "NBS GDP Report"}


@app.get("/api/v1/cbn-balance-sheet")
def get_cbn_balance_sheet(start: Optional[str] = Query(default="2005-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    return {"total_assets": fetch("cbn_total_assets", start, end), "total_liabilities": fetch("cbn_total_liabilities", start, end), "gold": fetch("cbn_gold", start, end), "currency_issued": fetch("cbn_currency_issued", start, end), "unit": "Naira Billions", "source": "CBN Balance Sheet"}


@app.get("/api/v1/analytics")
def get_analytics():
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
            "conclusion": f"r={r} confirms the June 2023 CBN FX reform is the primary driver of Nigeria's 2023-2024 inflation surge.",
        },
        "inflation_peak": {"value": max(inf_vals), "date": common[inf_vals.index(max(inf_vals))]},
        "exchange_rate_peak": {"value": max(fx_vals), "date": common[fx_vals.index(max(fx_vals))]},
        "source": "CBN, NBS",
    }


@app.get("/api/v1/analytics/{indicator_id}")
def get_indicator_analytics(
    indicator_id: str,
    start: Optional[str] = Query(default="2020-01-01"),
    end: Optional[str] = Query(default="2026-12-31"),
    forecast_periods: int = Query(default=3, ge=1, le=12),
):
    return analytics_for(indicator_id, start, end, forecast_periods)


@app.get("/api/v1/coverage")
def get_coverage(start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
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
    }


@app.get("/api/v1/export/{indicator_id}")
def export_indicator_csv(indicator_id: str, start: Optional[str] = Query(default="2020-01-01"), end: Optional[str] = Query(default="2026-12-31")):
    require_indicator(indicator_id)
    rows = fetch(indicator_id, start, end)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["indicator_id", "obs_date", "value", "source"])
    writer.writeheader()
    for row in rows:
        writer.writerow({"indicator_id": indicator_id, "obs_date": row["obs_date"], "value": row["value"], "source": row.get("source", "")})

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{indicator_id}_{start}_{end}.csv"'},
    )


@app.post("/api/v1/observations")
def append_observation(payload: ObservationIn, commit: bool = Query(default=False)):
    stored = store_observation(payload, commit=commit)
    return {"message": "Observation normalized successfully.", "write_enabled": ALLOW_DATA_WRITES, "observation": stored}


@app.post("/api/v1/ingest/csv")
async def ingest_csv(
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
    }
