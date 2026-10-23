# Troubleshooting Guide: Virtual Atmosphere (VA)

This document addresses common hardware, network, software, and deployment issues.

---

## 1. Hardware Issues

### Symptom: `i2cdetect -y 1` shows no sensor (all `--` markers)
- **Check Hardware I²C Interface:** Ensure I²C is enabled in Raspberry Pi OS:
  ```bash
  sudo raspi-config
  # Interface Options -> I2C -> Enable
  ```
- **Check 3.3V Power:** Ensure BMP280 `VCC` is plugged into Physical Pin 1 (3.3V). If plugged into Pin 2 or Pin 4 (5.0V), power off immediately to prevent damage.
- **Check Ground:** Verify Pin 6 is securely grounded.
- **Loose Breadboard or Dupont Wires:** Dupont jumper wires frequently experience internal conductor breaks. Test each jumper wire with a digital multimeter or swap cables.
- **Breakout SDO Pin:** If using a 6-pin breakout board, ensure SDO is tied to GND (for address 0x76) or 3.3V (for address 0x77).
- **Check Module Pull-Ups:** If CSB is present, verify it is tied to 3.3V (VCC) to force I²C mode.

---

## 2. Sensor Permissions

### Symptom: `Permission denied: '/dev/i2c-1'`
- By default, Raspberry Pi OS grants access to the `/dev/i2c-1` device node to members of the `i2c` user group.
- Add your user to the group:
  ```bash
  sudo usermod -aG i2c $USER
  ```
- Log out and log back in, or reboot.

---

## 3. Network & Mobile Access Issues

### Symptom: Dashboard accessible on Raspberry Pi (`localhost:5000`), but mobile phone cannot connect
1. **Binding Address:** Ensure the Flask server is bound to `0.0.0.0` (all network interfaces), not `127.0.0.1` (localhost only).
   ```bash
   export VA_HOST=0.0.0.0
   python app.py
   ```
2. **Same Wi-Fi Subnet:** Verify both your phone and Raspberry Pi are connected to the exact same Wi-Fi SSID and band (disable AP client isolation on the school router).
3. **Verify Pi IP:** Run `hostname -I` on the Pi to check its IP address. Use that IP address on your phone: `http://192.168.1.xxx:5000`.
4. **Firewall (ufw):** If a local firewall is running on Raspberry Pi OS, allow port 5000:
   ```bash
   sudo ufw allow 5000/tcp
   ```

---

## 4. systemd Service Troubleshooting

### Symptom: `virtual-atmosphere.service` fails to start
1. Inspect the service log:
   ```bash
   sudo journalctl -u virtual-atmosphere.service -n 50 --no-pager
   ```
2. Common causes:
   - **Incorrect WorkingDirectory:** Ensure `/etc/systemd/system/virtual-atmosphere.service` points to the actual project folder (e.g. `/home/pi/virtual-atmosphere`).
   - **Incorrect Python Path:** Confirm `ExecStart` points to your virtual environment's Python binary (`/home/pi/virtual-atmosphere/.venv/bin/python`).
   - **User Permissions:** Ensure the specified `User=` has read/write permissions to the `data/` folder for SQLite.

---

## 5. Port 5000 Already in Use

### Symptom: `OSError: [Errno 98] Address already in use`
Find and terminate any existing process occupying port 5000:
```bash
sudo lsof -i :5000
# or
sudo fuser -k 5000/tcp
```
Alternatively, configure a different port:
```bash
export VA_PORT=8080
python app.py
```
