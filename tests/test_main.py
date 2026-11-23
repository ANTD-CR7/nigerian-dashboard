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


def test_store_observation_writes_vintage_before_observation(monkeypatch):
    """The Ledger: a committed write must record a permanent vintage first,
    then touch observations -- never the other way around, so the two
    tables can't drift apart."""
    monkeypatch.setattr(main, "ALLOW_DATA_WRITES", True)
    order = []

    class _Query:
        def __init__(self, name):
            self.name = name

        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def insert(self, *a, **k): return self
        def update(self, *a, **k): return self

        def execute(self):
            class R:
                data = []
            return R()

    class _SB:
        def table(self, name):
            order.append(name)
            return _Query(name)

    monkeypatch.setattr(main, "supabase", _SB())
    payload = main.ObservationIn(indicator_id="inflation", obs_date="2025-01-01", value=34.8)
    result = main.store_observation(payload, commit=True)

    assert result["committed"] is True
    assert order[0] == "observation_vintages"
    assert order[1:] == ["observations", "observations"]


def test_store_observation_vintage_failure_blocks_observations_write(monkeypatch):
    """If the vintage insert fails, observations must never be touched --
    otherwise the Ledger and the current-value table silently drift apart."""
    monkeypatch.setattr(main, "ALLOW_DATA_WRITES", True)
    order = []

    class _FailingVintageQuery:
        def insert(self, *a, **k): return self

        def execute(self):
            raise RuntimeError("vintage insert failed")

    class _SB:
        def table(self, name):
            order.append(name)
            if name == "observation_vintages":
                return _FailingVintageQuery()
            raise AssertionError("observations must not be touched if the vintage insert failed")

    monkeypatch.setattr(main, "supabase", _SB())
    payload = main.ObservationIn(indicator_id="inflation", obs_date="2025-01-01", value=34.8)
    with pytest.raises(RuntimeError):
        main.store_observation(payload, commit=True)
    assert order == ["observation_vintages"]


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
    monkeypatch.setattr(main, "fetch_as_of", lambda *args, **kwargs: series)
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
    monkeypatch.setattr(main, "fetch_as_of", lambda *args, **kwargs: series)
    result = main.analytics_for("inflation", "2023-01-01", "2024-12-31", periods=1)
    assert result["year_over_year_change"]["absolute"] == pytest.approx(5.0)
    assert result["year_over_year_change"]["percent"] == pytest.approx(25.0)


def test_analytics_for_refuses_context_on_thin_history(monkeypatch):
    """The Rater's minimum-history rule: gdp_usd, gdp_growth, and mpr are all
    too thin in the real dataset to rate honestly -- confirm the refusal shape
    for each, using analytics_for() directly so this runs with no network."""
    thin_series = [{"obs_date": f"2020-0{i}-01", "value": float(i)} for i in range(1, 6)]  # 5 points
    monkeypatch.setattr(main, "fetch", lambda *args, **kwargs: thin_series)
    monkeypatch.setattr(main, "fetch_as_of", lambda *args, **kwargs: thin_series)
    for indicator_id in ("gdp_usd", "gdp_growth", "mpr"):
        result = main.analytics_for(indicator_id, "2020-01-01", "2020-12-31", periods=1)
        assert result["context"] == {
            "insufficient_history": True,
            "observations_available": 5,
            "minimum_required": 30,
        }


def test_analytics_for_context_on_sufficient_history(monkeypatch):
    """A long enough series gets real Rater stats instead of a refusal."""
    series = [{"obs_date": f"2020-{(i % 12) + 1:02d}-01", "value": 100.0 + i} for i in range(40)]
    monkeypatch.setattr(main, "fetch", lambda *args, **kwargs: series)
    monkeypatch.setattr(main, "fetch_as_of", lambda *args, **kwargs: series)
    result = main.analytics_for("inflation", "2020-01-01", "2024-12-31", periods=1)
    ctx = result["context"]
    assert "insufficient_history" not in ctx
    assert 0 <= ctx["percentile_rank"]["percentile"] <= 100
    assert math.isfinite(ctx["z_score"]["z_score"])
    assert "significant" in ctx["move_significance"]


def test_analytics_for_degrades_gracefully_when_ledger_rpc_fails(monkeypatch):
    """A Ledger/RPC hiccup must not take down the rest of analytics_for() --
    trend, forecast, and everything else that worked before the Rater existed
    must still return, with context degraded instead of the whole call 500ing."""
    series = [{"obs_date": "2024-01-01", "value": 10.0}, {"obs_date": "2024-02-01", "value": 12.0}]
    monkeypatch.setattr(main, "fetch", lambda *args, **kwargs: series)

    def _broken_fetch_as_of(*args, **kwargs):
        raise RuntimeError("RPC unavailable")

    monkeypatch.setattr(main, "fetch_as_of", _broken_fetch_as_of)
    result = main.analytics_for("inflation", "2024-01-01", "2024-03-31", periods=1)
    assert result["data_points"] == 2
    assert result["trend"]["direction"] in ("rising", "falling", "stable")
    assert result["context"] == {"error": "context temporarily unavailable"}


def test_analytics_for_context_flags_outlier_move(monkeypatch):
    """A deliberately placed outlier move should trip move_significance."""
    series = [{"obs_date": f"2020-{(i % 12) + 1:02d}-01", "value": 100.0} for i in range(39)]
    series.append({"obs_date": "2024-01-01", "value": 500.0})  # sharp final jump
    monkeypatch.setattr(main, "fetch", lambda *args, **kwargs: series)
    monkeypatch.setattr(main, "fetch_as_of", lambda *args, **kwargs: series)
    result = main.analytics_for("inflation", "2020-01-01", "2024-12-31", periods=1)
    assert result["context"]["move_significance"]["significant"] is True


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


def test_holt_winters_empty_series_does_not_crash():
    # regression: holt_winters([]) used to raise IndexError
    hw = forecasting.holt_winters([], 12, 6)
    assert hw["method"] == "no_data"
    assert hw["forecast"] == []


def test_cross_correlation_requires_minimum_overlap():
    # regression: a tiny overlap at an extreme lag must not report a spurious r
    cc = forecasting.cross_correlation([1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0], 5)
    # only 3 overlapping points -> below min overlap -> no spurious lead
    assert cc["best"]["r"] == 0.0
    # and the lag is capped to half the (shorter) series
    assert cc["max_lag"] <= 1


# --- The Rater: disclosed statistics (forecasting.py) ---


def test_insufficient_history_flags_thin_series():
    refusal = forecasting.insufficient_history(25)
    assert refusal == {"insufficient_history": True, "observations_available": 25, "minimum_required": 30}


def test_insufficient_history_passes_at_minimum():
    assert forecasting.insufficient_history(30) is None
    assert forecasting.insufficient_history(31) is None


def test_percentile_rank_of_the_maximum_is_near_100():
    # mean-rank method: the max of 5 distinct values is (4 below + 0.5 self)/5 * 100
    pr = forecasting.percentile_rank([1.0, 2.0, 3.0, 4.0, 5.0])
    assert pr["value"] == 5.0
    assert pr["percentile"] == 90.0
    assert pr["n"] == 5


def test_percentile_rank_splits_ties_evenly():
    # latest value (3.0) ties with the other 3.0 too -> both count as "tied" (incl. itself):
    # (2 below + 0.5*2 tied)/4 * 100
    pr = forecasting.percentile_rank([1.0, 2.0, 3.0, 3.0])
    assert pr["percentile"] == pytest.approx(75.0)


def test_z_score_of_constant_series_is_zero():
    z = forecasting.z_score([10.0, 10.0, 10.0, 10.0])
    assert z["std_dev"] == 0.0
    assert z["z_score"] == 0.0


def test_z_score_matches_hand_computed_value():
    z = forecasting.z_score([1.0, 2.0, 3.0, 4.0, 10.0])
    assert z["mean"] == pytest.approx(4.0)
    assert z["value"] == 10.0
    assert z["z_score"] > 1.5  # clearly above the pack, exact value depends on sample std-dev


def test_move_significance_flags_an_outlier_jump():
    # steady +1 moves, then one outlier +50 jump at the end
    values = [float(i) for i in range(40)] + [89.0]
    sig = forecasting.move_significance(values)
    assert sig["significant"] is True
    assert sig["z_score"] >= 2.0


def test_move_significance_does_not_flag_steady_series():
    values = [float(i) for i in range(40)]
    sig = forecasting.move_significance(values)
    assert sig["significant"] is False


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


# --- Automated collection framework (collectors/) ---

def test_collector_normalize_dedups_and_drops_invalid():
    from collectors.base import normalize
    rows = [
        {"indicator_id": "wb_gdp_usd", "obs_date": "2023-01-01", "value": 100.0, "source": "WB"},
        {"indicator_id": "wb_gdp_usd", "obs_date": "2023-01-01", "value": 200.0, "source": "WB"},  # dup, last wins
        {"indicator_id": "bad", "obs_date": "not-a-date", "value": 1, "source": "x"},               # bad date
        {"indicator_id": "inf", "obs_date": "2023-01-01", "value": float("inf"), "source": "x"},     # non-finite
    ]
    clean, dropped = normalize(rows)
    assert len(clean) == 1
    assert clean[0]["value"] == 200.0  # uniqueness rule: last write wins
    assert dropped == 2


def test_collector_runner_writes_demo_safe_snapshot(tmp_path):
    from collectors.base import Connector
    from collectors import runner

    class _Mock(Connector):
        name = "mock"
        source_label = "Mock"
        def fetch(self, start_year=2015):
            yield {"indicator_id": "wb_inflation", "obs_date": "2023-01-01", "value": 24.66, "source": "Mock"}

    summary = runner.run(connectors=[_Mock()], out_dir=str(tmp_path), write_db=False, stamp="unit")
    assert summary["rows"] == 1
    assert summary["written_to_db"] == 0  # never writes to DB by default
    assert (tmp_path / "collected_unit.json").exists()


def test_collector_runner_upsert_writes_vintage_before_observation(monkeypatch):
    """The Ledger's vintage-first ordering must hold in the automated
    collector path too, not just the API's manual ingestion path."""
    from collectors import runner

    monkeypatch.setenv("NPE_COLLECT_WRITE", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    order = []

    class _Query:
        def __init__(self, name):
            self.name = name

        def insert(self, *a, **k): return self
        def upsert(self, *a, **k): return self

        def execute(self):
            class R:
                data = []
            return R()

    class _FakeClient:
        def table(self, name):
            order.append(name)
            return _Query(name)

    monkeypatch.setattr("supabase.create_client", lambda url, key: _FakeClient())

    rows = [{"indicator_id": "inflation", "obs_date": "2025-01-01", "value": 34.8, "source": "NBS"}]
    written = runner._upsert(rows)

    assert written == 1
    assert order == ["observation_vintages", "observations"]


def test_collector_runner_survives_a_failing_connector(tmp_path):
    # regression: one connector raising must not abort the whole run
    from collectors.base import Connector
    from collectors import runner

    class _Boom(Connector):
        name = "boom"
        def fetch(self, start_year=2015):
            raise RuntimeError("connector exploded")

    class _Good(Connector):
        name = "good"
        def fetch(self, start_year=2015):
            yield {"indicator_id": "wb_gdp", "obs_date": "2023-01-01", "value": 1.0, "source": "Good"}

    summary = runner.run(connectors=[_Boom(), _Good()], out_dir=str(tmp_path), write_db=False, stamp="mix")
    assert summary["rows"] == 1                       # the good data survived
    assert "boom" in summary["errors"]                # the failure was recorded, not fatal


# --- Optional API-key auth + rate limiting middleware ---

from fastapi.testclient import TestClient


def _client_stubbed(monkeypatch):
    monkeypatch.setattr(main, "fetch", lambda *a, **k: [{"obs_date": "2026-01-01", "value": 1.0}])
    main._rate_state.clear()
    return TestClient(main.app)


def test_api_open_by_default_no_auth(monkeypatch):
    monkeypatch.delenv("NPE_API_KEYS", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("NPE_RATE_LIMIT_PER_MIN", "1000")
    client = _client_stubbed(monkeypatch)
    # no key required: /ask reaches the 503 (AI-not-configured), not a 401
    assert client.post("/api/v1/ask", json={"question": "hello there"}).status_code == 503


def test_api_key_required_when_configured(monkeypatch):
    monkeypatch.setenv("NPE_API_KEYS", "k1,k2")
    monkeypatch.setenv("NPE_RATE_LIMIT_PER_MIN", "1000")
    client = _client_stubbed(monkeypatch)
    assert client.post("/api/v1/ask", json={"question": "hello there"}).status_code == 401
    ok = client.post("/api/v1/ask", json={"question": "hello there"}, headers={"X-API-Key": "k1"})
    assert ok.status_code != 401  # passes auth (503 without an LLM key)


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.delenv("NPE_API_KEYS", raising=False)
    monkeypatch.setenv("NPE_RATE_LIMIT_PER_MIN", "3")
    client = _client_stubbed(monkeypatch)
    codes = [client.get("/api/v1/coverage").status_code for _ in range(5)]
    assert 429 in codes
    assert codes[0] != 429  # first few allowed


def test_malformed_date_param_returns_422_not_500(monkeypatch):
    monkeypatch.delenv("NPE_API_KEYS", raising=False)
    monkeypatch.setenv("NPE_RATE_LIMIT_PER_MIN", "1000")
    client = _client_stubbed(monkeypatch)
    assert client.get("/api/v1/coverage?start=garbage").status_code == 422
    assert client.get("/api/v1/coverage?end=2020-13-45").status_code == 422
    assert client.get("/api/v1/coverage?start=2020-01-01").status_code == 200


def test_get_reads_carry_cache_headers(monkeypatch):
    monkeypatch.delenv("NPE_API_KEYS", raising=False)
    monkeypatch.setenv("NPE_RATE_LIMIT_PER_MIN", "1000")
    client = _client_stubbed(monkeypatch)
    r = client.get("/api/v1/coverage")
    assert "max-age" in r.headers.get("Cache-Control", "")


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


# --- The Reconciler: concept divergence (main.py) ---

class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self._filter = None

    def select(self, *a, **k):
        return self

    def eq(self, field, value):
        self._filter = (field, value)
        return self

    def execute(self):
        class R:
            pass
        r = R()
        if self._filter:
            field, value = self._filter
            r.data = [row for row in self.rows if row.get(field) == value]
        else:
            r.data = list(self.rows)
        return r


class _FakeSupabase:
    def __init__(self, indicator_rows):
        self.indicator_rows = indicator_rows

    def table(self, name):
        assert name == "indicators"
        return _FakeQuery(self.indicator_rows)


def _client_for_reconcile(monkeypatch, indicator_rows, series_map):
    monkeypatch.setattr(main, "supabase", _FakeSupabase(indicator_rows))
    monkeypatch.setattr(main, "fetch_as_of", lambda iid, *a, **k: series_map.get(iid, []))
    monkeypatch.delenv("NPE_API_KEYS", raising=False)
    monkeypatch.setenv("NPE_RATE_LIMIT_PER_MIN", "1000")
    main._rate_state.clear()
    return TestClient(main.app)


def test_reconcile_concept_aligns_by_date_and_computes_spread(monkeypatch):
    monkeypatch.setattr(main, "supabase", _FakeSupabase([
        {"id": "a", "name": "A", "source": "X", "concept": "test_concept"},
        {"id": "b", "name": "B", "source": "Y", "concept": "test_concept"},
    ]))
    series = {
        "a": [{"obs_date": "2020-01-01", "value": 10.0}, {"obs_date": "2021-01-01", "value": 12.0},
              {"obs_date": "2022-01-01", "value": 14.0}, {"obs_date": "2023-01-01", "value": 99.0}],
        "b": [{"obs_date": "2020-01-01", "value": 11.0}, {"obs_date": "2021-01-01", "value": 12.5},
              {"obs_date": "2022-01-01", "value": 13.0}],
    }
    monkeypatch.setattr(main, "fetch_as_of", lambda iid, *a, **k: series[iid])
    members, rows = main.reconcile_concept("test_concept")
    assert len(rows) == 3  # 2023 excluded -- only "a" has it
    first = rows[0]
    assert first["obs_date"] == "2020-01-01"
    assert first["values"] == {"a": 10.0, "b": 11.0}
    assert first["spread"]["absolute"] == pytest.approx(1.0)
    assert first["spread"]["max_minus_min"] == pytest.approx(1.0)


def test_reconcile_concept_degrades_absolute_for_three_or_more_sources(monkeypatch):
    monkeypatch.setattr(main, "supabase", _FakeSupabase([
        {"id": "a", "name": "A", "source": "X", "concept": "c3"},
        {"id": "b", "name": "B", "source": "Y", "concept": "c3"},
        {"id": "c", "name": "C", "source": "Z", "concept": "c3"},
    ]))
    series = {
        "a": [{"obs_date": "2020-01-01", "value": 10.0}],
        "b": [{"obs_date": "2020-01-01", "value": 12.0}],
        "c": [{"obs_date": "2020-01-01", "value": 8.0}],
    }
    monkeypatch.setattr(main, "fetch_as_of", lambda iid, *a, **k: series[iid])
    _, rows = main.reconcile_concept("c3")
    assert rows[0]["spread"]["absolute"] is None
    assert rows[0]["spread"]["max_minus_min"] == pytest.approx(4.0)


def test_reconcile_endpoint_404_for_unknown_concept(monkeypatch):
    client = _client_for_reconcile(
        monkeypatch, [{"id": "a", "name": "A", "source": "X", "concept": "known_concept"}], {}
    )
    r = client.get("/api/v1/reconcile/not_a_real_concept")
    assert r.status_code == 404
    assert "known_concept" in r.json()["detail"]


def test_reconcile_endpoint_returns_divergence(monkeypatch):
    indicator_rows = [
        {"id": "a", "name": "A", "source": "X", "concept": "known_concept"},
        {"id": "b", "name": "B", "source": "Y", "concept": "known_concept"},
    ]
    series = {
        "a": [{"obs_date": "2020-01-01", "value": 10.0}],
        "b": [{"obs_date": "2020-01-01", "value": 15.0}],
    }
    client = _client_for_reconcile(monkeypatch, indicator_rows, series)
    r = client.get("/api/v1/reconcile/known_concept")
    assert r.status_code == 200
    body = r.json()
    assert body["concept"] == "known_concept"
    assert body["n"] == 1
    assert body["observations"][0]["spread"]["max_minus_min"] == pytest.approx(5.0)


def test_reconcile_index_groups_concepts(monkeypatch):
    indicator_rows = [
        {"id": "a", "name": "A", "source": "X", "concept": "c1"},
        {"id": "b", "name": "B", "source": "Y", "concept": "c1"},
        {"id": "c", "name": "C", "source": "Z", "concept": None},
    ]
    client = _client_for_reconcile(monkeypatch, indicator_rows, {})
    r = client.get("/api/v1/reconcile")
    assert r.status_code == 200
    concepts = {c["concept"]: c["indicators"] for c in r.json()["concepts"]}
    assert set(concepts.keys()) == {"c1"}
    assert len(concepts["c1"]) == 2


def test_reconcile_endpoint_422_when_no_overlap(monkeypatch):
    indicator_rows = [
        {"id": "a", "name": "A", "source": "X", "concept": "no_overlap"},
        {"id": "b", "name": "B", "source": "Y", "concept": "no_overlap"},
    ]
    series = {
        "a": [{"obs_date": "2020-01-01", "value": 10.0}],
        "b": [{"obs_date": "2021-01-01", "value": 11.0}],
    }
    client = _client_for_reconcile(monkeypatch, indicator_rows, series)
    r = client.get("/api/v1/reconcile/no_overlap")
    assert r.status_code == 422


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


def test_fetch_as_of_matches_fetch_output_shape(monkeypatch):
    main._CACHE.clear()

    class _RpcCall:
        def execute(self):
            class R:
                data = [{"obs_date": "2024-01-01", "value": 1.0}, {"obs_date": "2024-02-01", "value": 2.5}]
            return R()

    class _SB:
        def rpc(self, name, params):
            assert name == "observations_as_of"
            assert "p_indicator_id" in params and "p_as_of" in params
            return _RpcCall()

    monkeypatch.setattr(main, "supabase", _SB())
    result = main.fetch_as_of("inflation")
    assert result == [{"obs_date": "2024-01-01", "value": 1.0}, {"obs_date": "2024-02-01", "value": 2.5}]
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
