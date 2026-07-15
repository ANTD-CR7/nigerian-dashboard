# NPEDATA — Defence Essentials (the parts that matter)

Condensed from the full defence pack. This is what to hold in the room: the pitch, the
demo path, the hardest questions, and the one line to close on.

- **Dashboard:** https://antd-cr7.github.io/nigerian-dashboard/
- **Open API:** https://npedata-api.onrender.com (docs at `/docs`)
- **Repo:** https://github.com/ANTD-CR7/nigerian-dashboard

---

## The one-sentence pitch
"A platform that pulls Nigeria's scattered public economic data into one standardised store,
and serves it to both people and programs — through a dashboard and a free open API."

## What it is / what it isn't (say this early — it pre-empts half the hard questions)
- **Is:** a working prototype and a controlled 2020–2026 case-study dataset; open, documented, free.
- **Isn't:** national infrastructure, a bank/fintech, real-time, and it uses **no AI/ML** — by design.
- *Line:* "A deliberate choice — a smaller, correct, trustworthy platform over a bigger one that overstates itself."

## The core contribution (one idea to land)
It's a **7-stage pipeline**, not a re-display: Collect → Validate → Standardise → Store →
Analyse → API → Present. 122 indicators, ~12,100 clean observations from CBN, NBS and World
Bank, unified in one tidy `indicators / data_sources / observations` model. The sources
publish PDFs and spreadsheets with **no API and no common schema** — the aggregation and the
machine-readable access are the contribution, not the charts.

---

## Live demo path (rehearse this exact order, ~4–5 min)
1. **Homepage** → KPI row (live), scroll to **"When the Naira fell, inflation followed"** — two aligned panels, honest separate scales.
2. **⌘K search** → "reserves" → FX Reserves. Flip the navbar **Reader → Analyst** dial: a researcher stat panel appears (range, mean, volatility, OLS trend with R² and p-value). *"One codebase adapts its depth to the stakeholder."*
3. **Analytics → Compare** → CBN Total Assets vs Currency in Circulation → the **spurious-correlation warning fires** (r = 0.81 → detrended 0.03). *"The integrity feature — it stops you drawing a false conclusion."*
4. **Analytics → Reform Impact** → the before/after-June-2023 table with a critic's reading and a supporter's reading from the **same numbers**. *"It doesn't argue either side — that neutrality is the point."* **(keep this one no matter what — it's the most memorable moment)**
5. **API** → open `/docs`, run `GET /api/v1/summary`, show the `_links` block. *"Free, documented, navigable — Level 3 HATEOAS."*

*If Wi-Fi fails:* use the offline copy (double-click `offline_backup/index.html`) or the screenshots.

---

## The questions that actually get asked

**"Isn't this just a mirror of the CBN/NBS websites?"**
No. Those sources have no API and no common schema. I built a pipeline — collection →
validation → standardisation into one relational model → analytics → an open API. The
dashboard is one output; the standardised open API the sources don't offer is the other.

**"What did you actually build vs just display?"**
A unified schema; ETL/validation that reduced 13,535 raw rows to 12,100 clean, de-duplicated
observations; a FastAPI open API with HATEOAS; and a client-side analytics engine
(correlation with significance, trend, standardisation, spurious-correlation detection)
across all 122 indicators.

**"Why no AI/ML?"**
Deliberate. The problem is access and trust, not prediction. An opaque model would work
against the core value — that every result is transparent and checkable. The analytics are
classical and reproducible on purpose.

**"How do you know your figures are correct?"**
A systematic data-truthfulness audit cross-checked every chart's numbers, ranges and units
against the database. It found and fixed real defects (a data-censoring routine, a
factor-of-1000 unit mislabel, a mistitled relationship, a year-mismatched chart). There's
also a **24-test** automated Pytest suite on the API.

**"What is HATEOAS and why bother?"**
Hypermedia As The Engine Of Application State — the top level of the Richardson Maturity
Model. Every response embeds a `_links` block, so a client can navigate the whole API from
the root without hard-coding URLs. It makes the API self-describing — a recognised marker of
a well-designed REST API, and what makes this a *platform*, not just a website.

**"Explain the spurious-correlation warning."**
Two series that both trend upward correlate even when nothing connects them. I compute the
**detrended** correlation (correlation of their month-to-month changes); if the level
correlation is high but the detrended one collapses, I warn the user. CBN assets vs
currency-in-circulation: level r = 0.81, detrended ≈ 0.03 → flagged.

**"How do you know the API is really usable, not a cosmetic green light?"**
The status pill reads the live HTTP status of a real `fetch()` — point it at a bad path and
it shows a red 404. It can't be frontend fakery: the API is on a **different origin**
(`onrender.com`) from the site (`github.io`), so CORS proves the data crossed the network.
And it has real independent consumers — the 24-test suite, the HATEOAS Explorer, `curl`, and
the Swagger UI — all returning the same cross-checkable data.

**"People say Nigeria was better off before the 2023 reforms — what does your platform say?"**
It doesn't take a side. It puts inflation, exchange rate, reserves and GDP on one timeline
with the reform dates marked, computed from the data not from opinion. A critic points to the
inflation spike and Naira depreciation; a supporter points to reserves recovering from the
$32.5B April-2024 low. Same charts, same method, same source — the platform makes the data
checkable, it doesn't settle the argument. That neutrality is itself the contribution.

**"Why this tech stack — why not React / something bigger?"**
Measured, not default (report §4.9). At this scale the no-framework frontend scores 100/100
on accessibility, has zero build complexity, and is fully View-Source-able. Where I *measured*
friction I fixed it in-stack (a 5.4s endpoint → sub-second with a TTL cache). Layers are
decoupled with documented upgrade paths. A bigger stack would have been résumé-driven.

**"Scalability / security?"**
At 12,100 rows client-side compute is fine and keeps it transparent. The Supabase key is a
public anon key gated by row-level security, read-only; write endpoints are disabled.
Server-side compute and caching are noted as future work.

**"Contribution to knowledge?"**
A free, open-source, reproducible reference implementation of a unified Nigerian
public-economic-data platform with a HATEOAS open API and a transparency-first analytics
layer — which did not previously exist in freely accessible form.

**"If you had more time?"**
Automated ETL from the source portals; seasonal adjustment and proper forecasting with
intervals; lead/lag and causality analysis; server-side compute with caching; client SDKs.

---

## Close on this
"Aggregation is the input, the API is the output, and honesty is the contract between them —
a platform that tells you when it might be misleading you." Lead with the integrity story,
and return to it at the end.
