"""
FILE: main.py

HOW TO RUN:
    pip install fastapi uvicorn supabase httpx
    uvicorn main:app --reload

Then open: http://localhost:8000/docs
"""

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from supabase import create_client, Client
from typing import Optional
from contextlib import asynccontextmanager
import asyncio
import csv
import io
import httpx
import os
from datetime import date, datetime

# Optional: set SELF_URL env var to enable a keep-alive ping (not needed on Railway)
SELF_URL = os.environ.get("SELF_URL", "https://web-production-feb5f.up.railway.app")
ALLOW_DATA_WRITES = os.environ.get("ALLOW_DATA_WRITES", "false").lower() == "true"


async def _keep_alive():
    if not SELF_URL:
        return
    await asyncio.sleep(60)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await client.get(SELF_URL + "/", timeout=10.0)
            except Exception:
                pass
            await asyncio.sleep(240)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_keep_alive())
    yield


app = FastAPI(
    title="Nigerian Financial Data Aggregation System",
    description="Aggregates, stores, analyzes and supports continuous ingestion of Nigerian public economic data. The 2020-2024 dataset is used as a reproducible case study.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend folder as static files
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")

SUPABASE_URL = "https://fjsytcmcxapfbrwvawmu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqc3l0Y21jeGFwZmJyd3Zhd211Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4OTcxOTgsImV4cCI6MjA5MTQ3MzE5OH0.0lGkBdBsY7bQGu4jlHQA0MKm54dd51QwJTdeill_ADw"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

INDICATORS = {
    "gdp_growth": {
        "name": "GDP Growth Rate",
        "unit": "Percent (%)",
        "source": "NBS",
        "frequency": "quarterly",
        "period_months": 3,
    },
    "gdp_usd": {
        "name": "Nominal GDP",
        "unit": "USD Billions",
        "source": "World Bank",
        "frequency": "annual",
        "period_months": 12,
    },
    "inflation": {
        "name": "Headline Inflation Rate",
        "unit": "Percent (%)",
        "source": "NBS",
        "frequency": "monthly",
        "period_months": 1,
    },
    "exchange_rate": {
        "name": "Exchange Rate",
        "unit": "Naira per USD",
        "source": "CBN",
        "frequency": "monthly",
        "period_months": 1,
    },
    "mpr": {
        "name": "Monetary Policy Rate",
        "unit": "Percent (%)",
        "source": "CBN",
        "frequency": "policy decision",
        "period_months": 2,
    },
}


class ObservationIn(BaseModel):
    indicator_id: str = Field(..., examples=["inflation"])
    obs_date: date = Field(..., examples=["2025-01-01"])
    value: float = Field(..., examples=[34.8])
    source: str = Field(default="MANUAL", max_length=20, examples=["MANUAL"])


def fetch(indicator_id: str, start: str, end: str):
    try:
        res = (
            supabase.table("observations")
            .select("obs_date, value, created_at")
            .eq("indicator_id", indicator_id)
            .gte("obs_date", start)
            .lte("obs_date", end)
            .order("obs_date")
            .order("created_at")
            .execute()
        )
        return dedupe_observations(res.data)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database connection failed.") from exc


def fetch_with_source(indicator_id: str, start: str, end: str):
    try:
        res = (
            supabase.table("observations")
            .select("obs_date, value, source, created_at")
            .eq("indicator_id", indicator_id)
            .gte("obs_date", start)
            .lte("obs_date", end)
            .order("obs_date")
            .order("created_at")
            .execute()
        )
        return dedupe_observations(res.data)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database connection failed.") from exc


def dedupe_observations(rows):
    by_date = {}
    for row in rows:
        cleaned = {key: value for key, value in row.items() if key != "created_at"}
        by_date[row["obs_date"]] = cleaned
    return [by_date[obs_date] for obs_date in sorted(by_date)]


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
    points = [
        {
            "obs_date": row["obs_date"],
            "value": float(row["value"]),
        }
        for row in rows
    ]

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
    latest = points[-1]
    previous = points[-2] if len(points) > 1 else None
    previous_change = None
    if previous:
        change = latest["value"] - previous["value"]
        previous_change = {
            "absolute": round(change, 4),
            "percent": round((change / previous["value"]) * 100, 2) if previous["value"] else None,
        }

    latest_date = datetime.strptime(latest["obs_date"], "%Y-%m-%d").date()
    prior_year_date = latest_date.replace(year=latest_date.year - 1).isoformat()
    prior_year = next((point for point in points if point["obs_date"] == prior_year_date), None)
    yoy_change = None
    if prior_year:
        change = latest["value"] - prior_year["value"]
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
        projected_value = latest["value"] + slope * step
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
        "latest": latest,
        "previous_change": previous_change,
        "year_over_year_change": yoy_change,
        "trend": {
            "direction": direction,
            "slope_per_period": round(slope, 4),
        },
        "forecast": forecast,
    }


@app.get("/api/gdp")
def get_gdp(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2024-12-31")
):
    return {
        "gdp_growth": fetch("gdp_growth", start, end),
        "gdp_usd":    fetch("gdp_usd",    start, end),
        "unit_growth": "Percent (%)",
        "unit_usd":    "USD Billions",
        "source":      "NBS (growth), World Bank (USD)"
    }


@app.get("/api/inflation")
def get_inflation(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2024-12-31")
):
    return {
        "data":   fetch("inflation", start, end),
        "unit":   "Percent (%)",
        "source": "NBS CPI Report"
    }


@app.get("/api/exchange-rate")
def get_exchange_rate(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2024-12-31")
):
    return {
        "data":   fetch("exchange_rate", start, end),
        "unit":   "Naira per USD",
        "source": "CBN Official Rate"
    }


@app.get("/api/interest-rate")
def get_interest_rate(
    start: Optional[str] = Query(default="2020-01-01"),
    end:   Optional[str] = Query(default="2024-12-31")
):
    return {
        "data":   fetch("mpr", start, end),
        "unit":   "Percent (%)",
        "source": "CBN Monetary Policy Committee"
    }


@app.get("/api/summary")
def get_summary():
    def latest(ind):
        try:
            res = (
                supabase.table("observations")
                .select("obs_date, value")
                .eq("indicator_id", ind)
                .order("obs_date", desc=True)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database connection failed.") from exc

    return {
        "gdp_growth":    latest("gdp_growth"),
        "inflation":     latest("inflation"),
        "exchange_rate": latest("exchange_rate"),
        "mpr":           latest("mpr"),
        "fx_reserves":   latest("fx_reserves"),
    }


@app.get("/api/coverage")
def get_coverage(
    start: Optional[str] = Query(default="2020-01-01"),
    end: Optional[str] = Query(default="2024-12-31"),
):
    indicators = []
    total_observations = 0
    sources = set()

    for indicator_id, meta in INDICATORS.items():
        rows = fetch_with_source(indicator_id, start, end)
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


@app.get("/api/fx-reserves")
def get_fx_reserves():
    data = supabase.table('observations').select('*').eq('indicator_id', 'fx_reserves').order('obs_date').execute()
    return {"data": data.data}


@app.get("/api/currency-circulation")
def get_currency_circulation():
    data = supabase.table('observations').select('*').eq('indicator_id', 'currency_circulation').order('obs_date').execute()
    return {"data": data.data}


@app.get("/api/all-currencies")
def get_all_currencies():
    currencies = ['usd', 'gbp', 'eur', 'cny', 'jpy', 'chf', 'zar', 'aed', 'sar', 'sdr', 'cfa', 'waua']
    result = {}
    for c in currencies:
        for rate in ['buying', 'central', 'selling']:
            key = f"{c}_{rate}"
            data = supabase.table('observations').select('*').eq('indicator_id', key).order('obs_date').execute()
            if c not in result:
                result[c] = {}
            result[c][rate] = data.data
    return result


@app.get("/api/analytics")
def get_analytics():
    inf = supabase.table('observations').select('*').eq('indicator_id', 'inflation').order('obs_date').execute()
    fx  = supabase.table('observations').select('*').eq('indicator_id', 'exchange_rate').order('obs_date').execute()
    res = supabase.table('observations').select('*').eq('indicator_id', 'fx_reserves').order('obs_date').execute()
    gdp = supabase.table('observations').select('*').eq('indicator_id', 'gdp_growth').order('obs_date').execute()
    mpr = supabase.table('observations').select('*').eq('indicator_id', 'mpr').order('obs_date').execute()
    return {
        "inflation":     inf.data,
        "exchange_rate": fx.data,
        "fx_reserves":   res.data,
        "gdp":           gdp.data,
        "mpr":           mpr.data,
    }


@app.get("/api/analytics/{indicator_id}")
def get_indicator_analytics(
    indicator_id: str,
    start: Optional[str] = Query(default="2020-01-01"),
    end: Optional[str] = Query(default="2024-12-31"),
    forecast_periods: int = Query(default=3, ge=1, le=12),
):
    return analytics_for(indicator_id, start, end, forecast_periods)


@app.get("/api/export/{indicator_id}")
def export_indicator_csv(
    indicator_id: str,
    start: Optional[str] = Query(default="2020-01-01"),
    end: Optional[str] = Query(default="2024-12-31"),
):
    require_indicator(indicator_id)
    rows = fetch_with_source(indicator_id, start, end)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["indicator_id", "obs_date", "value", "source"])
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "indicator_id": indicator_id,
            "obs_date": row["obs_date"],
            "value": row["value"],
            "source": row.get("source", ""),
        })

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{indicator_id}_{start}_{end}.csv"'},
    )


@app.post("/api/observations")
def append_observation(payload: ObservationIn, commit: bool = Query(default=False)):
    stored = store_observation(payload, commit=commit)
    return {
        "message": "Observation normalized successfully.",
        "write_enabled": ALLOW_DATA_WRITES,
        "observation": stored,
    }


@app.post("/api/ingest/csv")
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


@app.get("/")
def root():
    return {
        "message": "API running. Visit /docs for endpoints, /app for the dashboard.",
        "system_capabilities": [
            "multi-source aggregation",
            "appendable time-series storage",
            "trend and year-over-year analytics",
            "simple linear regression forecasting",
            "demo-safe manual and CSV ingestion endpoints",
        ],
        "data_writes_enabled": ALLOW_DATA_WRITES,
    }
