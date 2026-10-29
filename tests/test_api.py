import pytest
import json
from app import create_app
from config import Config
import database

@pytest.fixture
def app_client(tmp_path):
    db_file = str(tmp_path / "test_api.db")
    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": db_file,
        "MODE": "demo"
    })
    client = app.test_client()

    # Seed 3 sample readings
    database.insert_reading(22.5, 1013.25, source="demo", validity_status="valid", db_path=db_file)
    database.insert_reading(23.0, 1014.0, source="demo", validity_status="valid", db_path=db_file)
    database.insert_reading(23.5, 1014.5, source="demo", validity_status="valid", db_path=db_file)

    return client, db_file

def test_pages_render(app_client):
    client, _ = app_client
    pages = ["/", "/dashboard", "/live", "/history", "/alerts", "/system", "/about", "/project", "/project-overview"]
    for p in pages:
        res = client.get(p)
        assert res.status_code in [200, 302], f"Failed on page: {p}"

def test_project_and_team_details_removed_and_redirected(app_client):
    client, _ = app_client
    # Verify legacy about and project routes redirect cleanly to /dashboard
    for legacy_route in ["/about", "/project", "/project-overview"]:
        res = client.get(legacy_route)
        assert res.status_code == 302
        assert res.headers["Location"].endswith("/dashboard") or res.headers["Location"] == "/dashboard"

    # Verify dashboard page focuses strictly on environmental monitoring without team/project cards
    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200
    html = res_dash.get_data(as_text=True)
    assert "Meet the Team" not in html
    assert "Thakshanamoorthi" not in html
    assert "Project Details" not in html

def test_api_status(app_client):
    client, _ = app_client
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "online"
    assert "sensor" in data
    assert "alert" in data
    assert "database" in data

def test_api_readings_latest(app_client):
    client, _ = app_client
    res = client.get("/api/readings/latest")
    assert res.status_code == 200
    data = res.get_json()
    assert data["latest"] is not None
    assert data["latest"]["temperature_c"] == 23.5
    assert "trend" in data
    assert "today_stats" in data

def test_api_readings_range(app_client):
    client, _ = app_client
    res = client.get("/api/readings?range=24h")
    assert res.status_code == 200
    data = res.get_json()
    assert "readings" in data
    assert len(data["readings"]) == 3
    assert data["summary"]["count"] == 3

def test_api_readings_history(app_client):
    client, _ = app_client
    res = client.get("/api/readings/history?page=1&limit=2")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["readings"]) == 2
    assert data["total"] == 3
    assert data["total_pages"] == 2
    assert data["has_next"] is True

def test_api_readings_export_csv(app_client):
    client, _ = app_client
    res = client.get("/api/readings/export.csv?range=24h")
    assert res.status_code == 200
    assert res.content_type.startswith("text/csv")
    csv_text = res.get_data(as_text=True)
    assert "Temperature (Celsius)" in csv_text
    assert "23.5" in csv_text

def test_api_settings_threshold_update(app_client):
    client, db_file = app_client

    # Unauthenticated mutation rejected
    res_unauth = client.post("/api/settings/threshold", json={"threshold_c": 36.5})
    assert res_unauth.status_code == 403
    assert res_unauth.get_json()["success"] is False

    # Authenticated with Control Key
    auth_headers = {"X-VA-Control-Key": Config.CONTROL_KEY}

    # Bad request (missing body or value)
    res_bad = client.post("/api/settings/threshold", json={}, headers=auth_headers)
    assert res_bad.status_code == 400

    # Out of bounds
    res_oob = client.post("/api/settings/threshold", json={"threshold_c": 120}, headers=auth_headers)
    assert res_oob.status_code == 400

    # Valid update
    res = client.post("/api/settings/threshold", json={"threshold_c": 36.5}, headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["threshold_c"] == 36.5

    settings = database.get_settings(db_path=db_file)
    assert settings["temperature_threshold_c"] == 36.5

def test_api_mode_toggle(app_client):
    client, _ = app_client

    # Unauthenticated mutation rejected
    res_unauth = client.post("/api/mode", json={"mode": "live"})
    assert res_unauth.status_code == 403

    # Authenticated with Bearer Control Key
    auth_headers = {"Authorization": f"Bearer {Config.CONTROL_KEY}"}
    res = client.post("/api/mode", json={"mode": "live"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["mode"] == "live"

    res2 = client.post("/api/mode", json={"mode": "demo"}, headers=auth_headers)
    assert res2.status_code == 200
    assert res2.get_json()["mode"] == "demo"
