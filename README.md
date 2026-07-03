# NPEDATA — Nigerian Public Economic Data Aggregation and Analytics Platform

A web platform that aggregates **public Nigerian economic data** from multiple official
sources into one place, cleans and standardises it, stores it in a single schema, and
serves it through both an **interactive dashboard** and a **free, open REST API** (no
authentication required).

Built as a Final Year Project (BSc Computer Science) at **Caleb University, Imota, Lagos**,
by **Taoheed Abdulmanan Olaosebikan** (2026).

> **Scope note.** This is a working prototype and a controlled case-study dataset, not
> national infrastructure. It performs no AI/ML and is not a real-time market feed; data
> is collected manually from published sources and ingested via CSV/API. The value is in
> the aggregation, standardisation, analytics and open-API layers on top of that data.

---

## Live

| | URL |
|---|---|
| Dashboard | https://antd-cr7.github.io/nigerian-dashboard/ |
| Open API | https://npedata-api.onrender.com |
| API docs (Swagger) | https://npedata-api.onrender.com/docs |
| Repository | https://github.com/ANTD-CR7/nigerian-dashboard |

---

## What's inside the data

- **122 indicators**, **~12,100 observations**.
- **Sources:** Central Bank of Nigeria (CBN), National Bureau of Statistics (NBS),
  World Bank Open Data.
- **Coverage** (varies by indicator):

| Domain | Indicators | Frequency | Range | Source |
|---|---|---|---|---|
| Exchange rate (NGN/USD) | official monthly avg | monthly | 2020–2026 | CBN |
| Multi-currency | 11 currencies × buying/central/selling | monthly | 2020–2026 (AED: Jan–Apr 2026) | CBN |
| NFEM | daily closing/high/low/weighted avg + turnover | daily | Dec 2024–Apr 2026 (348 sessions) | CBN |
| Monetary Policy Rate | MPR | per MPC meeting | 2020–2025 | CBN |
| FX reserves | gross / liquid / blocked | monthly | 2020–2026 | CBN |
| CBN balance sheet | 6 line items | monthly | 2005–2023 (₦'000) | CBN |
| Annual financial statement | assets, reserves, surplus, income… | annual | 1960–2012 (₦ million) | CBN |
| Currency in circulation | total | monthly | 2002–2024 (₦ million) | CBN |
| Inflation | headline / food / core | monthly | 2003–2026 | NBS |
| GDP growth | real GDP growth rate | quarterly | 2020–2024 | NBS |
| Real GDP by sector | 57 sectors | quarterly/annual | 1981–2024 | NBS |
| Nominal GDP | USD billions | annual | 2020–2024 | World Bank |

> **Units matter.** The CBN balance-sheet series is stored in ₦'000 and the annual
> financial statement in ₦ million; the frontend converts and labels these to ₦ trillions
> for display. Do not read the raw stored numbers without their unit.

---

## Architecture — a 7-stage pipeline

```
Collect  →  Validate  →  Standardise  →  Store  →  Analyse  →  API  →  Present
 (CSV/    (schema &     (one unified   (Supabase (Pearson r, (FastAPI  (dashboard +
  Excel    type checks)  indicator/     Postgres) trend, OLS  REST +    Chart.js)
  from                   observation              forecast)   HATEOAS)
  CBN/NBS/               model)
  World Bank)
```

- **Storage model:** three tables — `indicators`, `data_sources`, `observations`
  (long/tidy: one row per indicator per date).
- **Analytics** are computed on demand (Pearson correlation, period/YoY change, trend
  direction, simple linear-regression forecast) — in the API (Python) and, for the
  compare/analytics pages, client-side in JavaScript.
- **API** follows the Richardson Maturity Model **Level 3 (HATEOAS)**: responses include
  `_links`, and CSV exports carry an RFC 8288 `Link` header.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend API | Python, **FastAPI**, Uvicorn |
| Database | **Supabase** (PostgreSQL) via `supabase-py`, public read gated by RLS |
| Frontend | Static **HTML / CSS / vanilla JS**, **Chart.js v4** (annotation + zoom plugins) |
| Hosting | Dashboard on **GitHub Pages**; API on **Render** |
| Extras | An **MCP server** (`mcp-server/`) exposing the API as tools for LLM clients |

The dashboard talks to Supabase's REST endpoint directly (public anon key, read-only via
RLS), so it works without the FastAPI server running. The FastAPI service is the separate,
documented **Open API** for programmatic consumers.

---

## Project structure

```
.
├── main.py                     # FastAPI app — the canonical Open API
├── render.yaml, Procfile       # Render deployment config
├── requirements.txt            # API runtime deps
├── requirements-dev.txt        # test deps (pytest)
├── .env.example                # SUPABASE_URL / SUPABASE_KEY / ALLOW_DATA_WRITES
├── tests/
│   └── test_main.py            # pytest unit tests (endpoints + HATEOAS)
├── mcp-server/                 # Model Context Protocol server wrapping the API
├── project/
│   ├── database/
│   │   ├── setup.sql           # creates indicators / data_sources / observations
│   │   └── seed/               # reproducible snapshot + loader
│   │       ├── indicators.csv
│   │       ├── data_sources.csv
│   │       ├── observations.csv   # ~12,100 rows
│   │       └── load_seed.py
│   ├── etl/                    # source-specific loaders (GDP, other indicators)
│   └── frontend/               # the dashboard (deployed to GitHub Pages)
│       ├── index.html          # homepage + KPIs + "how it works" pipeline
│       ├── gdp / inflation / interest_rate / exchange_rate / reserves …
│       ├── multicurrency / nfem / currency_circulation / assets_liabilities /
│       │   financial_statement / currency_converter
│       ├── analytics / compare / api_docs / about / data_sources / status
│       ├── shared.js           # nav, chart helpers, terminal chart plugins
│       └── style.css           # "Lagos Noir" design system
```

---

## Run it locally

**Prerequisites:** Python 3.10+, a Supabase project (free tier is fine).

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env      # then set SUPABASE_URL and SUPABASE_KEY

# 3. Create the tables — run project/database/setup.sql in the Supabase SQL Editor

# 4. Load the reproducible data snapshot (~12,100 observations)
python project/database/seed/load_seed.py

# 5. Start the API
uvicorn main:app --reload
#   → http://127.0.0.1:8000        (API root, with HATEOAS links)
#   → http://127.0.0.1:8000/docs   (interactive Swagger UI)
```

**Frontend:** open `project/frontend/index.html` in a browser — it reads Supabase
directly, so no local server is required.

**Production API is started with proxy headers so HATEOAS links honour HTTPS:**
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```

---

## API reference

Base URL: `https://npedata-api.onrender.com` · All responses JSON with a `_links` block.

| Method | Path | Description |
|---|---|---|
| GET | `/` | API index / entry point (hypermedia links) |
| GET | `/api/v1/summary` | Latest value for the 5 headline indicators |
| GET | `/api/v1/gdp` | Quarterly GDP growth |
| GET | `/api/v1/inflation` | Headline inflation series |
| GET | `/api/v1/exchange-rate` | NGN/USD monthly average |
| GET | `/api/v1/interest-rate` | Monetary Policy Rate |
| GET | `/api/v1/fx-reserves` | Gross / liquid / blocked reserves |
| GET | `/api/v1/currency-circulation` | Currency in circulation |
| GET | `/api/v1/nfem` | NFEM daily rates |
| GET | `/api/v1/multicurrency` | 11-currency buying/central/selling (`?currency=`) |
| GET | `/api/v1/gdp-sectors` | Real GDP by sector |
| GET | `/api/v1/cbn-balance-sheet` | CBN balance-sheet items |
| GET | `/api/v1/analytics` | Pearson correlation: inflation vs exchange rate |
| GET | `/api/v1/analytics/{indicator_id}` | Latest, period & YoY change, trend, OLS forecast |
| GET | `/api/v1/coverage` | Observation counts, date ranges, sources per indicator |
| GET | `/api/v1/export/{indicator_id}` | Export one indicator as CSV |
| POST | `/api/v1/observations` | Validate one normalised observation* |
| POST | `/api/v1/ingest/csv` | Validate a CSV of `obs_date,value,source`* |

\* **Demo-safe by default.** Ingestion endpoints validate and normalise but do **not**
write to the live database unless the server runs with `ALLOW_DATA_WRITES=true` **and**
the request sends `commit=true`.

Example:
```bash
curl https://npedata-api.onrender.com/api/v1/analytics/inflation
curl https://npedata-api.onrender.com/api/v1/export/exchange_rate -o exchange_rate.csv
```

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest -q            # endpoint + HATEOAS unit tests in tests/test_main.py
```

---

## Deployment

- **Dashboard →** GitHub Pages via `.github/workflows/deploy.yml` (publishes
  `project/frontend/` on every push to `main`).
- **API →** Render (`render.yaml` / `Procfile`). A `keep-alive.yml` workflow pings the
  free-tier service so it doesn't cold-sleep.

---

## Honest limitations

- **Prototype, not production infrastructure.** A single-maintainer FYP.
- **Manual collection.** Source data is downloaded from CBN/NBS/World Bank publications and
  ingested; there is no automated live scraper.
- **Not real-time.** Figures are as fresh as the last ingested snapshot.
- **No AI/ML.** "Analytics" means classical statistics (correlation, OLS trend/forecast).
- **Public read-only data.** The Supabase anon key is public and gated by RLS; writes are
  disabled unless explicitly enabled.

---

## Author

**Taoheed Abdulmanan Olaosebikan** — BSc Computer Science, Caleb University, Imota, Lagos.
Final Year Project, 2026.

Data © their respective sources (CBN, NBS, World Bank). This project aggregates and
re-presents publicly available data for research and educational use.
