"""
Virtual Atmosphere - Comprehensive Chart System Tests
Verifies:
- Time-range filtering (1h, 6h, 24h, 7d, 30d, and custom ISO start/end)
- Peak-preserving and threshold-preserving downsampling
- Statistical calculation accuracy (computed from all raw readings)
- Missing data gap insertion without bridging across missing periods
- Real versus simulated data filtering (real_only)
- Distinction between DHT11 (temp & humidity) and BMP280 (pressure)
- Rendered chart structure across Dashboard, Live Data, and History pages
"""

import json
from datetime import datetime, timezone, timedelta
import pytest
from app import create_app
from config import Config
import database


@pytest.fixture
def chart_test_setup(tmp_path):
    db_file = str(tmp_path / "test_charts.db")
    database.init_db(db_path=db_file)
    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": db_file,
        "MODE": "live"
    })
    with app.test_client() as client:
        yield client, db_file


# ---------------------------------------------------------------------------
# 1. Time-Range Filtering Tests
# ---------------------------------------------------------------------------

def test_time_range_presets(chart_test_setup):
    """Test 1h, 6h, 24h, 7d, and 30d range filtering."""
    client, db_file = chart_test_setup
    now = datetime.now(timezone.utc)

    # Insert readings at various age intervals:
    # 30m ago (fits in 1h, 6h, 24h, 7d, 30d)
    database.insert_reading(24.0, 1012.0, timestamp=(now - timedelta(minutes=30)).isoformat(), humidity_pct=50.0, db_path=db_file)
    # 3h ago (fits in 6h, 24h, 7d, 30d)
    database.insert_reading(26.0, 1013.0, timestamp=(now - timedelta(hours=3)).isoformat(), humidity_pct=55.0, db_path=db_file)
    # 12h ago (fits in 24h, 7d, 30d)
    database.insert_reading(28.0, 1014.0, timestamp=(now - timedelta(hours=12)).isoformat(), humidity_pct=60.0, db_path=db_file)
    # 3d ago (fits in 7d, 30d)
    database.insert_reading(30.0, 1015.0, timestamp=(now - timedelta(days=3)).isoformat(), humidity_pct=65.0, db_path=db_file)
    # 15d ago (fits in 30d)
    database.insert_reading(32.0, 1016.0, timestamp=(now - timedelta(days=15)).isoformat(), humidity_pct=70.0, db_path=db_file)
    # 45d ago (outside 30d)
    database.insert_reading(34.0, 1017.0, timestamp=(now - timedelta(days=45)).isoformat(), humidity_pct=75.0, db_path=db_file)

    # 1h filter
    r1h = client.get("/api/readings?range=1h").get_json()
    assert r1h["summary"]["count"] == 1
    assert r1h["summary"]["range"] == "1h"

    # 6h filter
    r6h = client.get("/api/readings?range=6h").get_json()
    assert r6h["summary"]["count"] == 2
    assert r6h["summary"]["range"] == "6h"

    # 24h filter
    r24h = client.get("/api/readings?range=24h").get_json()
    assert r24h["summary"]["count"] == 3
    assert r24h["summary"]["range"] == "24h"

    # 7d filter
    r7d = client.get("/api/readings?range=7d").get_json()
    assert r7d["summary"]["count"] == 4
    assert r7d["summary"]["range"] == "7d"

    # 30d filter
    r30d = client.get("/api/readings?range=30d").get_json()
    assert r30d["summary"]["count"] == 5
    assert r30d["summary"]["range"] == "30d"


def test_custom_start_end_date_filtering(chart_test_setup):
    """Test custom start and end ISO timestamp filtering on /api/readings."""
    client, db_file = chart_test_setup

    t1 = "2026-06-01T10:00:00+00:00"
    t2 = "2026-06-01T12:00:00+00:00"
    t3 = "2026-06-01T14:00:00+00:00"
    t4 = "2026-06-01T16:00:00+00:00"

    database.insert_reading(20.0, 1010.0, timestamp=t1, db_path=db_file)
    database.insert_reading(22.0, 1012.0, timestamp=t2, db_path=db_file)
    database.insert_reading(24.0, 1014.0, timestamp=t3, db_path=db_file)
    database.insert_reading(26.0, 1016.0, timestamp=t4, db_path=db_file)

    # Filter between 11:00 and 15:00
    res = client.get(f"/api/readings?start=2026-06-01T11:00:00Z&end=2026-06-01T15:00:00Z")
    assert res.status_code == 200
    data = res.get_json()
    assert data["summary"]["count"] == 2
    assert data["summary"]["temp_min"] == 22.0
    assert data["summary"]["temp_max"] == 24.0


# ---------------------------------------------------------------------------
# 2. Downsampling & Peak Preservation Tests
# ---------------------------------------------------------------------------

def test_downsampling_preserves_extrema_and_threshold_crossings():
    """Verify that downsampling strictly retains global min/max and threshold crossings."""
    readings = []
    base_time = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)

    # Generate 600 readings (dense dataset)
    # Inject a dramatic low spike at index 120 (11.2°C)
    # Inject a threshold-exceeding high spike at index 450 (39.8°C with threshold 35.0°C)
    for i in range(600):
        ts = (base_time + timedelta(minutes=i * 2)).isoformat()
        if i == 120:
            temp = 11.2
        elif i == 450:
            temp = 39.8
        else:
            temp = 25.0 + (i % 5) * 0.5
        readings.append({
            "id": i + 1,
            "timestamp": ts,
            "temperature_c": temp,
            "pressure_hpa": 1013.0,
            "humidity_pct": 50.0,
            "heat_index_c": None
        })

    downsampled = database.downsample_readings(readings, max_points=200, threshold_c=35.0)

    # Resulting points must be reduced
    assert len(downsampled) <= 220
    assert len(downsampled) < len(readings)

    temps_downsampled = [r["temperature_c"] for r in downsampled if r.get("temperature_c") is not None]

    # Global min (11.2) must be preserved
    assert min(temps_downsampled) == 11.2

    # Global max (39.8) must be preserved
    assert max(temps_downsampled) == 39.8

    # Threshold violation reading (39.8 >= 35.0) must be preserved
    assert any(r["temperature_c"] == 39.8 for r in downsampled)

    # Chronological order must be strictly preserved
    timestamps = [r["timestamp"] for r in downsampled]
    assert timestamps == sorted(timestamps)


def test_missing_data_gap_insertion():
    """Verify that gaps in sensor telemetry are marked with a null break instead of bridging lines."""
    t0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=5)
    # Sensor went offline for 4 hours (14,400 seconds)
    t2 = t1 + timedelta(hours=4)
    t3 = t2 + timedelta(minutes=5)

    readings = [
        {"id": 1, "timestamp": t0.isoformat(), "temperature_c": 22.0, "pressure_hpa": 1013.0, "humidity_pct": 50.0},
        {"id": 2, "timestamp": t1.isoformat(), "temperature_c": 22.5, "pressure_hpa": 1013.0, "humidity_pct": 50.0},
        {"id": 3, "timestamp": t2.isoformat(), "temperature_c": 24.0, "pressure_hpa": 1012.0, "humidity_pct": 52.0},
        {"id": 4, "timestamp": t3.isoformat(), "temperature_c": 24.5, "pressure_hpa": 1012.0, "humidity_pct": 53.0},
    ]

    # max_gap_seconds=1800 (30 mins)
    result = database.downsample_readings(readings, max_points=100, max_gap_seconds=1800)

    # A gap point with temperature_c=None must be inserted between t1 and t2
    has_gap = any(r.get("is_gap") is True and r.get("temperature_c") is None for r in result)
    assert has_gap is True


def test_statistics_calculated_from_all_raw_records_not_downsampled(chart_test_setup):
    """Ensure statistical summaries use 100% of raw readings, never downsampled values."""
    client, db_file = chart_test_setup
    now = datetime.now(timezone.utc)

    # Insert 500 readings
    for i in range(500):
        ts = (now - timedelta(minutes=500 - i)).isoformat()
        database.insert_reading(
            temperature_c=20.0 + (i * 0.02), # 20.0 to 29.98
            pressure_hpa=1010.0,
            humidity_pct=40.0 + (i * 0.05),
            timestamp=ts,
            db_path=db_file
        )

    res = client.get("/api/readings?range=24h")
    assert res.status_code == 200
    data = res.get_json()

    summary = data["summary"]
    # Total count must be exactly 500
    assert summary["count"] == 500
    assert summary["temp_min"] == 20.0
    assert summary["temp_max"] == 29.98
    # Exact average
    expected_avg = round(sum(20.0 + (i * 0.02) for i in range(500)) / 500.0, 2)
    assert summary["temp_avg"] == expected_avg

    # Chart readings are downsampled for performance
    assert data["is_downsampled"] is True
    assert len(data["readings"]) < 500


# ---------------------------------------------------------------------------
# 3. Sensor Distinction & Pressure Unavailable Handling
# ---------------------------------------------------------------------------

def test_honest_pressure_unavailable_state_when_only_dht11(chart_test_setup):
    """When only DHT11 sensor readings exist (pressure is None), API honestly indicates pressure unavailable."""
    client, db_file = chart_test_setup
    now = datetime.now(timezone.utc)

    # Insert DHT11 reading (temperature & humidity only, pressure is None)
    database.insert_reading(
        temperature_c=28.5,
        pressure_hpa=None,
        humidity_pct=65.0,
        source="raspberry_pi_dht11",
        sensor_type="dht11",
        timestamp=now.isoformat(),
        db_path=db_file
    )

    res = client.get("/api/readings?range=24h")
    data = res.get_json()
    summary = data["summary"]

    assert summary["press_available"] is False
    assert summary["press_count"] == 0
    assert summary["press_latest"] is None
    assert summary["press_min"] is None
    assert summary["press_max"] is None

    # Temperature and humidity are available
    assert summary["temp_count"] == 1
    assert summary["temp_latest"] == 28.5
    assert summary["hum_count"] == 1
    assert summary["hum_latest"] == 65.0


def test_real_versus_simulated_data_filter(chart_test_setup):
    """Test real_only parameter distinguishes real hardware data from demo/simulated data."""
    client, db_file = chart_test_setup
    now = datetime.now(timezone.utc)

    # Insert 1 simulated reading and 1 hardware reading
    database.insert_reading(22.0, 1013.0, source="demo", timestamp=(now - timedelta(minutes=10)).isoformat(), db_path=db_file)
    database.insert_reading(25.0, 1014.0, source="hardware", timestamp=(now - timedelta(minutes=5)).isoformat(), db_path=db_file)

    # Default query (includes both)
    res_all = client.get("/api/readings?range=24h&real_only=0").get_json()
    assert res_all["summary"]["count"] == 2

    # real_only=1 query (strictly hardware)
    res_real = client.get("/api/readings?range=24h&real_only=1").get_json()
    assert res_real["summary"]["count"] == 1
    assert res_real["summary"]["temp_latest"] == 25.0


# ---------------------------------------------------------------------------
# 4. Rendered Pages Structure & Chart Separation Verification
# ---------------------------------------------------------------------------

def test_dashboard_contains_four_separated_chart_canvases(chart_test_setup):
    """Verify Dashboard page has dedicated separated canvases and empty overlays."""
    client, _ = chart_test_setup
    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # 4 distinct canvases
    assert 'id="temperatureChart"' in html
    assert 'id="humidityChart"' in html
    assert 'id="heatIndexChart"' in html
    assert 'id="pressureChart"' in html

    # Empty overlays
    assert 'id="tempChartEmptyOverlay"' in html
    assert 'id="humChartEmptyOverlay"' in html
    assert 'id="heatChartEmptyOverlay"' in html
    assert 'id="pressChartEmptyOverlay"' in html

    # Range buttons 1h to 30d
    assert 'data-range="1h"' in html
    assert 'data-range="6h"' in html
    assert 'data-range="24h"' in html
    assert 'data-range="7d"' in html
    assert 'data-range="30d"' in html

    # Clickable series legend
    assert 'id="dashboardLegendToggles"' in html
    assert 'id="tempChartStatsBar"' in html
    assert 'id="humChartStatsBar"' in html
    assert 'id="heatChartStatsBar"' in html
    assert 'id="pressChartStatsBar"' in html


def test_live_monitor_contains_live_charts_and_range_controls(chart_test_setup):
    """Verify Live Data page includes real-time streaming charts and range controls."""
    client, _ = chart_test_setup
    res = client.get("/live")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Live canvases
    assert 'id="liveTempChart"' in html
    assert 'id="liveHumChart"' in html
    assert 'id="liveHeatChart"' in html
    assert 'id="livePressChart"' in html

    # Live range selectors
    assert 'id="liveRangeSelector"' in html
    assert 'data-range="1h"' in html
    assert 'data-range="30d"' in html

    # Polling frequency group
    assert 'id="livePollingIntervalGroup"' in html


def test_history_page_contains_four_separated_historical_charts(chart_test_setup):
    """Verify History page provides 4 separated charts with presets and custom date filters."""
    client, _ = chart_test_setup
    res = client.get("/history")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Historical canvases
    assert 'id="historyChart"' in html
    assert 'id="historyHumChart"' in html
    assert 'id="historyHeatChart"' in html
    assert 'id="historyPressChart"' in html

    # Custom date filter inputs
    assert 'id="filterStartDate"' in html
    assert 'id="filterEndDate"' in html
    assert 'id="historyPresetGroup"' in html
