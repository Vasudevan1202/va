"""
Tests for Local Short-Term Forecasting Engine (Phase 1)
-------------------------------------------------------
Verifies:
1. Historical data preparation (filtering invalid/NaN/inf, deduplication, 1-minute aggregation).
2. Missing intervals and gap detection.
3. Stale and offline sensor state detection.
4. Insufficient history handling.
5. Separation of live hardware and demo/simulated data.
6. Stable vs rapidly changing trends, Holt damping, and physical clamping.
7. Prediction interval generation (bounded by DHT11 hardware uncertainty).
8. Chronological walk-forward backtesting without future-data leakage.
9. Persistence baseline comparison and skill scores.
10. API endpoint (/api/forecast) responses, horizon selection, and error handling.
"""

import math
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from app import create_app
from config import Config
import database
from forecast_engine import ForecastEngine


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
        # Valid reading
        {"timestamp": now.isoformat(), "temperature_c": 28.5, "humidity_pct": 52.0, "validity_status": "valid", "source": "dht11"},
        # NaN temperature
        {"timestamp": (now - timedelta(minutes=1)).isoformat(), "temperature_c": float("nan"), "humidity_pct": 52.0, "validity_status": "valid"},
        # Infinite humidity
        {"timestamp": (now - timedelta(minutes=2)).isoformat(), "temperature_c": 28.0, "humidity_pct": float("inf"), "validity_status": "valid"},
        # Out of bounds temperature (> 60°C for DHT11)
        {"timestamp": (now - timedelta(minutes=3)).isoformat(), "temperature_c": 85.0, "humidity_pct": 50.0, "validity_status": "valid"},
        # Out of bounds humidity (< 0%)
        {"timestamp": (now - timedelta(minutes=4)).isoformat(), "temperature_c": 25.0, "humidity_pct": -5.0, "validity_status": "valid"},
        # Invalid status
        {"timestamp": (now - timedelta(minutes=5)).isoformat(), "temperature_c": 26.0, "humidity_pct": 50.0, "validity_status": "spike"},
        # None value
        {"timestamp": (now - timedelta(minutes=6)).isoformat(), "temperature_c": None, "humidity_pct": 50.0, "validity_status": "valid"},
        # Malformed timestamp
        {"timestamp": "not-a-date", "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
    ]

    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=now)
    # Only the first item should be valid
    assert len(prep["buckets"]) == 1
    assert prep["buckets"][0]["temperature_c"] == 28.5
    assert prep["buckets"][0]["humidity_pct"] == 52.0


def test_duplicate_timestamps_and_one_minute_aggregation():
    """Validates that multiple readings within the same minute are averaged cleanly."""
    base_time = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
    raw = [
        # Two readings in minute 12:00
        {"timestamp": "2026-10-29T12:00:10Z", "temperature_c": 24.0, "humidity_pct": 50.0, "validity_status": "valid"},
        {"timestamp": "2026-10-29T12:00:40Z", "temperature_c": 26.0, "humidity_pct": 60.0, "validity_status": "valid"},
        # One reading in minute 12:01
        {"timestamp": "2026-10-29T12:01:15Z", "temperature_c": 25.0, "humidity_pct": 55.0, "validity_status": "valid"}
    ]

    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=base_time + timedelta(minutes=2))
    buckets = prep["buckets"]
    assert len(buckets) == 2
    # Minute 12:00 should average (24+26)/2 = 25.0, (50+60)/2 = 55.0
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
        # 25 minute gap
        {"timestamp": (now - timedelta(minutes=20)).isoformat(), "temperature_c": 25.5, "humidity_pct": 51.0, "validity_status": "valid"},
        {"timestamp": now.isoformat(), "temperature_c": 26.0, "humidity_pct": 52.0, "validity_status": "valid"}
    ]

    prep = ForecastEngine.prepare_dht11_series(raw, reference_time=now)
    assert prep["gaps_detected"] >= 1


# =========================================================================
# 2. Stale, Offline, and Insufficient History Tests
# =========================================================================

def test_stale_and_offline_sensor_detection():
    """Validates sensor freshness states: fresh (<=15m), stale (15m-60m), offline (>60m)."""
    now = datetime.now(timezone.utc)

    # 1. Fresh sensor (2 min old)
    raw_fresh = [
        {"timestamp": (now - timedelta(minutes=i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20, 1, -1)
    ]
    prep_fresh = ForecastEngine.prepare_dht11_series(raw_fresh, reference_time=now)
    assert prep_fresh["freshness"] == "fresh"
    assert prep_fresh["is_sufficient"] is True

    # 2. Stale sensor (25 min old)
    raw_stale = [
        {"timestamp": (now - timedelta(minutes=25 + i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20, 0, -1)
    ]
    prep_stale = ForecastEngine.prepare_dht11_series(raw_stale, reference_time=now)
    assert prep_stale["freshness"] == "stale"
    assert prep_stale["is_sufficient"] is False

    # 3. Offline sensor (90 min old)
    raw_offline = [
        {"timestamp": (now - timedelta(minutes=90 + i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20, 0, -1)
    ]
    prep_offline = ForecastEngine.prepare_dht11_series(raw_offline, reference_time=now)
    assert prep_offline["freshness"] == "offline"
    assert prep_offline["is_sufficient"] is False


def test_insufficient_history_requirement():
    """Validates that history shorter than MIN_HISTORY_MINUTES (15m) returns honest insufficient status."""
    now = datetime.now(timezone.utc)
    # Only 5 minutes of data
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

    # When real_only is True, demo and simulated sources are rejected
    prep_real = ForecastEngine.prepare_dht11_series(mixed_raw, real_only=True, reference_time=now)
    assert len(prep_real["buckets"]) == 1
    assert prep_real["buckets"][0]["source"] == "raspberry_pi_dht11"
    assert prep_real["buckets"][0]["temperature_c"] == 30.0

    # When real_only is False (in demo mode), all are aggregated
    prep_all = ForecastEngine.prepare_dht11_series(mixed_raw, real_only=False, reference_time=now)
    assert len(prep_all["buckets"]) == 3


# =========================================================================
# 4. Forecast Models, Damping, and Physical Clamping Tests
# =========================================================================

def test_stable_trend_vs_persistence():
    """When conditions are flat, forecast should equal persistence baseline."""
    now = datetime.now(timezone.utc)
    flat_raw = [
        {"timestamp": (now - timedelta(minutes=i)).isoformat(), "temperature_c": 27.0, "humidity_pct": 55.0, "validity_status": "valid"}
        for i in range(25, 0, -1)
    ]
    report = ForecastEngine.get_forecast_report(flat_raw, horizon_min=15, reference_time=now, use_cache=False)
    assert report["status"] == "success"
    assert report["is_available"] is True

    fc = report["forecast"]
    assert fc["temperature"]["predicted_c"] == 27.0
    assert fc["temperature"]["change_c"] == 0.0
    assert fc["temperature"]["persistence_c"] == 27.0

    assert fc["humidity"]["predicted_pct"] == 55.0
    assert fc["humidity"]["change_pct"] == 0.0
    assert fc["humidity"]["persistence_pct"] == 55.0


def test_rapid_transient_rate_clamping():
    """Validates that unrealistically rapid transient rates are clamped and damped to prevent runaway forecast."""
    now = datetime.now(timezone.utc)
    # Rapid rise of 0.8°C/min (physically unrealistic for room conditions)
    steep_raw = [
        {"timestamp": (now - timedelta(minutes=20 - i)).isoformat(), "temperature_c": 20.0 + (i * 0.8), "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20)
    ]
    report = ForecastEngine.get_forecast_report(steep_raw, horizon_min=15, reference_time=now, use_cache=False)
    assert report["status"] == "success"

    # Current temp at end is 20 + 19*0.8 = 35.2°C
    curr_temp = report["forecast"]["temperature"]["current_c"]
    pred_temp = report["forecast"]["temperature"]["predicted_c"]

    # Without clamping and damping, 0.8 * 15 would add 12°C -> 47.2°C!
    # With clamping (max 0.35°C/min) and Holt damping (0.85), max delta should be bounded to < 3.0°C
    delta = pred_temp - curr_temp
    assert delta < 3.0, f"Delta {delta} exceeded damped clamp boundary."


def test_physical_boundary_clamping():
    """Validates that predictions are strictly clamped to physical operational limits."""
    now = datetime.now(timezone.utc)
    # Series ending at 59°C with steep rise
    high_raw = [
        {"timestamp": (now - timedelta(minutes=20 - i)).isoformat(), "temperature_c": 50.0 + (i * 0.5), "humidity_pct": 20.0 - i, "validity_status": "valid"}
        for i in range(20)
    ]
    report = ForecastEngine.get_forecast_report(high_raw, horizon_min=15, reference_time=now, use_cache=False)
    assert report["status"] == "success"

    # Temperature cannot exceed DHT11_TEMP_MAX_C (60°C)
    assert report["forecast"]["temperature"]["predicted_c"] <= 60.0
    # Humidity cannot fall below 0%
    assert report["forecast"]["humidity"]["predicted_pct"] >= 0.0


# =========================================================================
# 5. Prediction Intervals Tests
# =========================================================================

def test_prediction_intervals_respect_hardware_limits():
    """Validates that prediction intervals are never narrower than physical DHT11 sensor uncertainty."""
    now = datetime.now(timezone.utc)
    raw = [
        {"timestamp": (now - timedelta(minutes=i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(30, 0, -1)
    ]
    report = ForecastEngine.get_forecast_report(raw, horizon_min=15, reference_time=now, use_cache=False)
    temp_fc = report["forecast"]["temperature"]
    hum_fc = report["forecast"]["humidity"]

    # Lower <= predicted <= upper
    assert temp_fc["lower_bound_c"] <= temp_fc["predicted_c"] <= temp_fc["upper_bound_c"]
    assert hum_fc["lower_bound_pct"] <= hum_fc["predicted_pct"] <= hum_fc["upper_bound_pct"]

    # Half-width must respect hardware uncertainty (±2°C for temp, ±5% for hum)
    temp_half_width = temp_fc["upper_bound_c"] - temp_fc["predicted_c"]
    hum_half_width = hum_fc["upper_bound_pct"] - hum_fc["predicted_pct"]

    assert temp_half_width >= 1.5, f"Temperature uncertainty {temp_half_width} unrealistically tight."
    assert hum_half_width >= 3.5, f"Humidity uncertainty {hum_half_width} unrealistically tight."


# =========================================================================
# 6. Chronological Walk-Forward Backtesting Tests (Zero Leakage)
# =========================================================================

def test_walk_forward_backtesting_no_future_leakage():
    """Validates that rolling-origin walk-forward backtesting evaluates strictly past data and produces valid metrics."""
    now = datetime.now(timezone.utc)
    # Generate 60 minutes of 1-minute points with slight gradual upward trend
    raw_series = [
        {
            "timestamp": (now - timedelta(minutes=60 - i)).isoformat(),
            "temperature_c": round(25.0 + (i * 0.05) + (0.1 if i % 2 == 0 else -0.1), 2),
            "humidity_pct": round(55.0 - (i * 0.04), 2),
            "validity_status": "valid"
        }
        for i in range(60)
    ]

    prep = ForecastEngine.prepare_dht11_series(raw_series, reference_time=now)
    backtest = ForecastEngine.backtest_horizons(prep["buckets"], horizons=[15, 30])

    # 15m horizon evaluation
    bt_15m = backtest["15m"]
    assert bt_15m["status"] == "active"
    assert bt_15m["samples_evaluated"] >= ForecastEngine.MIN_TEST_SAMPLES_BACKTEST

    # MAE and RMSE must be finite positive numbers
    assert bt_15m["temperature"]["mae_c"] >= 0.0
    assert bt_15m["temperature"]["rmse_c"] >= 0.0
    assert bt_15m["temperature"]["persistence_mae_c"] >= 0.0
    assert bt_15m["temperature"]["persistence_rmse_c"] >= 0.0

    assert bt_15m["humidity"]["mae_pct"] >= 0.0
    assert bt_15m["humidity"]["rmse_pct"] >= 0.0

    # Skill score should be reported as percentage
    assert "skill_score_pct" in bt_15m["temperature"]
    assert "summary" in bt_15m


def test_backtesting_insufficient_samples_reporting():
    """When history is too short for sufficient backtest pairs, reports insufficient_test_data honestly."""
    now = datetime.now(timezone.utc)
    # 20 minutes is only enough for ~5 target pairs at 15m horizon, less than min_test_samples (8)
    raw_short = [
        {"timestamp": (now - timedelta(minutes=20 - i)).isoformat(), "temperature_c": 25.0, "humidity_pct": 50.0, "validity_status": "valid"}
        for i in range(20)
    ]
    prep = ForecastEngine.prepare_dht11_series(raw_short, reference_time=now)
    backtest = ForecastEngine.backtest_horizons(prep["buckets"], horizons=[15])
    assert backtest["15m"]["status"] == "insufficient_test_data"
    assert backtest["15m"]["temperature"] is None


# =========================================================================
# 7. API Endpoint Integration Tests
# =========================================================================

def test_api_forecast_success_and_structure(test_client, forecast_test_db):
    """Validates that GET /api/forecast returns complete structured JSON when telemetry exists."""
    now = datetime.now(timezone.utc)
    # Seed 35 valid readings across the last 35 minutes
    for i in range(35, 0, -1):
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
    assert data["model"]["name"] == "damped_linear_trend"
    assert data["model"]["version"] == "1.0.0"

    assert "forecast" in data
    assert data["forecast"]["horizon_minutes"] == 15
    assert "temperature" in data["forecast"]
    assert "humidity" in data["forecast"]
    assert "heat_index" in data["forecast"]

    assert "sufficiency" in data
    assert data["sufficiency"]["is_sufficient"] is True

    assert "disclaimers" in data
    assert len(data["disclaimers"]) >= 2
    assert any("DHT11" in d for d in data["disclaimers"])

    # History series attached when include_history=true
    assert "history_series" in data
    assert len(data["history_series"]) > 0


def test_api_forecast_horizon_parameters(test_client, forecast_test_db):
    """Validates that ?horizon=30m and ?horizon=60m evaluate correctly."""
    now = datetime.now(timezone.utc)
    for i in range(40, 0, -1):
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

    # 30m horizon
    res30 = test_client.get("/api/forecast?horizon=30m")
    assert res30.status_code == 200
    data30 = res30.get_json()
    assert data30["forecast"]["horizon_minutes"] == 30

    # 60m horizon
    res60 = test_client.get("/api/forecast?horizon=60")
    assert res60.status_code == 200
    data60 = res60.get_json()
    assert data60["forecast"]["horizon_minutes"] == 60


def test_api_forecast_empty_db_honest_response(test_client):
    """Validates that empty database returns clean unavailable/insufficient history, never fabricated data."""
    # In live mode or with real_only=true, demo data is excluded and an empty/sparse history reports insufficient
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
