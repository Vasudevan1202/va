"""
Virtual Atmosphere (VA) - Local Short-Term Forecasting Engine (Phase 1)
------------------------------------------------------------------------
Provides explainable, short-term microclimate forecasting (15-minute primary horizon,
with 30m and 60m evaluations) using historical DHT11 temperature and relative humidity data.

Scientific & Design Principles:
1. Honest Data Preparation: Validates physical limits, excludes non-finite/implausible values,
   deduplicates timestamps, and aggregates into 1-minute averages to suppress DHT11 quantization jitter.
2. Empirical Model Selection: Evaluates a Holt-damped linear trend against a persistence
   baseline. If trend does not demonstrate positive out-of-sample skill over persistence,
   persistence is automatically selected as the superior default forecast.
3. Unbiased Backtesting: Time-ordered, rolling-origin walk-forward evaluation with strictly
   past data (zero future leakage) and non-overlapping target evaluation (zero target-overlap leakage).
4. Calibrated Prediction Intervals: Uncertainty intervals are calibrated directly against
   empirical out-of-sample error distributions, guaranteed to achieve >= 80% coverage while
   respecting physical DHT11 hardware uncertainty bounds (±2°C, ±5% RH).
5. Truthful Metrics & Summaries: Skill score = (baseline MAE - model MAE) / baseline MAE * 100.
   Positive skill denotes improvement over persistence; negative skill denotes worse performance.
   Summaries report temperature and humidity independently and never disguise negative skill.
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from weather_service import WeatherService

logger = logging.getLogger(__name__)


def compute_quantile(values: List[float], q: float) -> float:
    """
    Computes empirical quantile (0.0 <= q <= 1.0) using standard linear interpolation.
    """
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n == 1:
        return sorted_v[0]
    idx = (n - 1) * max(0.0, min(1.0, q))
    low = int(math.floor(idx))
    high = int(math.ceil(idx))
    if low == high:
        return sorted_v[low]
    weight = idx - low
    return sorted_v[low] * (1.0 - weight) + sorted_v[high] * weight


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
    DHT11_HARDWARE_TEMP_UNCERTAINTY_C = 2.0   # ±2°C
    DHT11_HARDWARE_HUM_UNCERTAINTY_PCT = 5.0   # ±5% RH

    # Rate of Change Clamping (Maximum plausible room/ambient rate per minute)
    MAX_TEMP_RATE_C_PER_MIN = 0.35   # ~21°C/hour max plausible ambient transient
    MAX_HUM_RATE_PCT_PER_MIN = 1.2   # ~72%/hour max plausible ambient transient

    # Model & Damping Parameters
    DEFAULT_DAMPING_FACTOR = 0.85     # Holt exponential trend damping (0.0 = persistence, 1.0 = linear)
    DEFAULT_HORIZON_MINUTES = 15
    EVALUATED_HORIZONS = [15, 30, 60]

    # Data Freshness & Continuity
    MAX_FRESHNESS_SECONDS = 900.0       # 15 min; beyond this, sensor is marked 'stale'
    OFFLINE_FRESHNESS_SECONDS = 3600.0  # 60 min; beyond this, sensor is marked 'offline'
    MAX_INTERPOLATION_GAP_MINUTES = 10.0  # Gaps > 10 min treated as missing intervals

    # History Sufficiency Configuration
    MIN_HISTORY_MINUTES = 15            # Minimum 15 minutes of historical telemetry required
    MIN_TEST_SAMPLES_BACKTEST = 5       # Minimum verification pairs needed for backtesting stats

    MODEL_VERSION = "1.1.0"

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
        for i in range(1, len(buckets)):
            delta_min = (buckets[i]["dt"] - buckets[i - 1]["dt"]).total_seconds() / 60.0
            if delta_min > cls.MAX_INTERPOLATION_GAP_MINUTES:
                gaps_detected += 1

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
        clamped_slope = max(-max_rate_per_min, min(max_rate_per_min, slope_per_min))

        if 0.0 < damping < 1.0:
            cumulative_weight = damping * (1.0 - (damping ** horizon_min)) / (1.0 - damping)
        elif damping >= 1.0:
            cumulative_weight = float(horizon_min)
        else:
            cumulative_weight = 0.0

        delta = clamped_slope * cumulative_weight
        projected = current_val + delta

        clamped_projected = max(min_bound, min(max_bound, projected))
        actual_delta = clamped_projected - current_val

        return round(clamped_projected, 2), round(actual_delta, 2)

    @classmethod
    def _calculate_calibrated_interval(
        cls,
        predicted_val: float,
        empirical_oos_errors: Optional[List[float]],
        hardware_uncertainty: float,
        min_bound: float,
        max_bound: float,
        target_coverage: float = 0.80
    ) -> Tuple[float, float, str, Optional[float]]:
        """
        Constructs prediction interval calibrated against out-of-sample empirical errors.
        Guarantees that at least target_coverage of empirical errors fall inside the interval,
        while respecting physical DHT11 hardware uncertainty limits.

        Returns (lower_bound, upper_bound, calibration_basis, empirical_coverage_pct).
        """
        hw_floor = hardware_uncertainty * 0.75

        if empirical_oos_errors and len(empirical_oos_errors) >= cls.MIN_TEST_SAMPLES_BACKTEST:
            abs_errors = [abs(e) for e in empirical_oos_errors]
            q_margin = compute_quantile(abs_errors, target_coverage)
            half_width = max(q_margin, hw_floor)

            covered = sum(1 for e in abs_errors if e <= half_width)
            actual_cov_pct = round((covered / len(abs_errors)) * 100.0, 1)

            lower = max(min_bound, round(predicted_val - half_width, 2))
            upper = min(max_bound, round(predicted_val + half_width, 2))
            return lower, upper, "empirical_out_of_sample_quantile", actual_cov_pct

        # Conservative prior based on sensor specification when out-of-sample history is sparse
        half_width = max(hw_floor, hardware_uncertainty * 1.0)
        lower = max(min_bound, round(predicted_val - half_width, 2))
        upper = min(max_bound, round(predicted_val + half_width, 2))
        return lower, upper, "sensor_tolerance_prior (uncalibrated - awaiting test pairs)", None

    @classmethod
    def backtest_horizons(
        cls,
        buckets: List[Dict[str, Any]],
        horizons: Optional[List[int]] = None,
        min_train_minutes: int = 15,
        min_test_samples: int = MIN_TEST_SAMPLES_BACKTEST,
        step_stride_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes chronological rolling-origin walk-forward backtesting.

        Guarantees:
        1. Zero Future-Data Leakage: Only observations up to t_eval are used for training.
        2. Zero Overlapping-Target Leakage: Stepping advances by horizon h (non-overlapping targets).
        3. Zero Training-Evaluation Overlap: Target is strictly in the future (t_eval + h).

        Computes:
        - MAE and RMSE separately for trend and persistence baselines.
        - Skill score: (baseline_mae - model_mae) / baseline_mae * 100.
          Positive skill = trend outperforms persistence.
          Negative skill = persistence outperforms trend.
        - Optimal model selection per horizon.
        - Out-of-sample error distributions for interval calibration.
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
                    "humidity": None,
                    "summary": f"Awaiting historical data to evaluate {h}m horizon."
                }
            return results

        dt_to_idx = {b["dt"].replace(second=0, microsecond=0): idx for idx, b in enumerate(buckets)}

        for h in target_horizons:
            temp_trend_errors: List[float] = []
            temp_pers_errors: List[float] = []
            hum_trend_errors: List[float] = []
            hum_pers_errors: List[float] = []

            # Advance by step_stride_minutes (defaults to horizon h to prevent overlapping targets)
            stride = step_stride_minutes or h
            i = min_train_minutes

            while i < n_total:
                t_eval = buckets[i]["dt"].replace(second=0, microsecond=0)
                t_target = t_eval + timedelta(minutes=h)

                target_idx = dt_to_idx.get(t_target)
                if target_idx is not None:
                    actual_point = buckets[target_idx]
                    actual_temp = actual_point["temperature_c"]
                    actual_hum = actual_point["humidity_pct"]

                    # Strictly past window (zero future leakage)
                    past_window = buckets[:i + 1]

                    # Generate trend prediction
                    recent = past_window[-30:]
                    curr_temp = past_window[-1]["temperature_c"]
                    curr_hum = past_window[-1]["humidity_pct"]

                    t0 = recent[0]["dt"]
                    x_mins = [(r["dt"] - t0).total_seconds() / 60.0 for r in recent]
                    temp_y = [r["temperature_c"] for r in recent]
                    hum_y = [r["humidity_pct"] for r in recent]

                    _, temp_slope, _ = cls._fit_linear_slope(x_mins, temp_y)
                    _, hum_slope, _ = cls._fit_linear_slope(x_mins, hum_y)

                    pred_trend_temp, _ = cls._damped_trend_projection(
                        curr_temp, temp_slope, h, cls.DEFAULT_DAMPING_FACTOR,
                        cls.MAX_TEMP_RATE_C_PER_MIN, cls.DHT11_TEMP_MIN_C, cls.DHT11_TEMP_MAX_C
                    )
                    pred_trend_hum, _ = cls._damped_trend_projection(
                        curr_hum, hum_slope, h, cls.DEFAULT_DAMPING_FACTOR,
                        cls.MAX_HUM_RATE_PCT_PER_MIN, cls.DHT11_HUM_MIN_PCT, cls.DHT11_HUM_MAX_PCT
                    )

                    # Persistence prediction: latest reading continues
                    pred_pers_temp = curr_temp
                    pred_pers_hum = curr_hum

                    # Record out-of-sample errors: (actual - predicted)
                    temp_trend_errors.append(actual_temp - pred_trend_temp)
                    temp_pers_errors.append(actual_temp - pred_pers_temp)
                    hum_trend_errors.append(actual_hum - pred_trend_hum)
                    hum_pers_errors.append(actual_hum - pred_pers_hum)

                # Non-overlapping step forward
                i += max(1, stride)

            n_samples = len(temp_trend_errors)
            if n_samples < min_test_samples:
                results[f"{h}m"] = {
                    "horizon_minutes": h,
                    "status": "insufficient_test_data",
                    "samples_evaluated": n_samples,
                    "min_samples_required": min_test_samples,
                    "explanation": f"Evaluated {n_samples} non-overlapping verification pairs. Minimum {min_test_samples} required for statistically sound validation.",
                    "temperature": None,
                    "humidity": None,
                    "summary": f"Awaiting at least {min_test_samples} verification pairs at {h}m horizon."
                }
                continue

            # Calculate Temperature Metrics
            temp_mae_trend = sum(abs(e) for e in temp_trend_errors) / n_samples
            temp_rmse_trend = math.sqrt(sum(e ** 2 for e in temp_trend_errors) / n_samples)
            temp_mae_pers = sum(abs(e) for e in temp_pers_errors) / n_samples
            temp_rmse_pers = math.sqrt(sum(e ** 2 for e in temp_pers_errors) / n_samples)

            # Skill Score: (baseline MAE - model MAE) / baseline MAE * 100
            # Positive = trend improves over persistence; Negative = persistence is superior
            temp_skill_mae = ((temp_mae_pers - temp_mae_trend) / max(1e-4, temp_mae_pers)) * 100.0
            temp_skill_rmse = ((temp_rmse_pers - temp_rmse_trend) / max(1e-4, temp_rmse_pers)) * 100.0

            # Calculate Humidity Metrics
            hum_mae_trend = sum(abs(e) for e in hum_trend_errors) / n_samples
            hum_rmse_trend = math.sqrt(sum(e ** 2 for e in hum_trend_errors) / n_samples)
            hum_mae_pers = sum(abs(e) for e in hum_pers_errors) / n_samples
            hum_rmse_pers = math.sqrt(sum(e ** 2 for e in hum_pers_errors) / n_samples)

            hum_skill_mae = ((hum_mae_pers - hum_mae_trend) / max(1e-4, hum_mae_pers)) * 100.0
            hum_skill_rmse = ((hum_rmse_pers - hum_rmse_trend) / max(1e-4, hum_rmse_pers)) * 100.0

            # Determine optimal model per metric
            temp_optimal = "damped_linear_trend" if temp_skill_mae > 0.0 else "persistence"
            hum_optimal = "damped_linear_trend" if hum_skill_mae > 0.0 else "persistence"

            # Truthful Temperature Summary
            if temp_skill_mae > 0.5:
                temp_summary = f"Trend model outperforms persistence by {temp_skill_mae:.1f}% (MAE {temp_mae_trend:.2f}°C vs {temp_mae_pers:.2f}°C)."
            elif temp_skill_mae < -0.5:
                temp_summary = f"Persistence outperforms trend model by {abs(temp_skill_mae):.1f}% (MAE {temp_mae_pers:.2f}°C vs {temp_mae_trend:.2f}°C). Persistence is selected."
            else:
                temp_summary = f"Trend model and persistence perform identically within ±0.5% (MAE {temp_mae_trend:.2f}°C vs {temp_mae_pers:.2f}°C). Persistence is selected."

            # Truthful Humidity Summary
            if hum_skill_mae > 0.5:
                hum_summary = f"Trend model outperforms persistence by {hum_skill_mae:.1f}% (MAE {hum_mae_trend:.2f}% vs {hum_mae_pers:.2f}%)."
            elif hum_skill_mae < -0.5:
                hum_summary = f"Persistence outperforms trend model by {abs(hum_skill_mae):.1f}% (MAE {hum_mae_pers:.2f}% vs {hum_mae_trend:.2f}%). Persistence is selected."
            else:
                hum_summary = f"Trend model and persistence perform identically within ±0.5% (MAE {hum_mae_trend:.2f}% vs {hum_mae_pers:.2f}%). Persistence is selected."

            # Combined Truthful Overview
            if temp_optimal == "persistence" and hum_optimal == "persistence":
                overall_summary = f"Persistence is the optimal predictor at {h}m horizon for both temperature and humidity."
            elif temp_optimal == "damped_linear_trend" and hum_optimal == "damped_linear_trend":
                overall_summary = f"Damped trend model outperforms persistence at {h}m horizon for both temperature and humidity."
            elif temp_optimal == "persistence":
                overall_summary = f"Persistence is optimal for temperature ({temp_summary}); trend is optimal for humidity ({hum_summary})."
            else:
                overall_summary = f"Trend is optimal for temperature ({temp_summary}); persistence is optimal for humidity ({hum_summary})."

            is_active_horizon = (h == cls.DEFAULT_HORIZON_MINUTES)
            results[f"{h}m"] = {
                "horizon_minutes": h,
                "status": "active" if is_active_horizon else "evaluated_experimental",
                "samples_evaluated": n_samples,
                "min_samples_required": min_test_samples,
                "evaluation_method": "rolling_origin_walk_forward_non_overlapping",
                "temperature": {
                    "trend_mae_c": round(temp_mae_trend, 2),
                    "trend_rmse_c": round(temp_rmse_trend, 2),
                    "persistence_mae_c": round(temp_mae_pers, 2),
                    "persistence_rmse_c": round(temp_rmse_pers, 2),
                    "skill_score_pct": round(temp_skill_mae, 1),
                    "skill_score_rmse_pct": round(temp_skill_rmse, 1),
                    "skill_status": "positive" if temp_skill_mae > 0.5 else ("negative" if temp_skill_mae < -0.5 else "neutral"),
                    "optimal_model": temp_optimal,
                    "summary": temp_summary,
                    # Stored for prediction interval calibration
                    "_empirical_oos_errors": temp_pers_errors if temp_optimal == "persistence" else temp_trend_errors
                },
                "humidity": {
                    "trend_mae_pct": round(hum_mae_trend, 2),
                    "trend_rmse_pct": round(hum_rmse_trend, 2),
                    "persistence_mae_pct": round(hum_mae_pers, 2),
                    "persistence_rmse_pct": round(hum_rmse_pers, 2),
                    "skill_score_pct": round(hum_skill_mae, 1),
                    "skill_score_rmse_pct": round(hum_skill_rmse, 1),
                    "skill_status": "positive" if hum_skill_mae > 0.5 else ("negative" if hum_skill_mae < -0.5 else "neutral"),
                    "optimal_model": hum_optimal,
                    "summary": hum_summary,
                    "_empirical_oos_errors": hum_pers_errors if hum_optimal == "persistence" else hum_trend_errors
                },
                "summary": overall_summary
            }

        return results

    @classmethod
    def generate_point_forecast(
        cls,
        buckets: List[Dict[str, Any]],
        horizon_min: int = 15,
        damping: float = DEFAULT_DAMPING_FACTOR,
        window_minutes: int = 30,
        backtest_evaluations: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generates point estimates and calibrated prediction intervals.
        Evaluates persistence as default; selects trend only where out-of-sample backtesting demonstrates positive skill.
        """
        if not buckets:
            raise ValueError("No historical observations provided to generate forecast.")

        latest = buckets[-1]
        curr_temp = latest["temperature_c"]
        curr_hum = latest["humidity_pct"]

        recent = buckets[-window_minutes:]
        n = len(recent)

        # 1. Baseline: Persistence predictions
        pers_temp = curr_temp
        pers_hum = curr_hum

        # 2. Damped Trend calculations
        if n >= 3:
            t0 = recent[0]["dt"]
            x_mins = [(r["dt"] - t0).total_seconds() / 60.0 for r in recent]
            temp_y = [r["temperature_c"] for r in recent]
            hum_y = [r["humidity_pct"] for r in recent]

            _, temp_slope, _ = cls._fit_linear_slope(x_mins, temp_y)
            _, hum_slope, _ = cls._fit_linear_slope(x_mins, hum_y)

            trend_temp, delta_trend_temp = cls._damped_trend_projection(
                curr_temp, temp_slope, horizon_min, damping,
                cls.MAX_TEMP_RATE_C_PER_MIN, cls.DHT11_TEMP_MIN_C, cls.DHT11_TEMP_MAX_C
            )
            trend_hum, delta_trend_hum = cls._damped_trend_projection(
                curr_hum, hum_slope, horizon_min, damping,
                cls.MAX_HUM_RATE_PCT_PER_MIN, cls.DHT11_HUM_MIN_PCT, cls.DHT11_HUM_MAX_PCT
            )
        else:
            trend_temp = pers_temp
            delta_trend_temp = 0.0
            trend_hum = pers_hum
            delta_trend_hum = 0.0
            temp_slope = 0.0
            hum_slope = 0.0

        # 3. Model Selection based on Out-of-Sample Backtesting Skill
        # Persistence is the default unless backtesting explicitly supports trend
        horizon_key = f"{horizon_min}m"
        bt_data = backtest_evaluations.get(horizon_key) if backtest_evaluations else None

        temp_skill = None
        hum_skill = None
        temp_oos_errors = None
        hum_oos_errors = None

        if bt_data and bt_data.get("status") == "active":
            temp_info = bt_data.get("temperature", {})
            hum_info = bt_data.get("humidity", {})
            temp_skill = temp_info.get("skill_score_pct")
            hum_skill = hum_info.get("skill_score_pct")
            temp_oos_errors = temp_info.get("_empirical_oos_errors")
            hum_oos_errors = hum_info.get("_empirical_oos_errors")

        # Select Temperature Forecast
        if temp_skill is not None and temp_skill > 0.0:
            selected_temp_model = "damped_linear_trend"
            pred_temp = trend_temp
            delta_temp = delta_trend_temp
            temp_reason = f"Damped trend selected: backtest skill +{temp_skill:.1f}% over persistence (MAE {bt_data['temperature']['trend_mae_c']}°C vs {bt_data['temperature']['persistence_mae_c']}°C)."
        else:
            selected_temp_model = "persistence"
            pred_temp = pers_temp
            delta_temp = 0.0
            if temp_skill is not None:
                temp_reason = f"Persistence selected as default: out-of-sample persistence outperforms trend by {abs(temp_skill):.1f}% (MAE {bt_data['temperature']['persistence_mae_c']}°C vs {bt_data['temperature']['trend_mae_c']}°C)."
            else:
                temp_reason = "Persistence selected as default: awaiting out-of-sample backtest validation."

        # Select Humidity Forecast
        if hum_skill is not None and hum_skill > 0.0:
            selected_hum_model = "damped_linear_trend"
            pred_hum = trend_hum
            delta_hum = delta_trend_hum
            hum_reason = f"Damped trend selected: backtest skill +{hum_skill:.1f}% over persistence (MAE {bt_data['humidity']['trend_mae_pct']}% vs {bt_data['humidity']['persistence_mae_pct']}%)."
        else:
            selected_hum_model = "persistence"
            pred_hum = pers_hum
            delta_hum = 0.0
            if hum_skill is not None:
                hum_reason = f"Persistence selected as default: out-of-sample persistence outperforms trend by {abs(hum_skill):.1f}% (MAE {bt_data['humidity']['persistence_mae_pct']}% vs {bt_data['humidity']['trend_mae_pct']}%)."
            else:
                hum_reason = "Persistence selected as default: awaiting out-of-sample backtest validation."

        # 4. Calibrated Prediction Intervals
        temp_lower, temp_upper, temp_cal_basis, temp_cov_pct = cls._calculate_calibrated_interval(
            pred_temp, temp_oos_errors, cls.DHT11_HARDWARE_TEMP_UNCERTAINTY_C,
            cls.DHT11_TEMP_MIN_C, cls.DHT11_TEMP_MAX_C, target_coverage=0.80
        )
        hum_lower, hum_upper, hum_cal_basis, hum_cov_pct = cls._calculate_calibrated_interval(
            pred_hum, hum_oos_errors, cls.DHT11_HARDWARE_HUM_UNCERTAINTY_PCT,
            cls.DHT11_HUM_MIN_PCT, cls.DHT11_HUM_MAX_PCT, target_coverage=0.80
        )

        return {
            "horizon_minutes": horizon_min,
            "temperature": {
                "current_c": curr_temp,
                "predicted_c": pred_temp,
                "change_c": delta_temp,
                "selected_model": selected_temp_model,
                "selection_reason": temp_reason,
                "persistence_c": pers_temp,
                "trend_predicted_c": trend_temp,
                "interval_80": [temp_lower, temp_upper],
                "lower_bound_c": temp_lower,
                "upper_bound_c": temp_upper,
                "interval_calibration": temp_cal_basis,
                "empirical_coverage_pct": temp_cov_pct,
                "rate_c_per_min": round(temp_slope, 4)
            },
            "humidity": {
                "current_pct": curr_hum,
                "predicted_pct": pred_hum,
                "change_pct": delta_hum,
                "selected_model": selected_hum_model,
                "selection_reason": hum_reason,
                "persistence_pct": pers_hum,
                "trend_predicted_pct": trend_hum,
                "interval_80": [hum_lower, hum_upper],
                "lower_bound_pct": hum_lower,
                "upper_bound_pct": hum_upper,
                "interval_calibration": hum_cal_basis,
                "empirical_coverage_pct": hum_cov_pct,
                "rate_pct_per_min": round(hum_slope, 4)
            },
            "heat_index": {
                "current_c": WeatherService.compute_heat_index(curr_temp, curr_hum),
                "predicted_c": WeatherService.compute_heat_index(pred_temp, pred_hum)
            }
        }

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
        1. Prepares and validates historical telemetry.
        2. Evaluates out-of-sample backtesting across horizons.
        3. Dynamically selects optimal champion model (persistence vs trend) per variable.
        4. Calibrates prediction intervals against empirical errors.
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

        # 3. Perform walk-forward rolling origin backtesting across all horizons first
        target_horizon = horizon_min if horizon_min in cls.EVALUATED_HORIZONS else cls.DEFAULT_HORIZON_MINUTES
        backtest_results = cls.backtest_horizons(buckets)

        # 4. Generate forecast with empirical model selection & calibrated intervals
        point_forecast = cls.generate_point_forecast(
            buckets,
            horizon_min=target_horizon,
            backtest_evaluations=backtest_results
        )

        target_dt = latest["dt"] + timedelta(minutes=target_horizon)

        # Clean internal evaluation artifacts before serialization
        clean_evaluations = {}
        for h_key, h_data in backtest_results.items():
            h_copy = dict(h_data)
            if "temperature" in h_copy and isinstance(h_copy["temperature"], dict):
                h_copy["temperature"] = {k: v for k, v in h_copy["temperature"].items() if not k.startswith("_")}
            if "humidity" in h_copy and isinstance(h_copy["humidity"], dict):
                h_copy["humidity"] = {k: v for k, v in h_copy["humidity"].items() if not k.startswith("_")}
            clean_evaluations[h_key] = h_copy

        primary_backtest = clean_evaluations.get(f"{target_horizon}m")

        result = {
            "status": "success",
            "is_available": True,
            "generated_at": now.isoformat(),
            "model": {
                "name": point_forecast["temperature"]["selected_model"],
                "version": cls.MODEL_VERSION,
                "strategy": "empirical_champion_selection",
                "temperature_selected": point_forecast["temperature"]["selected_model"],
                "humidity_selected": point_forecast["humidity"]["selected_model"]
            },
            "models_evaluated": {
                "persistence_baseline": "Latest observed reading projected forward (y_t+h = y_t)",
                "damped_linear_trend": f"Holt-damped local linear trend (damping factor {cls.DEFAULT_DAMPING_FACTOR})",
                "selection_policy": "Empirical champion selection: persistence is the default; trend is selected only when demonstrated to improve out-of-sample MAE."
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
            "evaluations": clean_evaluations,
            "sufficiency": {
                "is_sufficient": True,
                "usable_minutes": prep["usable_minutes"],
                "min_required_minutes": cls.MIN_HISTORY_MINUTES,
                "gaps_detected": prep["gaps_detected"],
                "reason": "Sufficient continuous telemetry available."
            },
            "backtest": primary_backtest,
            "disclaimers": disclaimers
        }

        if use_cache:
            cls._cache[cache_key] = (now, result)

        return result
