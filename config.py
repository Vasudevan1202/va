import os
import secrets
from pathlib import Path
from typing import Optional, Set

# Base directory
BASE_DIR = Path(__file__).resolve().parent

class ConfigMeta(type):
    """Metaclass enabling dynamic class-level property access on Config."""
    _overrides = {}

    @property
    def INGEST_KEY(cls) -> Optional[str]:
        if "INGEST_KEY" in cls._overrides:
            return cls._overrides["INGEST_KEY"]
        return cls.get_ingest_key()

    @INGEST_KEY.setter
    def INGEST_KEY(cls, val):
        cls._overrides["INGEST_KEY"] = val

    @INGEST_KEY.deleter
    def INGEST_KEY(cls):
        cls._overrides.pop("INGEST_KEY", None)

    @property
    def DHT11_INGEST_KEY(cls) -> Optional[str]:
        if "DHT11_INGEST_KEY" in cls._overrides:
            return cls._overrides["DHT11_INGEST_KEY"]
        return cls.get_dht11_ingest_key()

    @DHT11_INGEST_KEY.setter
    def DHT11_INGEST_KEY(cls, val):
        cls._overrides["DHT11_INGEST_KEY"] = val

    @DHT11_INGEST_KEY.deleter
    def DHT11_INGEST_KEY(cls):
        cls._overrides.pop("DHT11_INGEST_KEY", None)

    @property
    def CONTROL_KEY(cls) -> Optional[str]:
        if "CONTROL_KEY" in cls._overrides:
            return cls._overrides["CONTROL_KEY"]
        return cls.get_control_key()

    @CONTROL_KEY.setter
    def CONTROL_KEY(cls, val):
        cls._overrides["CONTROL_KEY"] = val

    @CONTROL_KEY.deleter
    def CONTROL_KEY(cls):
        cls._overrides.pop("CONTROL_KEY", None)

    @property
    def MODE(cls) -> str:
        if "MODE" in cls._overrides:
            return cls._overrides["MODE"]
        va_mode = os.environ.get("VA_MODE", "").strip().lower()
        if va_mode in ("live", "demo"):
            return va_mode
        if cls.is_production_mode():
            return "live"
        return "demo"

    @MODE.setter
    def MODE(cls, val):
        cls._overrides["MODE"] = val

    @MODE.deleter
    def MODE(cls):
        cls._overrides.pop("MODE", None)

    @property
    def TURSO_DATABASE_URL(cls) -> str:
        if "TURSO_DATABASE_URL" in cls._overrides:
            return cls._overrides["TURSO_DATABASE_URL"]
        return os.environ.get("TURSO_DATABASE_URL", "").strip()

    @TURSO_DATABASE_URL.setter
    def TURSO_DATABASE_URL(cls, val):
        cls._overrides["TURSO_DATABASE_URL"] = val

    @TURSO_DATABASE_URL.deleter
    def TURSO_DATABASE_URL(cls):
        cls._overrides.pop("TURSO_DATABASE_URL", None)

    @property
    def TURSO_AUTH_TOKEN(cls) -> str:
        if "TURSO_AUTH_TOKEN" in cls._overrides:
            return cls._overrides["TURSO_AUTH_TOKEN"]
        return os.environ.get("TURSO_AUTH_TOKEN", "").strip()

    @TURSO_AUTH_TOKEN.setter
    def TURSO_AUTH_TOKEN(cls, val):
        cls._overrides["TURSO_AUTH_TOKEN"] = val

    @TURSO_AUTH_TOKEN.deleter
    def TURSO_AUTH_TOKEN(cls):
        cls._overrides.pop("TURSO_AUTH_TOKEN", None)

    @property
    def DATABASE_PATH(cls) -> str:
        if "DATABASE_PATH" in cls._overrides:
            return cls._overrides["DATABASE_PATH"]
        is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
        data_dir = Path("/tmp") if is_vercel else (cls.BASE_DIR / "data")
        return os.environ.get("VA_DB_PATH", str(data_dir / "virtual_atmosphere.db"))

    @DATABASE_PATH.setter
    def DATABASE_PATH(cls, val):
        cls._overrides["DATABASE_PATH"] = val

    @DATABASE_PATH.deleter
    def DATABASE_PATH(cls):
        cls._overrides.pop("DATABASE_PATH", None)

class Config(metaclass=ConfigMeta):
    """Application configuration for Virtual Atmosphere."""

    # Product Branding
    PRODUCT_NAME = "Virtual Atmosphere"
    SHORT_NAME = "VA"
    WORDMARK = "VA | Virtual Atmosphere"
    DASHBOARD_NAME = "VA Monitor"
    TAGLINE = "Understand Your Atmosphere."
    VERSION = "1.0.0"
    ASSET_VERSION = os.environ.get("VA_ASSET_VERSION", "1.0.1")

    # Base directory reference
    BASE_DIR = BASE_DIR

    # Detect Vercel serverless cloud environment
    IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))

    # Network Binding
    # Default to 127.0.0.1 for secure local development.
    # Set VA_HOST=0.0.0.0 to allow access from phones/tablets on local Wi-Fi.
    HOST = os.environ.get("VA_HOST", "127.0.0.1")
    PORT = int(os.environ.get("VA_PORT", 5000))
    DEBUG = os.environ.get("FLASK_DEBUG", "0").strip() in ("1", "true", "True")

    # Database Settings
    # Note: DATABASE_PATH, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, and MODE are dynamically
    # evaluated via ConfigMeta to ensure environment variables (VA_MODE, TURSO_*) take effect immediately.

    # PostgreSQL / Neon / Supabase:
    POSTGRES_URL = os.environ.get("POSTGRES_URL", "").strip() or os.environ.get("DATABASE_URL", "").strip()

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

    # Secret Key for Session & CSRF Protection
    SECRET_KEY = os.environ.get("VA_SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

    # Session Cookie Security Configuration
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = bool(IS_VERCEL or os.environ.get("FLASK_ENV", "").strip().lower() in ("production", "prod"))

    # Known insecure placeholder keys that must NEVER be accepted as active credentials
    KNOWN_PLACEHOLDERS: Set[str] = {
        "va-secret-ingest-key",
        "va-secret-control-key",
        "changeme",
        "secret",
        "placeholder",
        "your-secret-key",
        "admin"
    }

    # Telemetry Ingestion Rate Limiting (process-local sliding window limit per minute)
    TELEMETRY_RATE_LIMIT_PER_MINUTE = int(os.environ.get("VA_TELEMETRY_RATE_LIMIT", 60))

    @classmethod
    def is_production_mode(cls) -> bool:
        """Determines if the application is running in production, on Vercel production, or in live hardware mode."""
        va_mode = os.environ.get("VA_MODE", "").strip().lower()
        if va_mode == "demo":
            return False
        if va_mode == "live":
            return True
        flask_env = os.environ.get("FLASK_ENV", "").strip().lower()
        vercel_env = os.environ.get("VERCEL_ENV", "").strip().lower()
        has_turso = bool(
            cls.TURSO_DATABASE_URL and cls.TURSO_AUTH_TOKEN
        )
        return bool(
            cls.IS_VERCEL
            or vercel_env == "production"
            or flask_env in ("production", "prod")
            or has_turso
        )



    @classmethod
    def get_ingest_key(cls) -> Optional[str]:
        """
        Retrieves the telemetry ingestion secret.
        - Never permits known insecure placeholders (e.g. 'va-secret-ingest-key').
        - In production/live mode, fails closed (returns None) if missing or placeholder.
        - In local development mode, permits a distinct local key ('dev-local-ingest-key') if unconfigured.
        """
        key = os.environ.get("VA_INGEST_KEY", "").strip()
        if not key:
            if cls.is_production_mode():
                return None
            return "dev-local-ingest-key"
        if key.lower() in cls.KNOWN_PLACEHOLDERS:
            return None
        return key

    @classmethod
    def get_control_key(cls) -> Optional[str]:
        """
        Retrieves the control / administrative mutation secret (separate from telemetry ingestion).
        Used for programmatic API mutations (threshold, mode, intervals).
        - In production/live mode, fails closed (returns None) if missing or placeholder.
        - In local development mode, permits a distinct local key ('dev-local-control-key') if unconfigured.
        """
        key = os.environ.get("VA_CONTROL_KEY", "").strip()
        if not key:
            if cls.is_production_mode():
                return None
            return "dev-local-control-key"
        if key.lower() in cls.KNOWN_PLACEHOLDERS:
            return None
        return key

    @classmethod
    def get_dht11_ingest_key(cls) -> Optional[str]:
        """
        Retrieves the telemetry ingestion secret for DHT11 endpoint (/api/ingest/dht11).
        Checks VA_DHT11_INGEST_KEY first, falling back to VA_INGEST_KEY.
        - Never permits known insecure placeholders.
        - In production/live mode, fails closed (returns None) if missing or placeholder.
        - In local development mode, permits a distinct local key ('dev-local-dht11-key') if unconfigured.
        """
        key = (os.environ.get("VA_DHT11_INGEST_KEY") or os.environ.get("VA_INGEST_KEY") or "").strip()
        if not key:
            if cls.is_production_mode():
                return None
            return "dev-local-dht11-key"
        if key.lower() in cls.KNOWN_PLACEHOLDERS:
            return None
        return key

    @classmethod
    def get_storage_backend(cls) -> str:
        """Determines active storage backend name."""
        if cls.TURSO_DATABASE_URL and cls.TURSO_AUTH_TOKEN:
            return "turso"
        if cls.POSTGRES_URL and cls.POSTGRES_URL.startswith(("postgres://", "postgresql://")):
            return "postgres"
        if cls.IS_VERCEL:
            return "sqlite_ephemeral"
        return "sqlite_local"

    @classmethod
    def is_storage_persistent(cls) -> bool:
        """Returns True if database records survive serverless function restarts."""
        backend = cls.get_storage_backend()
        if backend in ("turso", "postgres"):
            return True
        if backend == "sqlite_ephemeral":
            return False
        # Locally, data/virtual_atmosphere.db is durable on disk
        return True

    @classmethod
    def get_persistence_notice(cls) -> Optional[str]:
        """Returns descriptive notice if storage backend is ephemeral."""
        if not cls.is_storage_persistent():
            return (
                "Ephemeral /tmp storage in use on Vercel serverless. "
                "Readings will not persist across container lifecycles. "
                "Configure TURSO_DATABASE_URL + TURSO_AUTH_TOKEN or POSTGRES_URL for durable cloud persistence."
            )
        return None

    # Dynamic properties for backward compatibility
    @property
    def INGEST_KEY(self) -> Optional[str]:
        return self.get_ingest_key()

    @property
    def DHT11_INGEST_KEY(self) -> Optional[str]:
        return self.get_dht11_ingest_key()
