import pytest
import json
from app import create_app
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

def test_project_overview_and_team_content(app_client):
    client, _ = app_client
    res = client.get("/about")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Verify team members
    assert "Vasu" in html
    assert "Thakshanamoorthi S" in html
    assert "Nithilan" in html

    # Verify live production dashboard URL
    assert "va.developerhut.in" in html

    # Verify 7 workflow steps
    assert "Sensor Setup" in html
    assert "Data Collection" in html
    assert "Data Processing" in html
    assert "Data Storage" in html
    assert "Backend Processing" in html
    assert "Dashboard View" in html
    assert "Testing &amp; Deploy" in html

    # Verify transparency on measurement limitations (no fake humidity)
    assert "does not contain a relative humidity sensor" in html
    assert "No Fabricated Humidity" in html
    assert "WBGT" in html

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

    # Bad request (missing body or value)
    res_bad = client.post("/api/settings/threshold", json={})
    assert res_bad.status_code == 400

    # Out of bounds
    res_oob = client.post("/api/settings/threshold", json={"threshold_c": 120})
    assert res_oob.status_code == 400

    # Valid update
    res = client.post("/api/settings/threshold", json={"threshold_c": 36.5})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["threshold_c"] == 36.5

    settings = database.get_settings(db_path=db_file)
    assert settings["temperature_threshold_c"] == 36.5

def test_api_mode_toggle(app_client):
    client, _ = app_client
    res = client.post("/api/mode", json={"mode": "live"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["mode"] == "live"

    res2 = client.post("/api/mode", json={"mode": "demo"})
    assert res2.status_code == 200
    assert res2.get_json()["mode"] == "demo"
