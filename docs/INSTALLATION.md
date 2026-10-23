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
