"""NPEDATA - official Python client for the Nigerian Public Economic Data API.

Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966

Zero external dependencies (standard library only). A pandas helper is offered
when pandas happens to be installed.

    from npedata import NPEData
    api = NPEData()
    api.summary()                          # headline indicators
    api.inflation(start="2023-01-01")      # a named series
    api.forecast("inflation", periods=6)   # Holt-Winters + 95% intervals
    api.leadlag("exchange_rate", "inflation")
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

__version__ = "1.0.0"
__author__ = "Taoheed Abdulmanan Olaosebikan"

DEFAULT_BASE = "https://npedata-api.onrender.com"


class NPEDataError(RuntimeError):
    """Raised when the API returns a non-2xx response."""


class NPEData:
    """A thin, typed-ish wrapper over the NPEDATA REST API."""

    #: named data endpoints -> path
    _SERIES = {
        "summary": "/api/v1/summary",
        "gdp": "/api/v1/gdp",
        "inflation": "/api/v1/inflation",
        "exchange_rate": "/api/v1/exchange-rate",
        "interest_rate": "/api/v1/interest-rate",
        "fx_reserves": "/api/v1/fx-reserves",
        "currency_circulation": "/api/v1/currency-circulation",
        "nfem": "/api/v1/nfem",
        "multicurrency": "/api/v1/multicurrency",
        "gdp_sectors": "/api/v1/gdp-sectors",
        "cbn_balance_sheet": "/api/v1/cbn-balance-sheet",
    }

    def __init__(self, base_url: str = DEFAULT_BASE, api_key: str | None = None,
                 timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # ---- low level ------------------------------------------------------- #
    def _get(self, path: str, params: dict | None = None, raw: bool = False):
        url = path if path.startswith("http") else self.base_url + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(clean)
        req = urllib.request.Request(url, headers={"Accept": "*/*",
                                                   "User-Agent": f"npedata-python/{__version__}"})
        if self.api_key:
            req.add_header("X-API-Key", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise NPEDataError(f"{e.code} {e.reason} for {url}: {e.read().decode('utf-8', 'ignore')[:200]}")
        except urllib.error.URLError as e:
            raise NPEDataError(f"Network error for {url}: {e.reason}")
        except (TimeoutError, OSError) as e:
            raise NPEDataError(f"Request failed for {url}: {e}")
        return body if raw else json.loads(body)

    # ---- named series ---------------------------------------------------- #
    def series(self, name: str, start: str | None = None, end: str | None = None) -> dict:
        """Fetch a named data endpoint (see NPEData._SERIES)."""
        if name not in self._SERIES:
            raise KeyError(f"Unknown series '{name}'. Known: {', '.join(self._SERIES)}")
        return self._get(self._SERIES[name], {"start": start, "end": end})

    def __getattr__(self, name):
        # api.inflation(...) -> api.series("inflation", ...)
        if name in type(self)._SERIES:
            def _series(start=None, end=None, _n=name):
                return self.series(_n, start, end)
            return _series
        raise AttributeError(name)

    # ---- analytics ------------------------------------------------------- #
    def analytics(self, indicator_id: str, start=None, end=None, forecast_periods=3) -> dict:
        return self._get(f"/api/v1/analytics/{indicator_id}",
                         {"start": start, "end": end, "forecast_periods": forecast_periods})

    def forecast(self, indicator_id: str, periods: int = 6, confidence: float = 0.95,
                 start=None, end=None) -> dict:
        """Holt-Winters forecast with prediction intervals."""
        return self._get(f"/api/v1/forecast/{indicator_id}",
                         {"periods": periods, "confidence": confidence, "start": start, "end": end})

    def decompose(self, indicator_id: str, start=None, end=None) -> dict:
        """Additive seasonal decomposition (trend + seasonal + residual)."""
        return self._get(f"/api/v1/decompose/{indicator_id}", {"start": start, "end": end})

    def leadlag(self, x: str, y: str, max_lag: int = 12, start=None, end=None) -> dict:
        """Lead/lag cross-correlation between two indicators."""
        return self._get("/api/v1/leadlag",
                         {"x": x, "y": y, "max_lag": max_lag, "start": start, "end": end})

    def correlation(self) -> dict:
        return self._get("/api/v1/analytics")

    def coverage(self, start=None, end=None) -> dict:
        return self._get("/api/v1/coverage", {"start": start, "end": end})

    def export_csv(self, indicator_id: str, start=None, end=None) -> str:
        """Return the raw CSV text for an indicator."""
        return self._get(f"/api/v1/export/{indicator_id}", {"start": start, "end": end}, raw=True)

    # ---- HATEOAS --------------------------------------------------------- #
    def root(self) -> dict:
        return self._get("/")

    def follow(self, response: dict, rel: str) -> dict:
        """Follow a hypermedia link from a previous response's `_links` block."""
        links = response.get("_links", {})
        if rel not in links:
            raise KeyError(f"No link '{rel}'. Available: {', '.join(links)}")
        return self._get(links[rel]["href"])

    # ---- convenience ----------------------------------------------------- #
    def to_dataframe(self, indicator_id: str, start=None, end=None):
        """Return an indicator's observations as a pandas DataFrame (pandas
        must be installed). Uses the CSV export endpoint."""
        try:
            import io
            import pandas as pd
        except ImportError as e:  # pragma: no cover
            raise ImportError("to_dataframe requires pandas (pip install pandas)") from e
        return pd.read_csv(io.StringIO(self.export_csv(indicator_id, start, end)),
                           parse_dates=["obs_date"])
