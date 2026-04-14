"""
FILE: backend/main.py

PURPOSE:
    This is the FastAPI backend server. It receives requests from the
    web browser (frontend), queries the Supabase database, and returns
    data as JSON.

WHAT THIS FILE DOES:
    - Connects to Supabase
    - Defines 6 API endpoints (URLs the frontend calls)
    - Each endpoint runs a database query and returns the results

HOW TO RUN:
    pip install fastapi uvicorn supabase
    uvicorn main:app --reload

    Then open your browser at: http://localhost:8000/docs
    You will see all your API endpoints listed there automatically.

ENDPOINTS:
    GET /api/gdp            - GDP growth rate and nominal GDP in USD
    GET /api/inflation      - Monthly headline inflation rate
    GET /api/exchange-rate  - Monthly average NGN/USD exchange rate
    GET /api/interest-rate  - CBN MPR at each MPC decision date
    GET /api/summary        - Latest values for all 4 indicators at once
    GET /docs               - Auto-generated Swagger API documentation
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from typing import Optional

# ============================================================
# STEP 1: Create the FastAPI app
# The title and description appear in the /docs page
# ============================================================
app = FastAPI(
    title="Nigerian Financial Data Aggregation System",
    description="Aggregates GDP, inflation, exchange rate and MPR data from CBN, NBS and World Bank for 2020-2024",
    version="1.0.0"
)

# ============================================================
# STEP 2: Allow the frontend to call this API
# CORS (Cross-Origin Resource Sharing) means the browser
# is allowed to call this server from a different address.
# allow_origins=["*"] means allow all origins (fine for this project)
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# STEP 3: Connect to Supabase
# Replace these with your actual credentials
# ============================================================
SUPABASE_URL = "https://fjsytcmcxapfbrwvawmu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqc3l0Y21jeGFwZmJyd3Zhd211Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4OTcxOTgsImV4cCI6MjA5MTQ3MzE5OH0.0lGkBdBsY7bQGu4jlHQA0MKm54dd51QwJTdeill_ADw"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# HELPER FUNCTION
# This queries the observations table for a specific indicator
# and returns all rows between start_date and end_date
# ============================================================
def fetch_data(indicator_id: str, start_date: str, end_date: str):
    """
    Query Supabase for observations of a given indicator
    within the specified date range.
    Returns a list of dicts: [{obs_date, value}, ...]
    """
    response = (
        supabase.table("observations")
        .select("obs_date, value")
        .eq("indicator_id", indicator_id)
        .gte("obs_date", start_date)
        .lte("obs_date", end_date)
        .order("obs_date")
        .execute()
    )
    return response.data


# ============================================================
# ENDPOINT 1: GDP Growth Rate
# URL: GET /api/gdp
# Query params: from (default 2020-01-01), to (default 2024-12-31)
# Returns: quarterly GDP growth rate % AND annual nominal GDP in USD
# ============================================================
@app.get("/api/gdp")
def get_gdp(
    start: Optional[str] = Query(default="2020-01-01", description="Start date YYYY-MM-DD"),
    end:   Optional[str] = Query(default="2024-12-31", description="End date YYYY-MM-DD")
):
    """
    Returns quarterly real GDP growth rate (%) and annual nominal
    GDP in USD billions for Nigeria, for the specified date range.
    """
    growth = fetch_data("gdp_growth", start, end)
    usd    = fetch_data("gdp_usd",    start, end)

    return {
        "indicator":    "GDP",
        "gdp_growth":   growth,   # quarterly, percent
        "gdp_usd":      usd,      # annual, USD billions
        "unit_growth":  "Percent (%)",
        "unit_usd":     "USD Billions",
        "source":       "NBS (growth rate), World Bank (USD value)"
    }


# ============================================================
# ENDPOINT 2: Inflation Rate
# URL: GET /api/inflation
# Returns: monthly headline inflation rate %
# ============================================================
@app.get("/api/inflation")
def get_inflation(
    start: Optional[str] = Query(default="2020-01-01", description="Start date YYYY-MM-DD"),
    end:   Optional[str] = Query(default="2024-12-31", description="End date YYYY-MM-DD")
):
    """
    Returns monthly headline inflation rate (%) for Nigeria.
    Source: NBS Consumer Price Index (allItemsYearOn column).
    """
    data = fetch_data("inflation", start, end)

    return {
        "indicator": "Headline Inflation Rate",
        "data":      data,
        "unit":      "Percent (%)",
        "source":    "NBS CPI Report"
    }


# ============================================================
# ENDPOINT 3: Exchange Rate
# URL: GET /api/exchange-rate
# Returns: monthly average NGN/USD exchange rate
# ============================================================
@app.get("/api/exchange-rate")
def get_exchange_rate(
    start: Optional[str] = Query(default="2020-01-01", description="Start date YYYY-MM-DD"),
    end:   Optional[str] = Query(default="2024-12-31", description="End date YYYY-MM-DD")
):
    """
    Returns monthly average NGN/USD exchange rate.
    Source: CBN official daily rates, averaged to monthly.
    """
    data = fetch_data("exchange_rate", start, end)

    return {
        "indicator": "Exchange Rate (NGN/USD)",
        "data":      data,
        "unit":      "Naira per US Dollar",
        "source":    "CBN Official Rate"
    }


# ============================================================
# ENDPOINT 4: Monetary Policy Rate (MPR)
# URL: GET /api/interest-rate
# Returns: MPR at each MPC decision date
# ============================================================
@app.get("/api/interest-rate")
def get_interest_rate(
    start: Optional[str] = Query(default="2020-01-01", description="Start date YYYY-MM-DD"),
    end:   Optional[str] = Query(default="2024-12-31", description="End date YYYY-MM-DD")
):
    """
    Returns the CBN Monetary Policy Rate (%) at each MPC meeting date.
    Source: CBN MPC decisions and communiques.
    """
    data = fetch_data("mpr", start, end)

    return {
        "indicator": "Monetary Policy Rate (MPR)",
        "data":      data,
        "unit":      "Percent (%)",
        "source":    "CBN Monetary Policy Committee"
    }


# ============================================================
# ENDPOINT 5: Summary
# URL: GET /api/summary
# Returns: the most recent value for ALL four indicators
# This is used by the home dashboard page
# ============================================================
@app.get("/api/summary")
def get_summary():
    """
    Returns the latest available value for all four indicators.
    Used by the dashboard home page to populate the summary cards.
    """
    def latest(indicator_id: str):
        response = (
            supabase.table("observations")
            .select("obs_date, value")
            .eq("indicator_id", indicator_id)
            .order("obs_date", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    return {
        "gdp_growth":    latest("gdp_growth"),
        "inflation":     latest("inflation"),
        "exchange_rate": latest("exchange_rate"),
        "mpr":           latest("mpr"),
    }


# ============================================================
# ENDPOINT 6: Health check
# URL: GET /
# Returns: simple message to confirm the API is running
# ============================================================
@app.get("/")
def root():
    return {
        "message": "Nigerian Financial Data Aggregation System API",
        "status":  "running",
        "docs":    "/docs"
    }
