from __future__ import annotations

"""One-time helper for moving old local SQLite data into a PostgreSQL deployment.

Set SQLITE_PATH and DATABASE_URL, then run:
python scripts/migrate_sqlite_to_postgres.py
"""

import os
import sqlite3

from app import db


TABLES = ["materials", "quotations", "line_items", "import_files", "procurement_records", "quotation_items", "field_mappings"]


def main() -> None:
    sqlite_path = os.getenv("SQLITE_PATH", "quotation_history.db")
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    db.init_db()
    with db.connect() as target:
        for table in TABLES:
            rows = [dict(row) for row in source.execute(f"select * from {table}").fetchall()]
            if not rows:
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(columns))
            sql = f"insert into {table} ({', '.join(columns)}) values ({placeholders})"
            target.executemany(sql, [[row[column] for column in columns] for row in rows])
            print(f"copied {len(rows)} rows from {table}")


if __name__ == "__main__":
    main()
