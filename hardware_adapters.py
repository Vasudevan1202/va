"""
Virtual Atmosphere (VA) - Raspberry Pi Hardware Adapters
Supports:
- Bosch BME280 / BMP280 Environmental Sensors (I2C)
  * Distinguishes BME280 (Chip ID 0x60, Temperature, Pressure, Relative Humidity)
    from BMP280 (Chip ID 0x58, Temperature & Pressure only).
- DHT11 Digital Humidity & Temperature Sensor (GPIO, disabled by default)
- u-blox NEO-6M GPS Module (UART / Serial, disabled by default, NMEA parser)

All hardware-specific modules (smbus2, serial, RPi.GPIO) are imported conditionally
with try/except blocks so execution never crashes on Windows or Vercel serverless.
"""

import math
import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("virtual_atmosphere.hardware")

# ---------------------------------------------------------------------------
# Bosch BME280 / BMP280 Driver
# ---------------------------------------------------------------------------
class BME280Driver:
    """
    Direct I2C driver for Bosch Sensortec BME280 and BMP280 sensors.
    Detects hardware, reads factory calibration trims, and applies datasheet
    compensation equations.
    """
    CHIP_ID_REG = 0xD0
    RESET_REG = 0xE0
    STATUS_REG = 0xF3
    CTRL_HUM_REG = 0xF2
    CTRL_MEAS_REG = 0xF4
    CONFIG_REG = 0xF5
    PRESS_MSB_REG = 0xF7

    BMP280_CHIP_IDS = [0x58, 0x56, 0x57]
    BME280_CHIP_IDS = [0x60]

    def __init__(self, bus_num: int = 1, address_candidates: Optional[list] = None):
        self.bus_num = bus_num
        self.address_candidates = address_candidates or [0x76, 0x77]
        self.address: Optional[int] = None
        self.bus = None
        self.chip_id: Optional[int] = None
        self.sensor_type: str = "Unknown"  # "BME280", "BMP280", or "Unknown"
        self.has_humidity: bool = False
        self.is_initialized: bool = False
        self.calib: Dict[str, Any] = {}
        self.t_fine: int = 0

    def init_sensor(self) -> bool:
        """Attempts to open I2C bus and locate BME280 or BMP280 on candidate addresses."""
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
                if chip_id in self.BME280_CHIP_IDS:
                    self.address = addr
                    self.chip_id = chip_id
                    self.sensor_type = "BME280"
                    self.has_humidity = True
                    logger.info(f"BME280 detected on I2C bus {self.bus_num} at 0x{addr:02X} (Chip ID: 0x{chip_id:02X})")
                    self._read_calibration()
                    self._configure_sensor()
                    self.is_initialized = True
                    return True
                elif chip_id in self.BMP280_CHIP_IDS:
                    self.address = addr
                    self.chip_id = chip_id
                    self.sensor_type = "BMP280"
                    self.has_humidity = False
                    logger.info(f"BMP280 detected on I2C bus {self.bus_num} at 0x{addr:02X} (Chip ID: 0x{chip_id:02X}, Humidity not supported)")
                    self._read_calibration()
                    self._configure_sensor()
                    self.is_initialized = True
                    return True
                else:
                    logger.debug(f"Address 0x{addr:02X} responded with unexpected Chip ID 0x{chip_id:02X}")
            except Exception as e:
                logger.debug(f"Probing I2C address 0x{addr:02X} failed: {e}")

        logger.warning(f"No BME280/BMP280 sensor detected on bus {self.bus_num} at {self.address_candidates}")
        return False

    def _read_calibration(self):
        """Reads factory calibration registers."""
        # Temperature & Pressure calibration (24 bytes from 0x88 to 0x9F)
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

        # If BME280, read humidity calibration registers
        if self.has_humidity:
            # dig_H1 at 0xA1
            self.calib["dig_H1"] = self.bus.read_byte_data(self.address, 0xA1)
            # dig_H2 to dig_H6 from 0xE1 to 0xE7 (7 bytes)
            h_cal = self.bus.read_i2c_block_data(self.address, 0xE1, 7)

            h2 = (h_cal[1] << 8) | h_cal[0]
            self.calib["dig_H2"] = h2 - 65536 if h2 > 32767 else h2
            self.calib["dig_H3"] = h_cal[2]

            h4 = (h_cal[3] << 4) | (h_cal[4] & 0x0F)
            self.calib["dig_H4"] = h4 - 4096 if h4 > 2047 else h4

            h5 = (h_cal[5] << 4) | (h_cal[4] >> 4)
            self.calib["dig_H5"] = h5 - 4096 if h5 > 2047 else h5

            h6 = h_cal[6]
            self.calib["dig_H6"] = h6 - 256 if h6 > 127 else h6

    def _configure_sensor(self):
        """Sets oversampling, filter, and normal power mode."""
        # For BME280: ctrl_hum (0xF2) must be written BEFORE ctrl_meas (0xF4)
        if self.has_humidity:
            # Humidity oversampling x1 (001)
            self.bus.write_byte_data(self.address, self.CTRL_HUM_REG, 0x01)

        # Standby 62.5ms (010), filter coefficient 16 (100) -> 0x50
        self.bus.write_byte_data(self.address, self.CONFIG_REG, 0x50)

        # osrs_t = 2 (010), osrs_p = 16 (101), mode = normal (11) -> 01010111 = 0x57
        self.bus.write_byte_data(self.address, self.CTRL_MEAS_REG, 0x57)

    def read_raw(self) -> Tuple[float, float, Optional[float]]:
        """
        Reads raw registers and applies Bosch compensation formulas.
        Returns: (temperature_c, pressure_hpa, humidity_pct or None)
        """
        if not self.is_initialized:
            raise RuntimeError(f"{self.sensor_type} sensor is not initialized.")

        # Read measurements: 6 bytes for BMP280, 8 bytes for BME280
        num_bytes = 8 if self.has_humidity else 6
        data = self.bus.read_i2c_block_data(self.address, self.PRESS_MSB_REG, num_bytes)

        raw_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        raw_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)

        # Temperature compensation (Bosch datasheet)
        t1 = self.calib["dig_T1"]
        t2 = self.calib["dig_T2"]
        t3 = self.calib["dig_T3"]

        var1 = ((raw_t / 16384.0) - (t1 / 1024.0)) * t2
        var2 = (((raw_t / 131072.0) - (t1 / 8192.0)) ** 2) * t3
        self.t_fine = int(var1 + var2)
        temp_c = (var1 + var2) / 5120.0

        # Pressure compensation (Bosch datasheet)
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
            pressure_hpa = p / 100.0  # Convert Pa to hPa

        # Humidity compensation (Bosch BME280 datasheet)
        humidity_pct: Optional[float] = None
        if self.has_humidity and len(data) >= 8:
            raw_h = (data[6] << 8) | data[7]
            h1 = self.calib["dig_H1"]
            h2 = self.calib["dig_H2"]
            h3 = self.calib["dig_H3"]
            h4 = self.calib["dig_H4"]
            h5 = self.calib["dig_H5"]
            h6 = self.calib["dig_H6"]

            var_h = float(self.t_fine) - 76800.0
            if var_h != 0.0:
                var_h = (
                    (raw_h - ((h4 * 64.0) + (h5 / 16384.0 * var_h)))
                    * (h2 / 65536.0 * (1.0 + (h6 / 67108864.0 * var_h * (1.0 + (h3 / 67108864.0 * var_h)))))
                )
                var_h = var_h * (1.0 - (h1 * var_h / 524288.0))
                humidity_pct = max(0.0, min(100.0, var_h))

        return round(temp_c, 2), round(pressure_hpa, 2), (round(humidity_pct, 1) if humidity_pct is not None else None)

    def close(self):
        """Closes the I2C bus."""
        if self.bus:
            try:
                self.bus.close()
            except Exception:
                pass
            self.bus = None
        self.is_initialized = False


# ---------------------------------------------------------------------------
# DHT11 Digital Sensor Adapter (Disabled by Default)
# ---------------------------------------------------------------------------
class DHT11Adapter:
    """
    Adapter for DHT11 single-wire digital humidity & temperature sensor.
    Disabled by default; protects against missing libraries on non-Pi platforms.
    """
    def __init__(self, pin: int = 4, enabled: bool = False):
        self.pin = pin
        self.enabled = enabled
        self._device = None

    def read(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Reads (temperature_c, humidity_pct).
        Returns (None, None) if disabled or library unavailable.
        """
        if not self.enabled:
            return None, None

        try:
            # Try adafruit_dht if installed
            import board
            import adafruit_dht
            if self._device is None:
                # Map BCM pin number to board pin
                pin_attr = getattr(board, f"D{self.pin}", None)
                if pin_attr:
                    self._device = adafruit_dht.DHT11(pin_attr)

            if self._device:
                temp = self._device.temperature
                hum = self._device.humidity
                if temp is not None and hum is not None:
                    return round(float(temp), 1), round(float(hum), 1)
        except Exception as e:
            logger.debug(f"DHT11 read attempt failed: {e}")

        return None, None


# ---------------------------------------------------------------------------
# u-blox NEO-6M GPS Module Adapter (Disabled by Default)
# ---------------------------------------------------------------------------
class GPSAdapter:
    """
    UART / Serial interface adapter for u-blox NEO-6M GPS receiver.
    Parses NMEA $GPGGA and $GPRMC sentences.
    Disabled by default; protects against missing serial port or libraries.
    """
    def __init__(self, port: str = "/dev/serial0", baudrate: int = 9600, enabled: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.enabled = enabled
        self._serial = None

    @staticmethod
    def _parse_nmea_coord(raw_value: str, direction: str) -> Optional[float]:
        """Converts NMEA ddmm.mmmm to decimal degrees."""
        if not raw_value or not direction:
            return None
        try:
            val = float(raw_value)
            deg = int(val / 100)
            minutes = val - (deg * 100)
            decimal = deg + (minutes / 60.0)
            if direction.upper() in ("S", "W"):
                decimal = -decimal
            return round(decimal, 6)
        except Exception:
            return None

    def read_coordinates(self) -> Optional[Dict[str, Any]]:
        """
        Reads GPS coordinates from serial interface.
        Returns dict with latitude, longitude, and fix status, or None.
        """
        if not self.enabled:
            return None

        try:
            import serial
        except ImportError:
            logger.debug("pyserial not installed; GPS unavailable.")
            return None

        try:
            if self._serial is None:
                self._serial = serial.Serial(self.port, self.baudrate, timeout=1.0)

            # Read a batch of NMEA lines looking for GGA or RMC
            for _ in range(15):
                line = self._serial.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue

                parts = line.split(",")
                # $GPGGA: [0] $GPGGA, [1] UTC, [2] Lat, [3] N/S, [4] Lon, [5] E/W, [6] Fix Quality
                if parts[0] in ("$GPGGA", "$GNGGA") and len(parts) >= 7:
                    fix_quality = parts[6]
                    if fix_quality != "0" and parts[2] and parts[4]:
                        lat = self._parse_nmea_coord(parts[2], parts[3])
                        lon = self._parse_nmea_coord(parts[4], parts[5])
                        if lat is not None and lon is not None:
                            return {"latitude": lat, "longitude": lon, "fix": True, "type": "GGA"}

                # $GPRMC: [0] $GPRMC, [1] UTC, [2] Status (A=valid, V=void), [3] Lat, [4] N/S, [5] Lon, [6] E/W
                elif parts[0] in ("$GPRMC", "$GNRMC") and len(parts) >= 7:
                    status = parts[2]
                    if status == "A" and parts[3] and parts[5]:
                        lat = self._parse_nmea_coord(parts[3], parts[4])
                        lon = self._parse_nmea_coord(parts[5], parts[6])
                        if lat is not None and lon is not None:
                            return {"latitude": lat, "longitude": lon, "fix": True, "type": "RMC"}

        except Exception as e:
            logger.debug(f"GPS read error on {self.port}: {e}")

        return None

    def close(self):
        """Closes the serial connection."""
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
