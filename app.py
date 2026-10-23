import io
import csv
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify, request, render_template, redirect, url_for, Response
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

def create_app(test_config=None) -> Flask:
    """Application factory for Virtual Atmosphere."""
    base_dir = Config.BASE_DIR
    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
        static_url_path="/static"
    )

    if test_config:
        app.config.from_mapping(test_config)
    else:
        app.config.from_object(Config)

    # Initialize SQLite database
    db_path = app.config.get("DATABASE_PATH", Config.DATABASE_PATH)
    database.init_db(db_path)

    # On serverless (Vercel), populate with demo data if newly initialized in /tmp
    if Config.IS_VERCEL:
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

    # Ensure fresh telemetry on requests in serverless environments
    @app.before_request
    def ensure_fresh_telemetry():
        if not app.config.get("TESTING", False):
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
            "app_mode": app.sensor_service.mode
        }

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
    def about():
        return render_template("about.html", active_page="about")

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
        recent = database.get_recent_readings(limit=2, db_path=db_path)
        today_stats = database.get_today_stats(db_path=db_path)
        alert_info = AlertService.get_current_alert_status(db_path=db_path)
        sensor_status = app.sensor_service.get_status()

        latest = recent[0] if len(recent) > 0 else None
        previous = recent[1] if len(recent) > 1 else None

        temp_trend = 0.0
        press_trend = 0.0
        if latest and previous:
            temp_trend = round(latest["temperature_c"] - previous["temperature_c"], 2)
            press_trend = round(latest["pressure_hpa"] - previous["pressure_hpa"], 2)

        return jsonify({
            "latest": latest,
            "previous": previous,
            "trend": {
                "temperature_delta_c": temp_trend,
                "pressure_delta_hpa": press_trend
            },
            "today_stats": today_stats,
            "alert": alert_info,
            "sensor": sensor_status
        }), 200

    @app.route("/api/readings", methods=["GET"])
    def api_readings_range():
        """
        Retrieves chronological readings for chart display.
        Query parameters:
        - range: '1h', '6h', '24h' (default), '7d', '30d'
        """
        time_range = request.args.get("range", "24h").strip().lower()
        if time_range not in ["1h", "6h", "24h", "7d", "30d"]:
            time_range = "24h"

        readings = database.get_readings_range(range_code=time_range, db_path=db_path)

        # Calculate time-range specific summary
        temps = [r["temperature_c"] for r in readings if r.get("temperature_c") is not None]
        pressures = [r["pressure_hpa"] for r in readings if r.get("pressure_hpa") is not None]

        summary = {
            "count": len(readings),
            "range": time_range,
            "temp_min": min(temps) if temps else None,
            "temp_max": max(temps) if temps else None,
            "temp_avg": round(sum(temps) / len(temps), 2) if temps else None,
            "press_min": min(pressures) if pressures else None,
            "press_max": max(pressures) if pressures else None,
            "press_avg": round(sum(pressures) / len(pressures), 2) if pressures else None
        }

        return jsonify({
            "readings": readings,
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

        readings, total = database.get_readings_history(
            start_iso=start,
            end_iso=end,
            page=page,
            limit=limit,
            db_path=db_path
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

        readings = database.get_readings_for_export(
            range_code=time_range,
            start_iso=start,
            end_iso=end,
            db_path=db_path
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID",
            "Timestamp (UTC)",
            "Temperature (Celsius)",
            "Atmospheric Pressure (hPa)",
            "Data Source",
            "Validity Status"
        ])

        for r in readings:
            writer.writerow([
                r["id"],
                r["timestamp"],
                r["temperature_c"],
                r["pressure_hpa"],
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
        return render_template("base.html", error_title="404 - Page Not Found", error_message="The requested page could not be located."), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal Server Error: {error}")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error", "status_code": 500}), 500
        return render_template("base.html", error_title="500 - Server Error", error_message="An unexpected server error occurred."), 500

    return app

if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting Virtual Atmosphere server on {Config.HOST}:{Config.PORT} (Mode: {Config.MODE})")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
