#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backend configuration — database paths and environment detection."""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# DB_DRIVER: "sqlite" (default) or "postgres" (future)
DB_DRIVER = os.environ.get("DB_DRIVER", "sqlite")

# DB_DSN: SQLite file path or Postgres connection string
#   Docker:   file:/app/data/comments.db?mode=rwc&cache=shared&timeout=30
#   Local dev: defaults to db/comments.db
_default_db_path = os.path.join(BASE_DIR, "db", "comments.db")
DB_DSN = os.environ.get("DB_DSN", _default_db_path)

# Resolve DB_PATH for backward compatibility
# In Docker, DB_DSN might be a URI like "file:/app/data/comments.db?..."
_db_path_raw = DB_DSN
if _db_path_raw.startswith("file:"):
    _db_path_raw = _db_path_raw.split("?")[0].replace("file:", "")
DB_PATH = os.environ.get("TEST_DB_PATH") or _db_path_raw

# Upload / static files directory
#   Docker:   /app/uploads
#   Local dev: project root
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", BASE_DIR)

# Image URL prefix (used by frontend to construct image src)
#   Docker:   /uploads
#   Local dev: /comments
IMAGE_URL_PREFIX = os.environ.get("IMAGE_URL_PREFIX", "/comments")
