#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker entrypoint: initialize DB schema if needed, apply PRAGMAs.

This script runs before the Flask app starts. It ensures:
1. The SQLite database file exists with correct schema
2. WAL mode + recommended PRAGMAs are enabled
"""

import os
import sqlite3
import sys


def main():
    db_dsn = os.environ.get("DB_DSN", "file:data/sqlite/comments.db?mode=rwc")
    # Strip SQLite URI prefix
    db_path = db_dsn
    if db_path.startswith("file:"):
        db_path = db_path.split("?")[0].replace("file:", "")

    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.isdir(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        print(f"Created data directory: {db_dir}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Apply PRAGMAs
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")

    # Load schema if comments table doesn't exist
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='comments'"
    ).fetchone()

    if row is None:
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "db", "comments_schema.sql"
        )
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                # Skip PRAGMA lines (we already ran them) and execute the rest
                for stmt in f.read().split(";"):
                    stmt = stmt.strip()
                    if stmt and not stmt.upper().startswith("PRAGMA"):
                        conn.execute(stmt)
            conn.commit()
            print(f"Initialized database schema from {schema_path}")
        else:
            print(f"WARNING: Schema file not found: {schema_path}")

    conn.close()
    print(f"Database ready: {db_path}")


if __name__ == "__main__":
    main()
