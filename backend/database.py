#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Database connection helper"""

import sqlite3
import os as _os
from backend.config import DB_PATH

_db_path_override = None


def get_db():
    path = _db_path_override or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def set_db_path(path):
    global _db_path_override
    _db_path_override = path


def row_to_dict(row):
    return dict(row) if row else None