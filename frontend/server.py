#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask API server for finance sentiment comments"""

import os
import sqlite3
from flask import Flask, send_from_directory, jsonify, request

app = Flask(__name__, static_folder=".")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "comments.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    return dict(row) if row else None


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/comments")
def get_comments():
    conn = get_db()
    platform = request.args.get("platform")
    up_name = request.args.get("up_name")
    video_title = request.args.get("video_title")
    sentiment = request.args.get("sentiment")
    author = request.args.get("author")
    locked = request.args.get("locked")   # "1" = only locked, "0" = only auto
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    offset = (page - 1) * page_size

    where = []
    params = []
    if platform:
        where.append("platform = ?")
        params.append(platform)
    if up_name:
        where.append("up_name LIKE ?")
        params.append(f"%{up_name}%")
    if video_title:
        where.append("video_title LIKE ?")
        params.append(f"%{video_title}%")
    if sentiment:
        where.append("COALESCE(sentiment_fix, sentiment) = ?")
        params.append(sentiment)
    if author:
        where.append("author_name LIKE ?")
        params.append(f"%{author}%")
    if locked == "1":
        where.append("sentiment_fix IS NOT NULL")
    elif locked == "0":
        where.append("sentiment_fix IS NULL")

    where_clause = " AND ".join(where) if where else "1=1"

    total = conn.execute(
        f"SELECT COUNT(*) FROM comments WHERE {where_clause}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT id, platform, comment_id, author_name, content, likes,
               replies, retweets, source_url, video_bvid, video_title,
               up_name, up_uid, symbol, created_at, collected_at,
               sentiment, sentiment_score, sentiment_fix,
               video_title, raw_data
        FROM comments
        WHERE {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        params + [page_size, offset],
    ).fetchall()

    conn.close()
    return jsonify({
        "items": [row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    })


@app.route("/api/comments/<int:comment_id>", methods=["GET"])
def get_comment(comment_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM comments WHERE id = ?", (comment_id,)
    ).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/api/comments/<int:comment_id>", methods=["PATCH"])
def update_comment(comment_id):
    data = request.get_json()
    sentiment_fix = data.get("sentiment_fix")

    if sentiment_fix not in ("正面", "负面", "中性", None):
        return jsonify({"error": "Invalid sentiment_fix value"}), 400

    conn = get_db()
    # When sentiment_fix is set, also update sentiment to reflect the lock
    if sentiment_fix:
        conn.execute(
            "UPDATE comments SET sentiment_fix = ?, sentiment = ? WHERE id = ?",
            (sentiment_fix, sentiment_fix, comment_id)
        )
    else:
        conn.execute(
            "UPDATE comments SET sentiment_fix = NULL WHERE id = ?",
            (comment_id,)
        )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM comments WHERE id = ?", (comment_id,)
    ).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/api/stats")
def get_stats():
    conn = get_db()

    # Auto-sentiment (not locked)
    auto = conn.execute("""
        SELECT sentiment as s, COUNT(*) as cnt
        FROM comments WHERE sentiment_fix IS NULL
        GROUP BY s
    """).fetchall()

    # Locked (manual fix)
    locked = conn.execute("""
        SELECT sentiment_fix as s, COUNT(*) as cnt
        FROM comments WHERE sentiment_fix IS NOT NULL
        GROUP BY s
    """).fetchall()

    # Like-weighted (auto only)
    weighted = conn.execute("""
        SELECT sentiment as s, SUM(likes) as total_likes
        FROM comments WHERE likes > 0 AND sentiment_fix IS NULL
        GROUP BY s
    """).fetchall()
    total_likes = sum(r["total_likes"] for r in weighted if r["s"])

    conn.close()
    return jsonify({
        "auto": {r["s"]: r["cnt"] for r in auto},
        "locked": {r["s"]: r["cnt"] for r in locked},
        "locked_count": sum(r["cnt"] for r in locked),
        "auto_count": sum(r["cnt"] for r in auto),
        "like_weighted": {
            r["s"]: round(r["total_likes"] / total_likes * 100, 1) if total_likes else 0
            for r in weighted if r["s"]
        }
    })


@app.route("/api/up_masters")
def get_up_masters():
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT up_name, up_uid, platform
        FROM comments
        WHERE up_name IS NOT NULL AND up_name != ''
        ORDER BY platform, up_name
    """).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/videos")
def get_videos():
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT video_title, video_bvid, up_name, platform
        FROM comments
        WHERE video_title IS NOT NULL AND video_title != ''
        ORDER BY video_title
        LIMIT 200
    """).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)