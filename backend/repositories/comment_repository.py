#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comment repository — data access layer"""

from backend.database import get_db, row_to_dict


class CommentRepository:
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
                   replies, retweets, source_url, video_bvid, video_title,
                   up_name, up_uid, symbol, created_at, collected_at,
                   sentiment, sentiment_score, sentiment_fix
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

    def stats(self):
        conn = get_db()
        auto = conn.execute("""
            SELECT sentiment as s, COUNT(*) as cnt
            FROM comments WHERE sentiment_fix IS NULL
            GROUP BY s
        """).fetchall()

        locked = conn.execute("""
            SELECT sentiment_fix as s, COUNT(*) as cnt
            FROM comments WHERE sentiment_fix IS NOT NULL
            GROUP BY s
        """).fetchall()

        weighted = conn.execute("""
            SELECT sentiment as s, SUM(likes) as total_likes
            FROM comments WHERE likes > 0 AND sentiment_fix IS NULL
            GROUP BY s
        """).fetchall()
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

    def stats_by_date(self, granularity="day"):
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
            WHERE s IS NOT NULL
            GROUP BY period, s
            ORDER BY period ASC
        """).fetchall()
        conn.close()

        # Build {period: {sentiment: {cnt, likes}}}
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
                 source_url, video_bvid, video_title, up_name, up_uid,
                 symbol, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("platform"),
            data.get("comment_id"),
            data.get("author_name"),
            data.get("content"),
            data.get("likes", 0),
            data.get("source_url"),
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
            # Search both the commenter name and the UP主 / channel owner name
            # so a query like "李大霄" finds UP主 李大霄's videos even when the
            # individual commenter is recorded as "ST大霄" or similar.
            where.append("(author_name LIKE ? OR up_name LIKE ?)")
            params.append(f"%{a}%")
            params.append(f"%{a}%")
        locked = filters.get("locked")
        if locked == "1":
            where.append("sentiment_fix IS NOT NULL")
        elif locked == "0":
            where.append("sentiment_fix IS NULL")
        return where, params