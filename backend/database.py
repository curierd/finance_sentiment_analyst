#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Database connection helper — SQLite with WAL, foreign keys, timeout."""

import sqlite3
import os as _os
from backend.config import DB_PATH

_db_path_override = None


def get_db():
    """Get an SQLite connection with recommended PRAGMAs applied."""
    path = _db_path_override or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Apply PRAGMAs on every connection (idempotent, cheap)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def set_db_path(path):
    global _db_path_override
    _db_path_override = path


def row_to_dict(row):
    return dict(row) if row else None
