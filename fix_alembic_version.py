#!/usr/bin/env python
"""Fix Alembic migration version tracking on Windows."""
import sqlite3
from pathlib import Path

db_path = Path("gitonboard.db").resolve()
print(f"Database: {db_path}")

if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    # Check if alembic_version exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
    if cursor.fetchone():
        cursor.execute("SELECT version_num FROM alembic_version")
        versions = cursor.fetchall()
        print(f"Current versions: {versions}")

        # Stamp to latest migration
        cursor.execute("DELETE FROM alembic_version")
        cursor.execute("INSERT INTO alembic_version (version_num) VALUES (?)", ("e5f6a7b8c9d0",))
        conn.commit()
        print("✓ Stamped to e5f6a7b8c9d0 (latest)")
    else:
        print("No alembic_version table - creating and stamping...")
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        cursor.execute("INSERT INTO alembic_version (version_num) VALUES (?)", ("e5f6a7b8c9d0",))
        conn.commit()
        print("✓ Created and stamped to e5f6a7b8c9d0")

finally:
    conn.close()

print("\nNext: uv run phase2k_complete_e2e_validation.py")
