# VA | Virtual Atmosphere
> **Understand Your Atmosphere.**

A student-built atmospheric monitoring project powered by **Python Flask**, **SQLite**, and **Chart.js**, designed for direct I²C connection to a **Bosch GY-BMP280** sensor on a **Raspberry Pi 3 Model B+**.

🌐 **Live Production Dashboard:** [https://va.developerhut.in/dashboard](https://va.developerhut.in/dashboard)

---

## 1. Project Overview & Objectives

**Virtual Atmosphere (VA)** is an educational, student-built atmospheric monitoring platform developed to provide continuous environmental observation of localized microclimates (classrooms, computer labs, server rooms, and campus grounds).

### Problem Statement
Standard consumer weather applications rely on airport radar stations tens of kilometers away, completely missing indoor thermal buildups, microclimate heat anomalies, and localized barometric fluctuations. Additionally, existing educational IoT projects frequently depend on brittle intermediate microcontrollers (ESP32) or proprietary subscription clouds.

### Objectives & Expected Outcomes
- **Autonomous Local Telemetry:** Sample and log real-time ambient temperature and atmospheric pressure directly via hardware I²C bus 1.
- **Edge Storage (Zero Cloud Lock-in):** Store persistent time-series records in an indexed SQLite database using Write-Ahead Logging (WAL).
- **Safety Threshold Warnings:** Detect thermal violations with configurable thresholds, operator acknowledgment, deduplication, and hysteresis recovery.
- **Accessible Multi-Device Visualization:** Render responsive scientific charts and telemetry cards accessible from any phone, tablet, or laptop on the local school network.
- **Transparent Scientific Data:** Export genuine environmental readings to CSV for student STEM analysis, strictly avoiding synthetic or fabricated metrics.

---

## 2. Project Team (Meet the Team)

| Member | Role | Primary Responsibilities |
| :--- | :--- | :--- |
| **Vasu** | **Team Lead** | Project coordination, system architecture, software development, full-stack integration, and system testing. |
| **Thakshanamoorthi S** | **Project Team Member** | Assist with project development, hardware setup, I²C sensor wiring, reliability testing, and project documentation. |
| **Nithilan** | **Project Team Member** | Assist with sensor experiments, atmospheric data validation, threshold verification testing, and project presentation. |

*Note: Member responsibilities represent primary focus areas and can be adapted as project tasks evolve.*

---

## 3. System Architecture & Data Flow

```text
+---------------------+     I2C Bus 1      +------------------------+
| GY-BMP280 Sensor    | -----------------> | Raspberry Pi 3B+       |
| (Raw Temp/Pressure) |   (SDA/SCL 3.3V)   | (Quad-Core Host OS)    |
+---------------------+                    +------------------------+
                                                       |
                                                       v
+---------------------+     SQL Commits    +------------------------+
| SQLite Database     | <----------------- | Python Sensor Service  |
| (WAL Mode Storage)  |                    | (Poller & Bosch Comp.) |
+---------------------+                    +------------------------+
           |                                           |
           v                                           v
+-------------------------------------------------------------------+
| Flask Backend Web Service                                         |
| (REST APIs, Alert Logic, Hysteresis, Template Engine)             |
+-------------------------------------------------------------------+
                                   |
                                   v
+-------------------------------------------------------------------+
| VA Dashboard UI                                                   |
| (Responsive Dark Interface, Chart.js Visualizations, Mobile Nav)  |
+-------------------------------------------------------------------+
```

### Component Breakdown
1. **GY-BMP280 Sensor:** Precision piezoresistive transducer reading ambient temperature and barometric pressure.
2. **I²C Interface:** Two-wire synchronous serial communication bus (SDA/SCL) transmitting digital data at 3.3V logic levels.
3. **Raspberry Pi 3 Model B+:** Embedded Linux host computer managing hardware peripherals, system services, and local networking.
4. **Python Sensor Service:** Background daemon worker polling registers, computing polynomial compensation, and validating physical bounds.
5. **Flask Backend:** Lightweight web application serving REST endpoints, computing statistics, and managing threshold alert lifecycles.
6. **SQLite Database:** Local, zero-configuration database engine storing indexed historical readings and alert event logs.
7. **VA Dashboard:** Client-side interface rendering real-time telemetry cards, Chart.js time-series trends, and historical query tables.

---

## 4. Brief Project Workflow

1. **Step 1: Sensor Setup** — Connect the GY-BMP280 sensor to the Raspberry Pi 3 Model B+ 40-pin GPIO header using the hardware I²C interface.
2. **Step 2: Data Collection** — Python communicates with the sensor via `/dev/i2c-1` and polls raw temperature and pressure registers.
3. **Step 3: Data Processing** — Apply Bosch compensation formulas, validate readings (-40°C to 85°C, 300 to 1100 hPa), and attach UTC timestamps.
4. **Step 4: Data Storage** — Commit validated measurements to the local SQLite database using Write-Ahead Logging (WAL) and parameterized queries.
5. **Step 5: Backend Processing** — Flask REST APIs serve telemetry, compute statistics, and evaluate threshold alerts with deduplication and hysteresis recovery.
6. **Step 6: Dashboard Visualization** — Display readings, Chart.js time-series trend lines, recent measurements, and system status on a responsive dark UI.
7. **Step 7: Testing and Deployment** — Run automated test suites, verify failover without hardware, configure systemd startup services, and deploy for local LAN and web access.

---

## 5. Hardware and Software Specifications

### Hardware
- **Host Computer:** Raspberry Pi 3 Model B+ (Broadcom BCM2837B0, quad-core Cortex-A53 @ 1.4GHz, 1GB LPDDR2 RAM)
- **Sensor Module:** GY-BMP280 Barometric Pressure & Temperature Breakout (Bosch Sensortec)
- **Power Supply:** 5.0V / 2.5A micro-USB power adapter with stable voltage regulation
- **I²C Connections:** Female-to-female Dupont jumper wires (3.3V, GND, SDA on GPIO2, SCL on GPIO3)

### Software
- **Language & Runtime:** Python 3.9+ with virtual environment isolation (`.venv`)
- **Backend Framework:** Flask 3.x WSGI framework with factory pattern and canonical REST endpoints
- **Database Engine:** SQLite 3 with Write-Ahead Logging (WAL) and indexed time-series queries
- **Sensor Driver:** Python `smbus2` direct I²C register driver with fallback simulation engine
- **Frontend Interface:** HTML5, custom responsive CSS3 design system, Bootstrap 5 grid, Chart.js v4.4
- **Process Manager:** Linux `systemd` background service for autostart on Raspberry Pi boot

---

## 6. Sensor Wiring & Pinout Reference

| GY-BMP280 Pin | Raspberry Pi Pin | Physical Header Pin | Function |
| :--- | :--- | :--- | :--- |
| **VCC / VIN** | 3.3V Power | **Physical Pin 1** | +3.3V DC Supply |
| **GND** | Ground | **Physical Pin 6** | Common Ground (0V) |
| **SDA** | GPIO 2 (SDA1) | **Physical Pin 3** | I²C Serial Data |
| **SCL** | GPIO 3 (SCL1) | **Physical Pin 5** | I²C Serial Clock |

> [!CAUTION]
> Always power the GY-BMP280 from **Physical Pin 1 (3.3V)**. Connecting to 5V (Pin 2 or 4) will permanently damage the 3.3V sensor!

---

## 7. Hyperlocal Weather & Heat-Risk Intelligence

### NOAA / NWS Rothfusz Heat Index Algorithm
Virtual Atmosphere implements the official National Oceanic and Atmospheric Administration (NOAA) / National Weather Service (NWS) Rothfusz regression algorithm ([`weather_service.py`](weather_service.py)):

$$\text{HI} = -42.379 + 2.04901523 T + 10.14333127 R - 0.22475541 T R - 0.00683783 T^2 - 0.05481717 R^2 + 0.00122874 T^2 R + 0.00085282 T R^2 - 0.00000199 T^2 R^2$$

*(where $T$ is temperature in °F and $R$ is relative humidity in %)*

#### Strict Scientific Criteria & Honesty Rules
1. **Applicability Threshold:** Heat Index is physically applicable only when Temperature $\ge 26.7^\circ\text{C}$ ($80^\circ\text{F}$) and Relative Humidity $\ge 40\%$.
2. **Normal Baseline Comfort:** When ambient temperature is below $26.7^\circ\text{C}$, heat index is clinically not applicable (human perspiration evaporates efficiently). The system transparently reports `Normal` rather than inventing an artificially elevated number.
3. **No Fabrication from Temperature Alone:** A heat index is never calculated without a real relative humidity reading. If a sensor lacks humidity (e.g. BMP280), the system explicitly reports `Incomplete Data` with an advisory note explaining that a hygrometer cell is required.
4. **Thermodynamic Risk Categories:**
   - **Normal (< 26.7°C):** Baseline comfort.
   - **Caution (26.7°C – 32.2°C):** Fatigue possible with prolonged exposure and activity.
   - **Extreme Caution (32.8°C – 39.4°C):** Heat cramps and heat exhaustion possible.
   - **Danger (40.0°C – 51.1°C):** Heat cramps or exhaustion likely; heatstroke possible.
   - **Extreme Danger ($\ge$ 51.7°C):** Heatstroke highly likely; avoid prolonged outdoor exertion.

### Explicit Data Sources & Verification
The system enforces three distinct data source states across all layers:
- **`hardware`**: Readings obtained from actual physical sensors.
- **`simulated`**: Mathematically generated test data modeling diurnal cycles, for testing before hardware arrival.
- **`unavailable`**: Hardware mode expected, but physical sensors are offline or disconnected.

> [!IMPORTANT]
> The dashboard visibly identifies the active source at all times. Simulated test data is never presented as actual physical observations, and disconnected sensors never generate fabricated hardware readings. Historical records with `source="demo"` are maintained with 100% backward compatibility.

---

## 8. Raspberry Pi Hardware Adapters & Remote Ingestion

### Modular Hardware Adapters (`hardware_adapters.py`)
- **Bosch BME280 / BMP280 Driver:** Communicates over I²C bus 1 (addresses `0x76`, `0x77`). Reads register `0xD0` to identify sensor chip ID:
  - `0x60`: BME280 (reads temperature, barometric pressure, and relative humidity).
  - `0x58` / `0x56` / `0x57`: BMP280 (reads temperature and pressure; humidity returns `None`).
- **DHT11 Adapter:** Optional single-wire digital humidity sensor interface via GPIO (BCM pin 4). Disabled by default with protected imports.
- **u-blox NEO-6M GPS Adapter:** Optional UART/Serial interface (`/dev/serial0` at 9600 baud). Parses NMEA `$GPGGA` and `$GPRMC` sentences to extract decimal latitude and longitude. Disabled by default with protected imports.
- **Safety Guarantee:** All hardware modules (`smbus2`, `serial`, `RPi.GPIO`) use conditional imports with `try...except ImportError` so the application never crashes on Windows or Vercel serverless platforms.

### Secure Ingestion Endpoint (`POST /api/telemetry`)
Remote Raspberry Pi stations securely submit telemetry to the Virtual Atmosphere cloud or local instance:
- **Authentication & Fail-Closed Policy:** `Authorization: Bearer <VA_INGEST_KEY>` verified via `hmac.compare_digest` to prevent timing attacks. In production/live mode, ingestion fails closed (HTTP 401) if the key is unconfigured or matches any known placeholder (e.g. `va-secret-ingest-key`, `changeme`).
- **Physical Bounds & Numeric Validation:** Strictly rejects `NaN` and `Infinity`. Validates meteorological limits: Temperature (-40°C to 85°C), barometric pressure (300 to 1100 hPa), humidity (0% to 100%), and GPS coordinates (-90° to 90° lat, -180° to 180° lon).
- **Process-Local Rate Limiting:** Enforces a thread-safe sliding-window rate limit (default 60 submissions per minute per client IP) returning HTTP 429 (`Too Many Requests`) with a `Retry-After` header when exceeded.
  - *Serverless Architectural Note:* On serverless runtimes (such as Vercel), execution containers are ephemeral and process memory is isolated per worker. Process-local rate limiting protects individual worker processes from burst floods; true distributed rate limiting across concurrent serverless instances requires an edge proxy or datastore (e.g., Cloudflare WAF, Upstash Redis, or Vercel Edge Middleware).
- **Automatic Heat Risk Evaluation:** Automatically computes Heat Index using official NOAA polynomial regression and evaluates high-temperature safety alert thresholds upon ingestion.

### Mutation Endpoint Security & CSRF Architecture
All state-modifying mutation endpoints are protected against unauthorized modification and CSRF attacks:
- **Protected Routes:** `POST /api/settings/threshold`, `POST /api/settings/sampling_interval`, `POST /api/alerts/<id>/acknowledge`, `POST /api/mode`, `POST /api/demo/spike`.
- **Browser User CSRF Protection:** Legitimate dashboard users are issued a cryptographically secure session CSRF token (`session['csrf_token']`). Frontend AJAX/fetch requests automatically send this via the `X-CSRF-Token` header. Cross-origin and forgery requests without this token are rejected with HTTP 403 Forbidden.
- **Programmatic Control Key:** Automated scripts, CLI tools, or external control software authenticate using an independent Control Key (`VA_CONTROL_KEY`) via `Authorization: Bearer <KEY>` or `X-VA-Control-Key: <KEY>`, distinct from the telemetry ingestion secret.
- **Read-Only Dashboard Accessibility:** Read-only dashboard views, charts, and public telemetry monitoring endpoints remain open without requiring logins or credentials.

### Autonomous Raspberry Pi Telemetry Client (`scripts/pi_telemetry_client.py`)
Run on the Raspberry Pi 3 Model B+ to autonomously sample sensors and transmit readings:
```bash
# Production hardware mode posting to live dashboard
python scripts/pi_telemetry_client.py \
  --server https://va.developerhut.in \
  --token "<YOUR_VA_INGEST_KEY>" \
  --interval 10

# Test simulated telemetry before sensor arrival
python scripts/pi_telemetry_client.py \
  --server http://127.0.0.1:5000 \
  --mode simulated
```

### Dedicated DHT11 Remote Ingestion Endpoint (`POST /api/ingest/dht11`)
Designed specifically for remote microcontrollers and edge bridges (such as an Arduino Mega 2560 connected to a Raspberry Pi 3 Model B+):
- **Payload Schema:** Accepts JSON with `temperature_c` (float), `humidity_percent` (float), `timestamp` (ISO 8601 string), and `source` (string attribution):
  ```json
  {
    "temperature_c": 33.0,
    "humidity_percent": 46.0,
    "timestamp": "2026-10-29T10:45:00Z",
    "source": "arduino-mega-dht11"
  }
  ```
- **Authentication & Security:** Requires `Authorization: Bearer <TOKEN>` matching `VA_DHT11_INGEST_KEY` (or fallback `VA_INGEST_KEY`) verified via constant-time `hmac.compare_digest`. Fails closed (HTTP 401) in production/live mode when unconfigured.
- **Sensor Range & Type Validation:** Strictly validates DHT11 physical limits: Temperature (-20.0°C to 60.0°C), Relative Humidity (0.0% to 100.0% RH). Rejects non-numeric types, `NaN`, `Infinity`, and invalid ISO 8601 timestamps (HTTP 400).
- **Barometric Pressure Coexistence:** DHT11 sensors do not have a barometer. Ingested records commit to the database with `pressure_hpa = NULL` and `sensor_type = 'dht11'`, seamlessly coexisting with BMP280 records without triggering integrity violations or frontend `null.toFixed()` rendering errors.
- **Automatic Heat Index & Alert Triggers:** Immediately calculates NOAA Rothfusz Heat Index and evaluates high-temperature safety thresholds.

### Raspberry Pi DHT11 Serial Receiver Bridge (`scripts/pi_dht11_serial_receiver.py`)
Bridges sensor readings received via USB serial from an Arduino Mega 2560 to the Virtual Atmosphere cloud endpoint:
- **Pipeline Architecture:**
  $$\text{DHT11 Sensor} \longrightarrow \text{Arduino Mega 2560} \xrightarrow[\text{9600 baud}]{\text{/dev/ttyUSB0}} \text{Raspberry Pi 3B+} \xrightarrow[\text{Bearer Auth}]{\text{HTTPS POST /api/ingest/dht11}} \text{VA Cloud Dashboard}$$
- **Multi-Format Serial Parser:** Robustly parses both human-readable serial strings and raw CSV:
  - Text pattern: `Temperature: 33.0 °C | Humidity: 46.0%`
  - CSV pattern: `33.0, 46.0` or `33.0,46.0`
  - Key-Value pattern: `temp=33.0 hum=46.0`
- **Execution Syntax:**
  ```bash
  python scripts/pi_dht11_serial_receiver.py \
    --port /dev/ttyUSB0 \
    --baud 9600 \
    --server https://va.developerhut.in \
    --token "<YOUR_VA_DHT11_INGEST_KEY>" \
    --min-interval 5
  ```

---

## 9. Cloud Persistence Architecture & Vercel Storage Limitations

### Vercel Serverless `/tmp` Ephemeral Nature
In serverless cloud deployments like Vercel:
- The filesystem is strictly read-only except for the ephemeral `/tmp` directory.
- SQLite databases created in `/tmp` are wiped whenever Vercel tears down or cold-starts the serverless execution container.
- Concurrent serverless execution instances do not share the `/tmp` filesystem.
- The dashboard and `/api/status` endpoint transparently report storage status: `storage_backend="sqlite_ephemeral"`, `is_persistent=False`, and an advisory persistence notice.

### Durable Cloud Storage Backends
To achieve permanent, durable storage across container lifecycles on Vercel:
1. **Turso libSQL Database (Recommended for Edge/Vercel):**
   - Create a free database at [Turso](https://turso.tech).
   - Configure environment variables in the Vercel project dashboard:
     - `TURSO_DATABASE_URL`: e.g., `libsql://your-db-name.turso.io`
     - `TURSO_AUTH_TOKEN`: your Turso libSQL authentication token
   - Virtual Atmosphere detects these variables, switches `storage_backend="turso_libsql"`, sets `is_persistent=True`, and commits all telemetry persistently.
2. **PostgreSQL Database (Supabase / Neon / Vercel Postgres):**
   - Configure `POSTGRES_URL` or `DATABASE_URL` in your Vercel project environment variables.
3. **Self-Hosted Raspberry Pi with Cloudflare Tunnel:**
   - Host the entire application on the Raspberry Pi 3 Model B+ using local SQLite storage with Write-Ahead Logging (WAL).
   - Expose the dashboard using a zero-cost Cloudflare Tunnel (`cloudflared tunnel run va`), achieving 100% data sovereignty with no hosting fees.

---

## 10. Accurate Measurement Limitations

- **No Humidity on BMP280:** The BMP280 measures temperature and barometric pressure; it **does not measure relative humidity** (unlike the BME280). Virtual Atmosphere strictly adheres to scientific honesty and never synthesizes or displays fake humidity data.
- **Heat Index Boundaries:** Calculating a validated Heat Index requires simultaneous relative humidity and temperature measurements. These cannot be calculated from a BMP280 sensor alone.
- **Separation of Simulated vs. Hardware Data:** In Live Mode, disconnected sensors report `Hardware Unavailable` and record zero fake measurements. In Simulated Mode, all readings are explicitly tagged with `source="simulated"` or `source="demo"`.
- **Educational Notice:** This system is an educational prototype. Threshold alerts are software-configurable triggers, not clinical medical diagnoses or certified industrial safety shutoffs.

---

## 11. Branding, Favicons & Loading Experience

### Visual Identity & Source Asset
- **Source Logo:** [`logo.jpg`](logo.jpg) (1080×1080 square) serves as the primary visual identity.
- **Color Palette:**
  - Dark Navy Background: `#07111F`
  - Primary Cyan Accent: `#51D8FF`
  - Secondary Blue: `#1677FF`
  - Clean White Typography: `#FFFFFF`
  - Subdued Metallic Slate: `#91A9BF` / `#243B50`

### Generated Favicon & App Icon Suite
All icons are generated via [`scripts/generate_favicons.py`](scripts/generate_favicons.py):
- `static/favicon.ico`: Genuine multi-resolution ICO containing 16×16, 32×32, and 48×48 dimensions.
- `static/favicon-16x16.png`: Transparent 16×16 PNG for standard browser tabs.
- `static/favicon-32x32.png`: Transparent 32×32 PNG for high-DPI browser tabs.
- `static/apple-touch-icon.png`: 180×180 PNG on brand dark navy `#07111F` for iOS Home Screens.
- `static/android-chrome-192x192.png`: 192×192 PNG for Android Home Screens.
- `static/android-chrome-512x512.png`: 512×512 PNG for high-DPI splash and PWA manifests.
- `static/site.webmanifest`: Progressive Web App manifest defining theme colors, standalone mode, and icon paths.
- `static/img/va-logo-sm.png`: Optimized 64×64 PNG for sidebar header navigation.
- `static/img/va-logo-card.png`: 256×256 brand badge for loading screens and error views.
- `static/img/va-logo.png`: High-resolution 512×512 transparent logo.

To regenerate assets at any time:
```bash
python scripts/generate_favicons.py
```

### Browser Cache-Busting & Asset Versioning
Browsers aggressively cache favicons in an internal profile database (e.g. Chrome's `Favicons` SQLite DB) that ignores standard `Ctrl+F5` page reloads. To ensure instant updates across all browsers:
- Favicon references in `<head>` are served with an asset query parameter: `v={{ ASSET_VERSION }}` (e.g., `/static/favicon-32x32.png?v=1.0.1`).
- Direct routes (`/favicon.ico`, `/site.webmanifest`, `/apple-touch-icon.png`) serve explicit `Cache-Control: no-cache, must-revalidate` headers.
- The web app manifest [`static/site.webmanifest`](static/site.webmanifest) versions its embedded icon endpoints (`?v=1.0.1`).

### Initial Loading Experience
- Pure CSS animation with zero heavy external libraries.
- Centered VA monogram with ambient pulse glow and indeterminate cyan-to-blue gradient progress bar.
- Small status subtitle ("Initializing atmosphere monitor…") informing users of background telemetry sync.
- Automatically dismisses upon data arrival with a safety net fallback to prevent permanently locking the interface if the network stalls.
- Fully respects `prefers-reduced-motion` for vestibular accessibility.

### Component-Level Loading Feedback
- **Dashboard Telemetry:** Skeleton metric placeholders while initial readings are retrieved.
- **Charts:** Skeleton chart placeholders and inline dual-color spinners during range updates (1h, 6h, 24h, 7d). Range buttons are temporarily disabled to prevent race conditions.
- **CSV Export:** Tactile loading state with inline spinner and screen-reader confirmation during CSV generation.
- **Form Submissions:** Threshold setting and sampling interval forms show button spinners and lock inputs to prevent duplicate POST requests.
- **Accessibility:** Screen-reader live region announcements (`aria-live="polite"`) for background status changes.

### Custom Branded Error Pages
- **404 Not Found (`templates/404.html`):** Custom branded error page explaining missing routes, with direct links back to Overview, Live Monitor, and Sensor Diagnostics. Explicitly clarifies that a missing hardware sensor does not trigger 404s.
- **500 Server Error (`templates/500.html`):** Safe, professional fallback that logs server conditions without leaking internal tracebacks, paths, or environment variables.

---

## 12. Installation & Execution Instructions

### Local Development / Demo Mode (Laptop)

```bash
# 1. Clone repository
git clone https://github.com/Vasudevan1202/va.git
cd va

# 2. Create virtual environment & install requirements
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt

# 3. Start local application
python app.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser.

### Raspberry Pi 3B+ Deployment (Live Hardware Mode)

```bash
# 1. Enable I2C via raspi-config
sudo raspi-config
# Interface Options -> I2C -> Enable

# 2. Verify sensor on bus 1
sudo i2cdetect -y 1
# Expected output: 76 or 77

# 3. Run sensor diagnostic
python scripts/check_sensor.py

# 4. Start in Live Mode bound to all network interfaces
export VA_MODE=live
export VA_HOST=0.0.0.0
export VA_PORT=5000

python app.py
```

Access from any phone or computer on the same Wi-Fi network at `http://<RPI_IP>:5000`.

---

## 13. Running Automated Tests

Run the complete 76-test automated verification suite:

```bash
pytest -v
```

All 76 unit and integration tests verify:
- **Dedicated DHT11 Ingestion (`POST /api/ingest/dht11`):** Bearer token authentication, production fail-closed policy when unconfigured, rejection of non-numeric, `NaN`, and `Infinity` payloads, physical range validation (-20°C to 60°C, 0% to 100% RH), ISO 8601 timestamp validation, and serial bridge regex and CSV parser testing.
- **Sensor Coexistence:** Seamless integration of BMP280 records (`pressure_hpa` present, `humidity_pct` null) and DHT11 records (`humidity_pct` present, `pressure_hpa` null) without database schema errors or frontend JavaScript `null.toFixed()` exceptions.
- **NOAA / NWS Heat Index Algorithm:** Formula accuracy, 80°F (26.7°C) and 40% RH applicability gates, category assignments, and refusal to calculate from temperature alone.
- **Meteorological Boundary Checks:** Range enforcement on temperature, pressure, humidity, latitude, and longitude.
- **Database Schema & Migrations:** Nullable `humidity_pct`, `pressure_hpa`, `sensor_type`, automated table recreation migration for legacy non-null pressure columns, and updated `today_stats`.
- **Secure Telemetry Ingestion (`POST /api/telemetry`):** Constant-time Bearer token verification (`hmac.compare_digest`), range rejection (HTTP 400), unauthorized rejection (HTTP 401), alert evaluation, and successful record commits (HTTP 201).
- **Hardware Peripherals Safety:** BME280/BMP280 register driver, DHT11 adapter, and GPS NMEA sentence parser without crashing on non-Pi platforms.
- **CSV Data Export:** Verification that weather columns (Humidity, Heat Index, Latitude, Longitude, Sensor Type) are exported accurately.
- **Alert Deduplication & Lifecycle:** Hysteresis clearance, operator acknowledgment, and active alert state transitions.
- **REST API Contracts:** Endpoints (`/api/status`, `/api/readings`, `/api/readings/latest`, `/api/alerts`, `/api/telemetry`, `/api/ingest/dht11`).
- **Page Rendering & Branding Integrity:** Templates, favicons, web app manifest, error handling, and security guarantees.

---

## 14. Environment Variables Reference

| Variable | Description | Default (Dev) | Production / Live Mode |
| :--- | :--- | :--- | :--- |
| `VA_DHT11_INGEST_KEY` | Secret Bearer token for `POST /api/ingest/dht11`. | `va-dht11-secret-ingest-key` | **Required.** Must be strong secret. Fails closed (401) if unset. |
| `VA_INGEST_KEY` | Secret Bearer token for general `POST /api/telemetry`. Fallback for DHT11. | `va-secret-ingest-key` | **Required.** Fails closed (401) if unset. |
| `VA_CONTROL_KEY` | Secret token for mutating settings/alerts without browser CSRF session. | `va-secret-control-key` | **Required** for external CLI/automation scripts. |
| `VA_MODE` | Runtime mode: `live` (physical sensors) or `simulated` (demo loop). | `simulated` | Set to `live` on physical station. |
| `VA_HOST` | Network interface address to bind web server to. | `127.0.0.1` | `0.0.0.0` (binds all network interfaces). |
| `VA_PORT` | Port number to run web server on. | `5000` | `5000` or port assigned by host. |
| `TURSO_DATABASE_URL` | Turso libSQL connection URL for durable Vercel storage. | *None* | e.g. `libsql://va-db.turso.io` |
| `TURSO_AUTH_TOKEN` | Turso authentication token for libSQL remote access. | *None* | Turso issued JWT token. |
| `POSTGRES_URL` | PostgreSQL connection URL for Supabase / Neon durable storage. | *None* | `postgresql://...` |
| `SECRET_KEY` | Flask session cryptographic signing secret. | Random dev bytes | **Required.** Set to persistent secret in production. |

> [!WARNING]
> In production (`VA_MODE=live` or Vercel `VERCEL=1`), all ingestion and control endpoints fail closed (HTTP 401 Unauthorized) if secrets are missing or match development placeholders. Never commit secrets to source control or embed them in client-side code.

---

## 15. Deployment Considerations

### Raspberry Pi DHT11 Serial Receiver Service
To run the Arduino-to-Raspberry-Pi serial receiver bridge continuously as a systemd background service on the Pi:
```ini
# /etc/systemd/system/va-dht11-bridge.service
[Unit]
Description=Virtual Atmosphere DHT11 Serial Ingestion Bridge
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/va
Environment="VA_DHT11_INGEST_KEY=your_production_secret_token_here"
ExecStart=/home/pi/va/.venv/bin/python scripts/pi_dht11_serial_receiver.py \
  --port /dev/ttyUSB0 \
  --baud 9600 \
  --server https://va.developerhut.in \
  --min-interval 5
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable va-dht11-bridge.service
sudo systemctl start va-dht11-bridge.service
sudo systemctl status va-dht11-bridge.service
```

### Raspberry Pi Web Server Service
A production service file ([`virtual-atmosphere.service`](virtual-atmosphere.service)) is included for automatic daemon management and autostart on Pi boot.

### Vercel Serverless Cloud Deployment
Pre-configured with [`vercel.json`](vercel.json) and [`api/index.py`](api/index.py):
- By default without cloud credentials, SQLite storage operates in `/tmp/virtual_atmosphere.db` (`storage_backend="sqlite_ephemeral"`, `is_persistent=False`).
- To make storage permanent across Vercel cold starts, configure `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` in the Vercel Project Settings > Environment Variables.
- Ingestion endpoints seamlessly update the cloud database and status is reflected in the dashboard telemetry header.
