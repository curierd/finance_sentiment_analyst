#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import collected comments into SQLite database"""

import json
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

DB_PATH = "db/comments.db"


def import_bilibili():
    path = "comments/bilibili-comments.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("[SKIP] %s not found, skipping" % path)
        return 0

    conn = sqlite3.connect(DB_PATH)
    count = 0
    for comment in data.get("comments", []):
        conn.execute("""
            INSERT OR IGNORE INTO comments
                (platform, comment_id, author_id, author_name, content, likes,
                 source_url, video_bvid, video_title, up_name, up_uid,
                 created_at, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "bilibili",
            comment.get("comment_id"),
            None,
            comment.get("author"),
            comment.get("content"),
            comment.get("like", 0),
            None,
            comment.get("bvid"),
            comment.get("video_title"),
            comment.get("up_name"),
            comment.get("up_uid"),
            comment.get("pubdate"),
            json.dumps(comment, ensure_ascii=False),
        ))
        count += 1

    # Import up_masters
    for up in data.get("up_masters", []):
        conn.execute("""
            INSERT OR IGNORE INTO up_masters (platform, uid, name, source_file)
            VALUES ('bilibili', ?, ?, 'bili_data/finance-up.md')
        """, (up.get("uid"), up.get("name")))

    # Import videos
    for video in data.get("videos", []):
        conn.execute("""
            INSERT OR IGNORE INTO videos
                (platform, video_id, title, up_name, up_uid, stats, url)
            VALUES ('bilibili', ?, ?, ?, ?, ?, ?)
        """, (
            video.get("bvid"),
            video.get("title"),
            video.get("up_name"),
            video.get("up_uid"),
            json.dumps(video.get("stats", {}), ensure_ascii=False),
            "https://www.bilibili.com/video/" + video.get("bvid", ""),
        ))

    conn.commit()
    conn.close()
    print("[OK] Bilibili: imported %d comments" % count)
    return count


def import_xueqiu():
    path = "comments/xueqiu-comments.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("[SKIP] %s not found, skipping" % path)
        return 0

    conn = sqlite3.connect(DB_PATH)
    count = 0
    for comment in data.get("comments", []):
        conn.execute("""
            INSERT OR IGNORE INTO comments
                (platform, author_name, content, likes, replies, retweets,
                 source_url, symbol, created_at, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "xueqiu",
            comment.get("author"),
            comment.get("content"),
            comment.get("likes", 0),
            comment.get("replies", 0),
            comment.get("retweets", 0),
            comment.get("url"),
            comment.get("symbol"),
            comment.get("created_at"),
            json.dumps(comment, ensure_ascii=False),
        ))
        count += 1

    conn.commit()
    conn.close()
    print("[OK] Xueqiu: imported %d comments" % count)
    return count


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT COUNT(*) FROM comments")
    before = cur.fetchone()[0]
    conn.close()

    import_bilibili()
    import_xueqiu()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT COUNT(*) FROM comments")
    after = cur.fetchone()[0]
    conn.close()

    print("Total comments in DB: %d (added %d)" % (after, after - before))


if __name__ == "__main__":
    main()