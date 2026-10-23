import pytest
import database
from sensor_service import SensorService

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_sensor.db")
    database.init_db(db_path=db_file)
    return db_file

def test_sensor_service_demo_mode(test_db):
    service = SensorService(mode="demo", db_path=test_db)
    reading = service.read_sensor_once()

    assert reading is not None
    assert reading["source"] == "demo"
    assert reading["validity_status"] == "valid"
    assert -40.0 <= reading["temperature_c"] <= 85.0
    assert 300.0 <= reading["pressure_hpa"] <= 1100.0

    # Ensure saved to database
    latest = database.get_latest_reading(db_path=test_db)
    assert latest is not None
    assert latest["source"] == "demo"

    status = service.get_status()
    assert status["mode"] == "demo"
    assert status["is_connected"] is True
    assert status["data_freshness_seconds"] is not None

def test_sensor_service_live_mode_without_hardware(test_db):
    # Without RPi I2C hardware, live mode should fail gracefully
    service = SensorService(mode="live", db_path=test_db)
    reading = service.read_sensor_once()

    # Must NOT fabricate fake measurements
    assert reading is None

    # Must NOT write fake records to database
    latest = database.get_latest_reading(db_path=test_db)
    assert latest is None

    # Status must report offline
    status = service.get_status()
    assert status["mode"] == "live"
    assert status["is_connected"] is False
    assert status["consecutive_errors"] >= 1
    assert status["last_error"] is not None

def test_sensor_service_demo_spike(test_db):
    service = SensorService(mode="demo", db_path=test_db)
    database.update_temperature_threshold(35.0, db_path=test_db)

    # Normal reading (should be ~20-28°C)
    normal = service.read_sensor_once()
    assert normal["temperature_c"] < 35.0
    assert len(database.get_alerts(db_path=test_db)) == 0

    # Activate spike
    service.demo_spike_active = True
    spiked = service.read_sensor_once()
    assert spiked["temperature_c"] >= 35.0

    # Alert should have triggered
    alerts = database.get_alerts(db_path=test_db)
    assert len(alerts) == 1
    assert alerts[0]["status"] == "active"
