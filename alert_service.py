import logging
from typing import Optional, Dict, Any
from config import Config
import database

logger = logging.getLogger("virtual_atmosphere.alerts")

class AlertService:
    """
    Manages temperature warning alerts, tracking alert lifecycle:
    - active: threshold exceeded, unacknowledged
    - acknowledged: operator acknowledged the warning, condition still elevated
    - resolved: temperature has returned below the threshold
    """

    @staticmethod
    def evaluate_reading(temperature_c: float, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Evaluates a valid temperature reading against the current threshold.
        Avoids creating duplicate alerts during a continuous elevated event.
        Resolves active alerts when temperature safely drops below threshold.
        """
        settings = database.get_settings(db_path=db_path)
        threshold = settings.get("temperature_threshold_c", Config.DEFAULT_TEMPERATURE_THRESHOLD_C)
        hysteresis = Config.ALERT_CLEAR_HYSTERESIS_C

        conn = database.get_connection(db_path=db_path)
        try:
            cursor = conn.cursor()
            # Check for any ongoing alert (either active or acknowledged)
            cursor.execute(
                """
                SELECT id, timestamp, alert_type, measured_value, threshold_value, status, acknowledged_at
                FROM alerts
                WHERE status IN ('active', 'acknowledged')
                ORDER BY id DESC
                LIMIT 1;
                """
            )
            ongoing_alert = cursor.fetchone()

            if temperature_c >= threshold:
                # Temperature is above or equal to threshold
                if ongoing_alert is None:
                    # New alert event!
                    logger.warning(
                        f"Threshold exceeded: {temperature_c:.2f}°C >= {threshold:.2f}°C. Triggering alert."
                    )
                    alert_id = database.create_alert(
                        alert_type="high_temperature",
                        measured_value=temperature_c,
                        threshold_value=threshold,
                        db_path=db_path
                    )
                    return {
                        "id": alert_id,
                        "status": "active",
                        "measured_value": temperature_c,
                        "threshold_value": threshold,
                        "is_new": True
                    }
                else:
                    # Alert is already active or acknowledged for this event; do not duplicate
                    return {
                        "id": ongoing_alert["id"],
                        "status": ongoing_alert["status"],
                        "measured_value": ongoing_alert["measured_value"],
                        "threshold_value": ongoing_alert["threshold_value"],
                        "is_new": False
                    }
            else:
                # Temperature is below threshold
                # Check with hysteresis to avoid flapping at the threshold boundary
                if ongoing_alert is not None and temperature_c < (threshold - hysteresis):
                    logger.info(
                        f"Temperature normalized to {temperature_c:.2f}°C (< {threshold - hysteresis:.2f}°C). "
                        f"Resolving alert #{ongoing_alert['id']}."
                    )
                    database.resolve_active_alerts(db_path=db_path)
                return None
        finally:
            conn.close()

    @staticmethod
    def acknowledge(alert_id: int, db_path: Optional[str] = None) -> bool:
        """Acknowledges an ongoing active alert."""
        return database.acknowledge_alert(alert_id, db_path=db_path)

    @staticmethod
    def get_current_alert_status(db_path: Optional[str] = None) -> Dict[str, Any]:
        """Returns the current alert state for the dashboard and header indicator."""
        active = database.get_active_alert(db_path=db_path)
        settings = database.get_settings(db_path=db_path)
        return {
            "has_active_alert": active is not None,
            "active_alert": active,
            "threshold_c": settings.get("temperature_threshold_c", Config.DEFAULT_TEMPERATURE_THRESHOLD_C),
            "disclaimer": "Configurable temperature warning for school and educational project monitoring. Not certified for medical diagnosis or OSHA/WBGT industrial heat-risk assessment."
        }
