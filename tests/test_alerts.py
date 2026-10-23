import pytest
import database
from alert_service import AlertService

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_alerts.db")
    database.init_db(db_path=db_file)
    database.update_temperature_threshold(35.0, db_path=db_file)
    return db_file

def test_alert_not_triggered_below_threshold(test_db):
    res = AlertService.evaluate_reading(32.0, db_path=test_db)
    assert res is None
    alerts = database.get_alerts(db_path=test_db)
    assert len(alerts) == 0

def test_alert_triggered_above_threshold(test_db):
    res = AlertService.evaluate_reading(36.2, db_path=test_db)
    assert res is not None
    assert res["is_new"] is True
    assert res["status"] == "active"
    assert res["measured_value"] == 36.2

    alerts = database.get_alerts(db_path=test_db)
    assert len(alerts) == 1
    assert alerts[0]["status"] == "active"

def test_no_duplicate_alert_on_consecutive_polls(test_db):
    # First poll triggers alert
    res1 = AlertService.evaluate_reading(36.0, db_path=test_db)
    assert res1["is_new"] is True

    # Second poll at elevated temp should NOT create a new alert
    res2 = AlertService.evaluate_reading(37.5, db_path=test_db)
    assert res2 is not None
    assert res2["is_new"] is False
    assert res2["id"] == res1["id"]

    # Third poll also elevated
    res3 = AlertService.evaluate_reading(36.8, db_path=test_db)
    assert res3["is_new"] is False

    # Check database only has 1 alert
    alerts = database.get_alerts(db_path=test_db)
    assert len(alerts) == 1

def test_alert_acknowledgement(test_db):
    res = AlertService.evaluate_reading(36.5, db_path=test_db)
    alert_id = res["id"]

    # Acknowledge
    ok = AlertService.acknowledge(alert_id, db_path=test_db)
    assert ok is True

    active = database.get_active_alert(db_path=test_db)
    # Since it is now 'acknowledged', it is no longer 'active'
    assert active is None

    alerts = database.get_alerts(status_filter="acknowledged", db_path=test_db)
    assert len(alerts) == 1
    assert alerts[0]["id"] == alert_id
    assert alerts[0]["acknowledged_at"] is not None

def test_alert_auto_resolution_with_hysteresis(test_db):
    # Trigger alert (threshold = 35.0)
    AlertService.evaluate_reading(36.0, db_path=test_db)
    assert len(database.get_alerts(db_path=test_db)) == 1

    # Slightly below threshold (34.8) - within hysteresis (0.5C), so not yet resolved
    AlertService.evaluate_reading(34.8, db_path=test_db)
    alerts = database.get_alerts(db_path=test_db)
    assert alerts[0]["status"] == "active"

    # Safely below threshold - 0.5C (e.g. 34.0 < 34.5) -> resolved!
    AlertService.evaluate_reading(34.0, db_path=test_db)
    alerts_resolved = database.get_alerts(status_filter="resolved", db_path=test_db)
    assert len(alerts_resolved) == 1
    assert alerts_resolved[0]["status"] == "resolved"

    # Subsequent spike triggers a new event
    res_new = AlertService.evaluate_reading(36.2, db_path=test_db)
    assert res_new["is_new"] is True
    assert len(database.get_alerts(db_path=test_db)) == 2
