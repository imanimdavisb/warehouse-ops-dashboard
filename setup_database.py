"""Build warehouse_ops.db from the generated CSVs.

Runs sql/schema.sql, loads both tables, and prints a short summary so you can
see the load succeeded.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "warehouse_ops.db"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
DATA_DIR = ROOT / "data"

TABLES = {
    "warehouse_performance": "warehouse_performance.csv",
    "department_targets": "department_targets.csv",
}


def main() -> None:
    missing = [csv for csv in TABLES.values() if not (DATA_DIR / csv).exists()]
    if missing:
        raise SystemExit(f"Missing data files: {', '.join(missing)}. Run generate_data.py first.")

    connection = sqlite3.connect(DB_PATH)
    try:
        connection.executescript(SCHEMA_PATH.read_text())

        for table, csv_name in TABLES.items():
            frame = pd.read_csv(DATA_DIR / csv_name)
            frame.to_sql(table, connection, if_exists="append", index=False)
            print(f"Loaded {len(frame):,} rows into {table}")

        connection.commit()

        date_range = connection.execute(
            "SELECT MIN(work_date), MAX(work_date) FROM warehouse_performance"
        ).fetchone()
        print(f"Date range: {date_range[0]} to {date_range[1]}")
        print(f"Database ready at {DB_PATH.name}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
