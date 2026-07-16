# NPEDATA SDKs

Official client libraries for the [NPEDATA](https://antd-cr7.github.io/nigerian-dashboard/)
open API — Nigerian public economic data (CBN, NBS, World Bank) with forecasting and
statistical-integrity analytics. No API key required for reads.

- **Base URL:** `https://npedata-api.onrender.com`
- **Interactive docs:** `/docs`
- **License:** Apache-2.0 · © 2026 Taoheed Abdulmanan Olaosebikan

---

## Python  (`sdk/python`)

Zero dependencies (standard library only).

```bash
pip install ./sdk/python          # local install
```

```python
from npedata import NPEData

api = NPEData()

api.summary()                              # headline indicators
api.inflation(start="2023-01-01")          # any named series
api.forecast("inflation", periods=6)       # Holt-Winters + 95% intervals
api.decompose("inflation")                 # trend + seasonal + residual
api.leadlag("exchange_rate", "inflation")  # does FX lead inflation?

# HATEOAS: follow links returned by the API
s = api.summary()
api.follow(s, "gdp")

# pandas (optional):  pip install "npedata[pandas]"
df = api.to_dataframe("inflation", start="2020-01-01")
```

## JavaScript / TypeScript  (`sdk/javascript`)

Works in the browser and Node 18+ (native `fetch`). Ships TypeScript types.

```js
import { NPEData } from "@npedata/client";

const api = new NPEData();

await api.summary();
await api.inflation({ start: "2023-01-01" });
await api.forecast("inflation", { periods: 6 });   // Holt-Winters + 95% band
await api.leadlag("exchange_rate", "inflation");

// HATEOAS
const s = await api.summary();
await api.follow(s, "gdp");
```

Both clients cover every read endpoint: `summary`, the named series (gdp, inflation,
exchange_rate, interest_rate, fx_reserves, currency_circulation, nfem, multicurrency,
gdp_sectors, cbn_balance_sheet), `analytics`, `forecast`, `decompose`, `leadlag`,
`coverage`, `export` (CSV), plus `root()` and `follow()` for hypermedia navigation.
Pass `apiKey` in the constructor once key-gated tiers are enabled.
