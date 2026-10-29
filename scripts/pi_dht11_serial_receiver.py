#!/usr/bin/env python3
"""
Virtual Atmosphere (VA) - Raspberry Pi 3 Model B+ DHT11 Serial Ingestion Client
Reads DHT11 temperature & humidity readings transmitted over serial (USB) from
an Arduino Mega 2560, parses CSV or formatted text, and sends authenticated
telemetry to the Virtual Atmosphere endpoint POST /api/ingest/dht11.

Hardware Pipeline:
  DHT11 Sensor -> Arduino Mega 2560 -> USB Cable (/dev/ttyUSB0 @ 9600 baud)
  -> Raspberry Pi 3 Model B+ -> HTTP POST -> Virtual Atmosphere Dashboard

Usage:
  # Run live on Raspberry Pi:
  python3 scripts/pi_dht11_serial_receiver.py \
    --server https://va.developerhut.in \
    --token <YOUR_SECRET_TOKEN> \
    --port /dev/ttyUSB0 \
    --baud 9600

  # Test locally with simulated serial inputs:
  python3 scripts/pi_dht11_serial_receiver.py \
    --server http://127.0.0.1:5000 \
    --token dev-local-dht11-key \
    --mock
"""

import os
import re
import sys
import time
import json
import logging
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [DHT11-Bridge] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("va.dht11_receiver")

class DHT11SerialBridge:
    """Manages serial reading from Arduino Mega 2560 and HTTP transmission to Virtual Atmosphere."""

    def __init__(
        self,
        server_url: str,
        token: str,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        source: str = "raspberry_pi_dht11",
        timeout: float = 2.0,
        min_interval_seconds: float = 5.0,
        mock_mode: bool = False
    ):
        self.server_url = server_url.rstrip("/")
        self.endpoint = f"{self.server_url}/api/ingest/dht11"
        self.token = token
        self.port = port
        self.baudrate = baudrate
        self.source = source
        self.timeout = timeout
        self.min_interval = min_interval_seconds
        self.mock_mode = mock_mode
        self.serial_conn = None
        self.last_transmit_time = 0.0

        # Regex patterns for parsing Arduino output
        # Format 1: "Temperature: 33.0 °C | Humidity: 46.0%"
        self.pattern_formatted = re.compile(
            r"Temperature:\s*([+-]?\d+(?:\.\d+)?)\s*°?C?\s*\|\s*Humidity:\s*([+-]?\d+(?:\.\d+)?)\s*%",
            re.IGNORECASE
        )
        # Format 2: "Temp: 33.0, Hum: 46.0" or "T=33.0, H=46.0"
        self.pattern_labeled = re.compile(
            r"(?:Temp(?:erature)?|T)\s*[:=]\s*([+-]?\d+(?:\.\d+)?).*?(?:Hum(?:idity)?|H|RH)\s*[:=]\s*([+-]?\d+(?:\.\d+)?)",
            re.IGNORECASE
        )

    def parse_reading(self, raw_line: str) -> Optional[Tuple[float, float]]:
        """
        Parses raw serial string from Arduino Mega 2560.
        Supports:
          1. Formatted print: 'Temperature: 33.0 °C | Humidity: 46.0%'
          2. Raw CSV: '33.0, 46.0' or '33.0,46.0'
          3. Labeled key-value: 'Temp: 33.0, Humidity: 46.0'
        Returns (temperature_c, humidity_percent) or None if unparseable.
        """
        line = raw_line.strip()
        if not line:
            return None

        # Try formatted string match
        m1 = self.pattern_formatted.search(line)
        if m1:
            try:
                temp = float(m1.group(1))
                hum = float(m1.group(2))
                return temp, hum
            except (ValueError, TypeError):
                pass

        # Try labeled string match
        m2 = self.pattern_labeled.search(line)
        if m2:
            try:
                temp = float(m2.group(1))
                hum = float(m2.group(2))
                return temp, hum
            except (ValueError, TypeError):
                pass

        # Try pure CSV match: "33.0, 46.0" or "33.0,46.0"
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) >= 2:
            try:
                # Remove common non-numeric suffixes (°C, %, etc.)
                clean_t = re.sub(r"[^\d.-]", "", parts[0])
                clean_h = re.sub(r"[^\d.-]", "", parts[1])
                temp = float(clean_t)
                hum = float(clean_h)
                return temp, hum
            except (ValueError, TypeError):
                pass

        return None

    def connect_serial(self) -> bool:
        """Opens serial connection to Arduino Mega."""
        if self.mock_mode:
            logger.info("Running in mock mode: physical serial connection bypassed.")
            return True

        try:
            import serial
        except ImportError:
            logger.error(
                "pyserial package is not installed. Install it on your Raspberry Pi using:\n"
                "  pip3 install pyserial"
            )
            return False

        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            # Allow Arduino time to reset on DTR assertion
            time.sleep(2.0)
            self.serial_conn.reset_input_buffer()
            logger.info(f"Connected to Arduino Mega 2560 on {self.port} at {self.baudrate} baud.")
            return True
        except Exception as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            self.serial_conn = None
            return False

    def read_line(self) -> Optional[str]:
        """Reads a line of text from the serial connection or mock generator."""
        if self.mock_mode:
            # Deterministic mock reading for testing
            time.sleep(self.min_interval)
            return "Temperature: 33.0 °C | Humidity: 46.0%"

        if not self.serial_conn or not self.serial_conn.is_open:
            if not self.connect_serial():
                time.sleep(3.0)
                return None

        try:
            raw_bytes = self.serial_conn.readline()
            if not raw_bytes:
                return None
            return raw_bytes.decode("utf-8", errors="replace").strip()
        except Exception as e:
            logger.warning(f"Serial read exception on {self.port}: {e}")
            try:
                if self.serial_conn:
                    self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None
            return None

    def transmit(self, temp_c: float, hum_pct: float) -> bool:
        """Sends authenticated JSON telemetry to POST /api/ingest/dht11."""
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "temperature_c": temp_c,
            "humidity_percent": hum_pct,
            "timestamp": now_iso,
            "source": self.source
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "VirtualAtmosphere-PiDHT11Bridge/1.0"
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                status_code = resp.getcode()
                resp_data = json.loads(resp.read().decode("utf-8"))
                record_id = resp_data.get("id")
                risk = resp_data.get("heat_risk", {})
                risk_cat = risk.get("category", "Normal") if risk else "Normal"

                logger.info(
                    f"✓ Ingested [HTTP {status_code}] (ID #{record_id}) | "
                    f"Temp: {temp_c:.1f}°C | Hum: {hum_pct:.1f}% | "
                    f"Risk: {risk_cat} | Source: {self.source}"
                )
                self.last_transmit_time = time.time()
                return True
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"✗ Server rejected DHT11 ingestion [HTTP {e.code}]: {err_body}")
            return False
        except urllib.error.URLError as e:
            logger.error(f"✗ Network connection error reaching {self.server_url}: {e.reason}")
            return False
        except Exception as e:
            logger.error(f"✗ Unexpected error during transmission: {e}")
            return False

    def run(self):
        """Continuous ingestion bridge worker loop."""
        logger.info("=" * 65)
        logger.info(" Virtual Atmosphere - Raspberry Pi DHT11 Serial Ingestion Bridge")
        logger.info("=" * 65)
        logger.info(f"Target Server : {self.server_url}")
        logger.info(f"Endpoint      : {self.endpoint}")
        logger.info(f"Serial Port   : {self.port} @ {self.baudrate} baud")
        logger.info(f"Data Source   : {self.source}")
        logger.info(f"Min Interval  : {self.min_interval}s")
        logger.info(f"Mock Mode     : {'Enabled' if self.mock_mode else 'Disabled (Physical Hardware)'}")
        logger.info("=" * 65)

        if not self.token:
            logger.warning(
                "WARNING: No Bearer token provided! Telemetry requests will likely be rejected with 401 Unauthorized.\n"
                "Provide a token via --token <SECRET> or environment variable VA_DHT11_INGEST_KEY."
            )

        if not self.connect_serial() and not self.mock_mode:
            logger.warning(f"Could not open {self.port} immediately. Will retry in main loop...")

        try:
            while True:
                line = self.read_line()
                if line:
                    logger.debug(f"Serial RX: {line}")
                    parsed = self.parse_reading(line)
                    if parsed:
                        temp_c, hum_pct = parsed
                        now = time.time()
                        # Rate throttle to avoid flooding server if Arduino outputs at 10Hz
                        if (now - self.last_transmit_time) >= self.min_interval:
                            self.transmit(temp_c, hum_pct)
                        else:
                            logger.debug(f"Throttled reading: {temp_c}°C, {hum_pct}% (waiting for interval)")
                    else:
                        logger.debug(f"Ignored non-matching line: {line}")
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Stopping DHT11 serial bridge gracefully.")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                logger.info("Serial port closed.")

def main():
    parser = argparse.ArgumentParser(description="Virtual Atmosphere DHT11 Serial Ingestion Bridge")
    parser.add_argument(
        "--server",
        default=os.environ.get("VA_SERVER_URL", "https://va.developerhut.in"),
        help="Virtual Atmosphere base URL (default: https://va.developerhut.in)"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("VA_DHT11_INGEST_KEY") or os.environ.get("VA_INGEST_KEY", ""),
        help="Ingestion Bearer Secret Token (or set VA_DHT11_INGEST_KEY / VA_INGEST_KEY)"
    )
    parser.add_argument(
        "--port",
        default=os.environ.get("VA_SERIAL_PORT", "/dev/ttyUSB0"),
        help="Serial port connected to Arduino Mega (default: /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=int(os.environ.get("VA_SERIAL_BAUD", 9600)),
        help="Baud rate (default: 9600)"
    )
    parser.add_argument(
        "--source",
        default="raspberry_pi_dht11",
        help="Source attribution tag (default: 'raspberry_pi_dht11')"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("VA_SAMPLING_INTERVAL", 5.0)),
        help="Minimum transmission interval in seconds (default: 5.0)"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Simulate serial stream without physical serial hardware"
    )

    args = parser.parse_args()

    bridge = DHT11SerialBridge(
        server_url=args.server,
        token=args.token,
        port=args.port,
        baudrate=args.baud,
        source=args.source,
        min_interval_seconds=args.interval,
        mock_mode=args.mock
    )
    bridge.run()

if __name__ == "__main__":
    main()
