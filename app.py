import io
import csv
import math
import hmac
import time
import secrets
import logging
import threading
from functools import wraps
from datetime import datetime, timezone
from typing import Tuple, Optional
from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    redirect,
    url_for,
    Response,
    send_from_directory,
    session
)
from config import Config
import database
from sensor_service import SensorService
from alert_service import AlertService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("virtual_atmosphere.app")

# Thread-safe in-memory sliding-window rate limiter for telemetry ingestion
_telemetry_rate_lock = threading.Lock()
_telemetry_rate_records = {}  # Dict[str, list[float]]

def is_telemetry_rate_limited(client_ip: str, limit: int = 60, window_seconds: float = 60.0) -> Tuple[bool, int]:
    """
    Evaluates process-local sliding-window rate limit for telemetry ingestion.
    Returns (is_limited, retry_after_seconds).

    Architectural Note:
    On serverless platforms like Vercel, processes are ephemeral and memory is
    isolated per container. In-memory rate limiting prevents burst floods within
    an individual active worker process. Distributed production-grade rate limiting
    across distributed serverless invocations requires an edge proxy or datastore
    (such as Cloudflare WAF, Upstash Redis, or Vercel Edge Middleware).
    """
    now = time.time()
    cutoff = now - window_seconds
    with _telemetry_rate_lock:
        # Prevent unbounded memory accumulation: prune stale client records if dictionary grows
        if len(_telemetry_rate_records) > 1000:
            stale_keys = [k for k, ts in _telemetry_rate_records.items() if not ts or ts[-1] <= cutoff]
            for k in stale_keys:
                del _telemetry_rate_records[k]

        timestamps = _telemetry_rate_records.get(client_ip, [])
        valid_timestamps = [t for t in timestamps if t > cutoff]
        if len(valid_timestamps) >= limit:
            oldest_in_window = valid_timestamps[0]
            retry_after = max(1, int(window_seconds - (now - oldest_in_window)))
            _telemetry_rate_records[client_ip] = valid_timestamps
            return True, retry_after
        valid_timestamps.append(now)
        _telemetry_rate_records[client_ip] = valid_timestamps
        return False, 0

def create_app(test_config=None) -> Flask:
    """Application factory for Virtual Atmosphere."""
    base_dir = Config.BASE_DIR
    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
        static_url_path="/static"
    )

    app.config.from_object(Config)
    if test_config:
        app.config.from_mapping(test_config)

    # Configure session security settings
    secret_key = app.config.get("SECRET_KEY") or Config.SECRET_KEY or secrets.token_hex(32)
    app.secret_key = secret_key
    app.config["SECRET_KEY"] = secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = app.config.get("SESSION_COOKIE_HTTPONLY", Config.SESSION_COOKIE_HTTPONLY)
    app.config["SESSION_COOKIE_SAMESITE"] = app.config.get("SESSION_COOKIE_SAMESITE", Config.SESSION_COOKIE_SAMESITE)
    app.config["SESSION_COOKIE_SECURE"] = app.config.get("SESSION_COOKIE_SECURE", Config.SESSION_COOKIE_SECURE)

    # Initialize database
    if app.config.get("TESTING") or "DATABASE_PATH" in app.config:
        db_path = app.config.get("DATABASE_PATH")
    elif Config.TURSO_DATABASE_URL and Config.TURSO_AUTH_TOKEN:
        db_path = None
    else:
        db_path = Config.DATABASE_PATH
    database.init_db(db_path)

    # Only auto-seed demo data in local non-production demo development when the database is empty
    app_mode = app.config.get("MODE", Config.MODE)
    if not app.config.get("TESTING") and not Config.is_production_mode() and app_mode == "demo":
        try:
            stats = database.get_db_stats(db_path=db_path)
            if stats.get("readings_count", 0) == 0:
                from scripts.seed_demo_data import seed_demo_history
                seed_demo_history(hours=24, step_minutes=10, db_path=db_path)
        except Exception as e:
            logger.warning(f"Could not auto-seed demo data: {e}")


    # Initialize Sensor Service
    app_mode = app.config.get("MODE", Config.MODE)
    sensor_service = SensorService(mode=app_mode, db_path=db_path)
    app.sensor_service = sensor_service

    # Start sensor background loop if not in test configuration and not on Vercel
    if not app.config.get("TESTING", False) and not Config.IS_VERCEL:
        sensor_service.start()

    # Mutation authorization decorator (session CSRF or Control Key)
    def require_mutation_auth(f):
        """
        Protects public mutation endpoints against unauthorized modification and CSRF attacks.
        Accepts:
        1. Session CSRF Token: Header 'X-CSRF-Token' or body 'csrf_token' matching session['csrf_token'].
        2. Programmatic Control Key: Header 'Authorization: Bearer <CONTROL_KEY>' or 'X-VA-Control-Key'.
        Fails closed with HTTP 403 Forbidden if neither valid credential is provided.
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Programmatic Control Key check
            control_key = Config.get_control_key()
            auth_header = request.headers.get("Authorization", "").strip()
            custom_header = request.headers.get("X-VA-Control-Key", "").strip()

            token = None
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()
            elif custom_header:
                token = custom_header

            if token and control_key:
                if hmac.compare_digest(token.encode("utf-8"), control_key.encode("utf-8")):
                    return f(*args, **kwargs)

            # 2. Browser Session CSRF Token check
            session_token = session.get("csrf_token")
            request_token = request.headers.get("X-CSRF-Token", "").strip()
            if not request_token and request.is_json:
                payload = request.get_json(silent=True)
                if isinstance(payload, dict):
                    request_token = str(payload.get("csrf_token", "")).strip()

            if session_token and request_token:
                if hmac.compare_digest(request_token.encode("utf-8"), session_token.encode("utf-8")):
                    return f(*args, **kwargs)

            logger.warning(f"Unauthorized mutation attempt on {request.path} from {request.remote_addr}")
            return jsonify({
                "success": False,
                "error": "Unauthorized mutation: Valid CSRF token (X-CSRF-Token) or Control Key required."
            }), 403

        return decorated_function

    # Ensure fresh telemetry on requests in serverless environments and initialize session CSRF
    @app.before_request
    def ensure_session_and_telemetry():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(24)

        if not app.config.get("TESTING", False) and not Config.is_production_mode():
            if hasattr(app, "sensor_service") and app.sensor_service and app.sensor_service.mode == "demo":
                if not request.path.startswith("/static"):
                    app.sensor_service.ensure_sample()

    # Register Context Processor for global template variables
    @app.context_processor
    def inject_global_vars():
        return {
            "PRODUCT_NAME": Config.PRODUCT_NAME,
            "SHORT_NAME": Config.SHORT_NAME,
            "WORDMARK": Config.WORDMARK,
            "DASHBOARD_NAME": Config.DASHBOARD_NAME,
            "TAGLINE": Config.TAGLINE,
            "VERSION": Config.VERSION,
            "ASSET_VERSION": getattr(Config, "ASSET_VERSION", "1.0.1"),
            "app_mode": app.sensor_service.mode,
            "csrf_token": session.get("csrf_token", "")
        }

    # ==========================================
    # Favicon & Brand Asset Routes
    # ==========================================

    @app.route("/favicon.ico")
    def favicon():
        res = send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")
        res.headers["Cache-Control"] = "no-cache, must-revalidate"
        return res

    @app.route("/site.webmanifest")
    def site_manifest():
        res = send_from_directory(app.static_folder, "site.webmanifest", mimetype="application/manifest+json")
        res.headers["Cache-Control"] = "no-cache, must-revalidate"
        return res

    @app.route("/apple-touch-icon.png")
    @app.route("/apple-touch-icon-precomposed.png")
    def apple_touch_icon():
        res = send_from_directory(app.static_folder, "apple-touch-icon.png", mimetype="image/png")
        res.headers["Cache-Control"] = "no-cache, must-revalidate"
        return res

    # ==========================================
    # HTML Page Routes
    # ==========================================

    @app.route("/")
    def index():
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html", active_page="dashboard")

    @app.route("/live")
    def live_monitor():
        return render_template("live_monitor.html", active_page="live")

    @app.route("/history")
    def history():
        return render_template("history.html", active_page="history")

    @app.route("/alerts")
    def alerts():
        return render_template("alerts.html", active_page="alerts")

    @app.route("/system")
    def system():
        return render_template("system.html", active_page="system")

    @app.route("/about")
    @app.route("/project")
    @app.route("/project-overview")
    def about():
        """Redirect legacy project/team routes to main overview dashboard."""
        return redirect(url_for("dashboard"), code=302)

    # ==========================================
    # REST API Endpoints
    # ==========================================

    @app.route("/api/status", methods=["GET"])
    def api_status():
        """Returns hardware, backend runtime status, and active alert summary."""
        status = app.sensor_service.get_status()
        alert_info = AlertService.get_current_alert_status(db_path=db_path)
        db_stats = database.get_db_stats(db_path=db_path)

        return jsonify({
            "status": "online",
            "sensor": status,
            "alert": alert_info,
            "database": db_stats,
            "version": Config.VERSION
        }), 200

    @app.route("/api/readings/latest", methods=["GET"])
    def api_readings_latest():
        """Returns the most recent measurement, trend vs previous, and daily stats."""
        real_only = Config.is_production_mode() or request.args.get("real_only", "0").strip().lower() in ("1", "true")
        recent = database.get_recent_readings(limit=2, db_path=db_path, real_only=real_only)
        today_stats = database.get_today_stats(db_path=db_path, real_only=real_only)
        alert_info = AlertService.get_current_alert_status(db_path=db_path)
        sensor_status = app.sensor_service.get_status()

        latest = recent[0] if len(recent) > 0 else None
        previous = recent[1] if len(recent) > 1 else None

        # Calculate exact telemetry freshness and honest connectivity state
        age_seconds = None
        is_live = False
        is_stale = False
        status_label = "No Live Reading"

        if latest and latest.get("timestamp"):
            try:
                ts = datetime.fromisoformat(latest["timestamp"].replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                age_seconds = max(0.0, round((now - ts).total_seconds(), 1))
                if age_seconds < 180.0 and latest.get("source") not in ("demo", "simulated"):
                    is_live = True
                    is_stale = False
                    status_label = "Live Data"
                else:
                    is_live = False
                    is_stale = True
                    status_label = "Sensor Offline"
            except Exception:
                age_seconds = None

        temp_trend = 0.0
        press_trend = 0.0
        humidity_trend = 0.0
        if latest and previous:
            temp_trend = round(latest["temperature_c"] - previous["temperature_c"], 2)
            if latest.get("pressure_hpa") is not None and previous.get("pressure_hpa") is not None:
                press_trend = round(latest["pressure_hpa"] - previous["pressure_hpa"], 2)
            if latest.get("humidity_pct") is not None and previous.get("humidity_pct") is not None:
                humidity_trend = round(latest["humidity_pct"] - previous["humidity_pct"], 1)

        latest_dht11 = database.get_latest_dht11_reading(db_path=db_path, real_only=real_only)
        latest_bmp280 = database.get_latest_bmp280_reading(db_path=db_path, real_only=real_only)

        from weather_service import WeatherService
        heat_risk = None
        if latest:
            heat_risk = WeatherService.get_heat_risk_assessment(
                temp_c=latest.get("temperature_c"),
                humidity_pct=latest.get("humidity_pct"),
                source=latest.get("source", "simulated")
            )

        return jsonify({
            "latest": latest,
            "previous": previous,
            "dht11": latest_dht11,
            "bmp280": latest_bmp280,
            "freshness": {
                "age_seconds": age_seconds,
                "is_live": is_live,
                "is_stale": is_stale,
                "status_label": status_label,
                "last_update_iso": latest.get("timestamp") if latest else None
            },
            "trend": {
                "temperature_delta_c": temp_trend,
                "pressure_delta_hpa": press_trend,
                "humidity_delta_pct": humidity_trend
            },
            "today_stats": today_stats,
            "heat_risk": heat_risk,
            "alert": alert_info,
            "sensor": sensor_status
        }), 200


    @app.route("/api/ingest/dht11", methods=["POST"])
    def api_dht11_ingest():
        """
        Dedicated secure ingestion endpoint for Raspberry Pi / Arduino DHT11 sensor readings.
        Authentication: Authorization: Bearer <VA_DHT11_INGEST_KEY> (or VA_INGEST_KEY)
        Accepts JSON:
            temperature_c: numeric (valid range: -20°C to 60°C)
            humidity_percent: numeric (valid range: 0% to 100%)
            timestamp: optional ISO 8601 string (defaults to current UTC time)
            source: optional string attribution (default: 'dht11')
        """
        from weather_service import WeatherService

        # 1. Rate Limiting Check (sliding window per client IP)
        if Config.IS_VERCEL:
            client_ip = request.headers.get("x-vercel-forwarded-for") or request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        else:
            client_ip = request.remote_addr or "127.0.0.1"
        limit = app.config.get("TELEMETRY_RATE_LIMIT_PER_MINUTE", Config.TELEMETRY_RATE_LIMIT_PER_MINUTE)
        is_limited, retry_after = is_telemetry_rate_limited(client_ip, limit=limit, window_seconds=60.0)
        if is_limited:
            response = jsonify({
                "status": "error",
                "error": f"Rate limit exceeded. Maximum {limit} submissions per minute.",
                "retry_after": retry_after
            })
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response

        # 2. Authentication Verification (Fail-Closed)
        auth_header = request.headers.get("Authorization", "").strip()
        custom_header = request.headers.get("X-VA-DHT11-Key", "").strip() or request.headers.get("X-VA-Ingest-Key", "").strip()

        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        elif custom_header:
            token = custom_header

        if not token:
            return jsonify({
                "status": "error",
                "error": "Missing or malformed Authorization header. Expected 'Authorization: Bearer <token>'"
            }), 401

        expected = Config.get_dht11_ingest_key()
        if not expected:
            logger.error("DHT11 telemetry ingestion rejected: Ingestion key is unconfigured or a known placeholder.")
            return jsonify({
                "status": "error",
                "error": "Telemetry ingestion unauthorized (unconfigured secret)"
            }), 401

        if not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
            return jsonify({"status": "error", "error": "Invalid ingestion credentials"}), 401

        # 3. Payload Extraction & Structural Validation
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({"status": "error", "error": "Invalid or missing JSON payload"}), 400

        # Required fields: temperature_c and humidity_percent (accept humidity_pct as alias)
        if "temperature_c" not in payload:
            return jsonify({
                "status": "error",
                "error": "Missing required field: 'temperature_c'"
            }), 400

        hum_key = "humidity_percent" if "humidity_percent" in payload else ("humidity_pct" if "humidity_pct" in payload else None)
        if hum_key is None:
            return jsonify({
                "status": "error",
                "error": "Missing required field: 'humidity_percent'"
            }), 400

        try:
            temp_c = float(payload["temperature_c"])
        except (ValueError, TypeError):
            return jsonify({"status": "error", "error": "'temperature_c' must be a numeric value"}), 400

        try:
            humidity_percent = float(payload[hum_key])
        except (ValueError, TypeError):
            return jsonify({"status": "error", "error": "'humidity_percent' must be a numeric value"}), 400

        # Reject NaN and Infinity
        if math.isnan(temp_c) or math.isinf(temp_c):
            return jsonify({"status": "error", "error": "'temperature_c' must not be NaN or Infinity"}), 400

        if math.isnan(humidity_percent) or math.isinf(humidity_percent):
            return jsonify({"status": "error", "error": "'humidity_percent' must not be NaN or Infinity"}), 400

        # Meteorological and Physical Sensor Bounds Validation
        valid, msg = WeatherService.validate_dht11_reading(temp_c, humidity_percent)
        if not valid:
            return jsonify({"status": "error", "error": f"Invalid sensor reading: {msg}"}), 400

        # Validate timestamp
        raw_ts = payload.get("timestamp")
        if raw_ts:
            if not isinstance(raw_ts, str):
                return jsonify({"status": "error", "error": "'timestamp' must be an ISO 8601 string"}), 400
            try:
                datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                timestamp = raw_ts
            except Exception:
                return jsonify({"status": "error", "error": "Invalid 'timestamp' format. Must be ISO 8601 string"}), 400
        else:
            timestamp = datetime.now(timezone.utc).isoformat()

        # Validate source
        raw_source = payload.get("source", "dht11")
        if not isinstance(raw_source, str) or not raw_source.strip():
            return jsonify({"status": "error", "error": "'source' must be a non-empty string"}), 400
        source = raw_source.strip()[:64]

        # Compute heat index via NOAA Rothfusz formula
        heat_index_c = WeatherService.compute_heat_index(temp_c, humidity_percent)
        heat_risk = WeatherService.get_heat_risk_assessment(temp_c, humidity_percent, source)

        # Store durably in database
        try:
            record_id = database.insert_reading(
                temperature_c=temp_c,
                pressure_hpa=None,
                source=source,
                validity_status="valid",
                timestamp=timestamp,
                humidity_pct=humidity_percent,
                heat_index_c=heat_index_c,
                sensor_type="dht11",
                db_path=db_path
            )
            if not record_id:
                logger.error("DHT11 telemetry ingestion rejected: database write did not return a valid record id.")
                return jsonify({"status": "error", "error": "Database storage failure"}), 500
        except Exception as e:
            logger.error(f"Failed to persist DHT11 reading to database: {type(e).__name__}: {e}")
            return jsonify({"status": "error", "error": "Database storage failure"}), 500

        # Evaluate safety alerts for temperature threshold (non-fatal for ingestion)
        try:
            AlertService.evaluate_reading(temp_c, db_path=db_path)
        except Exception as e:
            logger.error(f"Alert evaluation non-fatal failure during DHT11 ingestion: {type(e).__name__}: {e}")

        # Update in-memory cache in sensor_service
        dht11_record = {
            "id": record_id,
            "timestamp": timestamp,
            "temperature_c": round(temp_c, 2),
            "humidity_percent": round(humidity_percent, 1),
            "heat_index_c": heat_index_c,
            "source": source,
            "validity_status": "valid"
        }
        try:
            if hasattr(app, "sensor_service") and app.sensor_service:
                app.sensor_service.update_dht11(dht11_record)
        except Exception as e:
            logger.debug(f"Could not update sensor_service DHT11 state: {e}")

        return jsonify({
            "status": "success",
            "id": record_id,
            "timestamp": timestamp,
            "temperature_c": round(temp_c, 2),
            "humidity_percent": round(humidity_percent, 1),
            "heat_index_c": heat_index_c,
            "source": source,
            "heat_risk": heat_risk
        }), 201

    @app.route("/api/telemetry", methods=["POST"])
    def api_telemetry_ingest():
        """
        Secure ingestion endpoint for Raspberry Pi remote telemetry.
        Authentication: Authorization: Bearer <INGEST_KEY>
        Accepts: JSON payload with temperature_c, pressure_hpa, optional humidity_pct,
                 optional latitude/longitude, optional source ('hardware' or 'simulated').
        """
        from weather_service import WeatherService

        # Rate Limiting Check (sliding window per client IP)
        if Config.IS_VERCEL:
            # When behind Vercel edge reverse proxy, trust forwarded header
            client_ip = request.headers.get("x-vercel-forwarded-for") or request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        else:
            # In direct/local deployments, use socket remote_addr to prevent arbitrary X-Forwarded-For spoofing
            client_ip = request.remote_addr or "127.0.0.1"
        limit = app.config.get("TELEMETRY_RATE_LIMIT_PER_MINUTE", Config.TELEMETRY_RATE_LIMIT_PER_MINUTE)
        is_limited, retry_after = is_telemetry_rate_limited(client_ip, limit=limit, window_seconds=60.0)
        if is_limited:
            response = jsonify({
                "status": "error",
                "error": f"Rate limit exceeded. Maximum {limit} telemetry submissions per minute.",
                "retry_after": retry_after
            })
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response

        # Ingestion Authentication Verification (Fail-Closed)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "error": "Missing or malformed Authorization header"}), 401

        token = auth_header.split(" ", 1)[1].strip()
        expected = Config.get_ingest_key()
        if not expected:
            logger.error("Telemetry ingestion rejected: Ingestion key is unconfigured or a known placeholder.")
            return jsonify({"status": "error", "error": "Telemetry ingestion unauthorized (unconfigured secret)"}), 401

        if not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
            return jsonify({"status": "error", "error": "Invalid ingestion credentials"}), 401

        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({"status": "error", "error": "Invalid or missing JSON payload"}), 400

        # Required fields
        if "temperature_c" not in payload or "pressure_hpa" not in payload:
            return jsonify({
                "status": "error",
                "error": "Missing required fields: 'temperature_c' and 'pressure_hpa' are mandatory"
            }), 400

        try:
            temp_c = float(payload["temperature_c"])
            pressure_hpa = float(payload["pressure_hpa"])
        except (ValueError, TypeError):
            return jsonify({"status": "error", "error": "temperature_c and pressure_hpa must be numeric"}), 400

        # Reject NaN and Infinity
        if math.isnan(temp_c) or math.isinf(temp_c) or math.isnan(pressure_hpa) or math.isinf(pressure_hpa):
            return jsonify({"status": "error", "error": "temperature_c and pressure_hpa must not be NaN or Infinity"}), 400

        # Optional fields
        humidity_pct = None
        if payload.get("humidity_pct") is not None:
            try:
                humidity_pct = float(payload["humidity_pct"])
            except (ValueError, TypeError):
                return jsonify({"status": "error", "error": "humidity_pct must be numeric"}), 400
            if math.isnan(humidity_pct) or math.isinf(humidity_pct):
                return jsonify({"status": "error", "error": "humidity_pct must not be NaN or Infinity"}), 400

        lat = None
        if payload.get("latitude") is not None:
            try:
                lat = float(payload["latitude"])
            except (ValueError, TypeError):
                return jsonify({"status": "error", "error": "latitude must be numeric"}), 400
            if math.isnan(lat) or math.isinf(lat):
                return jsonify({"status": "error", "error": "latitude must not be NaN or Infinity"}), 400

        lon = None
        if payload.get("longitude") is not None:
            try:
                lon = float(payload["longitude"])
            except (ValueError, TypeError):
                return jsonify({"status": "error", "error": "longitude must be numeric"}), 400
            if math.isnan(lon) or math.isinf(lon):
                return jsonify({"status": "error", "error": "longitude must not be NaN or Infinity"}), 400

        raw_source = payload.get("source", "hardware")
        if not isinstance(raw_source, str) or raw_source.strip().lower() not in ("hardware", "simulated", "demo"):
            return jsonify({
                "status": "error",
                "error": "Invalid source: must be 'hardware' or 'simulated'"
            }), 400
        source = raw_source.strip().lower()

        timestamp = payload.get("timestamp")
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        # Meteorological range validation
        valid, msg = WeatherService.validate_reading(temp_c, pressure_hpa, humidity_pct, lat, lon)
        if not valid:
            return jsonify({"status": "error", "error": f"Invalid measurement bounds: {msg}"}), 400

        # Compute heat index
        heat_index_c = payload.get("heat_index_c")
        if heat_index_c is not None:
            try:
                heat_index_c = float(heat_index_c)
            except (ValueError, TypeError):
                heat_index_c = WeatherService.compute_heat_index(temp_c, humidity_pct)
        else:
            heat_index_c = WeatherService.compute_heat_index(temp_c, humidity_pct)

        # Store in database
        try:
            record_id = database.insert_reading(
                temperature_c=temp_c,
                pressure_hpa=pressure_hpa,
                source=source,
                validity_status="valid",
                timestamp=timestamp,
                humidity_pct=humidity_pct,
                heat_index_c=heat_index_c,
                latitude=lat,
                longitude=lon,
                db_path=db_path
            )
            if not record_id:
                logger.error("Telemetry ingestion rejected: database write did not return a valid record id.")
                return jsonify({"status": "error", "error": "Database storage failure"}), 500
        except Exception as e:
            logger.error(f"Failed to persist telemetry reading to database: {type(e).__name__}: {e}")
            return jsonify({"status": "error", "error": "Database storage failure"}), 500

        # Evaluate safety alerts (non-fatal)
        try:
            AlertService.evaluate_reading(temp_c, db_path=db_path)
        except Exception as e:
            logger.error(f"Alert evaluation non-fatal failure during telemetry ingestion: {type(e).__name__}: {e}")

        # Update sensor_service cache
        try:
            with app.sensor_service.lock:
                app.sensor_service.is_connected = True
                app.sensor_service.last_reading_time = timestamp
                app.sensor_service.last_reading_val = {
                    "id": record_id,
                    "timestamp": timestamp,
                    "temperature_c": round(temp_c, 2),
                    "pressure_hpa": round(pressure_hpa, 2),
                    "humidity_pct": humidity_pct,
                    "heat_index_c": heat_index_c,
                    "latitude": lat,
                    "longitude": lon,
                    "source": source,
                    "validity_status": "valid"
                }
                app.sensor_service.last_error = None
                app.sensor_service.consecutive_errors = 0
        except Exception:
            pass

        heat_risk = WeatherService.get_heat_risk_assessment(temp_c, humidity_pct, source)

        return jsonify({
            "status": "success",
            "id": record_id,
            "timestamp": timestamp,
            "temperature_c": round(temp_c, 2),
            "pressure_hpa": round(pressure_hpa, 2),
            "humidity_pct": humidity_pct,
            "heat_index_c": heat_index_c,
            "latitude": lat,
            "longitude": lon,
            "source": source,
            "heat_risk": heat_risk
        }), 201

    @app.route("/api/readings", methods=["GET"])
    def api_readings_range():
        """
        Retrieves chronological readings for chart display.
        Query parameters:
        - range: '1h', '6h', '24h' (default), '7d', '30d'
        - start: optional ISO 8601 start timestamp
        - end: optional ISO 8601 end timestamp
        """
        time_range = request.args.get("range", "24h").strip().lower()
        if time_range not in ["1h", "6h", "24h", "7d", "30d"]:
            time_range = "24h"

        start_iso = request.args.get("start", "").strip() or None
        end_iso = request.args.get("end", "").strip() or None

        real_only = Config.is_production_mode() or request.args.get("real_only", "0").strip().lower() in ("1", "true")
        readings = database.get_readings_range(
            range_code=time_range,
            start_iso=start_iso,
            end_iso=end_iso,
            db_path=db_path,
            real_only=real_only
        )

        # Calculate exact time-range specific summary from 100% of raw valid database readings
        temps = [r["temperature_c"] for r in readings if r.get("temperature_c") is not None]
        pressures = [r["pressure_hpa"] for r in readings if r.get("pressure_hpa") is not None]
        humidities = [r["humidity_pct"] for r in readings if r.get("humidity_pct") is not None]
        heat_indices = [r["heat_index_c"] for r in readings if r.get("heat_index_c") is not None]

        # Latest valid readings and timestamps
        latest_temp = None
        latest_temp_time = None
        for r in reversed(readings):
            if r.get("temperature_c") is not None:
                latest_temp = r["temperature_c"]
                latest_temp_time = r.get("timestamp")
                break

        latest_hum = None
        latest_hum_time = None
        for r in reversed(readings):
            if r.get("humidity_pct") is not None:
                latest_hum = r["humidity_pct"]
                latest_hum_time = r.get("timestamp")
                break

        latest_press = None
        latest_press_time = None
        for r in reversed(readings):
            if r.get("pressure_hpa") is not None:
                latest_press = r["pressure_hpa"]
                latest_press_time = r.get("timestamp")
                break

        latest_heat = None
        latest_heat_time = None
        for r in reversed(readings):
            if r.get("heat_index_c") is not None:
                latest_heat = r["heat_index_c"]
                latest_heat_time = r.get("timestamp")
                break

        settings = database.get_settings(db_path=db_path)
        threshold_c = settings.get("temperature_threshold_c", Config.DEFAULT_TEMPERATURE_THRESHOLD_C)
        exceeded_count = sum(1 for t in temps if t >= threshold_c)

        summary = {
            "count": len(readings),
            "range": "custom" if (start_iso or end_iso) else time_range,
            "threshold_c": threshold_c,
            "exceeded_count": exceeded_count,
            # Temperature
            "temp_latest": latest_temp,
            "temp_latest_time": latest_temp_time,
            "temp_min": min(temps) if temps else None,
            "temp_max": max(temps) if temps else None,
            "temp_avg": round(sum(temps) / len(temps), 2) if temps else None,
            "temp_count": len(temps),
            # Pressure
            "press_latest": latest_press,
            "press_latest_time": latest_press_time,
            "press_min": min(pressures) if pressures else None,
            "press_max": max(pressures) if pressures else None,
            "press_avg": round(sum(pressures) / len(pressures), 2) if pressures else None,
            "press_count": len(pressures),
            "press_available": len(pressures) > 0,
            # Humidity
            "hum_latest": latest_hum,
            "hum_latest_time": latest_hum_time,
            "hum_min": min(humidities) if humidities else None,
            "hum_max": max(humidities) if humidities else None,
            "hum_avg": round(sum(humidities) / len(humidities), 1) if humidities else None,
            "hum_count": len(humidities),
            # Heat index
            "heat_latest": latest_heat,
            "heat_latest_time": latest_heat_time,
            "heat_min": min(heat_indices) if heat_indices else None,
            "heat_max": max(heat_indices) if heat_indices else None,
            "heat_avg": round(sum(heat_indices) / len(heat_indices), 1) if heat_indices else None,
            "heat_count": len(heat_indices)
        }

        # Apply peak-preserving and threshold-preserving downsampling for responsive charting
        chart_readings = database.downsample_readings(readings, max_points=400, threshold_c=threshold_c)

        return jsonify({
            "readings": chart_readings,
            "total_count": len(readings),
            "is_downsampled": len(chart_readings) < len(readings),
            "summary": summary
        }), 200

    @app.route("/api/readings/history", methods=["GET"])
    def api_readings_history():
        """
        Retrieves paginated readings with optional date filtering.
        Query parameters:
        - start: ISO 8601 start timestamp
        - end: ISO 8601 end timestamp
        - page: page number (default: 1)
        - limit: items per page (default: 25, max: 100)
        """
        start = request.args.get("start", "").strip() or None
        end = request.args.get("end", "").strip() or None

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1

        try:
            limit = min(100, max(1, int(request.args.get("limit", 25))))
        except ValueError:
            limit = 25

        real_only = Config.is_production_mode() or request.args.get("real_only", "0").strip().lower() in ("1", "true")
        readings, total = database.get_readings_history(
            start_iso=start,
            end_iso=end,
            page=page,
            limit=limit,
            db_path=db_path,
            real_only=real_only
        )

        total_pages = max(1, (total + limit - 1) // limit) if total > 0 else 1

        return jsonify({
            "readings": readings,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }), 200

    @app.route("/api/readings/export.csv", methods=["GET"])
    def api_readings_export_csv():
        """
        Exports sensor readings in CSV format.
        Query parameters:
        - range: '1h', '6h', '24h', '7d', 'all'
        - start: optional start ISO timestamp
        - end: optional end ISO timestamp
        """
        time_range = request.args.get("range", "24h").strip()
        start = request.args.get("start", "").strip() or None
        end = request.args.get("end", "").strip() or None

        real_only = Config.is_production_mode() or request.args.get("real_only", "0").strip().lower() in ("1", "true")
        readings = database.get_readings_for_export(
            range_code=time_range,
            start_iso=start,
            end_iso=end,
            db_path=db_path,
            real_only=real_only
        )


        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID",
            "Timestamp (UTC)",
            "Temperature (Celsius)",
            "Atmospheric Pressure (hPa)",
            "Relative Humidity (%)",
            "Heat Index (°C)",
            "Latitude",
            "Longitude",
            "Data Source",
            "Validity Status"
        ])

        for r in readings:
            writer.writerow([
                r["id"],
                r["timestamp"],
                r["temperature_c"],
                r["pressure_hpa"],
                r.get("humidity_pct") if r.get("humidity_pct") is not None else "",
                r.get("heat_index_c") if r.get("heat_index_c") is not None else "",
                r.get("latitude") if r.get("latitude") is not None else "",
                r.get("longitude") if r.get("longitude") is not None else "",
                r["source"],
                r["validity_status"]
            ])

        csv_content = output.getvalue()
        output.close()

        filename = f"virtual_atmosphere_readings_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )

    @app.route("/api/alerts", methods=["GET"])
    def api_alerts_list():
        """Retrieves list of alerts."""
        status_filter = request.args.get("status", "all").strip().lower()
        try:
            limit = min(100, max(5, int(request.args.get("limit", 50))))
        except ValueError:
            limit = 50

        alerts = database.get_alerts(status_filter=status_filter, limit=limit, db_path=db_path)
        settings = database.get_settings(db_path=db_path)

        return jsonify({
            "alerts": alerts,
            "threshold_c": settings.get("temperature_threshold_c", Config.DEFAULT_TEMPERATURE_THRESHOLD_C),
            "total": len(alerts)
        }), 200

    @app.route("/api/alerts/<int:alert_id>/acknowledge", methods=["POST"])
    @require_mutation_auth
    def api_alert_acknowledge(alert_id):
        """Acknowledges an active alert."""
        success = AlertService.acknowledge(alert_id, db_path=db_path)
        if success:
            return jsonify({
                "success": True,
                "message": f"Alert #{alert_id} acknowledged successfully.",
                "alert_id": alert_id
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": f"Alert #{alert_id} not found or was not in active state."
            }), 404

    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():
        """Retrieves current application settings."""
        settings = database.get_settings(db_path=db_path)
        sensor_status = app.sensor_service.get_status()
        return jsonify({
            "settings": settings,
            "mode": sensor_status["mode"],
            "version": Config.VERSION
        }), 200

    @app.route("/api/settings/threshold", methods=["POST"])
    @require_mutation_auth
    def api_settings_update_threshold():
        """Updates the temperature threshold."""
        data = request.get_json(silent=True) or {}
        if "threshold_c" not in data:
            return jsonify({"success": False, "error": "Missing 'threshold_c' in request body."}), 400

        try:
            threshold = float(data["threshold_c"])
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid 'threshold_c' value. Must be a valid number."}), 400

        # Validate reasonable limits: 0°C to 80°C
        if threshold < 0.0 or threshold > 80.0:
            return jsonify({
                "success": False,
                "error": "Threshold out of allowable bounds (0.0°C to 80.0°C)."
            }), 400

        success = database.update_temperature_threshold(threshold, db_path=db_path)
        if success:
            return jsonify({
                "success": True,
                "threshold_c": threshold,
                "message": f"Temperature threshold updated to {threshold:.1f}°C."
            }), 200
        return jsonify({"success": False, "error": "Failed to update threshold in database."}), 500

    @app.route("/api/settings/sampling_interval", methods=["POST"])
    @require_mutation_auth
    def api_settings_update_sampling():
        """Updates the sensor sampling interval."""
        data = request.get_json(silent=True) or {}
        if "interval_seconds" not in data:
            return jsonify({"success": False, "error": "Missing 'interval_seconds' in request body."}), 400

        try:
            interval = int(data["interval_seconds"])
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid interval. Must be an integer."}), 400

        if interval < 2 or interval > 3600:
            return jsonify({"success": False, "error": "Interval must be between 2 and 3600 seconds."}), 400

        success = database.update_sampling_interval(interval, db_path=db_path)
        if success:
            return jsonify({
                "success": True,
                "sampling_interval_seconds": interval,
                "message": f"Sampling interval updated to {interval} seconds."
            }), 200
        return jsonify({"success": False, "error": "Failed to update interval."}), 500

    @app.route("/api/mode", methods=["POST"])
    @require_mutation_auth
    def api_toggle_mode():
        """Switches mode between 'demo' and 'live'."""
        data = request.get_json(silent=True) or {}
        target_mode = data.get("mode", "").strip().lower()
        if target_mode not in ["demo", "live"]:
            return jsonify({"success": False, "error": "Invalid mode. Choose 'demo' or 'live'."}), 400

        app.sensor_service.set_mode(target_mode)
        return jsonify({
            "success": True,
            "mode": app.sensor_service.mode,
            "message": f"Runtime mode switched to '{target_mode}'."
        }), 200

    @app.route("/api/demo/spike", methods=["POST"])
    @require_mutation_auth
    def api_demo_spike():
        """Toggles simulated temperature spike in Demo mode for alert testing."""
        data = request.get_json(silent=True) or {}
        active = bool(data.get("active", not app.sensor_service.demo_spike_active))
        app.sensor_service.demo_spike_active = active
        return jsonify({
            "success": True,
            "demo_spike_active": active,
            "message": f"Demo temperature spike {'enabled (>36°C)' if active else 'disabled'}."
        }), 200

    # ==========================================
    # Error Handlers
    # ==========================================

    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found", "status_code": 404}), 404
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal Server Error: {error}")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error", "status_code": 500}), 500
        return render_template("500.html"), 500

    return app

if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting Virtual Atmosphere server on {Config.HOST}:{Config.PORT} (Mode: {Config.MODE})")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
