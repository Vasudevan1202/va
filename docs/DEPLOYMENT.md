# Virtual Atmosphere Deployment Guide

> **Sunset Warm Production Architecture & Hardware Ingestion Pipeline**

This guide details the deployment of **Virtual Atmosphere (VA)** to production on Vercel with **Turso libSQL** cloud persistence and the **Arduino Mega 2560 → Raspberry Pi 3B+ → Vercel** telemetry pipeline.

---

## 1. System Architecture Overview

```text
+-----------------------+
| Arduino Mega 2560     |
| (DHT11 Sensor on D2)  |
+-----------------------+
            |
            | USB Serial (9600 baud, e.g. /dev/ttyUSB0)
            v
+-------------------------------------------------------+
| Raspberry Pi 3 Model B+                               |
| - scripts/pi_dht11_serial_receiver.py (systemd)       |
| - Reads serial stream ("Temperature: 33.0 °C | ...")  |
| - Sends HTTPS POST with Bearer token authentication   |
+-------------------------------------------------------+
            |
            | HTTPS POST /api/ingest/dht11 (Bearer VA_DHT11_INGEST_KEY)
            v
+-------------------------------------------------------+
| Vercel Serverless API (Flask 3.x WSGI)               |
| - api/index.py / app.py                              |
| - Production Mode: VA_MODE=live                      |
| - Validates bounds: -20°C to 60°C, 0% to 100% RH     |
| - Evaluates NOAA Heat Index & safety alerts          |
+-------------------------------------------------------+
            |
            | libSQL v2 pipeline over HTTPS
            v
+-------------------------------------------------------+
| Turso libSQL Cloud Database                           |
| - Persistent time-series environmental records        |
| - Zero ephemeral /tmp data loss                       |
+-------------------------------------------------------+
            ^
            | Polls /api/readings/latest (Honest freshness checks)
+-------------------------------------------------------+
| Sunset Warm Dashboard UI                              |
| - Responsive desktop, tablet, and mobile navigation   |
| - WCAG AAA/AA accessible contrast & keyboard focus    |
| - Temperature, Humidity, and Heat Index separation    |
| - Shows honest "No live reading" / "Sensor offline"   |
|   when telemetry is absent or stale (>180s)           |
+-------------------------------------------------------+
```

---

## 2. Production Mode Configuration

Virtual Atmosphere uses explicit environment variable configuration to enforce production integrity and prevent synthetic/fabricated data.

### Required Production Environment Variables

| Variable | Recommended Production Value | Description |
| :--- | :--- | :--- |
| `VA_MODE` | `live` | Enforces real readings only. Suppresses demo loops and prevents auto-seeding. |
| `TURSO_DATABASE_URL` | `libsql://your-db.turso.io` or `https://...` | Turso database connection URL for persistent edge storage. |
| `TURSO_AUTH_TOKEN` | *Turso issued JWT token* | Authentication token for Turso libSQL database. |
| `VA_DHT11_INGEST_KEY` | *Cryptographically secure string (≥ 32 chars)* | Secret token for Arduino Mega / Raspberry Pi DHT11 telemetry. |
| `VA_INGEST_KEY` | *Cryptographically secure string (≥ 32 chars)* | Ingest secret for general telemetry (`POST /api/telemetry`). |
| `VA_CONTROL_KEY` | *Cryptographically secure string (≥ 32 chars)* | Secret token for external CLI management and threshold changes. |
| `SECRET_KEY` | *Cryptographically secure string (≥ 32 chars)* | Flask secret key for signing user sessions and CSRF tokens. |

> [!IMPORTANT]
> **Honest Data Guarantee:** When `VA_MODE=live` (or running in production on Vercel with Turso configured), Virtual Atmosphere:
> 1. Filters all queries (`real_only=True`) to exclude any historical records tagged `demo` or `simulated`.
> 2. Disables demo auto-seeding.
> 3. Automatically tracks reading freshness. If no readings exist, or if the latest reading is older than 180 seconds, the UI honestly renders **"Sensor Offline"** / **"No live reading"** with the last updated time.
> 4. Fails closed (HTTP 401) on ingestion routes if tokens are missing or match development placeholders.

---

## 3. Turso libSQL Database Setup

1. **Install the Turso CLI** (or sign up at [turso.tech](https://turso.tech)):
   ```bash
   # macOS / Linux:
   curl -sSfL https://get.tur.so/install.sh | bash
   # Windows (via Scoop or PowerShell):
   irm https://get.tur.so/install.ps1 | iex
   ```

2. **Authenticate & Create a Database**:
   ```bash
   turso auth signup # or turso auth login
   turso db create virtual-atmosphere
   ```

3. **Retrieve Database URL & Auth Token**:
   ```bash
   turso db show virtual-atmosphere --url
   # Example: libsql://virtual-atmosphere-user.turso.io

   turso db tokens create virtual-atmosphere
   # Returns a long JWT token
   ```

4. **Initialize Database Schema**:
   Virtual Atmosphere's internal client automatically runs `init_db()` on application boot, creating the necessary `readings`, `alerts`, and `settings` tables with full indexing.

---

## 4. Vercel Cloud Deployment

### Step 1: Deploy with Vercel CLI or GitHub Integration
Connect the repository to your Vercel account:
```bash
vercel
```

### Step 2: Configure Environment Variables
In your Vercel Project Dashboard under **Settings > Environment Variables**, add:
- `VA_MODE` = `live`
- `TURSO_DATABASE_URL` = `libsql://virtual-atmosphere-user.turso.io`
- `TURSO_AUTH_TOKEN` = `<your-turso-jwt-token>`
- `VA_DHT11_INGEST_KEY` = `<strong-random-ingest-secret>`
- `VA_INGEST_KEY` = `<strong-random-ingest-secret>`
- `VA_CONTROL_KEY` = `<strong-random-control-secret>`
- `SECRET_KEY` = `<strong-random-session-secret>`

### Step 3: Verify Storage Persistence & Live Status
Visit `https://your-domain.vercel.app/api/status`. The response should display:
```json
{
  "database": {
    "status": "healthy",
    "storage_backend": "turso_libsql",
    "is_persistent": true
  },
  "runtime_mode": "live"
}
```

---

## 5. Arduino Mega 2560 & Raspberry Pi DHT11 Setup

### Wiring Diagram
- **DHT11 VCC** $\rightarrow$ Arduino 5V
- **DHT11 GND** $\rightarrow$ Arduino GND
- **DHT11 DATA** $\rightarrow$ Arduino Digital Pin 2 (with 4.7kΩ–10kΩ pull-up resistor to 5V)
- **Arduino USB Port** $\rightarrow$ Raspberry Pi 3B+ USB Port (enumerated as `/dev/ttyUSB0` or `/dev/ttyACM0`)

### Arduino Sketch (`arduino_mega_dht11.ino`)
Upload this standard sketch to the Arduino Mega:
```cpp
#include <DHT.h>

#define DHTPIN 2
#define DHTTYPE DHT11

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  dht.begin();
}

void loop() {
  delay(5000); // Sample every 5 seconds
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    return;
  }

  // Print standardized line for receiver bridge
  Serial.print("Temperature: ");
  Serial.print(t, 1);
  Serial.print(" °C | Humidity: ");
  Serial.print(h, 1);
  Serial.println("%");
}
```

### Raspberry Pi Bridge Background Service

1. On the Raspberry Pi, clone the repository and set up a virtual environment:
   ```bash
   cd /home/pi
   git clone https://github.com/Vasudevan1202/va.git
   cd va
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create a systemd service file `/etc/systemd/system/va-dht11-bridge.service`:
   ```ini
   [Unit]
   Description=Virtual Atmosphere DHT11 Serial Ingestion Bridge
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/va
   Environment="VA_DHT11_INGEST_KEY=your_production_secret_token_here"
   ExecStart=/home/pi/va/.venv/bin/python scripts/pi_dht11_serial_receiver.py \
     --port /dev/ttyUSB0 \
     --baud 9600 \
     --server https://your-domain.vercel.app \
     --min-interval 5
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the bridge:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable va-dht11-bridge.service
   sudo systemctl start va-dht11-bridge.service
   sudo systemctl status va-dht11-bridge.service
   ```

4. View live logs:
   ```bash
   journalctl -u va-dht11-bridge.service -f
   ```

---

## 6. Sunset Warm Design System & Accessibility

Virtual Atmosphere features the **Sunset Warm** design system:

### Visual Characteristics
- **Header Banner:** Panoramic sunset gradient with sun orb and mountain silhouette layers.
- **Color Hierarchy:**
  - Base Background: Warm Cream (`#faf5ee`)
  - Card & Container Surfaces: Pure Crisp White (`#ffffff`) with subtle warm peach borders (`#f2decb`)
  - Active Navigation Pill: Vibrant Terracotta/Coral (`#f25c38`)
  - Primary Typography: Deep Warm Charcoal (`#1f1412`), providing **16.2:1** WCAG AAA contrast
  - Secondary Labels: Warm Umber (`#5a463e`), providing **7.2:1** WCAG AA contrast
  - Temperature Theme: Coral Warm (`#e05438`)
  - Relative Humidity Theme: Sky Cyan (`#0284c7`)
  - Calculated Heat Index Theme: Warm Amber (`#d97706`)

### Responsive & Accessibility Standards
- **Responsive Drawer:** Off-canvas mobile navigation drawer with accessible hamburger toggle, escape-key support, and body scroll lock.
- **Keyboard Navigation:** High-contrast 3px focus rings (`outline: 3px solid #f25c38; outline-offset: 2px`) on all interactive buttons, links, and form fields.
- **Skip Links:** Screen-reader accessible `.skip-link` immediately jumps focus to `#main-content`.
- **ARIA Live Regions:** Dynamic announcements (`#vaAnnouncer` with `aria-live="polite"`) inform assistive technologies when telemetry polls complete or change state.
- **Theme Persistence:** Theme state defaults to Sunset Warm and is stored in browser `localStorage.getItem('va_theme')`.

---

## 7. Verification Checklist

Run automated test suites to ensure 100% compliance:
```bash
pytest -v
```

All 83 tests should pass:
- [x] Dedicated DHT11 Ingestion (`POST /api/ingest/dht11`) with Bearer token authentication.
- [x] Turso libSQL v2 pipeline client with parameterized arguments and error handling.
- [x] Production mode resolution (`VA_MODE=live` without fake/demo auto-seeding).
- [x] Honest freshness states: "Live Data" (<180s), "Sensor Stale" (>180s), and "Sensor Offline" (0 readings).
- [x] Sunset Warm layout, skip-link, branding, and WCAG AA/AAA compliance.
- [x] NOAA Heat Index calculation and thermodynamic boundary enforcement.
- [x] CSRF protection and control key verification on state-changing endpoints.
