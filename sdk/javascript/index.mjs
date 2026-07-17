/*!
 * NPEDATA - official JavaScript/TypeScript client for the Nigerian Public
 * Economic Data API. Works in the browser and in Node 18+ (native fetch).
 *
 * Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
 * Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
 *
 *   import { NPEData } from "@npedata/client";
 *   const api = new NPEData();
 *   await api.summary();
 *   await api.inflation({ start: "2023-01-01" });
 *   await api.forecast("inflation", { periods: 6 });
 *   await api.leadlag("exchange_rate", "inflation");
 */

const DEFAULT_BASE = "https://npedata-api.onrender.com";

const SERIES = {
  summary: "/api/v1/summary",
  gdp: "/api/v1/gdp",
  inflation: "/api/v1/inflation",
  exchange_rate: "/api/v1/exchange-rate",
  interest_rate: "/api/v1/interest-rate",
  fx_reserves: "/api/v1/fx-reserves",
  currency_circulation: "/api/v1/currency-circulation",
  nfem: "/api/v1/nfem",
  multicurrency: "/api/v1/multicurrency",
  gdp_sectors: "/api/v1/gdp-sectors",
  cbn_balance_sheet: "/api/v1/cbn-balance-sheet",
};

export class NPEDataError extends Error {}

export class NPEData {
  constructor(opts = {}) {
    this.baseUrl = (opts.baseUrl || DEFAULT_BASE).replace(/\/$/, "");
    this.apiKey = opts.apiKey || null;
    this.fetch = opts.fetch || (typeof fetch !== "undefined" ? fetch.bind(globalThis) : null);
    if (!this.fetch) throw new NPEDataError("No fetch available; pass opts.fetch on old Node.");
    // convenience methods: api.inflation(), api.gdp(), ...
    for (const name of Object.keys(SERIES)) {
      this[name] = (o = {}) => this.series(name, o);
    }
  }

  async _get(path, params, raw = false) {
    let url = path.startsWith("http") ? path : this.baseUrl + path;
    if (params) {
      const q = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) if (v != null) q.append(k, v);
      const s = q.toString();
      if (s) url += (url.includes("?") ? "&" : "?") + s;
    }
    const headers = { Accept: "*/*" };
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;
    let res;
    try {
      res = await this.fetch(url, { headers });
    } catch (e) {
      throw new NPEDataError(`Network error for ${url}: ${e.message}`);
    }
    if (!res.ok) throw new NPEDataError(`${res.status} ${res.statusText} for ${url}`);
    return raw ? res.text() : res.json();
  }

  series(name, { start, end } = {}) {
    if (!SERIES[name]) throw new Error(`Unknown series '${name}'. Known: ${Object.keys(SERIES).join(", ")}`);
    return this._get(SERIES[name], { start, end });
  }

  analytics(id, { start, end, forecast_periods = 3 } = {}) {
    return this._get(`/api/v1/analytics/${id}`, { start, end, forecast_periods });
  }
  forecast(id, { periods = 6, confidence = 0.95, start, end } = {}) {
    return this._get(`/api/v1/forecast/${id}`, { periods, confidence, start, end });
  }
  decompose(id, { start, end } = {}) {
    return this._get(`/api/v1/decompose/${id}`, { start, end });
  }
  leadlag(x, y, { max_lag = 12, start, end } = {}) {
    return this._get(`/api/v1/leadlag`, { x, y, max_lag, start, end });
  }
  correlation() { return this._get("/api/v1/analytics"); }
  coverage({ start, end } = {}) { return this._get("/api/v1/coverage", { start, end }); }
  exportCsv(id, { start, end } = {}) { return this._get(`/api/v1/export/${id}`, { start, end }, true); }
  root() { return this._get("/"); }

  /** Follow a HATEOAS link from a previous response's `_links` block. */
  follow(response, rel) {
    const link = response?._links?.[rel];
    if (!link) throw new Error(`No link '${rel}'. Available: ${Object.keys(response?._links || {}).join(", ")}`);
    return this._get(link.href);
  }
}

export default NPEData;
