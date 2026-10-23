import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent

class Config:
    """Application configuration for Virtual Atmosphere."""

    # Product Branding
    PRODUCT_NAME = "Virtual Atmosphere"
    SHORT_NAME = "VA"
    WORDMARK = "VA | Virtual Atmosphere"
    DASHBOARD_NAME = "VA Monitor"
    TAGLINE = "Understand Your Atmosphere."
    VERSION = "1.0.0"

    # Base directory reference
    BASE_DIR = BASE_DIR

    # Detect Vercel serverless cloud environment
    IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))

    # Runtime Mode: 'demo' or 'live'
    # Default is 'demo' for immediate development/testing on laptops and Vercel.
    # Set VA_MODE=live when running on Raspberry Pi with real BMP280 hardware.
    MODE = "demo" if IS_VERCEL else os.environ.get("VA_MODE", "demo").strip().lower()

    # Network Binding
    # Default to 127.0.0.1 for secure local development.
    # Set VA_HOST=0.0.0.0 to allow access from phones/tablets on local Wi-Fi.
    HOST = os.environ.get("VA_HOST", "127.0.0.1")
    PORT = int(os.environ.get("VA_PORT", 5000))
    DEBUG = os.environ.get("FLASK_DEBUG", "0").strip() in ("1", "true", "True")

    # Database Settings
    # On Vercel serverless, the root directory is read-only; use writable /tmp
    DATA_DIR = Path("/tmp") if IS_VERCEL else (BASE_DIR / "data")
    DATABASE_PATH = os.environ.get("VA_DB_PATH", str(DATA_DIR / "virtual_atmosphere.db"))

    # Hardware & Sensor Configuration
    # Raspberry Pi 3 Model B+ typically uses I2C bus 1
    I2C_BUS = int(os.environ.get("VA_I2C_BUS", 1))
    # GY-BMP280 breakouts typically use address 0x76 (SDO->GND) or 0x77 (SDO->VCC)
    I2C_ADDRESS_CANDIDATES = [0x76, 0x77]
    SAMPLING_INTERVAL_SECONDS = int(os.environ.get("VA_SAMPLING_INTERVAL", 10))

    # Alert & Safety Thresholds
    # Initial configurable temperature warning threshold in Celsius
    DEFAULT_TEMPERATURE_THRESHOLD_C = float(os.environ.get("VA_TEMP_THRESHOLD", 35.0))
    # Temperature hysteresis for clearing alerts to avoid boundary flapping
    ALERT_CLEAR_HYSTERESIS_C = 0.5

    # Optional retention policy in days (0 or None means keep indefinitely)
    DATA_RETENTION_DAYS = int(os.environ.get("VA_RETENTION_DAYS", 0))
