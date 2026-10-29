import os
import json
import sqlite3
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple, Sequence
from config import Config

logger = logging.getLogger("va.database")

# ----------------- Remote Turso libSQL Client -----------------

def is_turso_active(db_path: Optional[str] = None) -> bool:
    """Returns True if remote Turso libSQL is configured and no local db_path override is provided."""
    url = getattr(Config, "TURSO_DATABASE_URL", "") or os.environ.get("TURSO_DATABASE_URL", "").strip()
    token = getattr(Config, "TURSO_AUTH_TOKEN", "") or os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if not (url and token):
        return False
    default_path = getattr(Config, "DATABASE_PATH", None)
    if db_path is None or db_path == default_path:
        return True
    return False

def _get_turso_pipeline_url() -> Optional[str]:
    url = Config.TURSO_DATABASE_URL
    if not url:
        return None
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    url = url.rstrip("/")
    if not url.endswith("/v2/pipeline"):
        url += "/v2/pipeline"
    return url

def _to_turso_arg(val: Any) -> Dict[str, Any]:
    if val is None:
        return {"type": "null"}
    elif isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    elif isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    elif isinstance(val, float):
        return {"type": "float", "value": val}
    else:
        return {"type": "text", "value": str(val)}

def _from_turso_cell(cell: Any) -> Any:
    if not isinstance(cell, dict):
        return cell
    cell_type = cell.get("type")
    val = cell.get("value")
    if cell_type == "null" or val is None:
        return None
    elif cell_type == "integer":
        return int(val)
    elif cell_type == "float":
        return float(val)
    elif cell_type == "text":
        return str(val)
    elif cell_type == "blob":
        return val
    return val

def execute_turso_pipeline(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Executes libSQL statements against the Turso v2 pipeline over HTTP."""
    url = _get_turso_pipeline_url()
    token = Config.TURSO_AUTH_TOKEN
    if not url or not token:
        raise RuntimeError("Turso credentials not configured.")

    body = json.dumps({"requests": requests + [{"type": "close"}]}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=12.0) as resp:
        resp_data = json.loads(resp.read().decode("utf-8"))

    results = resp_data.get("results", [])
    parsed_results = []
    for r in results:
        if r.get("type") == "error":
            err = r.get("error", {})
            raise RuntimeError(f"Turso query error: {err.get('message', 'unknown error')}")
        elif r.get("type") == "ok":
            response = r.get("response", {})
            if response.get("type") == "execute":
                res = response.get("result", {})
                cols = [c["name"] for c in res.get("cols", [])]
                raw_rows = res.get("rows", [])
                rows = []
                for raw_row in raw_rows:
                    row_dict = {}
                    for col_name, cell in zip(cols, raw_row):
                        row_dict[col_name] = _from_turso_cell(cell)
                    rows.append(row_dict)
                parsed_results.append({
                    "rows": rows,
                    "affected_row_count": res.get("affected_row_count", 0),
                    "last_insert_rowid": int(res.get("last_insert_rowid") or 0)
                })
            else:
                parsed_results.append({"rows": [], "affected_row_count": 0, "last_insert_rowid": 0})
    return parsed_results

def turso_query(sql: str, params: Optional[Sequence[Any]] = None, _retry_on_missing_table: bool = True) -> List[Dict[str, Any]]:
    stmt: Dict[str, Any] = {"sql": sql}
    if params:
        stmt["args"] = [_to_turso_arg(p) for p in params]
    try:
        res = execute_turso_pipeline([{"type": "execute", "stmt": stmt}])
        return res[0]["rows"] if res else []
    except RuntimeError as e:
        if _retry_on_missing_table and "no such table" in str(e).lower():
            logger.warning("Turso table missing during query; attempting idempotent schema initialization.")
            init_db(None)
            return turso_query(sql, params, _retry_on_missing_table=False)
        raise

def turso_execute(sql: str, params: Optional[Sequence[Any]] = None, _retry_on_missing_table: bool = True) -> Tuple[int, int]:
    stmt: Dict[str, Any] = {"sql": sql}
    if params:
        stmt["args"] = [_to_turso_arg(p) for p in params]
    try:
        res = execute_turso_pipeline([{"type": "execute", "stmt": stmt}])
        if res:
            return res[0]["last_insert_rowid"], res[0]["affected_row_count"]
        return 0, 0
    except RuntimeError as e:
        if _retry_on_missing_table and "no such table" in str(e).lower():
            logger.warning("Turso table missing during execute; attempting idempotent schema initialization.")
            init_db(None)
            return turso_execute(sql, params, _retry_on_missing_table=False)
        raise

# ----------------- Local SQLite Database Connection -----------------

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
    if is_turso_active(db_path):
        statements = [
            """
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                temperature_c REAL NOT NULL,
                pressure_hpa REAL,
                source TEXT NOT NULL,
                validity_status TEXT NOT NULL,
                humidity_pct REAL,
                heat_index_c REAL,
                latitude REAL,
                longitude REAL,
                sensor_type TEXT DEFAULT 'bmp280'
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_readings_source ON readings(source);",
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                measured_value REAL NOT NULL,
                threshold_value REAL NOT NULL,
                status TEXT NOT NULL,
                acknowledged_at TEXT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);",
            "CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);",
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                temperature_threshold_c REAL NOT NULL DEFAULT 35.0,
                sampling_interval_seconds INTEGER NOT NULL DEFAULT 10
            );
            """
        ]
        requests = [{"type": "execute", "stmt": {"sql": s}} for s in statements]
        execute_turso_pipeline(requests)

        # Check settings row
        rows = turso_query("SELECT id FROM settings WHERE id = 1;")
        if not rows:
            turso_execute(
                "INSERT INTO settings (id, temperature_threshold_c, sampling_interval_seconds) VALUES (1, ?, ?);",
                (Config.DEFAULT_TEMPERATURE_THRESHOLD_C, Config.SAMPLING_INTERVAL_SECONDS)
            )
        return

    conn = get_connection(db_path)
    try:
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    temperature_c REAL NOT NULL,
                    pressure_hpa REAL,
                    source TEXT NOT NULL,
                    validity_status TEXT NOT NULL,
                    humidity_pct REAL,
                    heat_index_c REAL,
                    latitude REAL,
                    longitude REAL,
                    sensor_type TEXT DEFAULT 'bmp280'
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

            # Auto-migrate existing databases to add new columns if missing
            cursor.execute("PRAGMA table_info(readings);")
            cols_info = {row["name"]: dict(row) for row in cursor.fetchall()}

            # If existing table has NOT NULL constraint on pressure_hpa, migrate to make it nullable for DHT11
            if cols_info.get("pressure_hpa", {}).get("notnull") == 1:
                cursor.execute("""
                    CREATE TABLE readings_mig_tmp (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        temperature_c REAL NOT NULL,
                        pressure_hpa REAL,
                        source TEXT NOT NULL,
                        validity_status TEXT NOT NULL,
                        humidity_pct REAL,
                        heat_index_c REAL,
                        latitude REAL,
                        longitude REAL,
                        sensor_type TEXT DEFAULT 'bmp280'
                    );
                """)
                col_names = [c for c in ("id", "timestamp", "temperature_c", "pressure_hpa", "source", "validity_status", "humidity_pct", "heat_index_c", "latitude", "longitude", "sensor_type") if c in cols_info]
                cols_str = ", ".join(col_names)
                cursor.execute(f"INSERT INTO readings_mig_tmp ({cols_str}) SELECT {cols_str} FROM readings;")
                cursor.execute("DROP TABLE readings;")
                cursor.execute("ALTER TABLE readings_mig_tmp RENAME TO readings;")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_readings_source ON readings(source);")
                cursor.execute("PRAGMA table_info(readings);")
                cols_info = {row["name"]: dict(row) for row in cursor.fetchall()}

            for col_name, col_type in [("humidity_pct", "REAL"), ("heat_index_c", "REAL"), ("latitude", "REAL"), ("longitude", "REAL"), ("sensor_type", "TEXT")]:
                if col_name not in cols_info:
                    cursor.execute(f"ALTER TABLE readings ADD COLUMN {col_name} {col_type};")
    finally:
        conn.close()

def insert_reading(
    temperature_c: float,
    pressure_hpa: Optional[float] = None,
    source: str = "hardware",
    validity_status: str = "valid",
    timestamp: Optional[str] = None,
    humidity_pct: Optional[float] = None,
    heat_index_c: Optional[float] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    sensor_type: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """Inserts a new sensor reading into the database."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    # Automatically compute heat index via NOAA Rothfusz formula if humidity is provided and heat index not pre-computed
    if heat_index_c is None and humidity_pct is not None:
        try:
            from weather_service import WeatherService
            heat_index_c = WeatherService.compute_heat_index(temperature_c, humidity_pct)
        except Exception:
            heat_index_c = None

    press_val = round(pressure_hpa, 2) if pressure_hpa is not None else None
    hum_val = round(humidity_pct, 1) if humidity_pct is not None else None
    hi_val = round(heat_index_c, 1) if heat_index_c is not None else None
    lat_val = round(latitude, 6) if latitude is not None else None
    lon_val = round(longitude, 6) if longitude is not None else None

    if sensor_type is None:
        if source and "dht11" in source.lower():
            sensor_type = "dht11"
        elif press_val is not None:
            sensor_type = "bmp280"
        else:
            sensor_type = "dht11" if hum_val is not None else "generic"

    if is_turso_active(db_path):
        last_id, _ = turso_execute(
            """
            INSERT INTO readings (
                timestamp, temperature_c, pressure_hpa, source, validity_status,
                humidity_pct, heat_index_c, latitude, longitude, sensor_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                timestamp,
                round(temperature_c, 2),
                press_val,
                source,
                validity_status,
                hum_val,
                hi_val,
                lat_val,
                lon_val,
                sensor_type
            )
        )
        return last_id

    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO readings (
                    timestamp, temperature_c, pressure_hpa, source, validity_status,
                    humidity_pct, heat_index_c, latitude, longitude, sensor_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    timestamp,
                    round(temperature_c, 2),
                    press_val,
                    source,
                    validity_status,
                    hum_val,
                    hi_val,
                    lat_val,
                    lon_val,
                    sensor_type
                )
            )
            return cursor.lastrowid
    finally:
        conn.close()

def get_latest_reading(db_path: Optional[str] = None, real_only: bool = False) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent reading from the database."""
    where_sql = "WHERE source NOT IN ('demo', 'simulated')" if real_only else ""

    if is_turso_active(db_path):
        rows = turso_query(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY id DESC
            LIMIT 1;
            """
        )
        return rows[0] if rows else None

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY id DESC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_latest_dht11_reading(db_path: Optional[str] = None, real_only: bool = False) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent DHT11 reading (temperature & humidity from Raspberry Pi/Arduino)."""
    base = "sensor_type = 'dht11' OR source LIKE '%dht11%' OR (humidity_pct IS NOT NULL AND pressure_hpa IS NULL)"
    where_sql = f"WHERE ({base}) AND source NOT IN ('demo', 'simulated')" if real_only else f"WHERE {base}"

    if is_turso_active(db_path):
        rows = turso_query(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY id DESC
            LIMIT 1;
            """
        )
        return rows[0] if rows else None

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY id DESC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_latest_bmp280_reading(db_path: Optional[str] = None, real_only: bool = False) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent BMP280 reading (ambient temperature & barometric pressure)."""
    base = "sensor_type IN ('bmp280', 'bme280') OR pressure_hpa IS NOT NULL"
    where_sql = f"WHERE ({base}) AND source NOT IN ('demo', 'simulated')" if real_only else f"WHERE {base}"

    if is_turso_active(db_path):
        rows = turso_query(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY id DESC
            LIMIT 1;
            """
        )
        return rows[0] if rows else None

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY id DESC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_recent_readings(limit: int = 20, db_path: Optional[str] = None, real_only: bool = False) -> List[Dict[str, Any]]:
    """Retrieves the latest N readings."""
    where_sql = "WHERE source NOT IN ('demo', 'simulated')" if real_only else ""

    if is_turso_active(db_path):
        return turso_query(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,)
        )

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
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

def get_readings_range(range_code: str = "24h", db_path: Optional[str] = None, real_only: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieves chronological readings within a standard time range for charting.
    Only returns valid readings.
    """
    cutoff = parse_range_to_cutoff(range_code).isoformat()
    extra_filter = "AND source NOT IN ('demo', 'simulated')" if real_only else ""

    if is_turso_active(db_path):
        return turso_query(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            WHERE timestamp >= ? AND validity_status = 'valid' {extra_filter}
            ORDER BY timestamp ASC;
            """,
            (cutoff,)
        )

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            WHERE timestamp >= ? AND validity_status = 'valid' {extra_filter}
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
    db_path: Optional[str] = None,
    real_only: bool = False
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated historical readings with optional date boundaries."""
    clauses = []
    params = []

    if start_iso:
        clauses.append("timestamp >= ?")
        params.append(start_iso)
    if end_iso:
        clauses.append("timestamp <= ?")
        params.append(end_iso)
    if real_only:
        clauses.append("source NOT IN ('demo', 'simulated')")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    offset = max(0, (page - 1) * limit)

    if is_turso_active(db_path):
        count_rows = turso_query(f"SELECT COUNT(*) as total FROM readings {where_sql};", params)
        total = count_rows[0]["total"] if count_rows else 0

        query_params = list(params) + [limit, offset]
        readings = turso_query(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?;
            """,
            query_params
        )
        return readings, total

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) as total FROM readings {where_sql};", params)
        total = cursor.fetchone()["total"]

        query_params = list(params) + [limit, offset]
        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
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
    db_path: Optional[str] = None,
    real_only: bool = False
) -> List[Dict[str, Any]]:
    """Retrieves readings matching the filter for CSV export."""
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

    if real_only:
        clauses.append("source NOT IN ('demo', 'simulated')")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    if is_turso_active(db_path):
        return turso_query(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY timestamp ASC;
            """,
            params
        )

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, timestamp, temperature_c, pressure_hpa, source, validity_status,
                   humidity_pct, heat_index_c, latitude, longitude, sensor_type
            FROM readings
            {where_sql}
            ORDER BY timestamp ASC;
            """,
            params
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_today_stats(db_path: Optional[str] = None, real_only: bool = False) -> Dict[str, Any]:
    """Calculates summary statistics for readings collected today (UTC)."""
    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    extra_filter = "AND source NOT IN ('demo', 'simulated')" if real_only else ""

    query_sql = f"""
        SELECT 
            COUNT(*) as count,
            MIN(temperature_c) as min_temp,
            MAX(temperature_c) as max_temp,
            AVG(temperature_c) as avg_temp,
            MIN(pressure_hpa) as min_pressure,
            MAX(pressure_hpa) as max_pressure,
            AVG(pressure_hpa) as avg_pressure,
            MIN(humidity_pct) as min_humidity,
            MAX(humidity_pct) as max_humidity,
            AVG(humidity_pct) as avg_humidity,
            MAX(heat_index_c) as max_heat_index,
            MAX(timestamp) as last_collection_time
        FROM readings
        WHERE timestamp >= ? AND validity_status = 'valid' {extra_filter};
    """

    if is_turso_active(db_path):
        rows = turso_query(query_sql, (today_start,))
        row = rows[0] if rows else None
        if row and row.get("count", 0) > 0:
            return {
                "count": row["count"],
                "min_temp": round(row["min_temp"], 2) if row["min_temp"] is not None else None,
                "max_temp": round(row["max_temp"], 2) if row["max_temp"] is not None else None,
                "avg_temp": round(row["avg_temp"], 2) if row["avg_temp"] is not None else None,
                "min_pressure": round(row["min_pressure"], 2) if row["min_pressure"] is not None else None,
                "max_pressure": round(row["max_pressure"], 2) if row["max_pressure"] is not None else None,
                "avg_pressure": round(row["avg_pressure"], 2) if row["avg_pressure"] is not None else None,
                "min_humidity": round(row["min_humidity"], 1) if row["min_humidity"] is not None else None,
                "max_humidity": round(row["max_humidity"], 1) if row["max_humidity"] is not None else None,
                "avg_humidity": round(row["avg_humidity"], 1) if row["avg_humidity"] is not None else None,
                "max_heat_index": round(row["max_heat_index"], 1) if row["max_heat_index"] is not None else None,
                "last_collection_time": row["last_collection_time"]
            }
        return {
            "count": 0, "min_temp": None, "max_temp": None, "avg_temp": None,
            "min_pressure": None, "max_pressure": None, "avg_pressure": None,
            "min_humidity": None, "max_humidity": None, "avg_humidity": None,
            "max_heat_index": None, "last_collection_time": None
        }

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query_sql, (today_start,))
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
                "min_humidity": round(row["min_humidity"], 1) if row["min_humidity"] is not None else None,
                "max_humidity": round(row["max_humidity"], 1) if row["max_humidity"] is not None else None,
                "avg_humidity": round(row["avg_humidity"], 1) if row["avg_humidity"] is not None else None,
                "max_heat_index": round(row["max_heat_index"], 1) if row["max_heat_index"] is not None else None,
                "last_collection_time": row["last_collection_time"]
            }
        return {
            "count": 0, "min_temp": None, "max_temp": None, "avg_temp": None,
            "min_pressure": None, "max_pressure": None, "avg_pressure": None,
            "min_humidity": None, "max_humidity": None, "avg_humidity": None,
            "max_heat_index": None, "last_collection_time": None
        }
    finally:
        conn.close()

# ----------------- Alerts Operations -----------------

def get_alerts(status_filter: Optional[str] = None, limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves list of alerts with optional status filter ('active', 'acknowledged', 'resolved')."""
    if status_filter and status_filter.lower() != "all":
        query_sql = """
            SELECT id, timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at
            FROM alerts
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ?;
        """
        params: Tuple[Any, ...] = (status_filter.lower(), limit)
    else:
        query_sql = """
            SELECT id, timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at
            FROM alerts
            ORDER BY id DESC
            LIMIT ?;
        """
        params = (limit,)

    if is_turso_active(db_path):
        return turso_query(query_sql, params)

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query_sql, params)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            logger.warning("Alerts table missing during get_alerts; auto-initializing schema.")
            init_db(db_path)
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            return [dict(row) for row in cursor.fetchall()]
        raise
    finally:
        conn.close()

def get_active_alert(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the current ongoing active alert, if any."""
    query_sql = """
        SELECT id, timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at
        FROM alerts
        WHERE status = 'active'
        ORDER BY id DESC
        LIMIT 1;
    """
    if is_turso_active(db_path):
        rows = turso_query(query_sql)
        return rows[0] if rows else None

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query_sql)
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            logger.warning("Alerts table missing during get_active_alert; auto-initializing schema.")
            init_db(db_path)
            cursor = conn.cursor()
            cursor.execute(query_sql)
            row = cursor.fetchone()
            return dict(row) if row else None
        raise
    finally:
        conn.close()

def get_ongoing_alert(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent ongoing alert (either active or acknowledged), if any."""
    query_sql = """
        SELECT id, timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at
        FROM alerts
        WHERE status IN ('active', 'acknowledged')
        ORDER BY id DESC
        LIMIT 1;
    """
    if is_turso_active(db_path):
        rows = turso_query(query_sql)
        return rows[0] if rows else None

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query_sql)
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            logger.warning("Alerts table missing during get_ongoing_alert; auto-initializing schema.")
            init_db(db_path)
            cursor = conn.cursor()
            cursor.execute(query_sql)
            row = cursor.fetchone()
            return dict(row) if row else None
        raise
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
    query_sql = """
        INSERT INTO alerts (timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at)
        VALUES (?, ?, ?, ?, 'active', NULL);
    """
    params = (timestamp, alert_type, round(measured_value, 2), round(threshold_value, 2))

    if is_turso_active(db_path):
        last_id, _ = turso_execute(query_sql, params)
        return last_id

    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            return cursor.lastrowid
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            logger.warning("Alerts table missing during create_alert; auto-initializing schema.")
            init_db(db_path)
            with conn:
                cursor = conn.cursor()
                cursor.execute(query_sql, params)
                return cursor.lastrowid
        raise
    finally:
        conn.close()

def acknowledge_alert(alert_id: int, db_path: Optional[str] = None) -> bool:
    """Marks an alert as acknowledged."""
    ack_time = datetime.now(timezone.utc).isoformat()
    query_sql = """
        UPDATE alerts
        SET status = 'acknowledged', acknowledged_at = ?
        WHERE id = ? AND status = 'active';
    """
    params = (ack_time, alert_id)

    if is_turso_active(db_path):
        _, affected = turso_execute(query_sql, params)
        return affected > 0

    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            return cursor.rowcount > 0
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            logger.warning("Alerts table missing during acknowledge_alert; auto-initializing schema.")
            init_db(db_path)
            with conn:
                cursor = conn.cursor()
                cursor.execute(query_sql, params)
                return cursor.rowcount > 0
        raise
    finally:
        conn.close()

def resolve_active_alerts(db_path: Optional[str] = None) -> int:
    """Marks any active alerts as resolved when temperature returns to safe zone."""
    query_sql = """
        UPDATE alerts
        SET status = 'resolved'
        WHERE status IN ('active', 'acknowledged');
    """
    if is_turso_active(db_path):
        _, affected = turso_execute(query_sql)
        return affected

    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(query_sql)
            return cursor.rowcount
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            logger.warning("Alerts table missing during resolve_active_alerts; auto-initializing schema.")
            init_db(db_path)
            with conn:
                cursor = conn.cursor()
                cursor.execute(query_sql)
                return cursor.rowcount
        raise
    finally:
        conn.close()

# ----------------- Settings Operations -----------------

def get_settings(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves current application settings."""
    query_sql = """
        SELECT temperature_threshold_c, sampling_interval_seconds
        FROM settings
        WHERE id = 1;
    """
    if is_turso_active(db_path):
        rows = turso_query(query_sql)
        if rows:
            return rows[0]
        return {
            "temperature_threshold_c": Config.DEFAULT_TEMPERATURE_THRESHOLD_C,
            "sampling_interval_seconds": Config.SAMPLING_INTERVAL_SECONDS
        }

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query_sql)
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {
            "temperature_threshold_c": Config.DEFAULT_TEMPERATURE_THRESHOLD_C,
            "sampling_interval_seconds": Config.SAMPLING_INTERVAL_SECONDS
        }
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            logger.warning("Settings table missing during get_settings; auto-initializing schema.")
            init_db(db_path)
            cursor = conn.cursor()
            cursor.execute(query_sql)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {
                "temperature_threshold_c": Config.DEFAULT_TEMPERATURE_THRESHOLD_C,
                "sampling_interval_seconds": Config.SAMPLING_INTERVAL_SECONDS
            }
        raise
    finally:
        conn.close()

def update_temperature_threshold(threshold_c: float, db_path: Optional[str] = None) -> bool:
    """Updates the temperature alert threshold in Celsius."""
    query_sql = """
        UPDATE settings
        SET temperature_threshold_c = ?
        WHERE id = 1;
    """
    params = (round(threshold_c, 2),)

    if is_turso_active(db_path):
        _, affected = turso_execute(query_sql, params)
        return affected > 0

    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            return cursor.rowcount > 0
    finally:
        conn.close()

def update_sampling_interval(interval_seconds: int, db_path: Optional[str] = None) -> bool:
    """Updates the sensor sampling interval."""
    query_sql = """
        UPDATE settings
        SET sampling_interval_seconds = ?
        WHERE id = 1;
    """
    params = (interval_seconds,)

    if is_turso_active(db_path):
        _, affected = turso_execute(query_sql, params)
        return affected > 0

    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            return cursor.rowcount > 0
    finally:
        conn.close()

def get_db_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Returns database size, record counts, and health status."""
    storage_backend = Config.get_storage_backend()
    is_persistent = Config.is_storage_persistent()
    persistence_notice = Config.get_persistence_notice()

    if is_turso_active(db_path):
        readings_rows = turso_query("SELECT COUNT(*) as count FROM readings;")
        readings_count = readings_rows[0]["count"] if readings_rows else 0
        alerts_rows = turso_query("SELECT COUNT(*) as count FROM alerts;")
        alerts_count = alerts_rows[0]["count"] if alerts_rows else 0
        dht11_rows = turso_query("SELECT COUNT(*) as count FROM readings WHERE sensor_type = 'dht11' OR source LIKE '%dht11%';")
        dht11_count = dht11_rows[0]["count"] if dht11_rows else 0

        return {
            "file_size_bytes": 0,
            "file_size_kb": 0.0,
            "readings_count": readings_count,
            "dht11_readings_count": dht11_count,
            "alerts_count": alerts_count,
            "status": "healthy",
            "storage_backend": "turso",
            "is_persistent": True,
            "persistence_notice": None
        }

    path = db_path or Config.DATABASE_PATH
    file_size_bytes = os.path.getsize(path) if os.path.exists(path) else 0
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM readings;")
        readings_count = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM alerts;")
        alerts_count = cursor.fetchone()["count"]

        # Count DHT11 readings
        dht11_count = 0
        try:
            cursor.execute("SELECT COUNT(*) as count FROM readings WHERE sensor_type = 'dht11' OR source LIKE '%dht11%';")
            dht11_count = cursor.fetchone()["count"]
        except Exception:
            pass

        return {
            "file_size_bytes": file_size_bytes,
            "file_size_kb": round(file_size_bytes / 1024, 2),
            "readings_count": readings_count,
            "dht11_readings_count": dht11_count,
            "alerts_count": alerts_count,
            "status": "healthy",
            "storage_backend": storage_backend,
            "is_persistent": is_persistent,
            "persistence_notice": persistence_notice
        }
    finally:
        conn.close()
