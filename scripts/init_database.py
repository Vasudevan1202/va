#!/usr/bin/env python3
"""
Virtual Atmosphere (VA) - Database Initialization Script
Initializes SQLite tables, indexes, and initial configuration.
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database
from config import Config

def main():
    print(f"Initializing Virtual Atmosphere database at: {Config.DATABASE_PATH}")
    database.init_db()
    stats = database.get_db_stats()
    print("Database initialization complete.")
    print(f"  - Status: {stats['status']}")
    print(f"  - Total readings: {stats['readings_count']}")
    print(f"  - Total alerts: {stats['alerts_count']}")
    print(f"  - File size: {stats['file_size_kb']} KB")

if __name__ == "__main__":
    main()
