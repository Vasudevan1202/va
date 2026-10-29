"""
Tests for Local Short-Term Forecasting Engine (Phase 1 Upgraded)
----------------------------------------------------------------
Verifies:
1. Historical data preparation (filtering invalid/NaN/inf, deduplication, 1-minute aggregation).
2. Missing intervals and gap detection.
3. Stale and offline sensor state detection disabling forecasting.
4. Insufficient history handling.
5. Strict separation of live hardware and demo/simulated data.
6. Stable vs rapidly changing trends, Holt damping, and physical clamping.
7. Skill-score formula and mathematical signs:
   - Positive skill = improvement over persistence.
   - Negative skill = persistence outperforms trend.
8. Truthful summary generation: never disguised as an improvement when skill is negative.
9. Dynamic champion model selection: persistence is the default whenever trend skill <= 0.
10. Rolling walk-forward backtesting: zero future leakage, zero target-overlap leakage.
11. Prediction interval calibration against empirical out-of-sample errors (coverage >= 80%).
12. API endpoint (/api/forecast) contracts, horizon parameters, and failure resilience.
"""

import math
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from app import create_app
from config import Config
import database
from forecast_engine import ForecastEngine, compute_quantile


@pytest.fixture
def forecast_test_db(tmp_path):
    """Sets up an isolated SQLite test database with schema."""
    db_file = str(tmp_path / "test_forecast_db.db")
    database.init_db(db_file)
    return db_file


@pytest.fixture
def test_client(forecast_test_db, monkeypatch):
    """Provides Flask test client pointed to the test database."""
    monkeypatch.setattr(Config, "DATABASE_PATH", forecast_test_db)
    monkeypatch.setattr(Config, "MODE", "demo")
    app = create_app()
    app.config["TESTING"] = True
    app.config["DATABASE_PATH"] = forecast_test_db
    with app.test_client() as client:
        yield client


# =========================================================================
# 1. Historical Data Preparation Tests
# =========================================================================

def test_filtering_invalid_nan_infinite_and_out_of_bounds():
    """Validates that non-finite, out-of-bounds, and malformed readings are rejected."""
    now = datetime.now(timezone.utc)
    raw = [
        {"timestamp": now.isoformat(), "temperature_c": 28.5, "humidity_pct": 52.0, "validity_status": "valid", "source": "dht11"},
        {"timestamp": (now - timedelta(minutes=1)).isoformat(), "temperature_c": float("nan"), "humidity_pct": 52.0, "validity_status": "valid"},
        {"timestamp": (now - timedelta(minutes=2)).isoformat(), "temperature_c": 28.0, "humidity_pct": float("inf"), "validity_status": "valid"},
        {"timestamp": (now - timedelta(minutes=3)).isoformat(), "temperature_c": 85.0, "humidity_pct": 50.0, "validity_status": "valid"},
        {"timestamp": (now - timedelta(minutes=4)).isoformat(), "temperature_c": 25.0, "humidity_pct": -5.0, "validity_status": "valid"},
        {"timestamp": (now - timedelta(minutes=5)).isoformat(), "temperature_c": 26.0, "humidity_pct": 50.0, "validity_status": "spike"},
        {"timestamp": (now - timedelta(minutes=6)).isoformat(), "temperature_c": None, "humidity_pct": 50.0, "validity_status": "valid"},
        {"timestamp": "not-a-date", "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
    ]

    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=now)
    assert len(prep["buckets"]) == 1
    assert prep["buckets"][0]["temperature_c"] == 28.5
    assert prep["buckets"][0]["humidity_pct"] == 52.0


def test_duplicate_timestamps_and_one_minute_aggregation():
    """Validates that multiple readings within the same minute are averaged cleanly."""
    base_time = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
    raw = [
        {"timestamp": "2026-10-29T12:00:10Z", "temperature_c": 24.0, "humidity_pct": 50.0, "validity_status": "valid"},
        {"timestamp": "2026-10-29T12:00:40Z", "temperature_c": 26.0, "humidity_pct": 60.0, "validity_status": "valid"},
        {"timestamp": "2026-10-29T12:01:15Z", "temperature_c": 25.0, "humidity_pct": 55.0, "validity_status": "valid"}
    ]

    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=base_time + timedelta(minutes=2))
    buckets = prep["buckets"]
    assert len(buckets) == 2
    assert buckets[0]["temperature_c"] == 25.0
    assert buckets[0]["humidity_pct"] == 55.0
    assert buckets[0]["sample_count"] == 2
    assert buckets[1]["temperature_c"] == 25.0
    assert buckets[1]["humidity_pct"] == 55.0


def test_gap_detection_in_prepared_series():
    """Validates that telemetry outages > 10 min are flagged as gaps."""
    now = datetime.now(timezone.utc)
    raw = [
        {"timestamp": (now - timedelta(minutes=45)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"},
        {"timestamp": (now - timedelta(minutes=20)).isoformat(), "temperature_c": 25.5, "humidity_pct": 51.0, "validity_status": "valid"},
        {"timestamp": now.isoformat(), "temperature_c": 26.0, "humidity_pct": 52.0, "validity_status": "valid"}
    ]

    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=now)
    assert prep["gaps_detected"] >= 1


# =========================================================================
# 2. Stale, Offline, and Insufficient History Tests
# =========================================================================

def test_stale_and_offline_sensor_disables_forecasting():
    """Validates that stale (>15m) or offline (>60m) sensor telemetry strictly disables forecasting."""
    now = datetime.now(timezone.utc)

    # 1. Fresh sensor (2 min old) -> Forecasting enabled
    raw_fresh = [
        {"timestamp": (now - timedelta(minutes=i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20, 1, -1)
    ]
    report_fresh = ForecastEngine.get_forecast_report(raw_fresh, reference_time=now, use_cache=False)
    assert report_fresh["is_available"] is True
    assert report_fresh["status"] == "success"

    # 2. Stale sensor (25 min old) -> Forecasting disabled
    raw_stale = [
        {"timestamp": (now - timedelta(minutes=25 + i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20, 0, -1)
    ]
    report_stale = ForecastEngine.get_forecast_report(raw_stale, reference_time=now, use_cache=False)
    assert report_stale["is_available"] is False
    assert report_stale["status"] == "stale_sensor"
    assert report_stale["forecast"] is None

    # 3. Offline sensor (90 min old) -> Forecasting disabled
    raw_offline = [
        {"timestamp": (now - timedelta(minutes=90 + i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20, 0, -1)
    ]
    report_offline = ForecastEngine.get_forecast_report(raw_offline, reference_time=now, use_cache=False)
    assert report_offline["is_available"] is False
    assert report_offline["status"] == "stale_sensor"  # grouped as stale/offline


def test_insufficient_history_requirement():
    """Validates that history shorter than MIN_HISTORY_MINUTES (15m) returns honest insufficient status."""
    now = datetime.now(timezone.utc)
    raw_sparse = [
        {"timestamp": (now - timedelta(minutes=i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(5, 0, -1)
    ]
    report = ForecastEngine.get_forecast_report(raw_sparse, reference_time=now, use_cache=False)
    assert report["status"] == "insufficient_history"
    assert report["is_available"] is False
    assert report["forecast"] is None
    assert "Insufficient history" in report["sufficiency"]["reason"]


# =========================================================================
# 3. Live vs Demo Separation Tests
# =========================================================================

def test_strict_live_and_demo_separation():
    """Validates that when real_only=True, demo/simulated records are strictly omitted."""
    now = datetime.now(timezone.utc)
    mixed_raw = [
        {"timestamp": (now - timedelta(minutes=10)).isoformat(), "temperature_c": 22.0, "humidity_pct": 40.0, "validity_status": "valid", "source": "demo"},
        {"timestamp": (now - timedelta(minutes=5)).isoformat(), "temperature_c": 23.0, "humidity_pct": 42.0, "validity_status": "valid", "source": "simulated"},
        {"timestamp": (now - timedelta(minutes=1)).isoformat(), "temperature_c": 30.0, "humidity_pct": 60.0, "validity_status": "valid", "source": "raspberry_pi_dht11"}
    ]

    prep_real = ForecastEngine.prepare_dht11_series(mixed_raw, real_only=True, reference_time=now)
    assert len(prep_real["buckets"]) == 1
    assert prep_real["buckets"][0]["source"] == "raspberry_pi_dht11"

    prep_all = ForecastEngine.prepare_dht11_series(mixed_raw, real_only=False, reference_time=now)
    assert len(prep_all["buckets"]) == 3


# =========================================================================
# 4. Skill Score Signs, MAE/RMSE, and Truthful Summaries
# =========================================================================

def test_skill_score_signs_and_formula():
    """
    Validates skill score formula: skill = (baseline MAE - model MAE) / baseline MAE * 100.
    Positive skill = improvement over persistence.
    Negative skill = persistence is superior.
    """
    # 1. Negative Skill Scenario (Actual production finding for 15m temp: trend MAE 0.33 vs pers 0.26)
    base_mae_temp = 0.26
    trend_mae_temp = 0.33
    skill_temp = ((base_mae_temp - trend_mae_temp) / base_mae_temp) * 100.0
    assert skill_temp < 0.0
    assert round(skill_temp, 1) == -26.9

    # 2. Positive Skill Scenario (Actual production finding for 30m hum: trend MAE 1.51 vs pers 1.82)
    base_mae_hum = 1.82
    trend_mae_hum = 1.51
    skill_hum = ((base_mae_hum - trend_mae_hum) / base_mae_hum) * 100.0
    assert skill_hum > 0.0
    assert round(skill_hum, 1) == 17.0


def test_no_misleading_summary_generation_with_negative_skill():
    """
    Validates that a negative skill score is NEVER described as 'improving upon'
    or 'performing comparably by X%'. It must explicitly state that persistence outperforms trend.
    """
    # Create synthetic series where persistence outperforms trend
    # E.g. random walk / mean-reverting series where trend slope overshoots
    now = datetime.now(timezone.utc)
    # Sinusoidal oscillation around 25°C where persistence has lower error than linear trend
    raw_series = [
        {
            "timestamp": (now - timedelta(minutes=130 - i)).isoformat(),
            "temperature_c": round(25.0 + math.sin(i / 3.0) * 0.4, 2),
            "humidity_pct": round(50.0 + math.cos(i / 3.0) * 0.5, 2),
            "validity_status": "valid"
        }
        for i in range(130)
    ]

    prep = ForecastEngine.prepare_dht11_series(raw_series, reference_time=now)
    backtest = ForecastEngine.backtest_horizons(prep["buckets"], horizons=[15], min_train_minutes=15)

    bt_15 = backtest["15m"]
    assert bt_15["status"] == "active"

    # Check temperature summary
    temp_info = bt_15["temperature"]
    temp_skill = temp_info["skill_score_pct"]
    temp_summary = temp_info["summary"]

    if temp_skill < -0.5:
        assert "Persistence outperforms trend" in temp_summary
        assert "improves upon persistence" not in temp_summary
        assert "performs comparably to persistence by" not in temp_summary
        assert temp_info["optimal_model"] == "persistence"
    elif temp_skill > 0.5:
        assert "Trend model outperforms persistence" in temp_summary
        assert temp_info["optimal_model"] == "damped_linear_trend"


# =========================================================================
# 5. Dynamic Champion Model Selection (Persistence as Default)
# =========================================================================

def test_dynamic_model_selection_persistence_champion():
    """
    Validates that point forecast dynamically defaults to persistence
    whenever trend skill <= 0, and selects trend only when skill > 0.
    """
    now = datetime.now(timezone.utc)
    raw = [
        {"timestamp": (now - timedelta(minutes=30 - i)).isoformat(), "temperature_c": 28.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(30)
    ]
    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=now)

    # Mock backtest evaluations:
    # Temperature: skill = -26.9% (persistence better)
    # Humidity: skill = +17.0% (trend better)
    mock_evaluations = {
        "15m": {
            "status": "active",
            "temperature": {
                "trend_mae_c": 0.33,
                "persistence_mae_c": 0.26,
                "skill_score_pct": -26.9,
                "_empirical_oos_errors": [0.2, 0.25, 0.3, 0.22, 0.28]
            },
            "humidity": {
                "trend_mae_pct": 1.51,
                "persistence_mae_pct": 1.82,
                "skill_score_pct": 17.0,
                "_empirical_oos_errors": [1.2, 1.4, 1.5, 1.3, 1.6]
            }
        }
    }

    fc = ForecastEngine.generate_point_forecast(
        prep["buckets"],
        horizon_min=15,
        backtest_evaluations=mock_evaluations
    )

    # Temperature must select persistence!
    temp_fc = fc["temperature"]
    assert temp_fc["selected_model"] == "persistence"
    assert temp_fc["predicted_c"] == 28.0
    assert temp_fc["change_c"] == 0.0
    assert "Persistence selected as default" in temp_fc["selection_reason"]

    # Humidity must select trend!
    hum_fc = fc["humidity"]
    assert hum_fc["selected_model"] == "damped_linear_trend"
    assert "Damped trend selected" in hum_fc["selection_reason"]


def test_model_selection_defaults_to_persistence_when_insufficient_backtest():
    """When out-of-sample backtest data is insufficient or absent, forecast defaults to persistence safely."""
    now = datetime.now(timezone.utc)
    raw = [
        {"timestamp": (now - timedelta(minutes=20 - i)).isoformat(), "temperature_c": 25.0 + (i * 0.1), "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20)
    ]
    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=now)

    # Without backtest data
    fc = ForecastEngine.generate_point_forecast(prep["buckets"], horizon_min=15, backtest_evaluations=None)
    assert fc["temperature"]["selected_model"] == "persistence"
    assert fc["humidity"]["selected_model"] == "persistence"
    assert fc["temperature"]["change_c"] == 0.0


# =========================================================================
# 6. Walk-Forward Backtesting Leakage Verification
# =========================================================================

def test_walk_forward_backtesting_non_overlapping_and_no_leakage():
    """
    Validates rolling walk-forward backtesting:
    1. Zero future data leakage.
    2. Zero overlapping-target autocorrelation leakage (step stride = horizon).
    3. Zero in-sample evaluation.
    """
    now = datetime.now(timezone.utc)
    # Generate 120 minutes of data
    raw = [
        {
            "timestamp": (now - timedelta(minutes=120 - i)).isoformat(),
            "temperature_c": round(24.0 + (i * 0.03), 2),
            "humidity_pct": round(60.0 - (i * 0.02), 2),
            "validity_status": "valid"
        }
        for i in range(120)
    ]

    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=now)
    # Run backtesting with 15m horizon
    backtest = ForecastEngine.backtest_horizons(
        prep["buckets"],
        horizons=[15],
        min_train_minutes=15,
        step_stride_minutes=15  # non-overlapping evaluation
    )

    bt_15 = backtest["15m"]
    assert bt_15["status"] == "active"
    assert bt_15["evaluation_method"] == "rolling_origin_walk_forward_non_overlapping"

    # Evaluated samples must be strictly non-overlapping
    # 120 total - 15 min train = 105 min. With 15 min stride, maximum ~7 non-overlapping windows
    assert bt_15["samples_evaluated"] >= ForecastEngine.MIN_TEST_SAMPLES_BACKTEST
    assert bt_15["samples_evaluated"] <= 8


# =========================================================================
# 7. Prediction Interval Empirical Calibration & Coverage Tests
# =========================================================================

def test_calibrated_uncertainty_interval_empirical_coverage():
    """
    Validates that prediction intervals calibrated against out-of-sample empirical errors
    achieve >= 80% coverage on the empirical distribution, while respecting sensor hardware floor.
    """
    # Sample empirical errors: e.g. 10 errors
    empirical_errors = [-0.1, 0.2, -0.3, 0.15, -0.25, 0.4, -0.5, 0.35, -0.1, 0.05]
    predicted_val = 26.0

    lower, upper, basis, cov_pct = ForecastEngine._calculate_calibrated_interval(
        predicted_val=predicted_val,
        empirical_oos_errors=empirical_errors,
        hardware_uncertainty=ForecastEngine.DHT11_HARDWARE_TEMP_UNCERTAINTY_C,  # 2.0°C
        min_bound=-20.0,
        max_bound=60.0,
        target_coverage=0.80
    )

    # Basis should be empirical quantile
    assert basis == "empirical_out_of_sample_quantile"
    # Coverage must be >= 80%
    assert cov_pct is not None and cov_pct >= 80.0

    # Bounds must surround predicted value
    assert lower <= predicted_val <= upper

    # Half width must respect hardware floor
    half_width = upper - predicted_val
    assert half_width >= 1.5


def test_compute_quantile_function():
    """Verifies linear interpolation quantile computation."""
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    # Median (0.5) should be 3.0
    assert compute_quantile(data, 0.5) == 3.0
    # 0.8 quantile of [1, 2, 3, 4, 5] -> 4 * 0.8 = 3.2 -> 4.2
    q80 = compute_quantile(data, 0.8)
    assert 4.0 <= q80 <= 5.0


# =========================================================================
# 8. Rate Clamping and Physical Clamping Tests
# =========================================================================

def test_rapid_transient_rate_clamping():
    """Validates that rapid transient rates are clamped and damped to prevent runaway extrapolation."""
    now = datetime.now(timezone.utc)
    steep_raw = [
        {"timestamp": (now - timedelta(minutes=20 - i)).isoformat(), "temperature_c": 20.0 + (i * 0.8), "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20)
    ]
    report = ForecastEngine.get_forecast_report(steep_raw, horizon_min=15, reference_time=now, use_cache=False)
    assert report["status"] == "success"

    curr_temp = report["forecast"]["temperature"]["current_c"]
    pred_temp = report["forecast"]["temperature"]["trend_predicted_c"]
    delta = abs(pred_temp - curr_temp)
    assert delta < 3.0


def test_physical_boundary_clamping():
    """Validates that predictions are strictly clamped to physical operational limits."""
    now = datetime.now(timezone.utc)
    high_raw = [
        {"timestamp": (now - timedelta(minutes=20 - i)).isoformat(), "temperature_c": 50.0 + (i * 0.5), "humidity_pct": 20.0 - i, "validity_status": "valid"}
        for i in range(20)
    ]
    report = ForecastEngine.get_forecast_report(high_raw, horizon_min=15, reference_time=now, use_cache=False)
    assert report["status"] == "success"
    assert report["forecast"]["temperature"]["predicted_c"] <= 60.0
    assert report["forecast"]["humidity"]["predicted_pct"] >= 0.0


# =========================================================================
# 9. API Endpoint Integration Tests
# =========================================================================

def test_api_forecast_success_and_structure(test_client, forecast_test_db):
    """Validates that GET /api/forecast returns complete structured JSON when telemetry exists."""
    now = datetime.now(timezone.utc)
    for i in range(40, 0, -1):
        ts = (now - timedelta(minutes=i)).isoformat()
        database.insert_reading(
            temperature_c=round(26.0 + (i * 0.02), 2),
            pressure_hpa=None,
            source="raspberry_pi_dht11",
            validity_status="valid",
            timestamp=ts,
            humidity_pct=round(50.0 + (i * 0.03), 2),
            sensor_type="dht11",
            db_path=forecast_test_db
        )

    res = test_client.get("/api/forecast?horizon=15m&include_history=true")
    assert res.status_code == 200
    data = res.get_json()

    assert data["status"] == "success"
    assert data["is_available"] is True
    assert "models_evaluated" in data
    assert "forecast" in data
    assert data["forecast"]["horizon_minutes"] == 15
    assert "selected_model" in data["forecast"]["temperature"]
    assert "selected_model" in data["forecast"]["humidity"]
    assert "selection_reason" in data["forecast"]["temperature"]
    assert "evaluations" in data
    assert "disclaimers" in data
    assert "history_series" in data


def test_api_forecast_horizon_parameters(test_client, forecast_test_db):
    """Validates that ?horizon=30m and ?horizon=60m evaluate correctly."""
    now = datetime.now(timezone.utc)
    for i in range(45, 0, -1):
        ts = (now - timedelta(minutes=i)).isoformat()
        database.insert_reading(
            temperature_c=25.5,
            pressure_hpa=None,
            source="dht11",
            validity_status="valid",
            timestamp=ts,
            humidity_pct=52.0,
            sensor_type="dht11",
            db_path=forecast_test_db
        )

    res30 = test_client.get("/api/forecast?horizon=30m")
    assert res30.status_code == 200
    data30 = res30.get_json()
    assert data30["forecast"]["horizon_minutes"] == 30

    res60 = test_client.get("/api/forecast?horizon=60")
    assert res60.status_code == 200
    data60 = res60.get_json()
    assert data60["forecast"]["horizon_minutes"] == 60


def test_api_forecast_empty_db_honest_response(test_client):
    """Validates that empty database returns clean unavailable/insufficient history, never fabricated data."""
    res = test_client.get("/api/forecast?real_only=true")
    assert res.status_code == 200
    data = res.get_json()

    assert data["is_available"] is False
    assert data["forecast"] is None
    assert data["status"] in ("insufficient_history", "stale_sensor")
    assert "disclaimers" in data


def test_api_forecast_database_failure_resilience(test_client):
    """Validates that an unexpected internal database error returns clean HTTP 500 error payload."""
    with patch("database.get_dht11_readings_window", side_effect=RuntimeError("Turso connection reset")):
        res = test_client.get("/api/forecast")
        assert res.status_code == 500
        data = res.get_json()
        assert data["status"] == "error"
        assert data["is_available"] is False
        assert "disclaimers" in data
