#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test helpers — isolated temp database setup and teardown."""

import os
import sqlite3
import tempfile
import atexit

# Set before any backend imports so config.py picks it up
os.environ["TEST_DB_PATH"] = ""

from backend.database import set_db_path

_temp_db_path = None
_cleanup_registered = False


def _cleanup():
    global _temp_db_path
    if _temp_db_path and os.path.exists(_temp_db_path):
        try:
            os.unlink(_temp_db_path)
        except OSError:
            pass


def setup_test_db():
    """Create an isolated temp SQLite database with schema + seed data.

    Returns the temp db path. Call once per test module (e.g. in setUpModule).
    """
    global _temp_db_path, _cleanup_registered

    if _temp_db_path:
        return _temp_db_path  # already set up

    # Schema file is at db/comments_schema.sql relative to repo root
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    schema_path = os.path.join(repo_root, "db", "comments_schema.sql")

    fd, _temp_db_path = tempfile.mkstemp(suffix=".db", prefix="test_comments_")
    os.close(fd)

    # Read schema and execute
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(_temp_db_path)
    conn.executescript(schema_sql)

    # Seed data: a few comments with varied sentiments, platforms, and locked states
    seed_rows = [
        ("bilibili", "bili_c1", "用户A", "A股大涨，赚钱了！", 10,
         None, "BV001", "财经视频1", "投资UP主", "uid_1", None, "2026-06-01", "正面", None),
        ("bilibili", "bili_c2", "用户B", "跌得想哭", 5,
         None, "BV001", "财经视频1", "投资UP主", "uid_1", None, "2026-06-02", "负面", None),
        ("xueqiu", "xq_c1", "用户C", "震荡行情，观望为主", 3,
         None, None, None, None, None, "SH600519", "2026-06-03", "中性", None),
        ("xiaohongshu", "xhs_c1", "用户D", "这个基金真不错", 8,
         None, None, None, None, None, None, "2026-06-04", "正面", None),
        ("bilibili", "bili_c3", "用户E", "被套牢了怎么办", 15,
         None, "BV002", "财经视频2", "投资随感录", "uid_2", None, "2026-06-05", "负面", "正面"),
        ("xueqiu", "xq_c2", "用户F", "长期看好", 20,
         None, None, None, None, None, "SH000001", "2026-06-06", "正面", None),
    ]

    conn.executemany("""
        INSERT INTO comments
            (platform, comment_id, author_name, content, likes,
             source_url, video_bvid, video_title, up_name, up_uid,
             symbol, created_at, sentiment, sentiment_fix)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, seed_rows)
    conn.commit()
    conn.close()

    # Point the backend at the temp DB
    set_db_path(_temp_db_path)

    if not _cleanup_registered:
        atexit.register(_cleanup)
        _cleanup_registered = True

    return _temp_db_path
