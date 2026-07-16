# NPEDATA automated collection

Connectors that pull source data into the platform's tidy shape
(`indicator_id, obs_date, value, source`), validate and de-duplicate it, and
write a **reviewable snapshot** — demo-safe by default, never touching the live
database unless explicitly enabled.

```bash
python -m collectors.runner           # -> data/collected/collected_<date>.json
python -m collectors.runner --write   # also upsert to Supabase (guarded, see below)
```

## Connectors

| Source | Status | Notes |
|--------|--------|-------|
| **World Bank** (`world_bank.py`) | ✅ live | Public API, no key. Fetches Nigeria annual series (GDP, inflation, unemployment, FDI, population…), namespaced `wb_*`. |
| **CBN** (`sources_scaffold.py`) | 🧩 scaffold | No public API — needs a PDF/Excel/HTML scraper. Interface ready. |
| **NBS** (`sources_scaffold.py`) | 🧩 scaffold | No public API — CPI/GDP published as PDFs. Interface ready. |

The CBN/NBS scaffolds are the point of the project: those agencies publish no
machine-readable API, so automating them means scraping. The framework lets a
scraper be dropped in later without changing the runner.

## Safety

Writing to the database is guarded **twice**: it requires `--write` *and*
`NPE_COLLECT_WRITE=true` *and* Supabase credentials. Otherwise the runner only
writes a local JSON snapshot for review. Uniqueness is enforced on
`(indicator_id, obs_date)` — the last value wins, matching the database rule.

## Scheduling

`.github/workflows/collect.yml` runs the collector every Monday (and on demand)
and uploads the snapshot as a build artifact. Flip the `NPE_COLLECT_WRITE`
repo variable to `true` and add the Supabase secrets to have it upsert.
