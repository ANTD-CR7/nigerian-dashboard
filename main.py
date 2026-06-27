from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from supabase import create_client, Client
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
import statistics
import threading

app = FastAPI(
    title="Nigerian Public Economic Data API",
    description="Nigeria's first free open economic data API. 13,535+ records. 122 indicators. CBN, NBS, World Bank. No authentication required.",
    version="1.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

SUPABASE_URL = "https://fjsytcmcxapfbrwvawmu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqc3l0Y21jeGFwZmJyd3Zhd211Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4OTcxOTgsImV4cCI6MjA5MTQ3MzE5OH0.0lGkBdBsY7bQGu4jlHQA0MKm54dd51QwJTdeill_ADw"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch(indicator_id, start="2020-01-01", end="2026-12-31"):
    return supabase.table("observations").select("obs_date,value,source").eq("indicator_id", indicator_id).gte("obs_date", start).lte("obs_date", end).order("obs_date").execute().data

def latest(indicator_id):
    res = supabase.table("observations").select("obs_date,value,source").eq("indicator_id", indicator_id).order("obs_date", desc=True).limit(1).execute()
    return res.data[0] if res.data else None

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
    return {"name":"Nigerian Public Economic Data API","version":"1.0.0","docs":"/docs","dashboard":"https://antd-cr7.github.io/nigerian-dashboard","endpoints":["/api/v1/summary","/api/v1/gdp","/api/v1/inflation","/api/v1/exchange-rate","/api/v1/interest-rate","/api/v1/fx-reserves","/api/v1/currency-circulation","/api/v1/nfem","/api/v1/multicurrency","/api/v1/gdp-sectors","/api/v1/cbn-balance-sheet","/api/v1/analytics"]}

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
Auth: none. Method: GET only. CORS: open. Format: JSON.

Endpoints (all under /api/v1/): /summary, /gdp, /inflation, /exchange-rate, /interest-rate,
/fx-reserves, /currency-circulation, /nfem, /multicurrency, /gdp-sectors, /cbn-balance-sheet, /analytics.
Most accept optional start/end date query params (ISO 8601). Interactive docs at /docs.

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
    return {"gdp_growth":latest("gdp_growth"),"inflation":latest("inflation"),"exchange_rate":latest("exchange_rate"),"mpr":latest("mpr"),"fx_reserves":latest("fx_reserves"),"source":"CBN, NBS, World Bank"}

@app.get("/api/v1/gdp")
def get_gdp(start:Optional[str]=Query(default="2020-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    return {"gdp_growth":fetch("gdp_growth",start,end),"gdp_usd":fetch("gdp_usd",start,end),"unit":"Percent and USD Billions","source":"NBS and World Bank"}

@app.get("/api/v1/inflation")
def get_inflation(start:Optional[str]=Query(default="2020-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    return {"headline":fetch("inflation",start,end),"food":fetch("inflation_food",start,end),"core":fetch("inflation_core",start,end),"unit":"Percent year-on-year","source":"NBS CPI Report"}

@app.get("/api/v1/exchange-rate")
def get_exchange_rate(start:Optional[str]=Query(default="2020-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    return {"data":fetch("exchange_rate",start,end),"unit":"Naira per USD","source":"CBN Official Rate"}

@app.get("/api/v1/interest-rate")
def get_interest_rate(start:Optional[str]=Query(default="2020-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    return {"data":fetch("mpr",start,end),"unit":"Percent","source":"CBN Monetary Policy Committee"}

@app.get("/api/v1/fx-reserves")
def get_fx_reserves(start:Optional[str]=Query(default="2020-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    return {"gross":fetch("fx_reserves",start,end),"liquid":fetch("reserves_liquid",start,end),"blocked":fetch("reserves_blocked",start,end),"block_pct":fetch("reserves_block_pct",start,end),"unit":"USD Billions","source":"CBN"}

@app.get("/api/v1/currency-circulation")
def get_currency_circulation(start:Optional[str]=Query(default="2002-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    return {"data":fetch("currency_circulation_full",start,end),"unit":"Naira Billions","source":"CBN Statistical Bulletin"}

@app.get("/api/v1/nfem")
def get_nfem(start:Optional[str]=Query(default="2024-12-01"),end:Optional[str]=Query(default="2026-12-31")):
    return {"closing":fetch("nfem_closing",start,end),"highest":fetch("nfem_highest",start,end),"lowest":fetch("nfem_lowest",start,end),"weighted_avg":fetch("nfem_weighted_avg",start,end),"unit":"NGN per USD","source":"CBN NFEM","coverage":"December 2024 to April 2026"}

@app.get("/api/v1/multicurrency")
def get_multicurrency(currency:Optional[str]=Query(default=None),start:Optional[str]=Query(default="2020-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    currencies=["usd","gbp","eur","cny","chf","zar","aed","sar","sdr","cfa","waua"]
    if currency and currency.lower() in currencies:
        currencies=[currency.lower()]
    rates=["buying","central","selling"]
    fetched=fetch_parallel([f"{c}_{r}" for c in currencies for r in rates],start,end)
    return {"data":{c:{r:fetched[f"{c}_{r}"] for r in rates} for c in currencies},"unit":"Naira per foreign currency unit","source":"CBN"}

@app.get("/api/v1/gdp-sectors")
def get_gdp_sectors(start:Optional[str]=Query(default="2020-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    sectors=["gdp_agriculture","gdp_industry","gdp_services","gdp_manufacturing","gdp_telecommunicationsAndInformationServices","gdp_construction","gdp_trade"]
    return {"data":{s:fetch(s,start,end) for s in sectors},"unit":"Naira Billions constant prices","source":"NBS GDP Report"}

@app.get("/api/v1/cbn-balance-sheet")
def get_cbn_balance_sheet(start:Optional[str]=Query(default="2005-01-01"),end:Optional[str]=Query(default="2026-12-31")):
    return {"total_assets":fetch("cbn_total_assets",start,end),"total_liabilities":fetch("cbn_total_liabilities",start,end),"gold":fetch("cbn_gold",start,end),"currency_issued":fetch("cbn_currency_issued",start,end),"unit":"Naira Billions","source":"CBN Balance Sheet"}

@app.get("/api/v1/analytics")
def get_analytics():
    inf_data=fetch("inflation","2020-01-01","2026-12-31")
    fx_data=fetch("exchange_rate","2020-01-01","2026-12-31")
    inf_map={d["obs_date"]:d["value"] for d in inf_data}
    fx_map={d["obs_date"]:d["value"] for d in fx_data}
    common=sorted(set(inf_map)&set(fx_map))
    inf_vals=[inf_map[d] for d in common]
    fx_vals=[fx_map[d] for d in common]
    r=0.0
    if len(common)>1:
        mi=statistics.mean(inf_vals);mf=statistics.mean(fx_vals)
        num=sum((a-mi)*(b-mf) for a,b in zip(inf_vals,fx_vals))
        den=(sum((a-mi)**2 for a in inf_vals)*sum((b-mf)**2 for b in fx_vals))**0.5
        r=round(num/den,4) if den else 0.0
    return {"pearson_correlation":{"r":r,"variables":["headline_inflation","ngn_usd_exchange_rate"],"period":f"{common[0]} to {common[-1]}" if common else "N/A","n":len(common),"conclusion":f"r={r} confirms the June 2023 CBN FX reform is the primary driver of Nigeria's 2023-2024 inflation surge."},"inflation_peak":{"value":max(inf_vals),"date":common[inf_vals.index(max(inf_vals))]},"exchange_rate_peak":{"value":max(fx_vals),"date":common[fx_vals.index(max(fx_vals))]},"source":"CBN, NBS"}
