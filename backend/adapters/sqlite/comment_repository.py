#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite adapter — implements domain repository interfaces with SQLite."""

import sqlite3
import os
from backend.database import get_db, row_to_dict, set_db_path

# Re-export for convenience
__all__ = ["CommentRepository", "SqliteUnitOfWork", "init_sqlite_pragmas"]


class CommentRepository:
    """SQLite-backed comment repository (adapts domain.CommentRepo protocol)."""

    def find_all(self, filters=None):
        filters = filters or {}
        conn = get_db()
        where, params = self._build_where(filters)

        total = conn.execute(
            f"SELECT COUNT(*) FROM comments WHERE {' AND '.join(where) if where else '1=1'}",
            params
        ).fetchone()[0]

        page = filters.get("page", 1)
        page_size = filters.get("page_size", 50)
        offset = (page - 1) * page_size

        rows = conn.execute(
            f"""
            SELECT id, platform, comment_id, author_name, content, likes,
                   replies, retweets, source_url, local_image_path, original_url,
                   video_bvid, video_title, up_name, up_uid, symbol, created_at,
                   collected_at, sentiment, sentiment_score, sentiment_fix
            FROM comments
            WHERE {' AND '.join(where) if where else '1=1'}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()
        conn.close()
        return {
            "items": [row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }

    def find_by_id(self, comment_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        conn.close()
        return row_to_dict(row)

    def update_image(self, comment_id, local_image_path=None, original_url=None):
        conn = get_db()
        sets, params = [], []
        if local_image_path is not None:
            sets.append("local_image_path = ?")
            params.append(local_image_path)
        if original_url is not None:
            sets.append("original_url = ?")
            params.append(original_url)
        if not sets:
            row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
            conn.close()
            return row_to_dict(row)
        params.append(comment_id)
        conn.execute(f"UPDATE comments SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        conn.close()
        return row_to_dict(row)

    def update_sentiment_fix(self, comment_id, sentiment_fix):
        conn = get_db()
        if sentiment_fix:
            conn.execute(
                "UPDATE comments SET sentiment_fix = ?, sentiment = ? WHERE id = ?",
                (sentiment_fix, sentiment_fix, comment_id),
            )
        else:
            conn.execute("UPDATE comments SET sentiment_fix = NULL WHERE id = ?", (comment_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        conn.close()
        return row_to_dict(row)

    def stats(self, filters=None):
        filters = filters or {}
        where, params = self._build_where(filters)
        where_clause = " AND ".join(where) if where else "1=1"

        conn = get_db()
        auto = conn.execute(f"""
            SELECT sentiment as s, COUNT(*) as cnt
            FROM comments WHERE sentiment_fix IS NULL AND ({where_clause})
            GROUP BY s
        """, params).fetchall()

        locked = conn.execute(f"""
            SELECT sentiment_fix as s, COUNT(*) as cnt
            FROM comments WHERE sentiment_fix IS NOT NULL AND ({where_clause})
            GROUP BY s
        """, params).fetchall()

        weighted = conn.execute(f"""
            SELECT sentiment as s, SUM(likes) as total_likes
            FROM comments WHERE likes > 0 AND sentiment_fix IS NULL AND ({where_clause})
            GROUP BY s
        """, params).fetchall()
        total_likes = sum(r["total_likes"] for r in weighted if r["s"])

        conn.close()
        return {
            "auto": {r["s"]: r["cnt"] for r in auto if r["s"]},
            "locked": {r["s"]: r["cnt"] for r in locked if r["s"]},
            "locked_count": sum(r["cnt"] for r in locked),
            "auto_count": sum(r["cnt"] for r in auto),
            "like_weighted": {
                r["s"]: round(r["total_likes"] / total_likes * 100, 1) if total_likes else 0
                for r in weighted if r["s"]
            },
        }

    def stats_by_date(self, granularity="day", filters=None):
        filters = filters or {}
        where, params = self._build_where(filters)
        where_clause = " AND ".join(where) if where else "1=1"

        if granularity not in ("day", "week", "month"):
            granularity = "day"
        date_format = {
            "day": "%Y-%m-%d",
            "week": "%Y-%W",
            "month": "%Y-%m",
        }[granularity]
        conn = get_db()
        rows = conn.execute(f"""
            SELECT
                strftime('{date_format}',
                    COALESCE(NULLIF(collected_at, ''), NULLIF(created_at, ''), 'now')
                ) as period,
                COALESCE(sentiment_fix, sentiment) as s,
                COUNT(*) as cnt,
                SUM(likes) as likes
            FROM comments
            WHERE s IS NOT NULL AND ({where_clause})
            GROUP BY period, s
            ORDER BY period ASC
        """, params).fetchall()
        conn.close()

        by_period = {}
        for r in rows:
            p = r["period"]
            if p is None:
                continue
            if p not in by_period:
                by_period[p] = {"total": 0, "positive": 0, "neutral": 0, "negative": 0}
            sentiment_key = {"正面": "positive", "中性": "neutral", "负面": "negative"}.get(r["s"])
            if sentiment_key:
                by_period[p][sentiment_key] = r["cnt"]
                by_period[p]["total"] += r["cnt"]
        return by_period

    def find_up_masters(self):
        conn = get_db()
        rows = conn.execute("""
            SELECT DISTINCT up_name, up_uid, platform
            FROM comments
            WHERE up_name IS NOT NULL AND up_name != ''
            ORDER BY platform, up_name
        """).fetchall()
        conn.close()
        return [row_to_dict(r) for r in rows]

    def find_videos(self):
        conn = get_db()
        rows = conn.execute("""
            SELECT DISTINCT video_title, video_bvid, up_name, platform
            FROM comments
            WHERE video_title IS NOT NULL AND video_title != ''
            ORDER BY video_title
            LIMIT 200
        """).fetchall()
        conn.close()
        return [row_to_dict(r) for r in rows]

    def insert(self, data):
        conn = get_db()
        conn.execute("""
            INSERT INTO comments
                (platform, comment_id, author_name, content, likes,
                 source_url, local_image_path, original_url,
                 video_bvid, video_title, up_name, up_uid,
                 symbol, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("platform"),
            data.get("comment_id"),
            data.get("author_name"),
            data.get("content"),
            data.get("likes", 0),
            data.get("source_url"),
            data.get("local_image_path"),
            data.get("original_url"),
            data.get("video_bvid"),
            data.get("video_title"),
            data.get("up_name"),
            data.get("up_uid"),
            data.get("symbol"),
            data.get("created_at"),
        ))
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (new_id,)).fetchone()
        conn.close()
        return row_to_dict(row)

    def delete(self, comment_id):
        conn = get_db()
        conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()
        changes = conn.total_changes
        conn.close()
        return changes > 0

    def find_unlocked_ids_by_filter(self, filters=None):
        filters = filters or {}
        where, params = self._build_where(filters)
        where.append("sentiment_fix IS NULL")
        where_clause = " AND ".join(where)

        conn = get_db()
        rows = conn.execute(
            f"SELECT id, content FROM comments WHERE {where_clause} ORDER BY id",
            params,
        ).fetchall()
        conn.close()
        return [{"id": r["id"], "content": r["content"]} for r in rows]

    def batch_update_sentiment(self, updates):
        conn = get_db()
        with conn:
            conn.executemany(
                "UPDATE comments SET sentiment = ?, sentiment_score = ? WHERE id = ?",
                updates,
            )
        conn.close()

    def _build_where(self, filters):
        where, params = [], []
        p = filters.get("platform")
        if p:
            where.append("platform = ?")
            params.append(p)
        up = filters.get("up_name")
        if up:
            where.append("up_name LIKE ?")
            params.append(f"%{up}%")
        vt = filters.get("video_title")
        if vt:
            where.append("video_title LIKE ?")
            params.append(f"%{vt}%")
        s = filters.get("sentiment")
        if s:
            where.append("COALESCE(sentiment_fix, sentiment) = ?")
            params.append(s)
        a = filters.get("author")
        if a:
            where.append("(author_name LIKE ? OR up_name LIKE ?)")
            params.append(f"%{a}%")
            params.append(f"%{a}%")
        locked = filters.get("locked")
        if locked == "1":
            where.append("sentiment_fix IS NOT NULL")
        elif locked == "0":
            where.append("sentiment_fix IS NULL")
        df = filters.get("date_from")
        if df:
            where.append("created_at >= ?")
            params.append(df)
        dt = filters.get("date_to")
        if dt:
            where.append("created_at <= ?")
            params.append(dt)
        return where, params


class SqliteUnitOfWork:
    """SQLite unit-of-work context manager."""

    def __init__(self, db_path: str = None):
        self._db_path = db_path
        self._conn = None
        self.comments = CommentRepository()

    def __enter__(self):
        path = self._db_path or os.environ.get(
            "DB_DSN", "file:data/sqlite/comments.db?mode=rwc&cache=shared&timeout=30"
        )
        # Strip SQLite URI prefix if present
        if path.startswith("file:"):
            path = path.split("?")[0].replace("file:", "")

        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


def init_sqlite_pragmas(db_path: str = None):
    """Apply recommended PRAGMAs to the SQLite database on startup."""
    from backend.config import DB_PATH as cfg_db_path
    path = db_path or cfg_db_path
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.close()
