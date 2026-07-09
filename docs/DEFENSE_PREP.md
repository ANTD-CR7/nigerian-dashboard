# NPEDATA — Project Defence Pack

Prep material for the final-year project defence. Three parts: a **slide outline** with
speaker notes, a **live-demo script**, and **anticipated questions with strong answers**.
Everything here is grounded in what the project actually does — so you can answer follow-ups
without over-claiming. Fill the `[ ]` placeholders.

- **Live dashboard:** https://antd-cr7.github.io/nigerian-dashboard/
- **Open API:** https://npedata-api.onrender.com (docs at `/docs`)
- **Repo:** https://github.com/ANTD-CR7/nigerian-dashboard

---

## PART A — Slide outline (aim for ~12–14 slides, ~10–12 min)

**Slide 1 — Title**
- Design and Development of a Nigerian Public Economic Data Aggregation and Analytics
  Platform with Open API Access: A 2020–2026 Case Study (NPEDATA). Your name, matric no., supervisor, department, date.
- *Say:* one sentence — "a platform that pulls Nigeria's scattered public economic data into
  one place and serves it to both people and programs."

**Slide 2 — The problem**
- Nigeria's economic data is real and public, but **fragmented** across CBN, NBS and World
  Bank, published in **PDFs and inconsistent spreadsheets**, with **no open API**.
- *Say:* give the concrete pain — "to study the 2023 FX reform and inflation, a researcher
  must find two datasets on two portals, reconcile date formats and units by hand, before
  any analysis. There's no single, machine-readable source."

**Slide 3 — Aim & objectives**
- Aim: aggregate the data into one standardised store, accessible via a dashboard and a free
  open API.
- The six objectives (collect → standardise → analytics → open API → dashboard → evaluate).
- *Say:* keep it to the aim + read the objectives; they map to your architecture.

**Slide 4 — Scope: what it is and isn't** *(this slide pre-empts half the hard questions)*
- **Is:** a working prototype + a controlled case-study dataset; open, documented, free.
- **Is not:** national infrastructure, a bank/fintech, real-time, and uses **no AI/ML** —
  by design.
- *Say:* "I made a deliberate choice: a smaller, correct, trustworthy platform over a bigger
  one that overstates itself."

**Slide 5 — System architecture (the 7-stage pipeline)**
- Collect → Validate → Standardise → Store → Analyse → API → Present. (Use the Mermaid
  diagram from the report.)
- *Say:* "This is the core contribution — it's a **pipeline**, not a re-display. Each number
  is collected, validated, standardised into one schema, analysed, and exposed two ways."

**Slide 6 — Data & sources**
- 122 indicators, ~12,100 observations; CBN, NBS, World Bank; the coverage table (1960–2026).
- The unified `indicators / data_sources / observations` model.
- *Say:* stress the standardisation win — "one tidy table holds daily, monthly, quarterly and
  annual series in different units, because I separated the value from its metadata."

**Slide 7 — The dashboard (live-demo cue)**
- Screenshot of the homepage flagship (the inflation/Naira small-multiples).
- *Say:* "Charts lead with meaning — an insight title, plain-language captions, and honest
  single-axis visuals." → switch to live demo (Part B).

**Slide 8 — The Open API**
- Free, no-auth REST API; auto Swagger docs; **HATEOAS (Richardson Maturity Level 3)** — every
  response embeds `_links` so the whole API is navigable from the root.
- *Say:* "This is what makes it a *platform* and not just a website — other programs can build
  on it, where the original sources have no API at all."

**Slide 9 — Analytics engine**
- Any of the 122 indicators → full profile (latest, YoY, range, volatility, trend). Compare
  any two with a correlation.
- Methods: descriptive stats, OLS trend (R²), Pearson r **with a significance p-value**,
  z-score standardisation, detrended spurious-correlation check.
- *Say:* "The analytics are inferential, not just descriptive — I report R² and a p-value, so
  you see both *strength* and *reliability*."

**Slide 10 — Integrity features (your differentiator)**
- Truthful charts (no dual-axis, no data censoring, correct units); the **spurious-correlation
  guard**; explicit "correlation ≠ causation."
- *Say:* "Most tools — even commercial ones — will happily show a misleading 0.9 correlation.
  Mine detrends it and warns you. Example: CBN assets vs currency-in-circulation shows r=0.81,
  but detrended it's 0.03 — the platform flags it as a shared trend."

**Slide 11 — Testing & validation**
- 16-test pytest suite (endpoints + HATEOAS); statistical validation (p-value vs known cases);
  a systematic data-truthfulness audit that found and fixed real defects; accessibility (WCAG
  2.1 AA).
- *Say:* "I didn't just eyeball it — I cross-checked every chart's numbers against the database
  and fixed genuine bugs, including a routine that was silently censoring data."

**Slide 12 — Limitations & future work**
- Manual collection (→ automated ETL); no seasonal adjustment; OLS forecast only (→ ARIMA);
  association not causation (→ Granger/lag); client-side compute (→ server-side + caching).
- *Say:* frame as conscious, scoped decisions — "each of these is documented and is a clear
  next step."

**Slide 13 — Contribution & conclusion**
- A free, open, reproducible reference implementation of a unified Nigerian public-economic-
  data platform with a HATEOAS open API — which did not previously exist in freely accessible
  form — built entirely with free tooling.

**Slide 14 — Thank you / Questions**

---

## PART B — Live demo script (~3–4 minutes, rehearse this exact path)

1. **Homepage** → point at the KPI row (live values), scroll to **"When the Naira fell,
   inflation followed"** — the two aligned panels. *Say:* "same timeline, honest separate
   scales — you read it top-to-bottom."
2. **⌘K / the Search box** → type "reserves" → jump to FX Reserves. *Say:* "power-user
   navigation across the whole site."
   Then flip the navbar dial **Reader → Analyst**: the page reveals a researcher-grade
   stat panel (range, mean, volatility, OLS trend with R² and p-value) under the chart.
   *Say:* "the platform adapts its depth to the stakeholder — plain language for the
   public, inferential statistics for researchers — one honest codebase, no duplicated
   pages."
3. **Analytics → "Analyze Any Indicator"** → pick a GDP sector or a CBN item. *Say:* "any of
   122 indicators, full profile computed live, correct units."
4. **Analytics → Compare** → set two obviously-trending series (CBN Total Assets vs Currency
   in Circulation) → **the spurious-correlation warning fires** (r=0.81 → detrended 0.03).
   *Say:* "this is the integrity feature — it stops you drawing a false conclusion."
5. **API** → open `https://npedata-api.onrender.com/docs`, run `GET /api/v1/summary`, show the
   `_links` block. *Say:* "free, documented, and navigable — Level 3 HATEOAS."

*Backup if Wi-Fi fails:* have screenshots of each step ready (see Part D).

---

## PART C — Anticipated questions & strong answers

**Q: "Isn't this just a dashboard — a mirror of the CBN/NBS websites?"**
A: No. The sources publish PDFs and spreadsheets with **no API and no common schema**. I
built a **pipeline**: collection → validation → standardisation into one relational model →
analytics → an open API. The dashboard is one output; the standardised open API — which the
sources don't provide — is the other. The contribution is the aggregation and the machine-
readable access, not the display.

**Q: "What did you actually build versus just display?"**
A: A unified database schema; ETL/validation that reduced 13,535 raw rows to 12,100 clean,
de-duplicated observations; a FastAPI open API with HATEOAS; and a client-side analytics
engine (correlation with significance, trend, standardisation, spurious-correlation
detection) that works across all 122 indicators.

**Q: "Why is data collection manual? Isn't that a weakness?"**
A: It's a scoped decision, and it's disclosed. Most Nigerian agencies publish no API, so
automated collection would be a project on its own. The architecture is built to accept
automated ETL later — ingestion already goes through a validation layer. The data itself is
a controlled case study, which is appropriate for an FYP.

**Q: "Why no machine learning / AI?"**
A: Deliberate. The problem is access and trust, not prediction. Adding an opaque ML model
would work against the project's core value — that every result is transparent and
checkable. The analytics are classical and reproducible on purpose.

**Q: "Why only a straight-line forecast and not ARIMA?"**
A: The forecast is explicitly labelled *illustrative, not a prediction*. A proper ARIMA/ETS
model with prediction intervals is listed as future work. I chose not to ship a forecast that
looks more authoritative than it is — that would be dishonest to a stakeholder.

**Q: "How do you know your figures are correct?"**
A: I ran a systematic data-truthfulness audit — every chart's stated numbers, ranges and
units were cross-checked against the database. It found real defects (a data-censoring
routine, unit mislabels off by a factor of a thousand, a mistitled "inverse" relationship,
a year-mismatched chart) which I traced to source and fixed. There's also a 16-test automated
suite on the API.

**Q: "What is HATEOAS and why did you bother?"**
A: Hypermedia As The Engine Of Application State — the top level of the Richardson Maturity
Model. Every JSON response embeds a `_links` block pointing to related resources, so a client
can navigate the whole API from the root without hard-coding URLs. It makes the API
self-describing and is a recognised marker of a well-designed REST API.

**Q: "Explain your spurious-correlation warning."**
A: Two series that both trend upward will show a high correlation that means nothing. I
compute the **detrended** correlation — the correlation of their month-to-month *changes* —
and if the level correlation is high but the detrended one collapses, I warn the user. E.g.
CBN assets vs currency-in-circulation: level r = 0.81, detrended r ≈ 0.03 → flagged.

**Q: "Why did you avoid dual-axis charts?"**
A: A dual axis (two y-scales on one plot) lets you fabricate a visual correlation by sliding
the scales — it's the most-criticised chart mistake. Where two series have different units I
use aligned panels or z-score standardisation on one axis, which is honest.

**Q: "How is this different from FRED or Trading Economics?"**
A: FRED is US-focused with little Nigerian granularity; Trading Economics is largely
paywalled. Neither offers this granular Nigerian data free with an open API. And my platform
adds an integrity layer — significance testing and spurious-correlation warnings — that those
consumer tools don't.

**Q: "People argue Nigeria was better off before the 2023 reforms — what does your platform say about that?"**
A: It doesn't take a side, and that's the point. The platform doesn't argue for or against the
reform — it puts inflation, the exchange rate, FX reserves and GDP on the same timeline with
the reform dates marked as event annotations, and computes the correlation and significance
directly from the data rather than from opinion. A critic of the reform can point to the
inflation spike and the Naira's depreciation after unification; a supporter can point to the
same reserves series recovering from its $32.5B low in April 2024 back to a rising trend. Both
readings are visible in the same charts, computed the same way, from the same source data —
the platform's job is to make that data checkable, not to settle the argument. That neutrality is itself the contribution: a Nigerian citizen or a policymaker on
either side of the debate can verify a specific claim against primary CBN/NBS numbers instead
of a partisan summary.

**Q: "Why hasn't the Federal Government already built something like this? Is it a legislative problem or an institutional one?"**
A: Genuinely both, and I don't think the honest answer simplifies neatly. There's a real
legislative gap: the Freedom of Information Act has legally mandated proactive publication of
this kind of public data since 2011, yet a six-organisation civil-society audit — BudgIT and
the ICIR among them — found 153 of 250 federal MDAs surveyed still scored below a basic
compliance benchmark in 2022 alone (Ogunyale & Osho, 2023). That's not an absence of law,
it's a law being routinely ignored, which points at enforcement rather than legislation as
the deeper problem. But Nigeria has closed an analogous gap before: the old data-protection
framework (NDPR, 2019) relied on NITDA — a technology agency with no legal power to penalise
anyone — to police it, and when the Nigeria Data Protection Act replaced it in 2023, it
created an independent regulator, the NDPC, with real fining and investigative powers (Falore
& Jidda, 2026). Nothing equivalent exists yet for government-data interoperability
specifically — the e-Government Interoperability Framework (Ne-GIF) is guidance, not law, and
ignoring it carries no consequence, same as the FOI Act mostly hasn't. So if there's a
legislative fix, it's probably not another framework document — Nigeria already has one — but
a body with the same enforcement teeth the NDPC got, applied specifically to interoperability.
Underneath the legislative angle, the deeper cause people who work on this describe is still
institutional: agencies treat the data they hold as leverage, and sharing it feels like giving
that up (Eleanya, 2026; Anintah, n.d.). A final-year project can't fix governance — what it
can do is remove the technical excuse, by showing the data-side problem was solvable all along
by one unfunded student in an academic year.

**Q: "Isn't your tech stack limiting? Why no React / bigger stack?"**
A: I re-evaluated the stack at the end of the build with measurements, not opinions
(report §4.9). At this scale it isn't the limit: the no-framework frontend scores 100/100
on accessibility, has zero build complexity, and any panelist can View-Source the whole
implementation; the drift risk of plain HTML is solved architecturally with one shared
library. Where I *measured* friction I fixed it inside the stack: the multi-currency
endpoint was ~5.4 s, so I added a TTL cache at the data layer — repeat responses are now
sub-second. Cold starts on the free API tier are mitigated by a keep-alive job, explicit
"waking" states, and the dashboard being architecturally independent of the API. And the
layers are decoupled, so each has a documented upgrade path — Postgres scales unchanged,
FastAPI containerises to an always-on host, and the frontend could be rebuilt in any
framework without touching the backend. Choosing a bigger stack by default would have been
résumé-driven engineering; choosing this one was a measured decision.

**Q: "What about scalability / performance / security?"**
A: At 12,100 rows, client-side computation is fine and keeps the system transparent. The
Supabase key is a public anon key gated by row-level security — read-only — so exposing it
client-side is safe; write endpoints are disabled by default. Server-side compute and caching
are noted as future work for larger scale.

**Q: "What is your contribution to knowledge?"**
A: A free, open-source, reproducible reference implementation of a unified Nigerian public-
economic-data platform with a HATEOAS open API and a transparency-first analytics layer —
an artefact that did not previously exist in freely accessible form.

**Q: "If you had more time, what would you add?"**
A: Automated ETL from the source portals; seasonal adjustment and proper time-series
forecasting with intervals; lead/lag and causality analysis; server-side compute with
caching; and client SDKs for the API.

---

## PART D — Screenshot checklist (capture these for the report figures & demo backup)

Capture at a clean, wide browser window; hide personal bookmarks.

- [ ] **Fig 4.1** — Homepage: KPI row + the "When the Naira fell, inflation followed" panels.
- [ ] **Fig 4.2** — Exchange-rate page (range selector + end-labels + crosshair on hover).
- [ ] **Fig 4.3** — Inflation page (headline/food/core comparison).
- [ ] **Fig 4.4** — Multi-currency page (central-rate line + dealing-spread panel).
- [ ] **Fig 4.5** — Assets & Liabilities (₦-trillions balance sheet + the three small-multiple panels).
- [ ] **Fig 4.6** — API docs page and the Swagger UI at `/docs`.
- [ ] **Fig 4.7** — A `GET /api/v1/summary` response showing the `_links` (HATEOAS) block.
- [ ] **Extra** — "Analyze Any Indicator" profile (stat tiles + chart).
- [ ] **Extra** — Compare tool showing the **spurious-correlation warning** (great demo moment).
- [ ] **Extra** — About page: Methodology & Limitations + Quality Assurance sections.

---

*Tip:* your single strongest, most memorable talking point is the **integrity story** —
"a platform that tells you when it might be misleading you." Lead with it, and return to it in
the conclusion.

---

## PART E — The winning narrative (creativity & innovation brief)

The judging criteria are **creativity/innovation in data aggregation** and **how the API is
used**. Map every demo moment to one of these two, explicitly. Say the criterion's words out
loud as you show the feature.

**Innovation in DATA AGGREGATION — show, don't claim:**
1. **The Aggregation Heatmap** (Data Sources page) — the whole achievement in one picture:
   122 indicators × 67 years, glowing by observation density, computed live from the
   database. *Say: "this is what aggregation means — every cell is data I collected,
   validated and standardised into one schema."*
2. **The pipeline that plays** (homepage) — the 7 stages lighting up in sequence. *Say:
   "13,535 raw rows in, 12,100 clean observations out — the de-duplication is part of the
   story, not hidden."*
3. **One schema, any frequency** — daily NFEM, monthly CPI, quarterly GDP, annual financials
   from 1960, all in one tidy observations table, all analysable by the same engine.
4. **The purchasing-power calculator** — aggregation made personally meaningful: "what
   ₦100,000 in 2020 buys today," chained from the real series with the method stated.

**Innovation in HOW THE API IS USED — three consumers, live:**
1. **Humans without docs — the HATEOAS Explorer** (API page): navigate the entire API from
   the root by clicking `_links`, live in the browser. *Say: "Richardson Maturity Level 3 —
   most commercial APIs never reach it; mine demonstrates it interactively."*
2. **Other websites — the embed widgets**: one iframe line puts a live NPEDATA chart in any
   blog or newsroom page, attribution built in. The API as infrastructure others build on.
3. **AI agents — the MCP server + llms.txt**: an AI assistant can query Nigeria's economy
   through this API as native tools, and llms.txt tells any agent what the platform offers.
   *The API is consumed by people, by websites, and by machines — that's the innovation.*

**"Make what people cannot do, done and usable" — the two capability jumps:**
1. **The Briefing Studio** (briefing.html) — nobody offers push-button, *cited*, print-ready
   Nigerian economic briefings. Pick indicators + a window → the platform composes a
   document: charts, statistics with R²/p-values, event context, APA citations, method
   notes — printable to PDF and shareable as a link that regenerates it. *Say: "the platform
   doesn't just show data; it produces defensible documents. A journalist, student or
   policymaker leaves with an artifact."*
2. **The Pipeline Playground** (playground.html) — the validation layer as a public,
   usable service. Hand the panel a broken CSV and let them watch every row get judged with
   reasons (bad date, non-numeric, duplicate, future) — live against the Open API, provably
   never written. *Say: "most projects hide their ETL; mine is an exhibit. Try to break it."*
   This is the contrarian move: the foundation itself becomes a feature.

**The closing line:** "Aggregation is the input, the API is the output, and honesty is the
contract between them — the platform serves people, other websites, and AI agents from one
open, verified dataset. And it doesn't stop at showing data: it validates yours, and writes
your briefing."
