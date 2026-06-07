#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Database connection helper"""

import sqlite3
from backend.config import DB_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    return dict(row) if row else None