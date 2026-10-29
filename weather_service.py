"""
Virtual Atmosphere (VA) - Weather & Heat-Risk Intelligence Service
Implements NOAA / National Weather Service (NWS) algorithms for Heat Index
estimation, thermodynamic discomfort categorization, and data source validation.
"""

import math
from typing import Optional, Dict, Any, Tuple

class WeatherService:
    """
    Computes scientific heat risk, validates meteorological bounds,
    and categorizes environmental safety.
    """

    # Physical meteorological operational limits
    TEMP_MIN_C = -40.0
    TEMP_MAX_C = 85.0
    HUMIDITY_MIN = 0.0
    HUMIDITY_MAX = 100.0
    PRESSURE_MIN_HPA = 300.0
    PRESSURE_MAX_HPA = 1100.0
    LAT_MIN = -90.0
    LAT_MAX = 90.0
    LON_MIN = -180.0
    LON_MAX = 180.0

    # NWS Heat Index Categories (in Celsius)
    # Caution: 26.7°C - 32.2°C (80°F - 90°F)
    # Extreme Caution: 32.8°C - 39.4°C (91°F - 103°F)
    # Danger: 40.0°C - 51.1°C (104°F - 124°F)
    # Extreme Danger: >= 51.7°C (>= 125°F)

    @classmethod
    def compute_heat_index(cls, temp_c: Optional[float], humidity_pct: Optional[float]) -> Optional[float]:
        """
        Calculates the estimated Heat Index using the official NOAA / National Weather
        Service (NWS) Rothfusz polynomial regression algorithm.

        Scientific Applicability & Rules:
        1. Heat Index is physically applicable only when Temperature >= 26.7°C (80°F)
           and Relative Humidity >= 40%.
        2. Below 26.7°C (80°F) or without relative humidity, Heat Index is not
           meaningful (body cooling occurs normally); returns None.
        3. Never calculates a heat index from temperature alone.
        """
        if temp_c is None or humidity_pct is None:
            return None

        # Validate physical meteorological bounds
        if not (cls.TEMP_MIN_C <= temp_c <= cls.TEMP_MAX_C):
            return None
        if not (cls.HUMIDITY_MIN <= humidity_pct <= cls.HUMIDITY_MAX):
            return None

        # Convert to Fahrenheit for standard NOAA equation
        tf = (temp_c * 9.0 / 5.0) + 32.0
        rh = float(humidity_pct)

        # Baseline check: If ambient temperature is below 80°F, heat index is not applicable
        if tf < 80.0:
            return None

        # Steadman's preliminary simple formula
        hi_simple = 0.5 * (tf + 61.0 + ((tf - 68.0) * 1.2) + (rh * 0.094))
        avg_hi = (hi_simple + tf) / 2.0

        if avg_hi < 80.0:
            hi_f = hi_simple
        else:
            # Full 9-parameter Rothfusz regression equation
            hi_f = (
                -42.379
                + (2.04901523 * tf)
                + (10.14333127 * rh)
                - (0.22475541 * tf * rh)
                - (0.00683783 * tf * tf)
                - (0.05481717 * rh * rh)
                + (0.00122874 * tf * tf * rh)
                + (0.00085282 * tf * rh * rh)
                - (0.00000199 * tf * tf * rh * rh)
            )

            # Low humidity adjustment
            if rh < 13.0 and (80.0 <= tf <= 112.0):
                adj = ((13.0 - rh) / 4.0) * math.sqrt((17.0 - abs(tf - 95.0)) / 17.0)
                hi_f -= adj

            # High humidity adjustment
            elif rh > 85.0 and (80.0 <= tf <= 87.0):
                adj = ((rh - 85.0) / 10.0) * ((87.0 - tf) / 5.0)
                hi_f += adj

        # Convert back to Celsius
        hi_c = (hi_f - 32.0) * 5.0 / 9.0
        return round(hi_c, 1)

    @classmethod
    def get_heat_risk_assessment(
        cls,
        temp_c: Optional[float],
        humidity_pct: Optional[float],
        source: str = "simulated"
    ) -> Dict[str, Any]:
        """
        Provides a comprehensive thermodynamic heat-risk evaluation with calculation
        basis, advisory notes, and clear simulation tagging.
        """
        hi_c = cls.compute_heat_index(temp_c, humidity_pct)
        is_simulated = source in ("simulated", "demo")

        if temp_c is None:
            return {
                "heat_index_c": None,
                "category": "Unavailable",
                "badge_class": "secondary",
                "advisory": "Awaiting valid ambient temperature reading.",
                "formula_basis": "None",
                "is_applicable": False,
                "is_simulated": is_simulated
            }

        if humidity_pct is None:
            return {
                "heat_index_c": None,
                "category": "Incomplete Data",
                "badge_class": "secondary",
                "advisory": "Relative humidity sensor required to compute heat index. (BMP280 lacks humidity cell; awaiting BME280/DHT11).",
                "formula_basis": "NWS Heat Index requires both Temperature and Relative Humidity.",
                "is_applicable": False,
                "is_simulated": is_simulated
            }

        if hi_c is None:
            # Ambient temperature is below 26.7°C (80°F)
            return {
                "heat_index_c": None,
                "category": "Normal",
                "badge_class": "success",
                "advisory": "Ambient conditions are within baseline comfort range. Heat index is not clinically elevated.",
                "formula_basis": "NWS criteria applicable only when Temp >= 26.7°C (80°F) and RH >= 40%.",
                "is_applicable": False,
                "is_simulated": is_simulated
            }

        # Categorize active heat index
        if hi_c < 32.2:
            category = "Caution"
            badge_class = "warning"
            advisory = "Fatigue possible with prolonged physical activity and exposure."
        elif hi_c < 39.4:
            category = "Extreme Caution"
            badge_class = "warning"
            advisory = "Heat cramps and heat exhaustion possible with continued exposure."
        elif hi_c < 51.1:
            category = "Danger"
            badge_class = "danger"
            advisory = "Heat cramps or exhaustion likely; heatstroke possible with prolonged activity."
        else:
            category = "Extreme Danger"
            badge_class = "danger"
            advisory = "Heatstroke highly likely. Avoid prolonged outdoor exertion."

        return {
            "heat_index_c": hi_c,
            "category": category,
            "badge_class": badge_class,
            "advisory": advisory,
            "formula_basis": "NOAA / NWS Rothfusz 9-parameter polynomial regression.",
            "is_applicable": True,
            "is_simulated": is_simulated
        }

    @classmethod
    def validate_reading(
        cls,
        temp_c: Optional[float],
        pressure_hpa: Optional[float],
        humidity_pct: Optional[float] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None
    ) -> Tuple[bool, str]:
        """Validates that all provided environmental readings fall within realistic physical bounds."""
        if temp_c is not None:
            if math.isnan(temp_c) or math.isinf(temp_c) or not (cls.TEMP_MIN_C <= temp_c <= cls.TEMP_MAX_C):
                return False, f"Temperature {temp_c}°C outside operational bounds (-40 to 85°C)"

        if pressure_hpa is not None:
            if math.isnan(pressure_hpa) or math.isinf(pressure_hpa) or not (cls.PRESSURE_MIN_HPA <= pressure_hpa <= cls.PRESSURE_MAX_HPA):
                return False, f"Barometric pressure {pressure_hpa} hPa outside operational bounds (300 to 1100 hPa)"

        if humidity_pct is not None:
            if math.isnan(humidity_pct) or math.isinf(humidity_pct) or not (cls.HUMIDITY_MIN <= humidity_pct <= cls.HUMIDITY_MAX):
                return False, f"Relative humidity {humidity_pct}% outside valid range (0 to 100%)"

        if lat is not None:
            if math.isnan(lat) or math.isinf(lat) or not (cls.LAT_MIN <= lat <= cls.LAT_MAX):
                return False, f"Latitude {lat} outside valid bounds (-90 to 90)"

        if lon is not None:
            if math.isnan(lon) or math.isinf(lon) or not (cls.LON_MIN <= lon <= cls.LON_MAX):
                return False, f"Longitude {lon} outside valid bounds (-180 to 180)"

        return True, "valid"

    # DHT11 operational limits
    DHT11_TEMP_MIN_C = -20.0
    DHT11_TEMP_MAX_C = 60.0
    DHT11_HUMIDITY_MIN = 0.0
    DHT11_HUMIDITY_MAX = 100.0

    @classmethod
    def validate_dht11_reading(cls, temp_c: Optional[float], humidity_pct: Optional[float]) -> Tuple[bool, str]:
        """Validates that DHT11 readings fall within realistic sensor limits."""
        if temp_c is None:
            return False, "temperature_c is required"
        if math.isnan(temp_c) or math.isinf(temp_c) or not (cls.DHT11_TEMP_MIN_C <= temp_c <= cls.DHT11_TEMP_MAX_C):
            return False, f"Temperature {temp_c}°C outside reasonable DHT11 limits ({cls.DHT11_TEMP_MIN_C} to {cls.DHT11_TEMP_MAX_C}°C)"

        if humidity_pct is None:
            return False, "humidity_percent is required"
        if math.isnan(humidity_pct) or math.isinf(humidity_pct) or not (cls.DHT11_HUMIDITY_MIN <= humidity_pct <= cls.DHT11_HUMIDITY_MAX):
            return False, f"Relative humidity {humidity_pct}% outside valid range ({cls.DHT11_HUMIDITY_MIN} to {cls.DHT11_HUMIDITY_MAX}%)"

        return True, "valid"
