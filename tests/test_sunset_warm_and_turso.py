import io
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from app import create_app
from config import Config
import database


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_sunset_suite.db")
    database.init_db(db_path=db_file)
    return db_file


@pytest.fixture
def test_client(test_db):
    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": test_db,
        "MODE": "demo"
    })
    with app.test_client() as client:
        yield client, test_db


# ---------------------------------------------------------------------------
# 1. Sunset Warm Theme & Accessibility Verification
# ---------------------------------------------------------------------------

def test_sunset_warm_theme_in_rendered_html(test_client):
    """Verify that Sunset Warm theme attributes and markup render correctly."""
    client, _ = test_client
    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # 1. data-theme="sunset-warm" attribute
    assert 'data-theme="sunset-warm"' in html

    # 2. Skip to main content accessible link
    assert 'class="skip-link"' in html
    assert "Skip to main content" in html

    # 3. Header panoramic elements
    assert "header-sun-orb" in html
    assert "header-mountains-svg" in html
    assert "Live Environmental Monitoring" in html
    assert "btnThemeToggle" in html
    assert "user-avatar" in html

    # 4. Reference image matching condition cards
    assert "Current Conditions" in html
    assert "conditionsLastUpdated" in html
    assert "currentConditionsPill" in html
    assert "temp-squircle" in html
    assert "hum-squircle" in html
    assert "heat-squircle" in html
    assert "cardTempVal" in html
    assert "cardHumidityVal" in html
    assert "cardHeatIndexVal" in html

    # 5. Dual-series Temperature & Humidity Chart
    assert "Temperature &amp; Humidity (Last 24 Hours)" in html
    assert "temp-dot" in html
    assert "hum-dot" in html

    # 6. Sidebar bottom sensor status
    assert "sidebarSensorStatusBox" in html
    assert "sidebarStatusDot" in html
    assert "sidebarStatusTitle" in html
    assert "sidebarStatusSub" in html


# ---------------------------------------------------------------------------
# 2. Production Mode Configuration & Supported Settings Tests
# ---------------------------------------------------------------------------

def test_production_mode_configuration_resolution(monkeypatch):
    """Verify production mode resolution uses actual supported settings, not guessed values."""
    # 1. Explicit VA_MODE=live
    monkeypatch.setenv("VA_MODE", "live")
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    assert Config.is_production_mode() is True

    # 2. VERCEL_ENV=production
    monkeypatch.setenv("VERCEL_ENV", "production")
    assert Config.is_production_mode() is True

    # 3. FLASK_ENV=production
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setenv("FLASK_ENV", "production")
    assert Config.is_production_mode() is True

    # 4. Turso Database credentials
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.delenv("VA_MODE", raising=False)
    monkeypatch.setattr(Config, "MODE", "demo")
    monkeypatch.setattr(Config, "IS_VERCEL", False)
    monkeypatch.setattr(Config, "TURSO_DATABASE_URL", "libsql://va-test.turso.io")
    monkeypatch.setattr(Config, "TURSO_AUTH_TOKEN", "valid-token")
    assert Config.is_production_mode() is True


# ---------------------------------------------------------------------------
# 3. Honest Sensor State & Stale Telemetry Detection Tests
# ---------------------------------------------------------------------------

def test_honest_offline_state_when_no_readings(test_client):
    """When no real readings exist, API reports 'No Live Reading' and does not fabricate data."""
    client, _ = test_client
    res = client.get("/api/readings/latest?real_only=1")
    assert res.status_code == 200
    data = res.get_json()

    assert data["latest"] is None
    freshness = data["freshness"]
    assert freshness["is_live"] is False
    assert freshness["is_stale"] is False
    assert freshness["status_label"] == "No Live Reading"


def test_honest_stale_state_when_readings_are_old(test_client):
    """When readings are older than 180s, API honestly marks them as stale / Sensor Offline."""
    client, db_file = test_client

    # Insert a reading from 10 minutes ago
    ten_mins_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    database.insert_reading(
        temperature_c=31.5,
        humidity_pct=52.0,
        source="raspberry_pi_dht11",
        timestamp=ten_mins_ago,
        db_path=db_file
    )

    res = client.get("/api/readings/latest?real_only=1")
    assert res.status_code == 200
    data = res.get_json()

    assert data["latest"] is not None
    assert data["latest"]["temperature_c"] == 31.5
    freshness = data["freshness"]
    assert freshness["is_live"] is False
    assert freshness["is_stale"] is True
    assert freshness["status_label"] == "Sensor Offline"
    assert freshness["age_seconds"] >= 500


def test_honest_live_state_when_readings_are_fresh(test_client):
    """When a fresh reading arrives, API reports 'Live Data'."""
    client, db_file = test_client

    # Insert a fresh reading from 10 seconds ago
    fresh_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    database.insert_reading(
        temperature_c=33.7,
        humidity_pct=49.0,
        source="raspberry_pi_dht11",
        timestamp=fresh_time,
        db_path=db_file
    )

    res = client.get("/api/readings/latest?real_only=1")
    assert res.status_code == 200
    data = res.get_json()

    assert data["latest"] is not None
    assert data["latest"]["temperature_c"] == 33.7
    assert data["latest"]["humidity_pct"] == 49.0
    freshness = data["freshness"]
    assert freshness["is_live"] is True
    assert freshness["is_stale"] is False
    assert freshness["status_label"] == "Live Data"


# ---------------------------------------------------------------------------
# 4. Turso libSQL HTTP Client Pipeline Tests
# ---------------------------------------------------------------------------

def test_turso_arg_serialization():
    """Verify Python types serialize into valid Turso libSQL typed objects."""
    assert database._to_turso_arg(None) == {"type": "null"}
    assert database._to_turso_arg(True) == {"type": "integer", "value": "1"}
    assert database._to_turso_arg(False) == {"type": "integer", "value": "0"}
    assert database._to_turso_arg(42) == {"type": "integer", "value": "42"}
    assert database._to_turso_arg(24.5) == {"type": "float", "value": 24.5}
    assert database._to_turso_arg("dht11") == {"type": "text", "value": "dht11"}


def test_turso_pipeline_execution_mock():
    """Verify Turso libSQL HTTP request construction and response parsing."""
    mock_response_body = {
        "baton": "session_123",
        "results": [
            {
                "type": "ok",
                "response": {
                    "type": "execute",
                    "result": {
                        "cols": [{"name": "id"}, {"name": "temperature_c"}, {"name": "source"}],
                        "rows": [
                            [
                                {"type": "integer", "value": "1"},
                                {"type": "float", "value": 33.7},
                                {"type": "text", "value": "raspberry_pi_dht11"}
                            ]
                        ],
                        "affected_row_count": 0,
                        "last_insert_rowid": "1"
                    }
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response_body).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("config.Config.TURSO_DATABASE_URL", "libsql://va-mock.turso.io"):
        with patch("config.Config.TURSO_AUTH_TOKEN", "mock-auth-token"):
            with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
                rows = database.turso_query("SELECT id, temperature_c, source FROM readings LIMIT 1;")
                assert len(rows) == 1
                assert rows[0]["id"] == 1
                assert rows[0]["temperature_c"] == 33.7
                assert rows[0]["source"] == "raspberry_pi_dht11"

                # Verify URL format converted from libsql:// to https://.../v2/pipeline
                call_args, _ = mock_urlopen.call_args
                req = call_args[0]
                assert req.full_url == "https://va-mock.turso.io/v2/pipeline"
                assert req.headers["Authorization"] == "Bearer mock-auth-token"
                assert req.headers["Content-type"] == "application/json"
