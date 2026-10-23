# VA | Virtual Atmosphere
> **Understand Your Atmosphere.**

A production-quality school environmental monitoring and IoT science web application powered by **Python Flask**, **SQLite**, and **Chart.js**, designed for direct I²C connection to a **Bosch BMP280** sensor on a **Raspberry Pi 3 Model B+**.

Virtual Atmosphere includes both a **Live Hardware Mode** for physical Raspberry Pi deployment and a high-fidelity **Demo Mode** with simulated diurnal environmental cycles for running immediately on any laptop without hardware.

---

## Key Features

- **Direct I²C Sensor Integration:** Direct hardware communication with Bosch BMP280 via Raspberry Pi I²C bus 1 (`/dev/i2c-1`) with register calibration and Bosch compensation formulas. No ESP32 or external microcontroller required.
- **Scientific Dark Dashboard:** Visual design system adhering to environmental intelligence standards (`#07111F` background, `#10263A` cards, `#51D8FF` cyan accents).
- **Time-Series Charts:** Interactive Chart.js graphs displaying temperature and atmospheric pressure trends over 1h, 6h, 24h, and 7d time horizons.
- **Configurable Temperature Alerts:** Configurable trigger thresholds (default 35.0°C) with persistent database logging, operator acknowledgment, deduplication, and hysteresis auto-recovery.
- **Complete Offline Support:** Local SQLite storage in Write-Ahead-Logging (WAL) mode; vendor assets bundled locally for schools without internet connectivity.
- **Historical Data Exploration & CSV Export:** Searchable, paginated reading history with date/time range filtering and instant one-click CSV file downloads.
- **Honest Environmental Reporting:** Clearly displays valid BMP280 measurements (temperature & barometric pressure). Does not fabricate humidity data.
- **Seamless Demo Mode:** Explicitly labeled demo mode for laptop development, complete with an interactive test spike trigger to verify alerts.

---

## Project Structure

```text
virtual-atmosphere/
├── app.py                      # Flask application factory, REST APIs & page routes
├── config.py                   # Centralized configuration & environment variable handling
├── database.py                 # SQLite thread-safe connection pool, queries & schema
├── sensor_service.py           # BMP280 I2C driver, background polling worker & demo engine
├── alert_service.py            # Deduplicated temperature alert evaluation & lifecycle
├── requirements.txt            # Python dependencies (Flask, pytest, smbus2)
├── virtual-atmosphere.service  # systemd service template for Raspberry Pi auto-start
├── templates/                  # Jinja2 HTML templates
│   ├── base.html               # Master layout with sidebar & live header
│   ├── dashboard.html          # Overview dashboard with live cards & charts
│   ├── live_monitor.html       # Real-time high-frequency gauge telemetry screen
│   ├── history.html            # Historical explorer, filters & paginated table
│   ├── alerts.html             # Alert log audit screen & threshold settings
│   ├── system.html             # Hardware I²C diagnostics & runtime mode controls
│   └── about.html              # Science principles, architecture & educational notes
├── static/                     # Static styling and client scripts
│   ├── css/
│   │   ├── bootstrap.min.css   # Bundled Bootstrap 5 (offline ready)
│   │   └── app.css             # Scientific dark design system stylesheet
│   └── js/
│       ├── bootstrap.bundle.min.js
│       ├── chart.umd.min.js    # Bundled Chart.js v4
│       ├── app.js              # Global polling & header clock
│       ├── dashboard.js        # Overview charts & threshold updater
│       ├── live_monitor.js     # Live telemetry gauges
│       ├── history.js          # Historical filtering & CSV export
│       └── alerts.js           # Alert audit table & acknowledgment
├── scripts/
│   ├── check_sensor.py         # Hardware I2C CLI verification tool
│   ├── init_database.py        # Schema setup and database health check
│   └── seed_demo_data.py       # Seeds 24h of realistic simulated history
├── tests/                      # Automated test suite (21 unit & integration tests)
│   ├── test_database.py        # Database operations & migrations
│   ├── test_alerts.py          # Alert deduplication, acknowledgment & hysteresis
│   ├── test_api.py             # REST API endpoint and page render tests
│   └── test_sensor_service.py  # Demo generator & live hardware offline fallback
├── docs/                       # Technical documentation
│   ├── INSTALLATION.md         # Step-by-step Raspberry Pi OS deployment
│   ├── HARDWARE_WIRING.md      # Pinout schematics & connection diagrams
│   ├── API.md                  # Complete REST API documentation
│   └── TROUBLESHOOTING.md      # Common hardware and network error solutions
└── README.md
```

---

## Quickstart (Demo Mode on Laptop)

Run the dashboard immediately on any regular computer (Windows, macOS, Linux):

1. **Clone repository & enter directory:**
   ```bash
   cd virtual-atmosphere
   ```

2. **Create virtual environment & install requirements:**
   ```bash
   python -m venv .venv
   # On Windows:
   .\.venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Start the application:**
   ```bash
   python app.py
   ```

4. **Open in your browser:**
   ```
   http://127.0.0.1:5000
   ```
   *The application starts in Demo Mode, displaying a visible "DEMO DATA" banner with physics-based simulated readings.*

---

## Raspberry Pi Deployment (Live Hardware Mode)

### 1. Hardware Pinout

Connect the GY-BMP280 sensor to the Raspberry Pi 3 Model B+ 40-pin header:

| GY-BMP280 Pin | Raspberry Pi Pin | Physical Pin # | Function |
| :--- | :--- | :--- | :--- |
| **VCC / VIN** | 3.3V Power | **Pin 1** | +3.3V DC Supply |
| **GND** | Ground | **Pin 6** | Ground (0V) |
| **SDA** | GPIO 2 (SDA1) | **Pin 3** | I²C Serial Data |
| **SCL** | GPIO 3 (SCL1) | **Pin 5** | I²C Serial Clock |

### 2. Run in Live Mode

```bash
# Enable I2C interface via: sudo raspi-config
export VA_MODE=live
export VA_HOST=0.0.0.0
export VA_PORT=5000

python app.py
```

### 3. Verify on Local Network
Find your Raspberry Pi's IP address:
```bash
hostname -I
```
Access the dashboard from any smartphone or tablet on the same Wi-Fi network at `http://<RPI_IP>:5000`.

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for configuring automatic startup with `systemd`.

---

## Running the Automated Tests

Execute the comprehensive test suite:
```bash
pytest -v
```

All 21 unit and integration tests verify:
- Database creation, indexing, statistics, and queries.
- Alert deduplication: repeated polling during an active warning never generates duplicate alerts.
- Alert acknowledgment and automatic resolution using hysteresis.
- REST API contracts, HTTP status codes, parameter validation, and streaming CSV export.
- Hardware failover: in live mode without hardware, the app starts cleanly, reports offline, and avoids fabricating fake data.

---

## Educational Notice
Virtual Atmosphere is created as an educational prototype for school IoT science projects. Threshold alerts are configurable educational triggers and are not certified for medical diagnosis or occupational heat-stress (WBGT/OSHA) compliance.
