# Virtual Atmosphere REST API Specification

All API endpoints return JSON data with standard HTTP status codes, unless specified otherwise (e.g. CSV exports).

---

## 1. System & Sensor Status
### `GET /api/status`
Returns real-time diagnostics of the sensor connection, active alerts, database storage health, and runtime mode.

**Response (200 OK):**
```json
{
  "status": "online",
  "version": "1.0.0",
  "sensor": {
    "mode": "live",
    "is_connected": true,
    "sensor_type": "BMP280",
    "bus": 1,
    "address": "0x76",
    "last_reading_time": "2026-10-22T14:45:00.123456Z",
    "data_freshness_seconds": 3.2,
    "consecutive_errors": 0,
    "last_error": null,
    "server_time": "2026-10-22T14:45:03.323456Z"
  },
  "alert": {
    "has_active_alert": false,
    "active_alert": null,
    "threshold_c": 35.0,
    "disclaimer": "Configurable temperature warning for school and educational project monitoring..."
  },
  "database": {
    "status": "healthy",
    "file_size_kb": 64.0,
    "readings_count": 288,
    "alerts_count": 0
  }
}
```

---

## 2. Latest Sensor Reading
### `GET /api/readings/latest`
Returns the most recent single reading, delta trend relative to the previous sample, and aggregated statistics for today.

**Response (200 OK):**
```json
{
  "latest": {
    "id": 288,
    "timestamp": "2026-10-22T14:45:00Z",
    "temperature_c": 24.85,
    "pressure_hpa": 1013.42,
    "source": "hardware",
    "validity_status": "valid"
  },
  "previous": {
    "id": 287,
    "temperature_c": 24.81,
    "pressure_hpa": 1013.40
  },
  "trend": {
    "temperature_delta_c": 0.04,
    "pressure_delta_hpa": 0.02
  },
  "today_stats": {
    "count": 288,
    "min_temp": 20.35,
    "max_temp": 28.40,
    "avg_temp": 24.12,
    "min_pressure": 1011.80,
    "max_pressure": 1014.95,
    "avg_pressure": 1013.30,
    "last_collection_time": "2026-10-22T14:45:00Z"
  }
}
```

---

## 3. Chart Time Series Data
### `GET /api/readings`
Returns chronological readings for Chart.js visualization.

**Query Parameters:**
- `range`: Time range code (`1h`, `6h`, `24h` [default], `7d`, `30d`).

**Response (200 OK):**
```json
{
  "readings": [
    {
      "id": 1,
      "timestamp": "2026-10-22T00:00:00Z",
      "temperature_c": 21.2,
      "pressure_hpa": 1012.8,
      "source": "hardware",
      "validity_status": "valid"
    }
  ],
  "summary": {
    "count": 144,
    "range": "24h",
    "temp_min": 20.1,
    "temp_max": 28.5,
    "temp_avg": 24.3,
    "press_min": 1011.5,
    "press_max": 1015.0,
    "press_avg": 1013.2
  }
}
```

---

## 4. Paginated Readings History
### `GET /api/readings/history`
Returns paginated reading records with optional start/end date filtering.

**Query Parameters:**
- `start`: ISO 8601 string (e.g. `2026-10-22T00:00:00Z`)
- `end`: ISO 8601 string (e.g. `2026-10-22T23:59:59Z`)
- `page`: Page index (default: 1)
- `limit`: Number of items per page (default: 25, max: 100)

**Response (200 OK):**
```json
{
  "readings": [...],
  "total": 540,
  "page": 1,
  "limit": 25,
  "total_pages": 22,
  "has_next": true,
  "has_prev": false
}
```

---

## 5. CSV Data Export
### `GET /api/readings/export.csv`
Streams a comma-separated values (CSV) file of measurements.

**Query Parameters:**
- `range`: `1h`, `6h`, `24h`, `7d`, or `all`
- `start`: Optional ISO timestamp
- `end`: Optional ISO timestamp

**Response Headers:**
```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename=virtual_atmosphere_readings_20261022_144500.csv
```

---

## 6. Alerts & Acknowledgment
### `GET /api/alerts`
Returns logged threshold events.

**Query Parameters:**
- `status`: `all` (default), `active`, `acknowledged`, `resolved`
- `limit`: max results (default: 50)

### `POST /api/alerts/<id>/acknowledge`
Marks an active alert event as acknowledged by the operator.

**Response (200 OK):**
```json
{
  "success": true,
  "alert_id": 12,
  "message": "Alert #12 acknowledged successfully."
}
```

---

## 7. Application Configuration
### `GET /api/settings`
Returns active settings and operational parameters.

### `POST /api/settings/threshold`
Updates the temperature alert threshold in Celsius.

**Request Body:**
```json
{
  "threshold_c": 36.5
}
```

### `POST /api/settings/sampling_interval`
Updates the sensor polling interval in seconds (2 to 3600 seconds).

**Request Body:**
```json
{
  "interval_seconds": 15
}
```

### `POST /api/mode`
Switches runtime mode between `demo` and `live`.

**Request Body:**
```json
{
  "mode": "live"
}
```

---

## 8. Ingestion Endpoints (Raspberry Pi & Sensors)

### `POST /api/ingest/dht11`
Dedicated secure ingestion endpoint for Raspberry Pi receiving DHT11 temperature & relative humidity readings from an Arduino Mega 2560.

**Authentication:**
- Header: `Authorization: Bearer <VA_DHT11_INGEST_KEY>` (or `VA_INGEST_KEY`)
- Protected against timing attacks via `hmac.compare_digest`.
- In production/live environments, fails closed with HTTP 401 if unconfigured or matching known placeholders.

**Request Headers:**
```http
POST /api/ingest/dht11 HTTP/1.1
Host: va.developerhut.in
Authorization: Bearer <YOUR_SECRET_TOKEN>
Content-Type: application/json
```

**Request Body (JSON):**
```json
{
  "temperature_c": 33.0,
  "humidity_percent": 46.0,
  "timestamp": "2026-10-29T10:20:00Z",
  "source": "raspberry_pi_dht11"
}
```

**Field Specifications:**
| Field | Type | Required | Description / Valid Bounds |
| :--- | :--- | :--- | :--- |
| `temperature_c` | Float | **Yes** | Ambient temperature in Celsius (-20.0°C to 60.0°C) |
| `humidity_percent` | Float | **Yes** | Relative humidity in percentage (0.0% to 100.0%) |
| `timestamp` | String | No | ISO 8601 UTC timestamp (defaults to current server time) |
| `source` | String | No | Attribution identifier (default: `"dht11"`, max 64 chars) |

**Response (201 Created):**
```json
{
  "status": "success",
  "id": 142,
  "temperature_c": 33.0,
  "humidity_percent": 46.0,
  "heat_index_c": 38.2,
  "timestamp": "2026-10-29T10:20:00Z",
  "source": "raspberry_pi_dht11",
  "heat_risk": {
    "heat_index_c": 38.2,
    "category": "Extreme Caution",
    "badge_class": "warning",
    "advisory": "Heat cramps and heat exhaustion possible with continued exposure.",
    "formula_basis": "NOAA / NWS Rothfusz 9-parameter polynomial regression.",
    "is_applicable": true,
    "is_simulated": false
  }
}
```

**Error Responses:**
- `400 Bad Request`: Missing required fields, non-numeric data, `NaN`/`Infinity`, or out-of-range sensor readings.
- `401 Unauthorized`: Missing or malformed `Authorization` header, unconfigured server secret, or invalid bearer token.
- `429 Too Many Requests`: Client IP exceeded the sliding-window ingestion rate limit (default 60 req/min).

---

### `POST /api/telemetry`
General multi-sensor ingestion endpoint supporting BMP280, BME280, and GPS coordinates.

**Authentication:**
- Header: `Authorization: Bearer <VA_INGEST_KEY>`

**Request Body (JSON):**
```json
{
  "temperature_c": 24.5,
  "pressure_hpa": 1013.25,
  "humidity_pct": 55.0,
  "latitude": 12.9716,
  "longitude": 77.5946,
  "source": "hardware"
}
```

**Response (201 Created):**
```json
{
  "status": "success",
  "id": 143,
  "temperature_c": 24.5,
  "pressure_hpa": 1013.25,
  "humidity_pct": 55.0,
  "heat_index_c": null,
  "source": "hardware",
  "heat_risk": {
    "category": "Normal",
    "is_applicable": false
  }
}
```
