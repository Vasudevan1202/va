import os
import pytest
from datetime import datetime, timezone, timedelta
import database

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_va.db")
    database.init_db(db_path=db_file)
    return db_file

def test_init_db(test_db):
    stats = database.get_db_stats(db_path=test_db)
    assert stats["status"] == "healthy"
    assert stats["readings_count"] == 0
    assert stats["alerts_count"] == 0

    settings = database.get_settings(db_path=test_db)
    assert settings["temperature_threshold_c"] == 35.0
    assert settings["sampling_interval_seconds"] == 10

def test_insert_and_get_latest_reading(test_db):
    r_id = database.insert_reading(
        temperature_c=25.4,
        pressure_hpa=1014.2,
        source="demo",
        validity_status="valid",
        db_path=test_db
    )
    assert r_id > 0

    latest = database.get_latest_reading(db_path=test_db)
    assert latest is not None
    assert latest["temperature_c"] == 25.4
    assert latest["pressure_hpa"] == 1014.2
    assert latest["source"] == "demo"
    assert latest["validity_status"] == "valid"

def test_today_stats(test_db):
    now = datetime.now(timezone.utc)
    # Empty db
    empty_stats = database.get_today_stats(db_path=test_db)
    assert empty_stats["count"] == 0
    assert empty_stats["min_temp"] is None

    # Insert two readings
    database.insert_reading(temperature_c=20.0, pressure_hpa=1010.0, db_path=test_db)
    database.insert_reading(temperature_c=30.0, pressure_hpa=1020.0, db_path=test_db)

    stats = database.get_today_stats(db_path=test_db)
    assert stats["count"] == 2
    assert stats["min_temp"] == 20.0
    assert stats["max_temp"] == 30.0
    assert stats["avg_temp"] == 25.0
    assert stats["min_pressure"] == 1010.0
    assert stats["max_pressure"] == 1020.0
    assert stats["avg_pressure"] == 1015.0

def test_readings_range_and_history(test_db):
    now = datetime.now(timezone.utc)
    # Insert older and newer readings
    old_time = (now - timedelta(hours=3)).isoformat()
    new_time = now.isoformat()

    database.insert_reading(22.0, 1012.0, timestamp=old_time, db_path=test_db)
    database.insert_reading(24.0, 1014.0, timestamp=new_time, db_path=test_db)

    # 1h range should only get new reading
    readings_1h = database.get_readings_range("1h", db_path=test_db)
    assert len(readings_1h) == 1
    assert readings_1h[0]["temperature_c"] == 24.0

    # 6h range should get both
    readings_6h = database.get_readings_range("6h", db_path=test_db)
    assert len(readings_6h) == 2

    # Paginated history
    history, total = database.get_readings_history(page=1, limit=1, db_path=test_db)
    assert total == 2
    assert len(history) == 1

def test_settings_update(test_db):
    ok = database.update_temperature_threshold(38.5, db_path=test_db)
    assert ok is True
    settings = database.get_settings(db_path=test_db)
    assert settings["temperature_threshold_c"] == 38.5

    ok2 = database.update_sampling_interval(15, db_path=test_db)
    assert ok2 is True
    settings2 = database.get_settings(db_path=test_db)
    assert settings2["sampling_interval_seconds"] == 15
