"""
FILE: main.py

HOW TO RUN:
    pip install fastapi uvicorn supabase httpx
    uvicorn main:app --reload

Then open: http://localhost:8000/docs
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from supabase import create_client, Client
from typing import Optional
from contextlib import asynccontextmanager
import asyncio
import httpx
import os

# Optional: set SELF_URL env var to enable a keep-alive ping (not needed on Railway)
SELF_URL = os.environ.get("SELF_URL", "")


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
    description="GDP, Inflation, Exchange Rate and MPR for Nigeria 2020-2024",
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


def fetch(indicator_id: str, start: str, end: str):
    res = (
        supabase.table("observations")
        .select("obs_date, value")
        .eq("indicator_id", indicator_id)
        .gte("obs_date", start)
        .lte("obs_date", end)
        .order("obs_date")
        .execute()
    )
    return res.data


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
        res = (
            supabase.table("observations")
            .select("obs_date, value")
            .eq("indicator_id", ind)
            .order("obs_date", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    return {
        "gdp_growth":    latest("gdp_growth"),
        "inflation":     latest("inflation"),
        "exchange_rate": latest("exchange_rate"),
        "mpr":           latest("mpr"),
    }


@app.get("/")
def root():
    return {"message": "API running. Visit /docs for endpoints, /app for the dashboard."}
