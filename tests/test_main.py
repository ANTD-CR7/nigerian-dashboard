"""
Unit tests for the pure validation/analytics logic in the root main.py
API. Network calls to Supabase are monkeypatched out so these run
offline and fast -- they check the math and validation rules, not
connectivity.
"""

import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main


def test_add_months_handles_year_rollover():
    assert main.add_months(date(2024, 11, 1), 3) == date(2025, 2, 1)


def test_add_months_clamps_day_to_28():
    assert main.add_months(date(2024, 1, 31), 1) == date(2024, 2, 28)


def test_require_indicator_known():
    meta = main.require_indicator("inflation")
    assert meta["source"] == "NBS"


def test_require_indicator_unknown_raises_404():
    with pytest.raises(HTTPException) as exc_info:
        main.require_indicator("not_a_real_indicator")
    assert exc_info.value.status_code == 404


def test_observation_in_rejects_bad_value_type():
    with pytest.raises(ValidationError):
        main.ObservationIn(indicator_id="inflation", obs_date="2025-01-01", value="not-a-number")


def test_observation_in_defaults_source_to_manual():
    obs = main.ObservationIn(indicator_id="inflation", obs_date="2025-01-01", value=34.8)
    assert obs.source == "MANUAL"


def test_store_observation_is_demo_safe_by_default(monkeypatch):
    """Even if a caller asks to commit, writes must stay blocked unless the
    server-side ALLOW_DATA_WRITES flag is explicitly enabled. This is the
    core safety property of the ingestion endpoints."""
    monkeypatch.setattr(main, "ALLOW_DATA_WRITES", False)
    payload = main.ObservationIn(indicator_id="inflation", obs_date="2025-01-01", value=34.8)
    result = main.store_observation(payload, commit=True)
    assert result["committed"] is False
    assert result["action"] == "validated"


def test_store_observation_rejects_unknown_indicator():
    payload = main.ObservationIn(indicator_id="not_a_real_indicator", obs_date="2025-01-01", value=1.0)
    with pytest.raises(HTTPException):
        main.store_observation(payload, commit=False)


def test_analytics_for_handles_empty_series(monkeypatch):
    monkeypatch.setattr(main, "fetch", lambda *args, **kwargs: [])
    result = main.analytics_for("inflation", "2020-01-01", "2024-12-31", periods=3)
    assert result["data_points"] == 0
    assert result["forecast"] == []


def test_analytics_for_computes_rising_trend_and_forecast(monkeypatch):
    series = [
        {"obs_date": "2024-01-01", "value": 10.0},
        {"obs_date": "2024-02-01", "value": 12.0},
        {"obs_date": "2024-03-01", "value": 14.0},
    ]
    monkeypatch.setattr(main, "fetch", lambda *args, **kwargs: series)
    result = main.analytics_for("inflation", "2024-01-01", "2024-03-31", periods=2)
    assert result["data_points"] == 3
    assert result["trend"]["direction"] == "rising"
    assert result["trend"]["slope_per_period"] == pytest.approx(2.0)
    assert len(result["forecast"]) == 2
    # Holt-Winters (short series -> Holt's linear) tracks the upward trend and
    # now carries a 95% prediction interval around each point.
    f0 = result["forecast"][0]
    assert f0["value"] == pytest.approx(16.0, abs=1.0)
    assert f0["lower_95"] < f0["value"] < f0["upper_95"]
    assert result["forecast_model"]["method"] == "holt_linear_trend"


def test_analytics_for_year_over_year_change(monkeypatch):
    series = [
        {"obs_date": "2023-06-01", "value": 20.0},
        {"obs_date": "2024-06-01", "value": 25.0},
    ]
    monkeypatch.setattr(main, "fetch", lambda *args, **kwargs: series)
    result = main.analytics_for("inflation", "2023-01-01", "2024-12-31", periods=1)
    assert result["year_over_year_change"]["absolute"] == pytest.approx(5.0)
    assert result["year_over_year_change"]["percent"] == pytest.approx(25.0)


# --- Forecasting & time-series engine (forecasting.py) ---

import math

import forecasting


def test_season_length_from_frequency():
    assert forecasting.season_length_for("monthly") == 12
    assert forecasting.season_length_for("quarterly") == 4
    assert forecasting.season_length_for("annual") == 0


def test_holt_winters_detects_seasonality_and_brackets_forecast():
    vals = [100 + 2 * t + 10 * math.sin(2 * math.pi * t / 12) for t in range(48)]
    hw = forecasting.holt_winters(vals, 12, 6)
    assert hw["method"] == "holt_winters_additive"
    assert hw["seasonal"] is True
    for e in hw["forecast"]:
        assert e["lower"] < e["value"] < e["upper"]
    # bands must widen with the horizon
    assert (hw["forecast"][-1]["upper"] - hw["forecast"][-1]["lower"]) > \
           (hw["forecast"][0]["upper"] - hw["forecast"][0]["lower"])


def test_holt_winters_short_series_falls_back_to_linear():
    hw = forecasting.holt_winters([10.0, 11.0, 12.0, 13.0], 12, 3)
    assert hw["method"] == "holt_linear_trend"
    assert hw["seasonal"] is False


def test_seasonal_decompose_recovers_strength():
    vals = [50 + 5 * math.sin(2 * math.pi * t / 4) for t in range(40)]
    d = forecasting.seasonal_decompose(vals, 4)
    assert d["seasonal_detected"] is True
    assert d["seasonal_strength"] > 0.8


def test_seasonal_decompose_rejects_short_series():
    d = forecasting.seasonal_decompose([1.0, 2.0, 3.0], 12)
    assert d["seasonal_detected"] is False


def test_cross_correlation_finds_lead():
    x = [math.sin(t / 3.0) for t in range(60)]
    y = [x[t - 3] if t >= 3 else 0.0 for t in range(60)]  # y lags x by 3
    cc = forecasting.cross_correlation(x, y, 8)
    assert cc["best"]["lag"] == 3
    assert cc["relationship"] == "x_leads_y"
    assert cc["best"]["r"] == pytest.approx(1.0, abs=1e-6)


# --- AI "ask the data" assistant (ai_assistant.py) ---

import ai_assistant


def test_ai_matches_indicators_from_question():
    ids = ai_assistant.match_indicators(
        "why did the naira weaken while inflation rose?", main.INDICATORS)
    assert "exchange_rate" in ids
    assert "inflation" in ids


def test_ai_key_not_configured_by_default(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai_assistant.key_configured() is False


def test_ai_build_user_message_embeds_figures():
    msg = ai_assistant.build_user_message("What is inflation?", {"indicators": {"inflation": {"latest": {"value": 15.38}}}})
    assert "15.38" in msg
    assert "What is inflation?" in msg


def test_ask_route_503_without_key(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(main.app)
    r = client.post("/api/v1/ask", json={"question": "What is inflation?"})
    assert r.status_code == 503


# --- HATEOAS / Richardson Maturity Model Level 3 ---

class _FakeRequest:
    """Minimal stand-in for fastapi.Request exposing only base_url, which is
    all hypermedia() reads. Avoids spinning up a real server for unit tests."""
    def __init__(self, base="https://api.example.com/"):
        self.base_url = base


def test_hypermedia_always_includes_self_and_docs():
    links = main.hypermedia(_FakeRequest(), "/api/v1/summary")
    assert links["self"]["href"] == "https://api.example.com/api/v1/summary"
    assert links["index"]["href"] == "https://api.example.com/"
    assert links["docs"]["href"] == "https://api.example.com/docs"


def test_hypermedia_root_omits_redundant_index():
    links = main.hypermedia(_FakeRequest(), "/")
    assert links["self"]["href"] == "https://api.example.com/"
    assert "index" not in links  # self already points at the root


def test_hypermedia_indicator_adds_analytics_and_export():
    links = main.hypermedia(_FakeRequest(), "/api/v1/gdp", indicator="gdp_growth")
    assert links["analytics"]["href"].endswith("/api/v1/analytics/gdp_growth")
    assert links["export_csv"]["href"].endswith("/api/v1/export/gdp_growth")


def test_hypermedia_related_and_extra_links_resolve():
    links = main.hypermedia(
        _FakeRequest(), "/api/v1/analytics/inflation",
        related=["coverage"], extra={"export_csv": "/api/v1/export/inflation"},
    )
    assert links["coverage"]["href"].endswith(main.API_LINKS["coverage"])
    assert links["export_csv"]["href"].endswith("/api/v1/export/inflation")


def test_api_links_catalog_paths_are_absolute_v1_routes():
    for name, path in main.API_LINKS.items():
        assert path.startswith("/api/v1/"), f"{name} -> {path}"


# ── /api/v1/validate/csv — the Validation Layer as a service ──

import asyncio
import io as _io

from fastapi import UploadFile


def _validate(csv_text, indicator="inflation"):
    upload = UploadFile(filename="t.csv", file=_io.BytesIO(csv_text.encode("utf-8")))
    return asyncio.run(main.validate_csv(_FakeRequest(), indicator_id=indicator, file=upload))


def test_validate_csv_accepts_clean_rows_and_never_writes():
    out = _validate("obs_date,value\n2024-01-01,28.9\n2024-02-01,31.7\n")
    assert out["rows_total"] == 2
    assert out["rows_valid"] == 2
    assert out["rows_rejected"] == 0
    assert out["written_to_database"] is False
    assert out["rows"][0]["normalized"]["value"] == 28.9


def test_validate_csv_reports_every_problem_not_just_the_first():
    out = _validate(
        "obs_date,value\n"
        "01/02/2024,10\n"        # bad date format
        "2024-03-01,abc\n"       # non-numeric value
        "2024-03-01,11\n"        # duplicate date
        "2099-01-01,12\n"        # future date
    )
    assert out["rows_total"] == 4
    assert out["rows_valid"] == 0          # every row has at least one problem
    assert out["rows_rejected"] == 4
    reasons = " ".join(r for row in out["rows"] if row["status"] == "rejected" for r in row["reasons"])
    assert "ISO date" in reasons
    assert "numeric" in reasons
    assert "duplicate" in reasons
    assert "future" in reasons


def test_validate_csv_rejects_unknown_indicator():
    with pytest.raises(HTTPException) as exc_info:
        _validate("obs_date,value\n2024-01-01,1\n", indicator="nope")
    assert exc_info.value.status_code == 404


def test_validate_csv_rejects_nan_and_infinity():
    out = _validate("obs_date,value\n2025-01-01,nan\n2025-02-01,inf\n2025-03-01,1e309\n2025-04-01,5.5\n")
    assert out["rows_valid"] == 1
    assert out["rows_rejected"] == 3
    reasons = " ".join(r for row in out["rows"] if row["status"] == "rejected" for r in row["reasons"])
    assert "finite" in reasons


def test_observation_in_rejects_nan():
    with pytest.raises(ValidationError):
        main.ObservationIn(indicator_id="inflation", obs_date=date(2025, 1, 1), value=float("nan"))


# ── TTL cache primitives ──

def test_cache_roundtrip_and_ttl_expiry(monkeypatch):
    main._CACHE.clear()
    now = [1000.0]
    monkeypatch.setattr(main.time, "time", lambda: now[0])
    main._cache_put(("series", "x", "a", "b"), [{"v": 1}])
    assert main._cache_get(("series", "x", "a", "b")) == [{"v": 1}]
    now[0] += main._CACHE_TTL_SECONDS + 1
    assert main._cache_get(("series", "x", "a", "b")) is None
    main._CACHE.clear()


def test_cache_size_cap_evicts_oldest(monkeypatch):
    main._CACHE.clear()
    monkeypatch.setattr(main.time, "time", lambda: 1000.0)
    for i in range(main._CACHE_MAX_KEYS):
        main._cache_put(("k", i), i)
    main._cache_put(("k", "overflow"), "new")
    assert len(main._CACHE) <= main._CACHE_MAX_KEYS
    assert main._cache_get(("k", "overflow")) == "new"
    main._CACHE.clear()


def test_fetch_uses_cache(monkeypatch):
    main._CACHE.clear()
    calls = {"n": 0}
    class _Q:
        def __init__(self): pass
        def select(self, *a): return self
        def eq(self, *a): return self
        def gte(self, *a): return self
        def lte(self, *a): return self
        def order(self, *a): return self
        def execute(self):
            calls["n"] += 1
            class R: data = [{"obs_date": "2024-01-01", "value": 1, "source": "T"}]
            return R()
    class _SB:
        def table(self, *a): return _Q()
    monkeypatch.setattr(main, "supabase", _SB())
    a = main.fetch("inflation", "2024-01-01", "2024-12-31")
    b = main.fetch("inflation", "2024-01-01", "2024-12-31")
    assert a == b
    assert calls["n"] == 1  # second call served from cache
    main._CACHE.clear()
