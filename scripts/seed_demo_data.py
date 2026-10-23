#!/usr/bin/env python3
"""
Virtual Atmosphere (VA) - Demo Data Seeder
Populates the database with realistic 24-hour historical environmental readings
for immediate dashboard testing in Demo mode.
"""
import sys
import math
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database
from config import Config

def seed_demo_history(hours: int = 24, step_minutes: int = 5, db_path: str = None):
    """Generates continuous historical samples spaced every step_minutes."""
    print(f"Seeding {hours} hours of simulated data ({step_minutes}-minute resolution)...")
    target_db = db_path or Config.DATABASE_PATH
    database.init_db(db_path=target_db)

    now = datetime.now(timezone.utc)
    total_steps = (hours * 60) // step_minutes

    temp_base = 24.5
    press_base = 1013.25

    inserted = 0
    for i in range(total_steps, 0, -1):
        dt = now - timedelta(minutes=i * step_minutes)
        hour_frac = dt.hour + dt.minute / 60.0

        # Sinusoidal daily temperature curve peaking at ~15:00 UTC
        temp_cycle = 4.0 * math.sin((hour_frac - 9.0) * (2.0 * math.pi / 24.0))
        noise_t = (random.random() - 0.5) * 0.4
        temp = round(temp_base + temp_cycle + noise_t, 2)

        # Semi-diurnal barometric tide
        press_tide = 1.2 * math.cos((hour_frac - 10.0) * (4.0 * math.pi / 24.0))
        noise_p = (random.random() - 0.5) * 0.3
        press = round(press_base + press_tide + noise_p, 2)

        database.insert_reading(
            temperature_c=temp,
            pressure_hpa=press,
            source="demo",
            validity_status="valid",
            timestamp=dt.isoformat(),
            db_path=target_db
        )
        inserted += 1

    print(f"Successfully inserted {inserted} demo measurements.")

if __name__ == "__main__":
    seed_demo_history()
