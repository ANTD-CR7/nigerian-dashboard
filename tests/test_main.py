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
    assert result["forecast"][0]["value"] == pytest.approx(16.0)


def test_analytics_for_year_over_year_change(monkeypatch):
    series = [
        {"obs_date": "2023-06-01", "value": 20.0},
        {"obs_date": "2024-06-01", "value": 25.0},
    ]
    monkeypatch.setattr(main, "fetch", lambda *args, **kwargs: series)
    result = main.analytics_for("inflation", "2023-01-01", "2024-12-31", periods=1)
    assert result["year_over_year_change"]["absolute"] == pytest.approx(5.0)
    assert result["year_over_year_change"]["percent"] == pytest.approx(25.0)


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
