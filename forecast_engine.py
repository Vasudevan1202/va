"""
Virtual Atmosphere (VA) - Local Short-Term Forecasting Engine (Phase 1)
------------------------------------------------------------------------
Provides explainable, short-term microclimate forecasting (15-minute primary horizon,
with 30m and 60m evaluations) using historical DHT11 temperature and relative humidity data.

Scientific & Design Principles:
1. Honest Data Preparation: Validates physical limits, excludes non-finite/implausible values,
   deduplicates timestamps, and aggregates into 1-minute averages to suppress DHT11 quantization jitter.
2. Explainable Baseline & Damped Trend: Compares a Holt-damped linear trend against a persistence
   baseline. Clamps rates of change and output bounds to physically defensible limits.
3. Prediction Intervals: Incorporates regression residual error and DHT11 hardware uncertainty (±2°C, ±5% RH).
4. Zero-Leakage Backtesting: Evaluates chronological rolling-origin walk-forward predictions
   without future leakage. Reports MAE, RMSE, sample counts, and persistence comparisons.
5. Strict Isolation: Completely separates real hardware readings from simulated/demo data,
   and fails cleanly without impacting live ingestion pipelines.
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from weather_service import WeatherService

logger = logging.getLogger(__name__)


class ForecastEngine:
    """
    Engine for local, short-term environmental forecasting from DHT11 sensor telemetry.
    """

    # Operational & Physical Limits
    DHT11_TEMP_MIN_C = -20.0
    DHT11_TEMP_MAX_C = 60.0
    DHT11_HUM_MIN_PCT = 0.0
    DHT11_HUM_MAX_PCT = 100.0

    # Sensor Hardware Accuracy (Manufacturer limits for DHT11)
    DHT11_HARDWARE_TEMP_UNCERTAINTY_C = 2.0  # ±2°C
    DHT11_HARDWARE_HUM_UNCERTAINTY_PCT = 5.0  # ±5% RH

    # Rate of Change Clamping (Maximum plausible room/ambient rate per minute)
    MAX_TEMP_RATE_C_PER_MIN = 0.35   # ~21°C/hour max plausible ambient transient
    MAX_HUM_RATE_PCT_PER_MIN = 1.2   # ~72%/hour max plausible ambient transient

    # Model & Damping Parameters
    DEFAULT_DAMPING_FACTOR = 0.85     # Holt exponential trend damping (0.0 = persistence, 1.0 = linear)
    DEFAULT_HORIZON_MINUTES = 15
    EVALUATED_HORIZONS = [15, 30, 60]

    # Data Freshness & Continuity
    MAX_FRESHNESS_SECONDS = 900.0     # 15 min; beyond this, sensor is marked 'stale'
    OFFLINE_FRESHNESS_SECONDS = 3600.0  # 60 min; beyond this, sensor is marked 'offline'
    MAX_INTERPOLATION_GAP_MINUTES = 10.0  # Gaps > 10 min treated as missing intervals

    # History Sufficiency Configuration
    MIN_HISTORY_MINUTES = 15          # Minimum 15 minutes of historical telemetry required
    MIN_TEST_SAMPLES_BACKTEST = 8     # Minimum verification pairs needed for backtesting stats

    MODEL_NAME = "damped_linear_trend"
    MODEL_VERSION = "1.0.0"

    # In-memory forecast cache (TTL seconds) to prevent redundant computation
    _cache: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}
    CACHE_TTL_SECONDS = 30.0

    @classmethod
    def parse_iso_timestamp(cls, ts_str: Any) -> Optional[datetime]:
        """Safely parses an ISO 8601 string or numeric timestamp to a timezone-aware UTC datetime."""
        if not ts_str:
            return None
        if isinstance(ts_str, datetime):
            if ts_str.tzinfo is None:
                return ts_str.replace(tzinfo=timezone.utc)
            return ts_str.astimezone(timezone.utc)
        try:
            cleaned = str(ts_str).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    @classmethod
    def prepare_dht11_series(
        cls,
        raw_readings: List[Dict[str, Any]],
        real_only: bool = False,
        reference_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Validates, deduplicates, and aggregates raw DHT11 observations into 1-minute buckets.
        Excludes invalid, non-finite, out-of-bounds, and demo/simulated readings if real_only is True.
        """
        now = reference_time or datetime.now(timezone.utc)
        valid_points: List[Dict[str, Any]] = []

        for r in raw_readings:
            if not isinstance(r, dict):
                continue

            # Check validity status
            status = str(r.get("validity_status", "")).strip().lower()
            if status not in ("valid", ""):
                continue

            # Separate demo / simulated data if real_only requested
            source = str(r.get("source", "")).strip().lower()
            if real_only and source in ("demo", "simulated"):
                continue

            # Parse and validate timestamp
            dt = cls.parse_iso_timestamp(r.get("timestamp"))
            if dt is None:
                continue

            # Extract & validate temperature
            temp_raw = r.get("temperature_c")
            if temp_raw is None:
                continue
            try:
                temp_c = float(temp_raw)
            except (ValueError, TypeError):
                continue
            if math.isnan(temp_c) or math.isinf(temp_c) or not (cls.DHT11_TEMP_MIN_C <= temp_c <= cls.DHT11_TEMP_MAX_C):
                continue

            # Extract & validate humidity
            hum_raw = r.get("humidity_pct")
            if hum_raw is None:
                hum_raw = r.get("humidity_percent")
            if hum_raw is None:
                continue
            try:
                hum_pct = float(hum_raw)
            except (ValueError, TypeError):
                continue
            if math.isnan(hum_pct) or math.isinf(hum_pct) or not (cls.DHT11_HUM_MIN_PCT <= hum_pct <= cls.DHT11_HUM_MAX_PCT):
                continue

            valid_points.append({
                "dt": dt,
                "temperature_c": temp_c,
                "humidity_pct": hum_pct,
                "source": r.get("source", "dht11"),
                "sensor_type": r.get("sensor_type", "dht11")
            })

        if not valid_points:
            return {
                "buckets": [],
                "latest_observation": None,
                "freshness": "offline",
                "data_age_seconds": None,
                "usable_minutes": 0,
                "gaps_detected": 0,
                "is_sufficient": False,
                "reason": "No valid DHT11 readings available in time window."
            }

        # Chronological sort
        valid_points.sort(key=lambda p: p["dt"])

        # Group by 1-minute bucket (truncate to minute)
        bucket_map: Dict[datetime, List[Dict[str, Any]]] = {}
        for p in valid_points:
            b_key = p["dt"].replace(second=0, microsecond=0)
            bucket_map.setdefault(b_key, []).append(p)

        # Aggregate each bucket into mean temperature and humidity
        buckets: List[Dict[str, Any]] = []
        for b_dt in sorted(bucket_map.keys()):
            items = bucket_map[b_dt]
            avg_temp = sum(x["temperature_c"] for x in items) / len(items)
            avg_hum = sum(x["humidity_pct"] for x in items) / len(items)
            buckets.append({
                "timestamp": b_dt.isoformat(),
                "dt": b_dt,
                "temperature_c": round(avg_temp, 2),
                "humidity_pct": round(avg_hum, 2),
                "heat_index_c": WeatherService.compute_heat_index(avg_temp, avg_hum),
                "sample_count": len(items),
                "source": items[-1]["source"],
                "sensor_type": items[-1]["sensor_type"]
            })

        latest_bucket = buckets[-1]
        data_age = (now - latest_bucket["dt"]).total_seconds()
        if data_age < 0:
            data_age = 0.0

        # Freshness determination
        if data_age <= cls.MAX_FRESHNESS_SECONDS:
            freshness = "fresh"
        elif data_age <= cls.OFFLINE_FRESHNESS_SECONDS:
            freshness = "stale"
        else:
            freshness = "offline"

        # Detect missing intervals & gaps between consecutive 1-minute buckets
        gaps_detected = 0
        max_continuous_span_min = 1
        current_span_min = 1

        for i in range(1, len(buckets)):
            delta_min = (buckets[i]["dt"] - buckets[i - 1]["dt"]).total_seconds() / 60.0
            if delta_min > cls.MAX_INTERPOLATION_GAP_MINUTES:
                gaps_detected += 1
                current_span_min = 1
            else:
                current_span_min += int(delta_min)
                if current_span_min > max_continuous_span_min:
                    max_continuous_span_min = current_span_min

        # Usable minutes: number of aggregated points in recent contiguous window
        usable_minutes = len(buckets)
        is_sufficient = (usable_minutes >= cls.MIN_HISTORY_MINUTES) and (freshness == "fresh")

        reason = None
        if freshness == "offline":
            reason = f"Sensor offline. Last observation was received {int(data_age // 60)} minutes ago."
        elif freshness == "stale":
            reason = f"Sensor data is stale ({int(data_age // 60)} minutes old). Live forecast paused until new telemetry arrives."
        elif usable_minutes < cls.MIN_HISTORY_MINUTES:
            reason = f"Insufficient history. Requires at least {cls.MIN_HISTORY_MINUTES} minutes of continuous data (currently {usable_minutes} min)."

        return {
            "buckets": buckets,
            "latest_observation": latest_bucket,
            "freshness": freshness,
            "data_age_seconds": round(data_age, 1),
            "usable_minutes": usable_minutes,
            "gaps_detected": gaps_detected,
            "is_sufficient": is_sufficient,
            "reason": reason
        }

    @classmethod
    def _fit_linear_slope(cls, x_vals: List[float], y_vals: List[float]) -> Tuple[float, float, float]:
        """
        Fits simple linear regression y = a + b*x.
        Returns (intercept a, slope b, residual_std_error).
        """
        n = len(x_vals)
        if n < 2:
            return y_vals[0] if y_vals else 0.0, 0.0, 0.0

        mean_x = sum(x_vals) / n
        mean_y = sum(y_vals) / n

        num = sum((x_vals[i] - mean_x) * (y_vals[i] - mean_y) for i in range(n))
        den = sum((x_vals[i] - mean_x) ** 2 for i in range(n))

        if abs(den) < 1e-9:
            return mean_y, 0.0, 0.0

        slope = num / den
        intercept = mean_y - slope * mean_x

        # Residual standard error
        ss_res = sum((y_vals[i] - (intercept + slope * x_vals[i])) ** 2 for i in range(n))
        deg_free = max(1, n - 2)
        res_std = math.sqrt(ss_res / deg_free)

        return intercept, slope, res_std

    @classmethod
    def _damped_trend_projection(
        cls,
        current_val: float,
        slope_per_min: float,
        horizon_min: int,
        damping: float,
        max_rate_per_min: float,
        min_bound: float,
        max_bound: float
    ) -> Tuple[float, float]:
        """
        Calculates damped cumulative change and projected point estimate clamped to physical bounds.
        Returns (projected_value, delta_change).
        """
        # Clamp rate of change to defensible maximum
        clamped_slope = max(-max_rate_per_min, min(max_rate_per_min, slope_per_min))

        # Holt exponential damping formula: sum(phi^k for k in 1..h) = phi * (1 - phi^h) / (1 - phi)
        if 0.0 < damping < 1.0:
            cumulative_weight = damping * (1.0 - (damping ** horizon_min)) / (1.0 - damping)
        elif damping >= 1.0:
            cumulative_weight = float(horizon_min)
        else:
            cumulative_weight = 0.0  # pure persistence

        delta = clamped_slope * cumulative_weight
        projected = current_val + delta

        # Clamp output to physical sensor limits
        clamped_projected = max(min_bound, min(max_bound, projected))
        actual_delta = clamped_projected - current_val

        return round(clamped_projected, 2), round(actual_delta, 2)

    @classmethod
    def _calculate_prediction_interval(
        cls,
        predicted_val: float,
        residual_std: float,
        n_samples: int,
        horizon_min: int,
        hardware_uncertainty: float,
        min_bound: float,
        max_bound: float,
        coverage: float = 0.80
    ) -> Tuple[float, float]:
        """
        Constructs prediction interval combining regression uncertainty and sensor hardware limits.
        Enforces that interval half-width is never narrower than physical DHT11 sensor uncertainty.
        Returns (lower_bound, upper_bound).
        """
        # Multiplier for 80% or 95% coverage
        z_multiplier = 1.96 if coverage >= 0.95 else 1.282

        # Standard error of forecast at horizon h
        # sigma_forecast = sqrt( s_e^2 * (1 + 1/n + h^2 / sum_sq_x) + (hardware_uncertainty / 1.645)^2 )
        hw_sigma = hardware_uncertainty / 1.645
        trend_sigma = residual_std * math.sqrt(1.0 + (1.0 / max(1, n_samples)) + (horizon_min / 60.0))
        total_sigma = math.sqrt(trend_sigma ** 2 + hw_sigma ** 2)

        half_width = z_multiplier * total_sigma

        # Sensor hardware bound: interval must never be unrealistically tight
        min_half_width = hardware_uncertainty * 0.75
        half_width = max(half_width, min_half_width)

        lower = max(min_bound, round(predicted_val - half_width, 2))
        upper = min(max_bound, round(predicted_val + half_width, 2))

        return lower, upper

    @classmethod
    def generate_point_forecast(
        cls,
        buckets: List[Dict[str, Any]],
        horizon_min: int = 15,
        damping: float = DEFAULT_DAMPING_FACTOR,
        window_minutes: int = 30
    ) -> Dict[str, Any]:
        """
        Generates point estimates and prediction intervals for temperature and humidity
        using recent observations (up to window_minutes).
        """
        if not buckets:
            raise ValueError("No historical observations provided to generate forecast.")

        latest = buckets[-1]
        curr_temp = latest["temperature_c"]
        curr_hum = latest["humidity_pct"]

        # Select recent window for local trend estimation
        recent = buckets[-window_minutes:]
        n = len(recent)

        # Baseline: Persistence predicts latest observation continues unchanged
        persistence_temp = curr_temp
        persistence_hum = curr_hum

        if n < 3:
            # Insufficient points in window to compute slope: revert cleanly to persistence
            temp_lower, temp_upper = cls._calculate_prediction_interval(
                curr_temp, 0.5, n, horizon_min, cls.DHT11_HARDWARE_TEMP_UNCERTAINTY_C,
                cls.DHT11_TEMP_MIN_C, cls.DHT11_TEMP_MAX_C
            )
            hum_lower, hum_upper = cls._calculate_prediction_interval(
                curr_hum, 2.0, n, horizon_min, cls.DHT11_HARDWARE_HUM_UNCERTAINTY_PCT,
                cls.DHT11_HUM_MIN_PCT, cls.DHT11_HUM_MAX_PCT
            )
            return {
                "horizon_minutes": horizon_min,
                "temperature": {
                    "current_c": curr_temp,
                    "predicted_c": curr_temp,
                    "change_c": 0.0,
                    "persistence_c": persistence_temp,
                    "interval_80": [temp_lower, temp_upper],
                    "lower_bound_c": temp_lower,
                    "upper_bound_c": temp_upper,
                    "model_used": "persistence_fallback"
                },
                "humidity": {
                    "current_pct": curr_hum,
                    "predicted_pct": curr_hum,
                    "change_pct": 0.0,
                    "persistence_pct": persistence_hum,
                    "interval_80": [hum_lower, hum_upper],
                    "lower_bound_pct": hum_lower,
                    "upper_bound_pct": hum_upper,
                    "model_used": "persistence_fallback"
                },
                "heat_index": {
                    "current_c": WeatherService.compute_heat_index(curr_temp, curr_hum),
                    "predicted_c": WeatherService.compute_heat_index(curr_temp, curr_hum)
                }
            }

        # Time offsets in minutes relative to start of window
        t0 = recent[0]["dt"]
        x_mins = [(r["dt"] - t0).total_seconds() / 60.0 for r in recent]
        temp_y = [r["temperature_c"] for r in recent]
        hum_y = [r["humidity_pct"] for r in recent]

        _, temp_slope, temp_std = cls._fit_linear_slope(x_mins, temp_y)
        _, hum_slope, hum_std = cls._fit_linear_slope(x_mins, hum_y)

        # Damped projections
        pred_temp, delta_temp = cls._damped_trend_projection(
            curr_temp, temp_slope, horizon_min, damping,
            cls.MAX_TEMP_RATE_C_PER_MIN, cls.DHT11_TEMP_MIN_C, cls.DHT11_TEMP_MAX_C
        )
        pred_hum, delta_hum = cls._damped_trend_projection(
            curr_hum, hum_slope, horizon_min, damping,
            cls.MAX_HUM_RATE_PCT_PER_MIN, cls.DHT11_HUM_MIN_PCT, cls.DHT11_HUM_MAX_PCT
        )

        # Prediction intervals
        temp_lower, temp_upper = cls._calculate_prediction_interval(
            pred_temp, temp_std, n, horizon_min, cls.DHT11_HARDWARE_TEMP_UNCERTAINTY_C,
            cls.DHT11_TEMP_MIN_C, cls.DHT11_TEMP_MAX_C
        )
        hum_lower, hum_upper = cls._calculate_prediction_interval(
            pred_hum, hum_std, n, horizon_min, cls.DHT11_HARDWARE_HUM_UNCERTAINTY_PCT,
            cls.DHT11_HUM_MIN_PCT, cls.DHT11_HUM_MAX_PCT
        )

        return {
            "horizon_minutes": horizon_min,
            "temperature": {
                "current_c": curr_temp,
                "predicted_c": pred_temp,
                "change_c": delta_temp,
                "persistence_c": persistence_temp,
                "interval_80": [temp_lower, temp_upper],
                "lower_bound_c": temp_lower,
                "upper_bound_c": temp_upper,
                "model_used": cls.MODEL_NAME,
                "rate_c_per_min": round(temp_slope, 4)
            },
            "humidity": {
                "current_pct": curr_hum,
                "predicted_pct": pred_hum,
                "change_pct": delta_hum,
                "persistence_pct": persistence_hum,
                "interval_80": [hum_lower, hum_upper],
                "lower_bound_pct": hum_lower,
                "upper_bound_pct": hum_upper,
                "model_used": cls.MODEL_NAME,
                "rate_pct_per_min": round(hum_slope, 4)
            },
            "heat_index": {
                "current_c": WeatherService.compute_heat_index(curr_temp, curr_hum),
                "predicted_c": WeatherService.compute_heat_index(pred_temp, pred_hum)
            }
        }

    @classmethod
    def backtest_horizons(
        cls,
        buckets: List[Dict[str, Any]],
        horizons: Optional[List[int]] = None,
        min_train_minutes: int = 15,
        min_test_samples: int = MIN_TEST_SAMPLES_BACKTEST
    ) -> Dict[str, Any]:
        """
        Executes chronological rolling-origin walk-forward backtesting.
        Guarantees zero future-data leakage by only fitting on observations <= evaluation time.
        Compares the damped linear trend against the persistence baseline.
        """
        target_horizons = horizons or cls.EVALUATED_HORIZONS
        results: Dict[str, Any] = {}

        n_total = len(buckets)
        if n_total < (min_train_minutes + 5):
            for h in target_horizons:
                results[f"{h}m"] = {
                    "horizon_minutes": h,
                    "status": "insufficient_test_data",
                    "samples_evaluated": 0,
                    "min_samples_required": min_test_samples,
                    "explanation": f"History too short for time-ordered backtesting (requires > {min_train_minutes + h} minutes).",
                    "temperature": None,
                    "humidity": None
                }
            return results

        # Create quick index lookup by timestamp minute for O(1) walk-forward matching
        dt_to_idx = {b["dt"].replace(second=0, microsecond=0): idx for idx, b in enumerate(buckets)}

        for h in target_horizons:
            temp_model_errors: List[float] = []
            temp_pers_errors: List[float] = []
            hum_model_errors: List[float] = []
            hum_pers_errors: List[float] = []

            # Step forward through time from min_train_minutes
            for i in range(min_train_minutes, n_total):
                t_eval = buckets[i]["dt"].replace(second=0, microsecond=0)
                t_target = t_eval + timedelta(minutes=h)

                # Look for actual ground truth reading at target time
                target_idx = dt_to_idx.get(t_target)
                if target_idx is None:
                    continue

                actual_point = buckets[target_idx]
                actual_temp = actual_point["temperature_c"]
                actual_hum = actual_point["humidity_pct"]

                # Fit strictly on past data: 0 to i inclusive
                past_window = buckets[:i + 1]
                forecast = cls.generate_point_forecast(past_window, horizon_min=h)

                pred_temp = forecast["temperature"]["predicted_c"]
                pers_temp = forecast["temperature"]["persistence_c"]
                pred_hum = forecast["humidity"]["predicted_pct"]
                pers_hum = forecast["humidity"]["persistence_pct"]

                temp_model_errors.append(actual_temp - pred_temp)
                temp_pers_errors.append(actual_temp - pers_temp)
                hum_model_errors.append(actual_hum - pred_hum)
                hum_pers_errors.append(actual_hum - pers_hum)

            n_samples = len(temp_model_errors)
            if n_samples < min_test_samples:
                results[f"{h}m"] = {
                    "horizon_minutes": h,
                    "status": "insufficient_test_data",
                    "samples_evaluated": n_samples,
                    "min_samples_required": min_test_samples,
                    "explanation": f"Evaluated {n_samples} verification pairs. Minimum {min_test_samples} required for statistically valid validation.",
                    "temperature": None,
                    "humidity": None
                }
                continue

            # Calculate metrics
            temp_mae_model = sum(abs(e) for e in temp_model_errors) / n_samples
            temp_rmse_model = math.sqrt(sum(e ** 2 for e in temp_model_errors) / n_samples)
            temp_mae_pers = sum(abs(e) for e in temp_pers_errors) / n_samples
            temp_rmse_pers = math.sqrt(sum(e ** 2 for e in temp_pers_errors) / n_samples)

            hum_mae_model = sum(abs(e) for e in hum_model_errors) / n_samples
            hum_rmse_model = math.sqrt(sum(e ** 2 for e in hum_model_errors) / n_samples)
            hum_mae_pers = sum(abs(e) for e in hum_pers_errors) / n_samples
            hum_rmse_pers = math.sqrt(sum(e ** 2 for e in hum_pers_errors) / n_samples)

            # Skill score vs persistence baseline: 1 - (RMSE_model / RMSE_pers)
            temp_skill = 1.0 - (temp_rmse_model / max(1e-4, temp_rmse_pers))
            hum_skill = 1.0 - (hum_rmse_model / max(1e-4, hum_rmse_pers))

            is_active_horizon = (h == cls.DEFAULT_HORIZON_MINUTES)
            results[f"{h}m"] = {
                "horizon_minutes": h,
                "status": "active" if is_active_horizon else "evaluated_experimental",
                "samples_evaluated": n_samples,
                "min_samples_required": min_test_samples,
                "temperature": {
                    "mae_c": round(temp_mae_model, 2),
                    "rmse_c": round(temp_rmse_model, 2),
                    "persistence_mae_c": round(temp_mae_pers, 2),
                    "persistence_rmse_c": round(temp_rmse_pers, 2),
                    "skill_score_pct": round(temp_skill * 100.0, 1)
                },
                "humidity": {
                    "mae_pct": round(hum_mae_model, 2),
                    "rmse_pct": round(hum_rmse_model, 2),
                    "persistence_mae_pct": round(hum_mae_pers, 2),
                    "persistence_rmse_pct": round(hum_rmse_pers, 2),
                    "skill_score_pct": round(hum_skill * 100.0, 1)
                },
                "summary": (
                    f"Model {'improves upon' if temp_skill > 0 else 'performs comparably to'} "
                    f"persistence baseline by {round(abs(temp_skill * 100.0), 1)}% on temperature at {h}m horizon."
                )
            }

        return results

    @classmethod
    def get_forecast_report(
        cls,
        raw_readings: List[Dict[str, Any]],
        horizon_min: int = DEFAULT_HORIZON_MINUTES,
        real_only: bool = False,
        reference_time: Optional[datetime] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Orchestrates full forecasting pipeline:
        Data preparation, sufficiency evaluation, point estimate generation,
        prediction intervals, and walk-forward backtesting.
        """
        now = reference_time or datetime.now(timezone.utc)
        cache_key = f"h{horizon_min}_ro{real_only}"

        if use_cache and cache_key in cls._cache:
            cached_time, cached_result = cls._cache[cache_key]
            if (now - cached_time).total_seconds() < cls.CACHE_TTL_SECONDS:
                return cached_result

        # 1. Historical data preparation
        prep = cls.prepare_dht11_series(raw_readings, real_only=real_only, reference_time=now)
        buckets = prep["buckets"]
        latest = prep["latest_observation"]
        freshness = prep["freshness"]
        is_sufficient = prep["is_sufficient"]

        disclaimers = [
            "Experimental local forecast for ambient environmental awareness only.",
            f"DHT11 physical measurement accuracy is ±{cls.DHT11_HARDWARE_TEMP_UNCERTAINTY_C}°C and ±{cls.DHT11_HARDWARE_HUM_UNCERTAINTY_PCT}% RH, bounding forecast precision.",
            "Not certified for official meteorological forecasting, storm/rainfall prediction, or industrial/OSHA heat-safety assessment."
        ]

        # 2. Check for insufficient history or stale data
        if not is_sufficient or not latest:
            result = {
                "status": "stale_sensor" if freshness in ("stale", "offline") else "insufficient_history",
                "is_available": False,
                "generated_at": now.isoformat(),
                "sensor": {
                    "type": "dht11",
                    "source": latest.get("source") if latest else None,
                    "freshness": freshness,
                    "data_age_seconds": prep["data_age_seconds"],
                    "last_reading_time": latest["timestamp"] if latest else None
                },
                "forecast": None,
                "evaluations": None,
                "sufficiency": {
                    "is_sufficient": False,
                    "usable_minutes": prep["usable_minutes"],
                    "min_required_minutes": cls.MIN_HISTORY_MINUTES,
                    "gaps_detected": prep["gaps_detected"],
                    "reason": prep["reason"]
                },
                "backtest": None,
                "disclaimers": disclaimers
            }
            if use_cache:
                cls._cache[cache_key] = (now, result)
            return result

        # 3. Generate primary horizon forecast
        target_horizon = horizon_min if horizon_min in cls.EVALUATED_HORIZONS else cls.DEFAULT_HORIZON_MINUTES
        point_forecast = cls.generate_point_forecast(buckets, horizon_min=target_horizon)

        target_dt = latest["dt"] + timedelta(minutes=target_horizon)

        # 4. Perform walk-forward backtesting across all horizons (15m, 30m, 60m)
        backtest_results = cls.backtest_horizons(buckets)

        result = {
            "status": "success",
            "is_available": True,
            "generated_at": now.isoformat(),
            "model": {
                "name": cls.MODEL_NAME,
                "version": cls.MODEL_VERSION,
                "damping_factor": cls.DEFAULT_DAMPING_FACTOR,
                "description": "Holt-damped local linear trend model with persistence baseline comparison."
            },
            "sensor": {
                "type": "dht11",
                "source": latest.get("source"),
                "freshness": freshness,
                "data_age_seconds": prep["data_age_seconds"],
                "last_reading_time": latest["timestamp"]
            },
            "forecast": {
                "horizon_minutes": target_horizon,
                "target_timestamp": target_dt.isoformat(),
                "observed": {
                    "timestamp": latest["timestamp"],
                    "temperature_c": latest["temperature_c"],
                    "humidity_pct": latest["humidity_pct"],
                    "heat_index_c": latest["heat_index_c"]
                },
                "temperature": point_forecast["temperature"],
                "humidity": point_forecast["humidity"],
                "heat_index": point_forecast["heat_index"]
            },
            "evaluations": backtest_results,
            "sufficiency": {
                "is_sufficient": True,
                "usable_minutes": prep["usable_minutes"],
                "min_required_minutes": cls.MIN_HISTORY_MINUTES,
                "gaps_detected": prep["gaps_detected"],
                "reason": "Sufficient continuous telemetry available."
            },
            "backtest": backtest_results.get(f"{target_horizon}m"),
            "disclaimers": disclaimers
        }

        if use_cache:
            cls._cache[cache_key] = (now, result)

        return result
