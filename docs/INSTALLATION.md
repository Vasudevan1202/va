# Raspberry Pi OS Deployment & Installation Guide

This guide walks through configuring and running **Virtual Atmosphere (VA)** on a **Raspberry Pi 3 Model B+** with a **GY-BMP280** sensor breakout board.

---

## 1. Prerequisites & OS Setup
1. Flash **Raspberry Pi OS (64-bit or 32-bit with desktop or Lite)** to a high-end microSD card using the [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Boot your Raspberry Pi and connect it to your local Wi-Fi or Ethernet network.

---

## 2. Enable Hardware I²C Interface
The BMP280 communicates via the hardware Inter-Integrated Circuit (I²C) bus on GPIO pins 2 & 3.

Run the Raspberry Pi configuration tool:
```bash
sudo raspi-config
```
1. Navigate to **Interface Options** &rarr; **I2C**.
2. Select **Yes** to enable the ARM I²C interface driver.
3. Select **Finish** and reboot if prompted:
   ```bash
   sudo reboot
   ```

---

## 3. Install System Packages
Open a terminal on your Raspberry Pi and ensure system packages, Python 3, and I²C diagnostic utilities are installed:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv i2c-tools git
```

---

## 4. Transfer or Clone Project
Transfer the project folder to your Raspberry Pi user directory (e.g. `/home/pi/virtual-atmosphere`):
```bash
cd /home/pi
git clone <your-repository-url> virtual-atmosphere
# or copy via scp
cd /home/pi/virtual-atmosphere
```

---

## 5. Create Python Virtual Environment & Install Dependencies
Create an isolated Python 3 virtual environment and install required libraries (`Flask`, `smbus2`, `pytest`):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 6. Hardware Wiring Connection
With the Raspberry Pi **powered off**, wire the GY-BMP280 sensor to the 40-pin GPIO header:

| GY-BMP280 Breakout Pin | Raspberry Pi 3B+ Header Pin | Physical Pin # | Function |
| :--- | :--- | :--- | :--- |
| **VCC / VIN** | 3.3V Power | **Physical Pin 1** | +3.3V DC Supply |
| **GND** | Ground | **Physical Pin 6** | Ground (0V) |
| **SDA** | GPIO 2 (SDA1) | **Physical Pin 3** | I²C Serial Data |
| **SCL** | GPIO 3 (SCL1) | **Physical Pin 5** | I²C Serial Clock |

> [!CAUTION]
> Never connect the BMP280 to 5.0V pins (Pin 2 or 4). Overvoltage will damage the 3.3V sensor!

---

## 7. Verify Sensor Detection on I²C Bus
Power on your Raspberry Pi and run:
```bash
i2cdetect -y 1
```
You should see either `76` or `77` illuminate in the grid:
```text
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- -- 
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
40: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
70: -- -- -- -- -- -- 76 --                         
```

Next, run the included hardware diagnostic script:
```bash
python scripts/check_sensor.py
```
This tool reads the factory calibration constants and prints 5 consecutive temperature and atmospheric pressure measurements.

---

## 8. Configure Live Mode & Start Application
To run in Live Mode connected to physical hardware and allow network access:
```bash
export VA_MODE=live
export VA_HOST=0.0.0.0
export VA_PORT=5000

python app.py
```

---

## 9. Local Browser Access
- **From the Raspberry Pi desktop browser:**
  Open Chromium and navigate to:
  ```
  http://localhost:5000
  ```

---

## 10. Access from Phone / Laptop on Local Wi-Fi
1. Find your Raspberry Pi's local IP address:
   ```bash
   hostname -I
   ```
   *(Example output: `192.168.1.145`)*
2. Connect your phone or laptop to the **same Wi-Fi network**.
3. Open any modern mobile or desktop browser (Safari, Chrome, Firefox) and navigate to:
   ```
   http://<YOUR_PI_IP>:5000
   ```
   *(Example: `http://192.168.1.145:5000`)*

---

## 11. Run Automatically at Boot with systemd
To ensure Virtual Atmosphere starts automatically when the Raspberry Pi powers on:

1. Copy the systemd service template to the system directory:
   ```bash
   sudo cp virtual-atmosphere.service /etc/systemd/system/virtual-atmosphere.service
   ```
2. Verify that paths match your username and installation directory:
   ```bash
   sudo nano /etc/systemd/system/virtual-atmosphere.service
   ```
3. Reload systemd daemons and enable the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable virtual-atmosphere.service
   sudo systemctl start virtual-atmosphere.service
   ```
4. Verify service status and inspect live logs:
   ```bash
   sudo systemctl status virtual-atmosphere.service
   sudo journalctl -u virtual-atmosphere.service -f
   ```

---

## 12. Raspberry Pi 3 B+ DHT11 & Arduino Mega 2560 Pipeline Setup

Connect your physical DHT11 sensor pipeline to the live Virtual Atmosphere dashboard (`https://va.developerhut.in`):

### Sensor Hardware Pipeline
```text
+-----------------------+     Digital Signal      +------------------------+
| DHT11 Sensor          | ----------------------> | Arduino Mega 2560      |
| (Temp & Humidity)     |   (Pin D4 / VCC / GND)  | (Serial at 9600 Baud)  |
+-----------------------+                         +------------------------+
                                                              |
                                                              | USB Cable (/dev/ttyUSB0)
                                                              v
+-----------------------+     HTTPS Ingest        +------------------------+
| Virtual Atmosphere    | <---------------------- | Raspberry Pi 3B+       |
| Cloud Dashboard       |   (Bearer Token Auth)   | (Python Bridge Worker) |
+-----------------------+                         +------------------------+
```

### 1. Arduino Mega 2560 Serial Output Format
Ensure your Arduino sketch prints temperature and humidity to Serial at **9600 baud**:
- Supported format 1: `Temperature: 33.0 °C | Humidity: 46.0%`
- Supported format 2 (CSV): `33.0, 46.0`

### 2. Connect Arduino to Raspberry Pi
Plug the Arduino Mega 2560 into any USB port of the Raspberry Pi 3 Model B+. The serial port will typically be `/dev/ttyUSB0` (or `/dev/ttyACM0`).

Verify serial port detection:
```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
```

### 3. Run the Python DHT11 Serial Ingestion Bridge
Install `pyserial` on the Raspberry Pi:
```bash
pip3 install pyserial
```

Run the bridge client to stream readings directly to your cloud dashboard:
```bash
python3 scripts/pi_dht11_serial_receiver.py \
  --server https://va.developerhut.in \
  --token "<YOUR_SECRET_TOKEN>" \
  --port /dev/ttyUSB0 \
  --baud 9600 \
  --source "raspberry_pi_dht11" \
  --interval 10
```

---

## 13. Environment Variables Reference & Vercel Durable Persistence

### Complete Environment Variables Reference

| Variable | Description | Default | Required in Production |
| :--- | :--- | :--- | :--- |
| `VA_DHT11_INGEST_KEY` | Secret Bearer token for `POST /api/ingest/dht11` | None (fails closed) | **Yes** |
| `VA_INGEST_KEY` | Secret Bearer token for `POST /api/telemetry` | None (fails closed) | **Yes** |
| `VA_CONTROL_KEY` | Programmatic Bearer token for control mutations | None (fails closed) | Optional |
| `VA_SECRET_KEY` / `FLASK_SECRET_KEY` | Flask session cookie encryption secret | Auto-generated | **Yes** |
| `TURSO_DATABASE_URL` | Turso libSQL cloud database URL for durable Vercel persistence | None | Recommended for Vercel |
| `TURSO_AUTH_TOKEN` | Turso cloud database Bearer authentication token | None | With `TURSO_DATABASE_URL` |
| `POSTGRES_URL` / `DATABASE_URL` | Managed PostgreSQL database connection string | None | Alternative for Vercel |
| `VA_MODE` | Runtime mode (`demo` or `live`) | `demo` (Vercel) / `demo` | No |
| `VA_HOST` | Network interface IP binding | `127.0.0.1` | No (`0.0.0.0` on Pi) |
| `VA_PORT` | HTTP port | `5000` | No |
| `VA_TEMP_THRESHOLD` | High-temperature safety alert trigger threshold (°C) | `35.0` | No |
| `VA_SAMPLING_INTERVAL` | Polling interval in seconds (2 to 3600) | `10` | No |
| `VA_TELEMETRY_RATE_LIMIT`| Process-local sliding window rate limit (req/min) | `60` | No |

### Configuring Durable Cloud Persistence on Vercel

On Vercel serverless functions, the local filesystem is ephemeral: SQLite databases created in `/tmp` are wiped when serverless containers cold start.

To store readings durably across serverless requests on Vercel:
1. Create a free database on **Turso** ([turso.tech](https://turso.tech)) or **Neon** ([neon.tech](https://neon.tech)).
2. In your Vercel Project Settings &rarr; **Environment Variables**, add:
   - For Turso:
     - `TURSO_DATABASE_URL` = `https://<your-db>-<org>.turso.io`
     - `TURSO_AUTH_TOKEN` = `<your-turso-token>`
   - For PostgreSQL / Neon / Supabase:
     - `POSTGRES_URL` = `postgresql://<user>:<password>@<host>/<dbname>?sslmode=require`
   - Ingestion Authentication:
     - `VA_DHT11_INGEST_KEY` = `<secure-random-token-hex>`
     - `VA_INGEST_KEY` = `<secure-random-token-hex>`
     - `VA_SECRET_KEY` = `<secure-random-token-hex>`
3. Deploy to Vercel. Virtual Atmosphere will automatically detect the durable cloud backend, initialize tables, and persist incoming DHT11 and BMP280 telemetry across all serverless invocations.
