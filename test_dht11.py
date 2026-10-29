#!/usr/bin/env python3
"""
Standalone Hardware Test Utility for Physical DHT11 Sensor
Target: Raspberry Pi 3 Model B+
Wiring:
  - DATA: GPIO4 (Physical Pin 7)
  - VCC:  3.3V  (Physical Pin 1)
  - GND:  GND   (Physical Pin 6)
"""

import sys
import time

def main():
    try:
        import board
        import adafruit_dht
    except ImportError as err:
        print(f"[ERROR] Required hardware library not found: {err}")
        print("Please activate the virtual environment and install adafruit-circuitpython-dht:")
        print("  source .venv/bin/activate")
        print("  pip install adafruit-circuitpython-dht")
        sys.exit(1)

    print("=" * 60)
    print(" DHT11 Physical Sensor Hardware Test")
    print(" Target: Raspberry Pi 3 Model B+ (GPIO4 / Pin 7)")
    print("=" * 60)

    dht_device = None
    max_retries = 5
    retry_delay_seconds = 2.0
    read_success = False

    try:
        # Initialize DHT11 sensor on board.D4 (BCM GPIO4, Physical Pin 7)
        dht_device = adafruit_dht.DHT11(board.D4)
        print("[INFO] Sensor initialized on board.D4 (GPIO4, Physical Pin 7).")
        print(f"[INFO] Attempting to read sensor (up to {max_retries} attempts, {retry_delay_seconds}s delay)...")
        print("-" * 60)

        for attempt in range(1, max_retries + 1):
            try:
                # Read actual temperature and humidity from physical hardware
                temperature_c = dht_device.temperature
                humidity_pct = dht_device.humidity

                if temperature_c is not None and humidity_pct is not None:
                    print(f"[Attempt {attempt}/{max_retries}] Read successful!")
                    print(f"Temperature: {temperature_c:.1f} °C")
                    print(f"Humidity: {humidity_pct:.1f} %")
                    read_success = True
                    break
                else:
                    print(f"[Attempt {attempt}/{max_retries}] Incomplete data received (temp={temperature_c}, humidity={humidity_pct}).")

            except RuntimeError as err:
                # DHT sensors frequently raise RuntimeError due to microsecond single-wire timing
                print(f"[Attempt {attempt}/{max_retries}] Temporary read error: {err}")
            except Exception as err:
                print(f"[Attempt {attempt}/{max_retries}] Unexpected sensor error: {err}")

            if attempt < max_retries:
                print(f"       Waiting {retry_delay_seconds}s before next attempt...")
                time.sleep(retry_delay_seconds)

        print("-" * 60)

        if not read_success:
            print(f"[FAILURE] Unable to acquire valid reading after {max_retries} attempts.")
            print("Troubleshooting steps:")
            print("  1. Verify physical wiring:")
            print("     - VCC  -> Physical Pin 1 (3.3V)")
            print("     - DATA -> Physical Pin 7 (GPIO4 / BCM 4)")
            print("     - GND  -> Physical Pin 6 (Ground)")
            print("  2. If using a bare DHT11 sensor (4 pins), ensure a 4.7k-10k pull-up resistor is placed between DATA and VCC.")
            print("  3. Verify that 1-Wire is not conflicting on GPIO4 in /boot/config.txt (dtoverlay=w1-gpio).")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n[INFO] Test aborted by user.")
        sys.exit(130)
    finally:
        if dht_device is not None:
            try:
                dht_device.exit()
                print("[INFO] DHT11 sensor cleaned up successfully.")
            except Exception as err:
                print(f"[WARNING] Error cleaning up sensor: {err}")


if __name__ == "__main__":
    main()
