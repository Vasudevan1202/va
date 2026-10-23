#!/usr/bin/env python3
"""
Virtual Atmosphere (VA) - Sensor Hardware Diagnostic Utility
Probes Raspberry Pi I2C bus for Bosch BMP280, validates registers, and performs a test read.
"""
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from sensor_service import BMP280Driver

def main():
    print("=" * 60)
    print(" Virtual Atmosphere (VA) - Hardware Diagnostic Tool")
    print(" Target Hardware: Raspberry Pi 3 Model B+ & GY-BMP280")
    print("=" * 60)

    try:
        import smbus2
        print("[✓] smbus2 Python module is installed.")
    except ImportError:
        print("[✗] smbus2 module is NOT installed.")
        print("    Run: pip install smbus2  or  sudo apt-get install python3-smbus")
        sys.exit(1)

    bus_num = Config.I2C_BUS
    print(f"\n[i] Scanning I²C Bus {bus_num} (/dev/i2c-{bus_num})...")

    driver = BMP280Driver(bus_num=bus_num, address_candidates=Config.I2C_ADDRESS_CANDIDATES)
    success = driver.init_sensor()

    if not success:
        print("\n[✗] BMP280 sensor was NOT detected on I²C bus.")
        print("    Troubleshooting steps:")
        print("    1. Is I²C enabled on your Raspberry Pi? (Run: sudo raspi-config -> Interface Options -> I2C)")
        print("    2. Check physical wiring:")
        print("       - VCC/VIN -> Pin 1 (3.3V)")
        print("       - GND     -> Pin 6 (GND)")
        print("       - SDA     -> Pin 3 (GPIO 2)")
        print("       - SCL     -> Pin 5 (GPIO 3)")
        print("    3. Run 'i2cdetect -y 1' to verify device response at 0x76 or 0x77.")
        print("    4. If address is not 0x76, tie SDO to GND (for 0x76) or VCC (for 0x77).")
        sys.exit(1)

    print(f"[✓] Sensor successfully detected at I²C address: 0x{driver.address:02X}")
    print("[✓] Calibration parameters loaded successfully:")
    for k, v in driver.calib.items():
        print(f"    {k}: {v}")

    print("\n[i] Reading 5 consecutive test samples (1s delay):")
    print("-" * 50)
    print(f"{'Sample':<8}{'Temperature (°C)':<20}{'Pressure (hPa)':<15}")
    print("-" * 50)

    for i in range(1, 6):
        try:
            t, p = driver.read_raw()
            print(f"#{i:<7}{t:<20.2f}{p:<15.2f}")
        except Exception as e:
            print(f"#{i:<7}Error: {e}")
        time.sleep(1.0)

    driver.close()
    print("-" * 50)
    print("[✓] Sensor diagnostic completed successfully.")

if __name__ == "__main__":
    main()
