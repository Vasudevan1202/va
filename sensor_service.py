import os
import sys
import time
import math
import random
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from config import Config
import database
from alert_service import AlertService
from weather_service import WeatherService
from hardware_adapters import BME280Driver

logger = logging.getLogger("virtual_atmosphere.sensor")

class BMP280Driver:
    """
    Direct I2C driver for the Bosch BMP280 Barometric Pressure & Temperature Sensor.
    Implements hardware detection, register calibration readout, and datasheet compensation.
    Compatible with Raspberry Pi I2C via smbus2.
    """
    CHIP_ID_REG = 0xD0
    RESET_REG = 0xE0
    STATUS_REG = 0xF3
    CTRL_MEAS_REG = 0xF4
    CONFIG_REG = 0xF5
    PRESS_MSB_REG = 0xF7

    BMP280_CHIP_IDS = [0x58, 0x56, 0x57, 0x60] # 0x58 is standard BMP280, 0x60 is BME280 compatibility

    def __init__(self, bus_num: int = 1, address_candidates: Optional[list] = None):
        self.bus_num = bus_num
        self.address_candidates = address_candidates or [0x76, 0x77]
        self.address = None
        self.bus = None
        self.is_initialized = False
        self.calib = {}
        self.t_fine = 0

    def init_sensor(self) -> bool:
        """Attempts to open I2C bus and locate BMP280 on candidate addresses."""
        try:
            import smbus2
        except ImportError:
            logger.warning("smbus2 module not installed. Hardware I2C is unavailable.")
            return False

        try:
            self.bus = smbus2.SMBus(self.bus_num)
        except Exception as e:
            logger.warning(f"Failed to open I2C bus {self.bus_num}: {e}")
            return False

        for addr in self.address_candidates:
            try:
                chip_id = self.bus.read_byte_data(addr, self.CHIP_ID_REG)
                if chip_id in self.BMP280_CHIP_IDS:
                    self.address = addr
                    logger.info(f"BMP280 detected on I2C bus {self.bus_num} at 0x{addr:02X} (Chip ID: 0x{chip_id:02X})")
                    self._read_calibration(smbus2)
                    self._configure_sensor()
                    self.is_initialized = True
                    return True
                else:
                    logger.debug(f"Address 0x{addr:02X} responded with unexpected Chip ID 0x{chip_id:02X}")
            except Exception as e:
                logger.debug(f"Probing I2C address 0x{addr:02X} failed: {e}")

        logger.warning(f"No BMP280 sensor detected on bus {self.bus_num} at {self.address_candidates}")
        return False

    def _read_calibration(self, smbus2):
        """Reads calibration coefficients from registers 0x88 through 0xA1."""
        # Read 24 bytes of calibration data
        cal = self.bus.read_i2c_block_data(self.address, 0x88, 24)

        def to_uint16(idx):
            return (cal[idx + 1] << 8) | cal[idx]

        def to_int16(idx):
            val = to_uint16(idx)
            return val - 65536 if val > 32767 else val

        self.calib = {
            "dig_T1": to_uint16(0),
            "dig_T2": to_int16(2),
            "dig_T3": to_int16(4),
            "dig_P1": to_uint16(6),
            "dig_P2": to_int16(8),
            "dig_P3": to_int16(10),
            "dig_P4": to_int16(12),
            "dig_P5": to_int16(14),
            "dig_P6": to_int16(16),
            "dig_P7": to_int16(18),
            "dig_P8": to_int16(20),
            "dig_P9": to_int16(22),
        }

    def _configure_sensor(self):
        """Configures normal mode, 16x oversampling for pressure and 2x for temperature."""
        # Standby 62.5ms (010), filter coefficient 16 (100) -> 0x50
        self.bus.write_byte_data(self.address, self.CONFIG_REG, 0x50)
        # osrs_t = 2 (010), osrs_p = 16 (101), mode = normal (11) -> 01010111 = 0x57
        self.bus.write_byte_data(self.address, self.CTRL_MEAS_REG, 0x57)

    def read_raw(self) -> Tuple[float, float]:
        """
        Reads raw registers and applies Bosch BMP280 compensation formulas.
        Returns (temperature_c, pressure_hpa).
        """
        if not self.is_initialized:
            raise RuntimeError("BMP280 sensor is not initialized.")

        # Read 6 data bytes: press_msb, press_lsb, press_xlsb, temp_msb, temp_lsb, temp_xlsb
        data = self.bus.read_i2c_block_data(self.address, self.PRESS_MSB_REG, 6)
        raw_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        raw_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)

        # Temperature compensation (from Bosch BMP280 datasheet)
        t1 = self.calib["dig_T1"]
        t2 = self.calib["dig_T2"]
        t3 = self.calib["dig_T3"]

        var1 = ((raw_t / 16384.0) - (t1 / 1024.0)) * t2
        var2 = (((raw_t / 131072.0) - (t1 / 8192.0)) ** 2) * t3
        self.t_fine = int(var1 + var2)
        temp_c = (var1 + var2) / 5120.0

        # Pressure compensation
        p1 = self.calib["dig_P1"]
        p2 = self.calib["dig_P2"]
        p3 = self.calib["dig_P3"]
        p4 = self.calib["dig_P4"]
        p5 = self.calib["dig_P5"]
        p6 = self.calib["dig_P6"]
        p7 = self.calib["dig_P7"]
        p8 = self.calib["dig_P8"]
        p9 = self.calib["dig_P9"]

        p_var1 = (self.t_fine / 2.0) - 64000.0
        p_var2 = p_var1 * p_var1 * p6 / 32768.0
        p_var2 = p_var2 + (p_var1 * p5 * 2.0)
        p_var2 = (p_var2 / 4.0) + (p4 * 65536.0)
        p_var1 = ((p3 * p_var1 * p_var1 / 524288.0) + (p2 * p_var1)) / 524288.0
        p_var1 = (1.0 + (p_var1 / 32768.0)) * p1

        if p_var1 == 0:
            pressure_hpa = 0.0
        else:
            p = 1048576.0 - raw_p
            p = (p - (p_var2 / 4096.0)) * 6250.0 / p_var1
            p_var1 = (p9 * p * p) / 2147483648.0
            p_var2 = p * p8 / 32768.0
            p = p + ((p_var1 + p_var2 + p7) / 16.0)
            pressure_hpa = p / 100.0 # Convert Pa to hPa

        return temp_c, pressure_hpa

    def close(self):
        """Closes the I2C bus."""
        if self.bus:
            try:
                self.bus.close()
            except Exception:
                pass
            self.bus = None
        self.is_initialized = False


class SensorService:
    """
    Orchestrates sensor sampling in a background thread.
    Manages both Live I2C Hardware mode and deterministic Demo mode.
    Validates physical ranges, stores readings in SQLite, and forwards to AlertService.
    """

    def __init__(self, mode: Optional[str] = None, db_path: Optional[str] = None):
        self.mode = (mode or Config.MODE).lower()
        self.db_path = db_path or Config.DATABASE_PATH
        self.driver = None
        self.is_running = False
        self.worker_thread = None

        # Telemetry State
        self.lock = threading.Lock()
        self.is_connected = False
        self.last_reading_time: Optional[str] = None
        self.last_reading_val: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self.consecutive_errors: int = 0
        self.detected_address: Optional[str] = None
        self.i2c_bus_num: int = Config.I2C_BUS

        # DHT11 Ingested Telemetry State (from Raspberry Pi / Arduino pipeline)
        self.last_dht11_reading: Optional[Dict[str, Any]] = None
        self.last_dht11_time: Optional[str] = None

        # Demo Mode state generator variables
        self.demo_temp_base = 24.5
        self.demo_pressure_base = 1013.25
        self.demo_spike_active = False # Can be toggled for alert verification

    def set_mode(self, new_mode: str):
        """Switches runtime mode between 'demo' and 'live'."""
        with self.lock:
            self.mode = new_mode.lower()
            self.consecutive_errors = 0
            self.last_error = None
            if self.mode == "demo":
                self.is_connected = True
            else:
                self.is_connected = False
                self.detected_address = None
                if self.driver:
                    self.driver.close()
                    self.driver = None

    def update_dht11(self, reading_dict: Dict[str, Any]):
        """Updates in-memory telemetry state for DHT11 remote readings."""
        with self.lock:
            self.last_dht11_reading = reading_dict
            self.last_dht11_time = reading_dict.get("timestamp") or datetime.now(timezone.utc).isoformat()

    def start(self):
        """Starts the background polling worker."""
        if self.is_running:
            return
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._run_loop, name="SensorWorker", daemon=True)
        self.worker_thread.start()
        logger.info(f"SensorService worker started in '{self.mode}' mode.")

    def stop(self):
        """Stops the worker thread."""
        self.is_running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=3.0)
        if self.driver:
            self.driver.close()
        logger.info("SensorService worker stopped.")

    def _init_hardware(self) -> bool:
        """Initializes hardware driver in live mode."""
        if self.driver is None:
            self.driver = BME280Driver(
                bus_num=self.i2c_bus_num,
                address_candidates=Config.I2C_ADDRESS_CANDIDATES
            )
        success = self.driver.init_sensor()
        if success:
            self.detected_address = f"0x{self.driver.address:02X}"
            self.is_connected = True
            self.last_error = None
            self.consecutive_errors = 0
        else:
            self.detected_address = None
            self.is_connected = False
        return success

    def _simulate_reading(self) -> Tuple[float, float, float, str]:
        """
        Generates realistic environmental values for simulated/demo mode.
        Models time-of-day temperature curve (cool morning, warmer afternoon),
        atmospheric pressure diurnal tide, and realistic relative humidity (inverse to temperature).
        """
        now = datetime.now(timezone.utc)
        # Hour fraction 0.0 to 24.0
        hour_fraction = now.hour + now.minute / 60.0 + now.second / 3600.0

        # Daily temperature sinusoidal cycle (peaks around 15:00 UTC, trough around 05:00 UTC)
        # Mean 24°C, Amplitude 4°C -> 20°C to 28°C
        temp_cycle = 4.0 * math.sin((hour_fraction - 9.0) * (2.0 * math.pi / 24.0))
        noise_temp = (random.random() - 0.5) * 0.4 # ±0.2°C noise
        temp = self.demo_temp_base + temp_cycle + noise_temp

        if self.demo_spike_active:
            # Simulated high-temperature event to reliably exceed the 35°C threshold
            temp = max(temp + 15.0, 36.5)

        # Pressure semi-diurnal atmospheric tide variation (peaks at 10:00 and 22:00)
        tide = 1.2 * math.cos((hour_fraction - 10.0) * (4.0 * math.pi / 24.0))
        noise_p = (random.random() - 0.5) * 0.3
        pressure = self.demo_pressure_base + tide + noise_p

        # Relative humidity diurnal cycle: generally inverse to temperature
        # Cool mornings have higher humidity (~68-75%), warm afternoons lower (~45-55%)
        hum_cycle = -12.0 * math.sin((hour_fraction - 9.0) * (2.0 * math.pi / 24.0))
        noise_h = (random.random() - 0.5) * 1.5
        humidity = max(10.0, min(95.0, 58.0 + hum_cycle + noise_h))

        # Explicit data source attribution
        source = "demo" if self.mode == "demo" else "simulated"

        return round(temp, 2), round(pressure, 2), round(humidity, 1), source

    def read_sensor_once(self) -> Optional[Dict[str, Any]]:
        """
        Performs one measurement read cycle (either Live hardware or Demo simulation).
        Validates value ranges and saves to database if valid.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        if self.mode in ("demo", "simulated", "simulation"):
            temp_c, pressure_hpa, humidity_pct, source = self._simulate_reading()
            valid, _ = WeatherService.validate_reading(temp_c, pressure_hpa, humidity_pct)
            validity = "valid" if valid else "out_of_range"

            # Compute heat index if criteria met
            heat_index_c = WeatherService.compute_heat_index(temp_c, humidity_pct)

            # Save to SQLite
            record_id = database.insert_reading(
                temperature_c=temp_c,
                pressure_hpa=pressure_hpa,
                source=source,
                validity_status=validity,
                timestamp=now_iso,
                humidity_pct=humidity_pct,
                heat_index_c=heat_index_c,
                db_path=self.db_path
            )

            with self.lock:
                self.is_connected = True
                self.last_reading_time = now_iso
                self.last_reading_val = {
                    "id": record_id,
                    "timestamp": now_iso,
                    "temperature_c": temp_c,
                    "pressure_hpa": pressure_hpa,
                    "humidity_pct": humidity_pct,
                    "heat_index_c": heat_index_c,
                    "source": source,
                    "validity_status": validity
                }
                self.last_error = None
                self.consecutive_errors = 0

            # Evaluate alerts if reading is valid
            if validity == "valid":
                AlertService.evaluate_reading(temp_c, db_path=self.db_path)

            return self.last_reading_val

        else:
            # LIVE HARDWARE MODE
            if not self.is_connected or not self.driver or not self.driver.is_initialized:
                init_ok = self._init_hardware()
                if not init_ok:
                    with self.lock:
                        self.is_connected = False
                        self.consecutive_errors += 1
                        self.last_error = "BME280/BMP280 sensor not detected on I2C bus. Check wiring."
                    logger.debug("Live mode poll: Sensor not connected.")
                    # Do NOT fabricate measurements when hardware is disconnected!
                    return None

            try:
                # read_raw returns (temp_c, pressure_hpa, humidity_pct)
                temp_c, pressure_hpa, humidity_pct = self.driver.read_raw()
                valid, _ = WeatherService.validate_reading(temp_c, pressure_hpa, humidity_pct)
                validity = "valid" if valid else "out_of_range"
                if not valid:
                    logger.warning(f"Sensor reading out of range: {temp_c}°C, {pressure_hpa} hPa, {humidity_pct}%")

                heat_index_c = WeatherService.compute_heat_index(temp_c, humidity_pct)

                record_id = database.insert_reading(
                    temperature_c=temp_c,
                    pressure_hpa=pressure_hpa,
                    source="hardware",
                    validity_status=validity,
                    timestamp=now_iso,
                    humidity_pct=humidity_pct,
                    heat_index_c=heat_index_c,
                    db_path=self.db_path
                )

                with self.lock:
                    self.is_connected = True
                    self.last_reading_time = now_iso
                    self.last_reading_val = {
                        "id": record_id,
                        "timestamp": now_iso,
                        "temperature_c": round(temp_c, 2),
                        "pressure_hpa": round(pressure_hpa, 2),
                        "humidity_pct": humidity_pct,
                        "heat_index_c": heat_index_c,
                        "source": "hardware",
                        "validity_status": validity
                    }
                    self.last_error = None
                    self.consecutive_errors = 0

                if validity == "valid":
                    AlertService.evaluate_reading(temp_c, db_path=self.db_path)

                return self.last_reading_val

            except Exception as e:
                with self.lock:
                    self.is_connected = False
                    self.consecutive_errors += 1
                    self.last_error = f"I2C read exception: {str(e)}"
                    if self.driver:
                        self.driver.close()
                logger.error(f"Live hardware read error: {e}")
                # Fail gracefully: do not fabricate records
                return None

    def _run_loop(self):
        """Continuous polling loop running in the background thread."""
        while self.is_running:
            try:
                # Read interval setting from DB
                settings = database.get_settings(db_path=self.db_path)
                interval = max(2, settings.get("sampling_interval_seconds", Config.SAMPLING_INTERVAL_SECONDS))

                self.read_sensor_once()

            except Exception as e:
                logger.error(f"Unexpected error in sensor polling loop: {e}", exc_info=True)

            # Sleep in 0.5s increments to respond promptly to stop signal
            for _ in range(int(interval * 2)):
                if not self.is_running:
                    break
                time.sleep(0.5)

    def get_status(self, db_path: Optional[str] = None) -> Dict[str, Any]:
        """Returns the current sensor and backend diagnostic status."""
        active_db = db_path or self.db_path
        with self.lock:
            # Calculate DHT11 freshness
            # In serverless environments, worker memory is isolated; fetch latest real reading from DB if cache is empty
            last_dht11_reading = self.last_dht11_reading
            last_dht11_time = self.last_dht11_time
            if not last_dht11_reading:
                try:
                    db_dht = database.get_latest_dht11_reading(db_path=active_db, real_only=(self.mode == "live"))
                    if db_dht:
                        dht_dict = dict(db_dht)
                        hum_val = dht_dict.get("humidity_percent", dht_dict.get("humidity_pct"))
                        dht_dict["humidity_percent"] = hum_val
                        dht_dict["humidity_pct"] = hum_val
                        last_dht11_reading = dht_dict
                        last_dht11_time = dht_dict.get("timestamp")
                        self.last_dht11_reading = dht_dict
                        self.last_dht11_time = last_dht11_time
                except Exception as e:
                    logger.debug(f"Could not load latest DHT11 from database: {e}")

            dht11_freshness = None
            if last_dht11_time:
                try:
                    dht_dt = datetime.fromisoformat(last_dht11_time.replace("Z", "+00:00"))
                    dht11_freshness = max(0.0, round((datetime.now(timezone.utc) - dht_dt).total_seconds(), 1))
                except Exception:
                    pass

            dht11_is_active = bool(dht11_freshness is not None and dht11_freshness < 180)
            dht11_status = {
                "active": dht11_is_active,
                "last_reading_time": last_dht11_time,
                "data_freshness_seconds": dht11_freshness,
                "latest": last_dht11_reading
            }

            # Calculate primary sensor data freshness in seconds
            freshness_seconds = None
            if self.last_reading_time:
                try:
                    last_dt = datetime.fromisoformat(self.last_reading_time.replace("Z", "+00:00"))
                    freshness_seconds = max(0.0, round((datetime.now(timezone.utc) - last_dt).total_seconds(), 1))
                except Exception:
                    pass

            sensor_model = "BME280"
            if self.mode in ("demo", "simulated", "simulation"):
                source_state = "simulated"
            elif self.is_connected:
                source_state = "hardware"
                if self.driver:
                    sensor_model = getattr(self.driver, "sensor_type", "BME280")
            elif dht11_is_active:
                source_state = "hardware"
                sensor_model = "DHT11"
            else:
                source_state = "unavailable"

            # In live mode when no local I2C BMP280 is attached, report remote DHT11 telemetry state
            display_last_time = self.last_reading_time or (last_dht11_time if self.mode == "live" else None)
            display_freshness = freshness_seconds if self.last_reading_time else (dht11_freshness if self.mode == "live" else None)
            display_is_connected = self.is_connected or (dht11_is_active if self.mode == "live" else False)

            return {
                "mode": self.mode,
                "data_source": source_state,
                "is_connected": display_is_connected,
                "sensor_type": sensor_model,
                "bus": self.i2c_bus_num,
                "address": self.detected_address or ("0x76/0x77 (Scanning)" if self.mode == "live" and not dht11_is_active else ("DHT11 (Remote)" if dht11_is_active else ("0x76/0x77 (Scanning)" if self.mode == "live" else "Simulated"))),
                "last_reading_time": display_last_time,
                "data_freshness_seconds": display_freshness,
                "consecutive_errors": self.consecutive_errors,
                "last_error": self.last_error,
                "demo_spike_active": self.demo_spike_active,
                "dht11": dht11_status,
                "server_time": datetime.now(timezone.utc).isoformat()
            }

    def ensure_sample(self):
        """
        Ensures telemetry data exists and stays fresh in serverless environments
        where long-running background threads are suspended.
        """
        now = datetime.now(timezone.utc)
        need_read = False
        with self.lock:
            if not self.last_reading_time:
                need_read = True
            else:
                try:
                    last_dt = datetime.fromisoformat(self.last_reading_time)
                    if (now - last_dt).total_seconds() >= 10:
                        need_read = True
                except Exception:
                    need_read = True

        if need_read:
            self.read_sensor_once()
