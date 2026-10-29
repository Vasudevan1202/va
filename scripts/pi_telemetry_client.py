#!/usr/bin/env python3
"""
Virtual Atmosphere (VA) - Raspberry Pi 3 Model B+ Telemetry Ingestion Client
Periodically samples attached hardware sensors (Bosch BME280/BMP280 via I2C,
optional DHT11 via GPIO, optional u-blox NEO-6M GPS via UART/Serial)
and transmits authenticated environmental telemetry to the Virtual Atmosphere API.

Usage:
    python scripts/pi_telemetry_client.py --server https://va.developerhut.in --token <SECRET_KEY>
    python scripts/pi_telemetry_client.py --server http://127.0.0.1:5000 --simulated
"""

import os
import sys
import time
import math
import random
import logging
import argparse
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

# Add project root directory to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from hardware_adapters import BME280Driver, DHT11Adapter, GPSAdapter
    from weather_service import WeatherService
except ImportError:
    BME280Driver = None
    DHT11Adapter = None
    GPSAdapter = None
    WeatherService = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("va.pi_client")

class PiTelemetryStation:
    """Manages sensor sampling and remote telemetry transmission for Raspberry Pi."""

    def __init__(
        self,
        server_url: str,
        token: str,
        interval_seconds: int = 10,
        mode: str = "hardware",
        dht_pin: int = 4,
        enable_dht: bool = False,
        gps_port: str = "/dev/serial0",
        gps_baud: int = 9600,
        enable_gps: bool = False
    ):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.interval = interval_seconds
        self.mode = mode.lower()

        # Hardware drivers
        self.bme280 = BME280Driver(bus_num=1) if BME280Driver else None
        self.dht11 = DHT11Adapter(pin=dht_pin, enabled=enable_dht) if DHT11Adapter else None
        self.gps = GPSAdapter(port=gps_port, baudrate=gps_baud, enabled=enable_gps) if GPSAdapter else None

        self.hardware_available = False
        if self.mode != "simulated":
            self._init_hardware()
        else:
            logger.info("Station initialized in explicit SIMULATED test mode.")

    def _init_hardware(self):
        """Attempts to initialize connected I2C sensors."""
        if self.bme280 and self.mode == "hardware":
            try:
                self.hardware_available = self.bme280.init_sensor()
                if self.hardware_available:
                    logger.info(f"Connected to {self.bme280.sensor_type} on I2C address 0x{self.bme280.address:02X}")
                else:
                    logger.warning("No BME280/BMP280 sensor detected on I2C bus.")
            except Exception as e:
                logger.warning(f"I2C detection error: {e}")
                self.hardware_available = False
        else:
            self.hardware_available = False

        if not self.hardware_available and self.mode == "hardware":
            logger.error("Hardware sensor offline. Simulation will NOT be used without explicit selection.")

    def _generate_simulated_reading(self) -> Dict[str, Any]:
        """Generates realistic diurnal simulated test readings."""
        now = datetime.now(timezone.utc)
        hour_fraction = now.hour + now.minute / 60.0 + now.second / 3600.0

        # Daily temperature sinusoidal cycle (peak ~15:00 UTC, trough ~05:00 UTC)
        temp_cycle = 4.0 * math.sin((hour_fraction - 9.0) * (2.0 * math.pi / 24.0))
        noise_temp = (random.random() - 0.5) * 0.4
        temp = round(24.5 + temp_cycle + noise_temp, 2)

        # Barometric pressure semi-diurnal atmospheric tide
        tide = 1.2 * math.cos((hour_fraction - 10.0) * (4.0 * math.pi / 24.0))
        noise_p = (random.random() - 0.5) * 0.3
        pressure = round(1013.25 + tide + noise_p, 2)

        # Relative humidity (inverse to temperature cycle)
        hum_cycle = -12.0 * math.sin((hour_fraction - 9.0) * (2.0 * math.pi / 24.0))
        noise_h = (random.random() - 0.5) * 1.5
        humidity = round(max(10.0, min(95.0, 58.0 + hum_cycle + noise_h)), 1)

        # Default simulated station coordinates (e.g. Bangalore, India)
        lat = 12.9716
        lon = 77.5946

        return {
            "temperature_c": temp,
            "pressure_hpa": pressure,
            "humidity_pct": humidity,
            "latitude": lat,
            "longitude": lon,
            "source": "simulated",
            "timestamp": now.isoformat()
        }

    def sample(self) -> Optional[Dict[str, Any]]:
        """
        Collects environmental sample from hardware sensors or simulation.
        Hardware failures NEVER silently create fabricated sensor readings;
        simulation strictly requires explicit selection.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Explicit simulation mode
        if self.mode == "simulated":
            return self._generate_simulated_reading()

        # Hardware mode
        if not self.hardware_available or not self.bme280 or not self.bme280.is_initialized:
            self._init_hardware()
            if not self.hardware_available:
                logger.error("Hardware sensor is unavailable. Zero telemetry recorded this cycle (simulation is not enabled).")
                return None

        try:
            temp_c, pressure_hpa, humidity_pct = self.bme280.read_raw()

            # If BMP280 lacks humidity cell, try DHT11 secondary sensor
            if humidity_pct is None and self.dht11 and self.dht11.enabled:
                _, dht_hum = self.dht11.read()
                if dht_hum is not None:
                    humidity_pct = dht_hum

            # Read GPS if enabled
            lat, lon = None, None
            if self.gps and self.gps.enabled:
                coords = self.gps.read_coordinates()
                if coords:
                    lat = coords.get("latitude")
                    lon = coords.get("longitude")

            return {
                "temperature_c": temp_c,
                "pressure_hpa": pressure_hpa,
                "humidity_pct": humidity_pct,
                "latitude": lat,
                "longitude": lon,
                "source": "hardware",
                "timestamp": now_iso
            }
        except Exception as e:
            logger.error(f"Hardware sensor read error: {e}. Reading dropped — simulated data will not be fabricated.")
            return None

    def transmit(self, payload: Dict[str, Any]) -> bool:
        """Sends JSON telemetry payload to server via HTTP POST with Bearer authentication."""
        endpoint = f"{self.server_url}/api/telemetry"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "VirtualAtmosphere-PiStation/1.0"
        }

        # Use urllib to eliminate external pip dependency (requests)
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                status_code = resp.getcode()
                response_data = json.loads(resp.read().decode("utf-8"))

                hr = response_data.get("heat_risk", {})
                risk_cat = hr.get("category", "Normal") if hr else "Normal"

                logger.info(
                    f"Transmitted [HTTP {status_code}] Source: {payload['source'].upper()} | "
                    f"Temp: {payload['temperature_c']}°C | "
                    f"Hum: {payload.get('humidity_pct', '--')}% | "
                    f"Press: {payload['pressure_hpa']} hPa | "
                    f"Heat Risk: {risk_cat}"
                )
                return True
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Server rejected telemetry [HTTP {e.code}]: {err_body}")
            return False
        except Exception as e:
            logger.error(f"Telemetry network error: {e}")
            return False

    def run(self):
        """Main sampling and transmission loop."""
        logger.info(f"Starting Virtual Atmosphere Telemetry Client -> {self.server_url}")
        logger.info(f"Polling Interval: {self.interval}s | Target Mode: {self.mode.upper()}")

        try:
            while True:
                payload = self.sample()
                if payload:
                    self.transmit(payload)
                else:
                    logger.warning("No sensor telemetry obtained this cycle.")
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Stopping telemetry client gracefully.")
        finally:
            if self.bme280:
                self.bme280.close()
            if self.gps:
                self.gps.close()

def main():
    parser = argparse.ArgumentParser(description="Virtual Atmosphere Raspberry Pi Telemetry Station")
    parser.add_argument("--server", default=os.environ.get("VA_SERVER_URL", "https://va.developerhut.in"), help="Virtual Atmosphere server URL")
    parser.add_argument("--token", default=os.environ.get("VA_INGEST_KEY", ""), help="Ingestion Bearer token")
    parser.add_argument("--interval", type=int, default=int(os.environ.get("VA_SAMPLING_INTERVAL", 10)), help="Sampling interval in seconds")
    parser.add_argument("--mode", choices=["hardware", "simulated"], default="hardware", help="Station operation mode (default: hardware)")
    parser.add_argument("--simulated", action="store_true", help="Explicitly enable simulated test telemetry mode")
    parser.add_argument("--dht-pin", type=int, default=4, help="DHT11 GPIO BCM pin (default 4)")
    parser.add_argument("--enable-dht", action="store_true", help="Enable DHT11 reading")
    parser.add_argument("--gps-port", default="/dev/serial0", help="NEO-6M GPS serial port")
    parser.add_argument("--enable-gps", action="store_true", help="Enable GPS receiver")

    args = parser.parse_args()
    selected_mode = "simulated" if args.simulated else args.mode

    client = PiTelemetryStation(
        server_url=args.server,
        token=args.token,
        interval_seconds=args.interval,
        mode=selected_mode,
        dht_pin=args.dht_pin,
        enable_dht=args.enable_dht,
        gps_port=args.gps_port,
        enable_gps=args.enable_gps
    )
    client.run()

if __name__ == "__main__":
    main()
