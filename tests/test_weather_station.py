import pytest
import hmac
import json
from datetime import datetime, timezone
import database
from app import create_app
from config import Config
from weather_service import WeatherService
from hardware_adapters import BME280Driver, DHT11Adapter, GPSAdapter

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_weather_station.db")
    database.init_db(db_path=db_file)
    return db_file

@pytest.fixture
def app_client(test_db):
    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": test_db,
        "MODE": "demo"
    })
    with app.test_client() as client:
        yield client

# ---------------------------------------------------------------------------
# 1. WeatherService & NOAA Rothfusz Algorithm Tests
# ---------------------------------------------------------------------------

def test_heat_index_requires_both_temp_and_humidity():
    # Heat index must never be computed from temperature alone
    assert WeatherService.compute_heat_index(35.0, None) is None
    assert WeatherService.compute_heat_index(None, 65.0) is None
    assert WeatherService.compute_heat_index(None, None) is None

def test_heat_index_below_nws_threshold():
    # Below 26.7°C (80°F), heat index is not clinically applicable (normal cooling occurs)
    assert WeatherService.compute_heat_index(22.0, 75.0) is None
    assert WeatherService.compute_heat_index(25.0, 60.0) is None

    assessment = WeatherService.get_heat_risk_assessment(22.0, 75.0)
    assert assessment["category"] == "Normal"
    assert assessment["badge_class"] == "success"
    assert assessment["heat_index_c"] is None
    assert assessment["is_applicable"] is False

def test_heat_index_elevated_conditions():
    # 32°C (89.6°F) and 70% RH should yield elevated heat index in Extreme Caution or Danger
    hi = WeatherService.compute_heat_index(32.0, 70.0)
    assert hi is not None
    assert hi > 32.0  # Apparent temperature exceeds ambient

    assessment = WeatherService.get_heat_risk_assessment(32.0, 70.0)
    assert assessment["is_applicable"] is True
    assert assessment["category"] in ("Extreme Caution", "Danger")
    assert assessment["badge_class"] in ("warning", "danger")
    assert "Rothfusz" in assessment["formula_basis"]

def test_heat_risk_incomplete_data():
    assessment = WeatherService.get_heat_risk_assessment(30.0, None)
    assert assessment["is_applicable"] is False
    assert assessment["category"] == "Incomplete Data"
    assert "BMP280 lacks humidity" in assessment["advisory"]

def test_meteorological_validation():
    # Valid
    valid, msg = WeatherService.validate_reading(25.0, 1013.25, 55.0, 12.97, 77.59)
    assert valid is True
    assert msg == "valid"

    # Temperature out of bounds
    valid, msg = WeatherService.validate_reading(120.0, 1013.25)
    assert valid is False
    assert "Temperature" in msg

    # Pressure out of bounds
    valid, msg = WeatherService.validate_reading(25.0, 150.0)
    assert valid is False
    assert "pressure" in msg

    # Humidity out of bounds
    valid, msg = WeatherService.validate_reading(25.0, 1013.25, 110.0)
    assert valid is False
    assert "humidity" in msg

    # GPS latitude out of bounds
    valid, msg = WeatherService.validate_reading(25.0, 1013.25, 50.0, 95.0, 50.0)
    assert valid is False
    assert "Latitude" in msg

# ---------------------------------------------------------------------------
# 2. Database Schema Extension & Auto-Migration Tests
# ---------------------------------------------------------------------------

def test_database_nullable_columns(test_db):
    # Insert reading without humidity (e.g. BMP280 legacy)
    r1 = database.insert_reading(
        temperature_c=25.0,
        pressure_hpa=1013.0,
        source="hardware",
        db_path=test_db
    )
    latest1 = database.get_latest_reading(db_path=test_db)
    assert latest1["id"] == r1
    assert latest1["humidity_pct"] is None
    assert latest1["heat_index_c"] is None
    assert latest1["latitude"] is None
    assert latest1["longitude"] is None

    # Insert reading with humidity and GPS
    r2 = database.insert_reading(
        temperature_c=31.0,
        pressure_hpa=1012.0,
        source="hardware",
        humidity_pct=65.0,
        latitude=12.9716,
        longitude=77.5946,
        db_path=test_db
    )
    latest2 = database.get_latest_reading(db_path=test_db)
    assert latest2["id"] == r2
    assert latest2["humidity_pct"] == 65.0
    assert latest2["heat_index_c"] is not None  # Auto-computed via WeatherService
    assert latest2["latitude"] == 12.9716
    assert latest2["longitude"] == 77.5946

def test_database_today_stats_with_humidity(test_db):
    database.insert_reading(temperature_c=20.0, pressure_hpa=1010.0, humidity_pct=40.0, db_path=test_db)
    database.insert_reading(temperature_c=30.0, pressure_hpa=1020.0, humidity_pct=80.0, db_path=test_db)

    stats = database.get_today_stats(db_path=test_db)
    assert stats["count"] == 2
    assert stats["min_humidity"] == 40.0
    assert stats["max_humidity"] == 80.0
    assert stats["avg_humidity"] == 60.0

# ---------------------------------------------------------------------------
# 3. Secure Telemetry Ingestion Endpoint Tests
# ---------------------------------------------------------------------------

def test_telemetry_missing_auth(app_client):
    res = app_client.post("/api/telemetry", json={"temperature_c": 25.0, "pressure_hpa": 1013.0})
    assert res.status_code == 401
    data = res.get_json()
    assert data["status"] == "error"

def test_telemetry_invalid_token(app_client):
    headers = {"Authorization": "Bearer wrong-secret-token"}
    res = app_client.post("/api/telemetry", json={"temperature_c": 25.0, "pressure_hpa": 1013.0}, headers=headers)
    assert res.status_code == 401

def test_telemetry_missing_required_fields(app_client):
    headers = {"Authorization": f"Bearer {Config.INGEST_KEY}"}
    res = app_client.post("/api/telemetry", json={"temperature_c": 25.0}, headers=headers)
    assert res.status_code == 400
    assert "mandatory" in res.get_json()["error"]

def test_telemetry_out_of_bounds_reading(app_client):
    headers = {"Authorization": f"Bearer {Config.INGEST_KEY}"}
    res = app_client.post("/api/telemetry", json={
        "temperature_c": 150.0,
        "pressure_hpa": 1013.0
    }, headers=headers)
    assert res.status_code == 400
    assert "Invalid measurement bounds" in res.get_json()["error"]

def test_telemetry_valid_hardware_submission(app_client):
    headers = {"Authorization": f"Bearer {Config.INGEST_KEY}"}
    res = app_client.post("/api/telemetry", json={
        "temperature_c": 28.5,
        "pressure_hpa": 1014.2,
        "humidity_pct": 62.0,
        "latitude": 12.9716,
        "longitude": 77.5946,
        "source": "hardware"
    }, headers=headers)

    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "success"
    assert data["source"] == "hardware"
    assert data["temperature_c"] == 28.5
    assert data["humidity_pct"] == 62.0
    assert data["heat_risk"] is not None
    assert data["heat_risk"]["is_applicable"] is True

def test_telemetry_simulated_submission_preserved(app_client):
    headers = {"Authorization": f"Bearer {Config.INGEST_KEY}"}
    res = app_client.post("/api/telemetry", json={
        "temperature_c": 24.0,
        "pressure_hpa": 1013.0,
        "humidity_pct": 50.0,
        "source": "simulated"
    }, headers=headers)

    assert res.status_code == 201
    data = res.get_json()
    assert data["source"] == "simulated"
    assert data["heat_risk"]["is_simulated"] is True

def test_telemetry_invalid_source_rejected(app_client):
    headers = {"Authorization": f"Bearer {Config.INGEST_KEY}"}
    res = app_client.post("/api/telemetry", json={
        "temperature_c": 24.0,
        "pressure_hpa": 1013.0,
        "source": "unauthorized_fake_source"
    }, headers=headers)
    assert res.status_code == 400
    assert "Invalid source" in res.get_json()["error"]

def test_telemetry_malformed_payload(app_client):
    headers = {"Authorization": f"Bearer {Config.INGEST_KEY}", "Content-Type": "application/json"}
    # Non-dict JSON (array)
    res = app_client.post("/api/telemetry", data="[1, 2, 3]", headers=headers)
    assert res.status_code == 400

    # Non-numeric temperature
    res2 = app_client.post("/api/telemetry", json={
        "temperature_c": "twenty-five",
        "pressure_hpa": 1013.0
    }, headers=headers)
    assert res2.status_code == 400
    assert "numeric" in res2.get_json()["error"]

def test_pi_client_hardware_failure_does_not_fabricate_data():
    from scripts.pi_telemetry_client import PiTelemetryStation
    # Without physical I2C sensor hardware, hardware mode MUST NOT fabricate simulated data
    client = PiTelemetryStation(
        server_url="http://127.0.0.1:5000",
        token="test-token",
        mode="hardware"
    )
    sample = client.sample()
    assert sample is None  # Never fabricate readings on hardware failure

def test_pi_client_explicit_simulation_mode():
    from scripts.pi_telemetry_client import PiTelemetryStation
    # Explicit simulated mode must clearly generate simulated data
    client = PiTelemetryStation(
        server_url="http://127.0.0.1:5000",
        token="test-token",
        mode="simulated"
    )
    sample = client.sample()
    assert sample is not None
    assert sample["source"] == "simulated"
    assert "temperature_c" in sample
    assert "pressure_hpa" in sample
    assert "humidity_pct" in sample

# ---------------------------------------------------------------------------
# 4. Hardware Adapters Safety Tests
# ---------------------------------------------------------------------------

def test_hardware_adapters_safe_instantiation():
    # Must not raise exceptions on non-Pi platforms
    bme = BME280Driver(bus_num=1)
    assert bme.sensor_type == "Unknown"
    assert bme.has_humidity is False

    dht = DHT11Adapter(pin=4, enabled=False)
    temp, hum = dht.read()
    assert temp is None and hum is None

    gps = GPSAdapter(port="/dev/serial0", enabled=False)
    coords = gps.read_coordinates()
    assert coords is None

def test_gps_nmea_coordinate_parsing():
    # Latitude: 1258.2960 N -> 12 degrees + 58.2960/60 = 12.9716
    lat = GPSAdapter._parse_nmea_coord("1258.2960", "N")
    assert round(lat, 4) == 12.9716

    # Longitude: 07735.6760 E -> 77 degrees + 35.6760/60 = 77.5946
    lon = GPSAdapter._parse_nmea_coord("07735.6760", "E")
    assert round(lon, 4) == 77.5946

    # South and West signs
    lat_s = GPSAdapter._parse_nmea_coord("1258.2960", "S")
    assert lat_s < 0
    lon_w = GPSAdapter._parse_nmea_coord("07735.6760", "W")
    assert lon_w < 0

# ---------------------------------------------------------------------------
# 5. CSV Export Format Tests
# ---------------------------------------------------------------------------

def test_csv_export_includes_weather_columns(app_client, test_db):
    database.insert_reading(
        temperature_c=26.5,
        pressure_hpa=1012.8,
        humidity_pct=60.5,
        latitude=12.97,
        longitude=77.59,
        source="hardware",
        db_path=test_db
    )

    res = app_client.get("/api/readings/export.csv?range=24h")
    assert res.status_code == 200
    content = res.get_data(as_text=True)
    header = content.splitlines()[0]

    assert "Relative Humidity (%)" in header
    assert "Heat Index (°C)" in header
    assert "Latitude" in header
    assert "Longitude" in header
    assert "26.5" in content
    assert "60.5" in content

# ---------------------------------------------------------------------------
# 6. Security Hardening, Ingestion Keys, CSRF & Rate Limiting Tests
# ---------------------------------------------------------------------------

def test_production_mode_fails_closed_when_keys_missing(monkeypatch):
    """In production mode or on Vercel, unconfigured secrets must return None (fail closed)."""
    monkeypatch.setattr(Config, "IS_VERCEL", True)
    monkeypatch.delenv("VA_INGEST_KEY", raising=False)
    monkeypatch.delenv("VA_CONTROL_KEY", raising=False)
    assert Config.get_ingest_key() is None
    assert Config.get_control_key() is None

def test_placeholder_ingest_and_control_keys_rejected(monkeypatch):
    """Insecure known placeholders must be rejected as credentials."""
    for placeholder in Config.KNOWN_PLACEHOLDERS:
        monkeypatch.setenv("VA_INGEST_KEY", placeholder)
        monkeypatch.setenv("VA_CONTROL_KEY", placeholder)
        assert Config.get_ingest_key() is None
        assert Config.get_control_key() is None

def test_telemetry_fails_closed_when_key_unconfigured(app_client, monkeypatch):
    """If ingest key returns None, /api/telemetry must return 401 unauthorized."""
    monkeypatch.setattr(Config, "get_ingest_key", classmethod(lambda cls: None))
    headers = {"Authorization": "Bearer any-token"}
    res = app_client.post("/api/telemetry", json={"temperature_c": 25.0, "pressure_hpa": 1013.0}, headers=headers)
    assert res.status_code == 401
    assert "unauthorized" in res.get_json()["error"]

def test_telemetry_rejects_nan_and_infinity(app_client):
    headers = {"Authorization": f"Bearer {Config.INGEST_KEY}"}

    # Reject NaN
    res_nan = app_client.post("/api/telemetry", json={
        "temperature_c": float("nan"),
        "pressure_hpa": 1013.0
    }, headers=headers)
    assert res_nan.status_code == 400
    assert "NaN or Infinity" in res_nan.get_json()["error"]

    # Reject Infinity
    res_inf = app_client.post("/api/telemetry", json={
        "temperature_c": float("inf"),
        "pressure_hpa": 1013.0
    }, headers=headers)
    assert res_inf.status_code == 400
    assert "NaN or Infinity" in res_inf.get_json()["error"]

def test_mutation_endpoints_reject_unauthorized_access(app_client):
    """All 5 mutation endpoints must reject requests lacking CSRF or Control Key with 403."""
    endpoints = [
        ("/api/settings/threshold", {"threshold_c": 35.0}),
        ("/api/settings/sampling_interval", {"interval_seconds": 10}),
        ("/api/alerts/1/acknowledge", {}),
        ("/api/mode", {"mode": "demo"}),
        ("/api/demo/spike", {"active": True}),
    ]
    for url, payload in endpoints:
        res = app_client.post(url, json=payload)
        assert res.status_code == 403, f"Endpoint {url} failed to reject unauthorized request"
        assert res.get_json()["success"] is False

def test_mutation_endpoints_authorized_via_control_key(app_client):
    """Mutations succeed when providing valid Control Key via header."""
    headers = {"X-VA-Control-Key": Config.CONTROL_KEY}

    res = app_client.post("/api/settings/threshold", json={"threshold_c": 37.0}, headers=headers)
    assert res.status_code == 200
    assert res.get_json()["success"] is True

    res = app_client.post("/api/settings/sampling_interval", json={"interval_seconds": 15}, headers=headers)
    assert res.status_code == 200
    assert res.get_json()["success"] is True

    res = app_client.post("/api/mode", json={"mode": "demo"}, headers=headers)
    assert res.status_code == 200

    res = app_client.post("/api/demo/spike", json={"active": True}, headers=headers)
    assert res.status_code == 200

def test_mutation_endpoints_authorized_via_session_csrf(app_client):
    """Browser users with active session CSRF token can perform mutations."""
    with app_client.session_transaction() as sess:
        sess["csrf_token"] = "valid-session-csrf-token"

    headers = {"X-CSRF-Token": "valid-session-csrf-token"}
    res = app_client.post("/api/settings/threshold", json={"threshold_c": 36.0}, headers=headers)
    assert res.status_code == 200
    assert res.get_json()["success"] is True

def test_telemetry_rate_limiting(app_client, monkeypatch):
    """Telemetry endpoint enforces rate limits and returns 429 when threshold exceeded."""
    from app import _telemetry_rate_records

    # Clear rate limit records for test isolation
    _telemetry_rate_records.clear()

    # Set rate limit to 3 requests per minute for this test
    app_client.application.config["TELEMETRY_RATE_LIMIT_PER_MINUTE"] = 3
    headers = {"Authorization": f"Bearer {Config.INGEST_KEY}"}
    payload = {"temperature_c": 25.0, "pressure_hpa": 1013.0, "source": "hardware"}

    # 3 allowed requests
    for i in range(3):
        res = app_client.post("/api/telemetry", json=payload, headers=headers)
        assert res.status_code == 201

    # 4th request must be rate-limited (HTTP 429)
    res_limited = app_client.post("/api/telemetry", json=payload, headers=headers)
    assert res_limited.status_code == 429
    data = res_limited.get_json()
    assert "Rate limit exceeded" in data["error"]
    assert "Retry-After" in res_limited.headers

    # Cleanup
    _telemetry_rate_records.clear()

def test_session_cookie_security_configuration(app_client):
    """Session cookies must be configured with HttpOnly and SameSite=Lax for CSRF defense."""
    config = app_client.application.config
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert config["SESSION_COOKIE_SAMESITE"] == "Lax"

def test_rate_limiter_prunes_stale_records():
    """Rate limiter must prune stale IP entries when tracking table exceeds capacity."""
    import time
    from app import _telemetry_rate_records, is_telemetry_rate_limited

    _telemetry_rate_records.clear()
    old_time = time.time() - 120.0

    # Simulate 1200 stale client IPs
    for i in range(1200):
        _telemetry_rate_records[f"10.0.0.{i}"] = [old_time]

    assert len(_telemetry_rate_records) == 1200

    # Next check should prune all stale records
    is_limited, _ = is_telemetry_rate_limited("10.1.1.1", limit=60, window_seconds=60.0)
    assert is_limited is False
    # Size must have dropped significantly below 1000
    assert len(_telemetry_rate_records) < 50

    _telemetry_rate_records.clear()
