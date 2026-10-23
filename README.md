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

## 7. Accurate Measurement Limitations

- **No Humidity Sensor:** The BMP280 measures temperature and barometric pressure; it **does not measure relative humidity** (unlike the BME280). Virtual Atmosphere strictly adheres to scientific honesty and never synthesizes or displays fake humidity data.
- **Heat Index & WBGT Boundaries:** Calculating a validated Heat Index or Wet Bulb Globe Temperature (WBGT) requires simultaneous relative humidity and natural wet-bulb measurements. These cannot be calculated from a BMP280 sensor alone.
- **Separation of Demo vs. Live Data:** In Live Mode, disconnected sensors report `Sensor Offline` and record zero fake measurements. In Demo Mode, all simulated readings are explicitly tagged with `source="demo"`.
- **Educational Notice:** This system is an educational prototype. Threshold alerts are software-configurable triggers, not clinical medical diagnoses or certified industrial safety shutoffs.

---

## 8. Installation & Execution Instructions

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

## 9. Running Automated Tests

Run the complete 22-test automated verification suite:

```bash
pytest -v
```

All 22 unit and integration tests verify:
- Database schema initialization, WAL mode, queries, and today's summary stats.
- Alert deduplication: repeated polls during elevated conditions never create duplicate alerts.
- Alert acknowledgment and automatic hysteresis resolution when temperature normalizes.
- REST API contracts (`/api/status`, `/api/readings`, `/api/alerts`, CSV export).
- Page rendering: `/dashboard`, `/live`, `/history`, `/alerts`, `/system`, `/about`, `/project`.
- Project overview and team information rendering with measurement limitation guarantees.
- Hardware failover: offline sensor reporting without fabricating fake data.

---

## 10. Deployment Considerations

- **Raspberry Pi systemd:** A production service file ([`virtual-atmosphere.service`](virtual-atmosphere.service)) is included for automatic daemon management and autostart on boot.
- **Vercel Cloud Deployment:** Pre-configured with [`vercel.json`](vercel.json) and [`api/index.py`](api/index.py). When deployed to Vercel, SQLite storage automatically redirects to `/tmp/virtual_atmosphere.db` and on-demand telemetry advances simulated demo readings.
