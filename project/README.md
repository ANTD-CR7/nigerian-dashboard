# NPEDATA — project assets

> **The canonical documentation lives in the [repository root README](../README.md).**
> This folder holds the platform's assets; the root README covers the architecture,
> data coverage, API reference, local setup and testing.

| Folder | Contents |
|---|---|
| `database/` | `setup.sql` (creates `indicators` / `data_sources` / `observations`) and `seed/` — the reproducible data snapshot (~12,100 observations) plus `load_seed.py` |
| `etl/` | Source-specific loaders that cleaned and standardised the raw CBN/NBS/World Bank files |
| `frontend/` | The dashboard deployed to GitHub Pages (static HTML/CSS/JS + Chart.js) |

Quick start (details in the root README):

```bash
pip install -r requirements.txt          # from the repository root
# run project/database/setup.sql in the Supabase SQL editor
python project/database/seed/load_seed.py
uvicorn main:app --reload                # API at http://127.0.0.1:8000/docs
```

The dashboard (`frontend/index.html`) reads Supabase directly and can be opened in a
browser without running the API.
