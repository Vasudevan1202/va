import pytest
import json
import math
from datetime import datetime, timezone
import database
from app import create_app
from config import Config
from weather_service import WeatherService
from scripts.pi_dht11_serial_receiver import DHT11SerialBridge

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_dht11_suite.db")
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
        yield client, test_db

# ---------------------------------------------------------------------------
# 1. Authentication Tests for POST /api/ingest/dht11
# ---------------------------------------------------------------------------

def test_dht11_missing_auth(app_client):
    client, _ = app_client
    res = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": 46.0
    })
    assert res.status_code == 401
    data = res.get_json()
    assert data["status"] == "error"
    assert "Authorization" in data["error"]

def test_dht11_invalid_bearer_token(app_client):
    client, _ = app_client
    headers = {"Authorization": "Bearer invalid-dht11-token"}
    res = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": 46.0
    }, headers=headers)
    assert res.status_code == 401
    data = res.get_json()
    assert data["status"] == "error"
    assert "Invalid ingestion credentials" in data["error"]

def test_dht11_malformed_auth_header(app_client):
    client, _ = app_client
    headers = {"Authorization": "Basic dXNlcjpwYXNz"}
    res = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": 46.0
    }, headers=headers)
    assert res.status_code == 401

def test_dht11_fails_closed_in_production_when_unconfigured(app_client, monkeypatch):
    client, _ = app_client
    monkeypatch.setattr(Config, "IS_VERCEL", True)
    monkeypatch.delenv("VA_DHT11_INGEST_KEY", raising=False)
    monkeypatch.delenv("VA_INGEST_KEY", raising=False)

    headers = {"Authorization": "Bearer any-token"}
    res = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": 46.0
    }, headers=headers)
    assert res.status_code == 401
    assert "unauthorized" in res.get_json()["error"]

# ---------------------------------------------------------------------------
# 2. Payload Validation & Sensor Range Bounds Tests
# ---------------------------------------------------------------------------

def test_dht11_missing_json_payload(app_client):
    client, _ = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}
    res = client.post("/api/ingest/dht11", data="not json", headers=headers)
    assert res.status_code == 400
    assert "Invalid or missing JSON" in res.get_json()["error"]

def test_dht11_missing_required_temperature(app_client):
    client, _ = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}
    res = client.post("/api/ingest/dht11", json={"humidity_percent": 46.0}, headers=headers)
    assert res.status_code == 400
    assert "temperature_c" in res.get_json()["error"]

def test_dht11_missing_required_humidity(app_client):
    client, _ = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}
    res = client.post("/api/ingest/dht11", json={"temperature_c": 33.0}, headers=headers)
    assert res.status_code == 400
    assert "humidity_percent" in res.get_json()["error"]

def test_dht11_non_numeric_types(app_client):
    client, _ = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}

    # Non-numeric temperature
    res1 = client.post("/api/ingest/dht11", json={
        "temperature_c": "thirty-three",
        "humidity_percent": 46.0
    }, headers=headers)
    assert res1.status_code == 400
    assert "numeric" in res1.get_json()["error"]

    # Non-numeric humidity
    res2 = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": "forty-six"
    }, headers=headers)
    assert res2.status_code == 400
    assert "numeric" in res2.get_json()["error"]

def test_dht11_rejects_nan_and_infinity(app_client):
    client, _ = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}

    res_nan = client.post("/api/ingest/dht11", json={
        "temperature_c": float("nan"),
        "humidity_percent": 46.0
    }, headers=headers)
    assert res_nan.status_code == 400
    assert "NaN or Infinity" in res_nan.get_json()["error"]

    res_inf = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": float("inf")
    }, headers=headers)
    assert res_inf.status_code == 400
    assert "NaN or Infinity" in res_inf.get_json()["error"]

def test_dht11_out_of_range_temperature(app_client):
    client, _ = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}

    # Beyond upper bound (>60°C)
    res_high = client.post("/api/ingest/dht11", json={
        "temperature_c": 85.0,
        "humidity_percent": 50.0
    }, headers=headers)
    assert res_high.status_code == 400
    assert "outside reasonable DHT11 limits" in res_high.get_json()["error"]

    # Below lower bound (<-20°C)
    res_low = client.post("/api/ingest/dht11", json={
        "temperature_c": -35.0,
        "humidity_percent": 50.0
    }, headers=headers)
    assert res_low.status_code == 400
    assert "outside reasonable DHT11 limits" in res_low.get_json()["error"]

def test_dht11_out_of_range_humidity(app_client):
    client, _ = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}

    # Humidity > 100%
    res_high = client.post("/api/ingest/dht11", json={
        "temperature_c": 25.0,
        "humidity_percent": 115.0
    }, headers=headers)
    assert res_high.status_code == 400
    assert "outside valid range" in res_high.get_json()["error"]

    # Humidity < 0%
    res_low = client.post("/api/ingest/dht11", json={
        "temperature_c": 25.0,
        "humidity_percent": -5.0
    }, headers=headers)
    assert res_low.status_code == 400
    assert "outside valid range" in res_low.get_json()["error"]

def test_dht11_invalid_timestamp_and_source(app_client):
    client, _ = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}

    # Invalid timestamp format
    res_ts = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": 46.0,
        "timestamp": "yesterday afternoon"
    }, headers=headers)
    assert res_ts.status_code == 400
    assert "timestamp" in res_ts.get_json()["error"]

    # Empty source
    res_src = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": 46.0,
        "source": "   "
    }, headers=headers)
    assert res_src.status_code == 400
    assert "source" in res_src.get_json()["error"]

# ---------------------------------------------------------------------------
# 3. Successful Ingestion & Reading Retrieval Tests
# ---------------------------------------------------------------------------

def test_dht11_successful_ingestion(app_client):
    client, db_file = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}

    test_ts = "2026-10-29T10:20:30+00:00"
    payload = {
        "temperature_c": 33.0,
        "humidity_percent": 46.0,
        "timestamp": test_ts,
        "source": "raspberry_pi_dht11"
    }

    res = client.post("/api/ingest/dht11", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.get_json()

    assert data["status"] == "success"
    assert data["temperature_c"] == 33.0
    assert data["humidity_percent"] == 46.0
    assert data["source"] == "raspberry_pi_dht11"
    assert data["timestamp"] == test_ts
    assert "id" in data
    assert data["heat_risk"] is not None
    assert data["heat_risk"]["is_applicable"] is True

    # Verify stored in database
    latest = database.get_latest_reading(db_path=db_file)
    assert latest is not None
    assert latest["temperature_c"] == 33.0
    assert latest["humidity_pct"] == 46.0
    assert latest["pressure_hpa"] is None  # DHT11 has no barometer
    assert latest["sensor_type"] == "dht11"
    assert latest["source"] == "raspberry_pi_dht11"

def test_dht11_reading_retrieval_endpoints(app_client):
    client, db_file = app_client
    headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}

    # Ingest a sample reading
    client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": 46.0,
        "source": "arduino_mega_dht11"
    }, headers=headers)

    # 1. GET /api/readings/latest
    res_latest = client.get("/api/readings/latest")
    assert res_latest.status_code == 200
    data_latest = res_latest.get_json()
    assert data_latest["latest"]["temperature_c"] == 33.0
    assert data_latest["latest"]["humidity_pct"] == 46.0
    assert data_latest["dht11"] is not None
    assert data_latest["dht11"]["temperature_c"] == 33.0
    assert data_latest["dht11"]["humidity_pct"] == 46.0

    # 2. GET /api/readings?range=24h
    res_range = client.get("/api/readings?range=24h")
    assert res_range.status_code == 200
    readings = res_range.get_json()["readings"]
    assert any(r["temperature_c"] == 33.0 and r["humidity_pct"] == 46.0 for r in readings)

    # 3. GET /api/readings/history
    res_hist = client.get("/api/readings/history")
    assert res_hist.status_code == 200
    hist_readings = res_hist.get_json()["readings"]
    assert any(r["source"] == "arduino_mega_dht11" for r in hist_readings)

    # 4. GET /api/status
    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    status_data = res_status.get_json()
    assert status_data["database"]["dht11_readings_count"] >= 1
    assert "dht11" in status_data["sensor"]
    assert status_data["sensor"]["dht11"]["latest"] is not None

# ---------------------------------------------------------------------------
# 4. Coexistence with BMP280 & Non-Breaking Isolation Tests
# ---------------------------------------------------------------------------

def test_dht11_bmp280_coexistence(app_client):
    """Verifies that BMP280 readings and DHT11 readings coexist without null exceptions."""
    client, db_file = app_client
    dht_headers = {"Authorization": f"Bearer {Config.DHT11_INGEST_KEY}"}
    bmp_headers = {"Authorization": f"Bearer {Config.INGEST_KEY}"}

    # 1. Ingest BMP280 reading (has temperature & pressure, no humidity)
    res_bmp = client.post("/api/telemetry", json={
        "temperature_c": 24.5,
        "pressure_hpa": 1013.25,
        "source": "hardware"
    }, headers=bmp_headers)
    assert res_bmp.status_code == 201

    # 2. Ingest DHT11 reading (has temperature & humidity, no pressure)
    res_dht = client.post("/api/ingest/dht11", json={
        "temperature_c": 33.0,
        "humidity_percent": 46.0,
        "source": "raspberry_pi_dht11"
    }, headers=dht_headers)
    assert res_dht.status_code == 201

    # 3. Ingest another BMP280 reading
    res_bmp2 = client.post("/api/telemetry", json={
        "temperature_c": 24.8,
        "pressure_hpa": 1013.50,
        "source": "hardware"
    }, headers=bmp_headers)
    assert res_bmp2.status_code == 201

    # 4. Verify /api/readings/latest provides both separate representations
    res_latest = client.get("/api/readings/latest")
    assert res_latest.status_code == 200
    latest_data = res_latest.get_json()

    assert latest_data["bmp280"] is not None
    assert latest_data["bmp280"]["pressure_hpa"] == 1013.50

    assert latest_data["dht11"] is not None
    assert latest_data["dht11"]["temperature_c"] == 33.0
    assert latest_data["dht11"]["humidity_pct"] == 46.0

    # Trend calculations must not crash when one reading lacks pressure
    assert "trend" in latest_data

# ---------------------------------------------------------------------------
# 5. Serial Bridge Parser Tests (Arduino Output Decoding)
# ---------------------------------------------------------------------------

def test_serial_bridge_parser():
    bridge = DHT11SerialBridge(server_url="http://127.0.0.1:5000", token="test", mock_mode=True)

    # Format 1: User's exact Arduino print format
    res1 = bridge.parse_reading("Temperature: 33.0 °C | Humidity: 46.0%")
    assert res1 == (33.0, 46.0)

    # Format 2: CSV format from Arduino
    res2 = bridge.parse_reading("33.0, 46.0")
    assert res2 == (33.0, 46.0)

    res3 = bridge.parse_reading("28.5,62.0")
    assert res3 == (28.5, 62.0)

    # Format 3: Labeled format
    res4 = bridge.parse_reading("Temp: 31.2 C, Hum: 55.0 %")
    assert res4 == (31.2, 55.0)

    # Invalid junk strings
    assert bridge.parse_reading("Initializing Arduino Mega...") is None
    assert bridge.parse_reading("Sensor read error") is None
    assert bridge.parse_reading("") is None
