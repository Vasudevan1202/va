import json
from pathlib import Path
from PIL import Image
import pytest
from app import create_app
import database

@pytest.fixture
def test_client(tmp_path):
    db_file = str(tmp_path / "test_branding.db")
    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": db_file,
        "MODE": "demo"
    })
    client = app.test_client()
    return client, app

def test_source_logo_preserved():
    """Verify that the original source logo.jpg remains intact and is square."""
    logo_path = Path("logo.jpg")
    assert logo_path.exists(), "Source logo.jpg must be preserved"
    with Image.open(logo_path) as im:
        assert im.format == "JPEG"
        assert im.size == (1080, 1080)

def test_favicon_files_exist_and_valid():
    """Verify all required favicon assets and webmanifest exist and have valid properties."""
    static_dir = Path("static")
    
    # 1. favicon.ico
    ico_path = static_dir / "favicon.ico"
    assert ico_path.exists(), "favicon.ico must exist in static/"
    assert ico_path.stat().st_size > 500
    with Image.open(ico_path) as im:
        assert im.format == "ICO"

    # Multi-resolution check
    with open(ico_path, "rb") as f:
        ico_bytes = f.read()
    image_count = int.from_bytes(ico_bytes[4:6], "little")
    assert image_count >= 2, f"Expected multi-resolution ICO, got {image_count} sizes"

    # 2. favicon-16x16.png
    fav16 = static_dir / "favicon-16x16.png"
    assert fav16.exists()
    with Image.open(fav16) as im:
        assert im.size == (16, 16)
        assert im.mode == "RGBA"

    # 3. favicon-32x32.png
    fav32 = static_dir / "favicon-32x32.png"
    assert fav32.exists()
    with Image.open(fav32) as im:
        assert im.size == (32, 32)
        assert im.mode == "RGBA"

    # 4. apple-touch-icon.png
    apple_icon = static_dir / "apple-touch-icon.png"
    assert apple_icon.exists()
    with Image.open(apple_icon) as im:
        assert im.size == (180, 180)
        assert im.mode == "RGBA"

    # 5. android-chrome-192x192.png
    android192 = static_dir / "android-chrome-192x192.png"
    assert android192.exists()
    with Image.open(android192) as im:
        assert im.size == (192, 192)
        assert im.mode == "RGBA"

    # 6. android-chrome-512x512.png
    android512 = static_dir / "android-chrome-512x512.png"
    assert android512.exists()
    with Image.open(android512) as im:
        assert im.size == (512, 512)
        assert im.mode == "RGBA"

    # 7. Optimized web logos
    logo_sm = static_dir / "img" / "va-logo-sm.png"
    assert logo_sm.exists()
    with Image.open(logo_sm) as im:
        assert im.size == (64, 64)

    logo_card = static_dir / "img" / "va-logo-card.png"
    assert logo_card.exists()
    with Image.open(logo_card) as im:
        assert im.size == (256, 256)

def test_site_webmanifest_validity():
    """Verify site.webmanifest is valid JSON with required PWA metadata."""
    manifest_path = Path("static/site.webmanifest")
    assert manifest_path.exists(), "site.webmanifest must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["name"] == "Virtual Atmosphere"
    assert data["short_name"] == "VA"
    assert data["theme_color"] == "#07111F"
    assert data["background_color"] == "#07111F"
    assert data["display"] == "standalone"
    assert len(data["icons"]) >= 2
    sizes = [icon["sizes"] for icon in data["icons"]]
    assert "192x192" in sizes
    assert "512x512" in sizes

def test_direct_branding_routes(test_client):
    """Verify that root-level requests for /favicon.ico, /site.webmanifest, and /apple-touch-icon.png succeed."""
    client, _ = test_client

    # /favicon.ico
    res = client.get("/favicon.ico")
    assert res.status_code == 200
    assert "image" in res.content_type

    # /site.webmanifest
    res = client.get("/site.webmanifest")
    assert res.status_code == 200
    assert "application/manifest+json" in res.content_type
    manifest = json.loads(res.get_data(as_text=True))
    assert manifest["name"] == "Virtual Atmosphere"

    # /apple-touch-icon.png
    res = client.get("/apple-touch-icon.png")
    assert res.status_code == 200
    assert "image/png" in res.content_type

def test_favicon_and_branding_in_rendered_html(test_client):
    """Verify all pages include favicon links, viewport, theme-color, and consistent title."""
    client, _ = test_client
    pages = [
        ("/dashboard", "VA Monitor | Virtual Atmosphere"),
        ("/live", "Live Monitor | Virtual Atmosphere"),
        ("/history", "Historical Data | Virtual Atmosphere"),
        ("/alerts", "Alerts &amp; Thresholds | Virtual Atmosphere"),
        ("/system", "Sensor &amp; System | Virtual Atmosphere"),
        ("/about", "Project &amp; Team | Virtual Atmosphere"),
    ]

    for path, expected_title in pages:
        res = client.get(path)
        assert res.status_code == 200, f"Page {path} failed to render"
        html = res.get_data(as_text=True)

        # Title format
        assert expected_title in html, f"Page {path} title missing: {expected_title}"

        # Favicons in <head> with versioning
        assert "favicon.ico" in html, f"favicon.ico link missing in {path}"
        assert "favicon-16x16.png" in html, f"favicon-16x16 link missing in {path}"
        assert "favicon-32x32.png" in html, f"favicon-32x32 link missing in {path}"
        assert "apple-touch-icon.png" in html, f"apple-touch-icon link missing in {path}"
        assert "site.webmanifest" in html, f"webmanifest link missing in {path}"
        assert "?v=" in html, f"Cache-busting version query parameter missing in {path}"
        assert '<meta name="theme-color" content="#07111F">' in html

        # Initial loader
        assert 'id="vaAppLoader"' in html, f"vaAppLoader missing in {path}"
        assert "Virtual Atmosphere" in html
        assert "Understand Your Atmosphere." in html

        # Sidebar logo
        assert "va-logo-sm.png" in html, f"Sidebar logo missing in {path}"

def test_custom_404_error_page(test_client):
    """Verify custom branded 404 page renders for nonexistent pages and does not leak server secrets."""
    client, _ = test_client
    res = client.get("/nonexistent-coordinate-page")
    assert res.status_code == 404
    html = res.get_data(as_text=True)

    # Branded elements
    assert "404 Not Found | Virtual Atmosphere" in html
    assert "Atmospheric Coordinate Not Found" in html
    assert "Return to Dashboard" in html
    assert "va-logo-card.png" in html

    # Distinct from sensor failure
    assert "Hardware Sensor Notice" in html
    assert "A missing or offline BMP280 sensor does not cause a 404" in html

    # No stack trace or internal server path leakage
    assert "Traceback" not in html
    assert "File \"" not in html

def test_api_404_returns_json(test_client):
    """Verify that 404 on /api/ endpoints returns structured JSON, not HTML."""
    client, _ = test_client
    res = client.get("/api/unknown_endpoint")
    assert res.status_code == 404
    assert res.is_json
    data = res.get_json()
    assert data["status_code"] == 404
    assert "Resource not found" in data["error"]

def test_custom_500_error_page(test_client):
    """Verify custom branded 500 error page renders cleanly without leaking tracebacks."""
    client, app = test_client
    app.config["PROPAGATE_EXCEPTIONS"] = False

    # Define a temporary route that triggers an unhandled 500 error
    @app.route("/test-500-trigger")
    def trigger_500():
        raise RuntimeError("Simulated server fault for branding verification")

    res = client.get("/test-500-trigger")
    assert res.status_code == 500
    html = res.get_data(as_text=True)

    # Branded elements
    assert "500 Server Error | Virtual Atmosphere" in html
    assert "Telemetry Service Condition" in html
    assert "Retry Request" in html
    assert "va-logo-card.png" in html

    # Safe: no leaked sensitive details
    assert "Simulated server fault" not in html
    assert "RuntimeError" not in html
    assert "Traceback" not in html
