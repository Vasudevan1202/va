import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from config import Config

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Creates a thread-safe connection to the SQLite database."""
    path = db_path or Config.DATABASE_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency between sensor background thread and Flask web requests
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db(db_path: Optional[str] = None) -> None:
    """Initializes tables and default settings if they do not exist."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    temperature_c REAL NOT NULL,
                    pressure_hpa REAL NOT NULL,
                    source TEXT NOT NULL,
                    validity_status TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp);
                CREATE INDEX IF NOT EXISTS idx_readings_source ON readings(source);

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    measured_value REAL NOT NULL,
                    threshold_value REAL NOT NULL,
                    status TEXT NOT NULL,
                    acknowledged_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);

                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    temperature_threshold_c REAL NOT NULL DEFAULT 35.0,
                    sampling_interval_seconds INTEGER NOT NULL DEFAULT 10
                );
            """)

            # Ensure row with id=1 exists in settings
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM settings WHERE id = 1;")
            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO settings (id, temperature_threshold_c, sampling_interval_seconds)
                    VALUES (1, ?, ?);
                    """,
                    (Config.DEFAULT_TEMPERATURE_THRESHOLD_C, Config.SAMPLING_INTERVAL_SECONDS)
                )
    finally:
        conn.close()

def insert_reading(
    temperature_c: float,
    pressure_hpa: float,
    source: str = "hardware",
    validity_status: str = "valid",
    timestamp: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """Inserts a new sensor reading into the database."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO readings (timestamp, temperature_c, pressure_hpa, source, validity_status)
                VALUES (?, ?, ?, ?, ?);
                """,
                (timestamp, round(temperature_c, 2), round(pressure_hpa, 2), source, validity_status)
            )
            return cursor.lastrowid
    finally:
        conn.close()

def get_latest_reading(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent reading from the database."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status
            FROM readings
            ORDER BY id DESC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_recent_readings(limit: int = 20, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves the latest N readings."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status
            FROM readings
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def parse_range_to_cutoff(range_code: str) -> datetime:
    """Converts a range string like '1h', '6h', '24h', '7d' to a UTC cutoff datetime."""
    now = datetime.now(timezone.utc)
    range_map = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    delta = range_map.get(range_code.lower(), timedelta(hours=24))
    return now - delta

def get_readings_range(range_code: str = "24h", db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves chronological readings within a standard time range for charting.
    Only returns valid readings.
    """
    cutoff = parse_range_to_cutoff(range_code).isoformat()
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status
            FROM readings
            WHERE timestamp >= ? AND validity_status = 'valid'
            ORDER BY timestamp ASC;
            """,
            (cutoff,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_readings_history(
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    page: int = 1,
    limit: int = 25,
    db_path: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated historical readings with optional date boundaries."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        clauses = []
        params = []

        if start_iso:
            clauses.append("timestamp >= ?")
            params.append(start_iso)
        if end_iso:
            clauses.append("timestamp <= ?")
            params.append(end_iso)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        # Count total matches
        cursor.execute(f"SELECT COUNT(*) as total FROM readings {where_sql};", params)
        total = cursor.fetchone()["total"]

        offset = max(0, (page - 1) * limit)
        query_params = list(params) + [limit, offset]

        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status
            FROM readings
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?;
            """,
            query_params
        )
        readings = [dict(row) for row in cursor.fetchall()]
        return readings, total
    finally:
        conn.close()

def get_readings_for_export(
    range_code: Optional[str] = None,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieves readings matching the filter for CSV export."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        clauses = []
        params = []

        if range_code and range_code != "all":
            cutoff = parse_range_to_cutoff(range_code).isoformat()
            clauses.append("timestamp >= ?")
            params.append(cutoff)
        else:
            if start_iso:
                clauses.append("timestamp >= ?")
                params.append(start_iso)
            if end_iso:
                clauses.append("timestamp <= ?")
                params.append(end_iso)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status
            FROM readings
            {where_sql}
            ORDER BY timestamp ASC;
            """,
            params
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_today_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Calculates summary statistics for readings collected today (UTC)."""
    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                COUNT(*) as count,
                MIN(temperature_c) as min_temp,
                MAX(temperature_c) as max_temp,
                AVG(temperature_c) as avg_temp,
                MIN(pressure_hpa) as min_pressure,
                MAX(pressure_hpa) as max_pressure,
                AVG(pressure_hpa) as avg_pressure,
                MAX(timestamp) as last_collection_time
            FROM readings
            WHERE timestamp >= ? AND validity_status = 'valid';
            """,
            (today_start,)
        )
        row = cursor.fetchone()
        if row and row["count"] > 0:
            return {
                "count": row["count"],
                "min_temp": round(row["min_temp"], 2) if row["min_temp"] is not None else None,
                "max_temp": round(row["max_temp"], 2) if row["max_temp"] is not None else None,
                "avg_temp": round(row["avg_temp"], 2) if row["avg_temp"] is not None else None,
                "min_pressure": round(row["min_pressure"], 2) if row["min_pressure"] is not None else None,
                "max_pressure": round(row["max_pressure"], 2) if row["max_pressure"] is not None else None,
                "avg_pressure": round(row["avg_pressure"], 2) if row["avg_pressure"] is not None else None,
                "last_collection_time": row["last_collection_time"]
            }
        return {
            "count": 0,
            "min_temp": None,
            "max_temp": None,
            "avg_temp": None,
            "min_pressure": None,
            "max_pressure": None,
            "avg_pressure": None,
            "last_collection_time": None
        }
    finally:
        conn.close()

# ----------------- Alerts Operations -----------------

def get_alerts(status_filter: Optional[str] = None, limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves list of alerts with optional status filter ('active', 'acknowledged', 'resolved')."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        if status_filter and status_filter.lower() != "all":
            cursor.execute(
                """
                SELECT id, timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at
                FROM alerts
                WHERE status = ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (status_filter.lower(), limit)
            )
        else:
            cursor.execute(
                """
                SELECT id, timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at
                FROM alerts
                ORDER BY id DESC
                LIMIT ?;
                """,
                (limit,)
            )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_active_alert(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the current ongoing active alert, if any."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at
            FROM alerts
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def create_alert(
    alert_type: str,
    measured_value: float,
    threshold_value: float,
    db_path: Optional[str] = None
) -> int:
    """Inserts a new alert event."""
    timestamp = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO alerts (timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at)
                VALUES (?, ?, ?, ?, 'active', NULL);
                """,
                (timestamp, alert_type, round(measured_value, 2), round(threshold_value, 2))
            )
            return cursor.lastrowid
    finally:
        conn.close()

def acknowledge_alert(alert_id: int, db_path: Optional[str] = None) -> bool:
    """Marks an alert as acknowledged."""
    ack_time = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE alerts
                SET status = 'acknowledged', acknowledged_at = ?
                WHERE id = ? AND status = 'active';
                """,
                (ack_time, alert_id)
            )
            return cursor.rowcount > 0
    finally:
        conn.close()

def resolve_active_alerts(db_path: Optional[str] = None) -> int:
    """Marks any active alerts as resolved when temperature returns to safe zone."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE alerts
                SET status = 'resolved'
                WHERE status IN ('active', 'acknowledged');
                """
            )
            return cursor.rowcount
    finally:
        conn.close()

# ----------------- Settings Operations -----------------

def get_settings(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves current application settings."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT temperature_threshold_c, sampling_interval_seconds
            FROM settings
            WHERE id = 1;
            """
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {
            "temperature_threshold_c": Config.DEFAULT_TEMPERATURE_THRESHOLD_C,
            "sampling_interval_seconds": Config.SAMPLING_INTERVAL_SECONDS
        }
    finally:
        conn.close()

def update_temperature_threshold(threshold_c: float, db_path: Optional[str] = None) -> bool:
    """Updates the temperature alert threshold in Celsius."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE settings
                SET temperature_threshold_c = ?
                WHERE id = 1;
                """,
                (round(threshold_c, 2),)
            )
            return cursor.rowcount > 0
    finally:
        conn.close()

def update_sampling_interval(interval_seconds: int, db_path: Optional[str] = None) -> bool:
    """Updates the sensor sampling interval."""
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE settings
                SET sampling_interval_seconds = ?
                WHERE id = 1;
                """,
                (interval_seconds,)
            )
            return cursor.rowcount > 0
    finally:
        conn.close()

def get_db_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Returns database size, record counts, and health status."""
    path = db_path or Config.DATABASE_PATH
    file_size_bytes = os.path.getsize(path) if os.path.exists(path) else 0
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM readings;")
        readings_count = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM alerts;")
        alerts_count = cursor.fetchone()["count"]
        return {
            "file_size_bytes": file_size_bytes,
            "file_size_kb": round(file_size_bytes / 1024, 2),
            "readings_count": readings_count,
            "alerts_count": alerts_count,
            "status": "healthy"
        }
    finally:
        conn.close()
