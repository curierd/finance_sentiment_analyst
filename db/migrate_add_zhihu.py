#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate existing SQLite DB to support 'zhihu' platform.

SQLite doesn't support ALTER TABLE for CHECK constraints, so we:
1. Create new tables with updated constraints
2. Copy all data
3. Drop old tables
4. Rename new tables
5. Recreate indexes

Run: python db/migrate_add_zhihu.py
"""

import os
import sqlite3
import sys

DB_PATH = os.environ.get("TEST_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "comments.db"
)


def migrate_comments_table(conn):
    print("[MIGRATE] Updating comments table...")

    existing = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='comments'").fetchone()
    if not existing:
        print("[SKIP] comments table not found")
        return

    current_sql = existing[0]
    if "zhihu" in current_sql:
        print("[SKIP] zhihu already in CHECK constraint")
        return

    print("  Creating comments_new...")
    conn.execute("""
        CREATE TABLE comments_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL CHECK(platform IN ('bilibili', 'xiaohongshu', 'xueqiu', 'zhihu')),
            comment_id      TEXT,
            author_id       TEXT,
            author_name     TEXT,
            content TEXT NOT NULL,
            likes           INTEGER DEFAULT 0,
            replies         INTEGER DEFAULT 0,
            retweets        INTEGER DEFAULT 0,
            source_url      TEXT,
            local_image_path TEXT,
            original_url    TEXT,
            video_bvid      TEXT,
            video_title     TEXT,
            up_name         TEXT,
            up_uid          TEXT,
            symbol TEXT,
            created_at      TEXT,
            collected_at    TEXT DEFAULT (datetime('now')),
            sentiment TEXT CHECK(sentiment IN ('正面', '负面', '中性')),
            sentiment_score REAL,
            sentiment_fix TEXT CHECK(sentiment_fix IN ('正面', '负面', '中性')),
            raw_data TEXT
        )
    """)

    print("  Copying data...")
    cols = [
        "id", "platform", "comment_id", "author_id", "author_name", "content",
        "likes", "replies", "retweets", "source_url", "local_image_path",
        "original_url", "video_bvid", "video_title", "up_name", "up_uid",
        "symbol", "created_at", "collected_at", "sentiment", "sentiment_score",
        "sentiment_fix", "raw_data"
    ]
    col_list = ", ".join(cols)
    conn.execute(f"INSERT INTO comments_new ({col_list}) SELECT {col_list} FROM comments")
    count = conn.execute("SELECT COUNT(*) FROM comments_new").fetchone()[0]
    print(f"  Copied {count} rows")

    print("  Dropping old comments table...")
    conn.execute("DROP TABLE comments")

    print("  Renaming comments_new to comments...")
    conn.execute("ALTER TABLE comments_new RENAME TO comments")

    print("  Recreating indexes...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_platform ON comments(platform)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_likes ON comments(likes DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_sentiment ON comments(sentiment)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_platform_date ON comments(platform, collected_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_high_likes ON comments(likes) WHERE likes > 10")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_platform_sentiment ON comments(platform, sentiment)")

    print("[OK] comments table migrated")


def migrate_up_masters_table(conn):
    print("[MIGRATE] Updating up_masters table...")

    existing = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='up_masters'").fetchone()
    if not existing:
        print("[SKIP] up_masters table not found")
        return

    current_sql = existing[0]
    if "zhihu" in current_sql:
        print("[SKIP] zhihu already in CHECK constraint")
        return

    conn.execute("""
        CREATE TABLE up_masters_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL CHECK(platform IN ('bilibili', 'xiaohongshu', 'xueqiu', 'zhihu')),
            uid TEXT NOT NULL,
            name TEXT NOT NULL,
            fans_count INTEGER DEFAULT 0,
            video_count INTEGER DEFAULT 0,
            blacklisted INTEGER DEFAULT 0,
            source_file TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(platform, uid)
        )
    """)

    cols = ["id", "platform", "uid", "name", "fans_count", "video_count",
            "blacklisted", "source_file", "created_at"]
    col_list = ", ".join(cols)
    conn.execute(f"INSERT INTO up_masters_new ({col_list}) SELECT {col_list} FROM up_masters")
    conn.execute("DROP TABLE up_masters")
    conn.execute("ALTER TABLE up_masters_new RENAME TO up_masters")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_up_masters_platform ON up_masters(platform)")
    print("[OK] up_masters table migrated")


def migrate_videos_table(conn):
    print("[MIGRATE] Updating videos table...")

    existing = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='videos'").fetchone()
    if not existing:
        print("[SKIP] videos table not found")
        return

    current_sql = existing[0]
    if "zhihu" in current_sql:
        print("[SKIP] zhihu already in CHECK constraint")
        return

    conn.execute("""
        CREATE TABLE videos_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL CHECK(platform IN ('bilibili', 'xiaohongshu', 'xueqiu', 'zhihu')),
            video_id TEXT NOT NULL,
            title TEXT,
            up_name         TEXT,
            up_uid TEXT,
            stats TEXT,
            pubdate         TEXT,
            url TEXT,
            collected_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(platform, video_id)
        )
    """)

    cols = ["id", "platform", "video_id", "title", "up_name", "up_uid",
            "stats", "pubdate", "url", "collected_at"]
    col_list = ", ".join(cols)
    conn.execute(f"INSERT INTO videos_new ({col_list}) SELECT {col_list} FROM videos")
    conn.execute("DROP TABLE videos")
    conn.execute("ALTER TABLE videos_new RENAME TO videos")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_platform ON videos(platform)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_up ON videos(up_uid)")
    print("[OK] videos table migrated")


def main():
    if not os.path.exists(DB_PATH):
        print(f"[FATAL] Database not found: {DB_PATH}")
        sys.exit(1)

    print(f"[MIGRATE] Target DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")

    try:
        migrate_comments_table(conn)
        migrate_up_masters_table(conn)
        migrate_videos_table(conn)
        conn.commit()
        print("\n[DONE] Migration completed successfully")
    except Exception as e:
        conn.rollback()
        print(f"\n[FATAL] Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
