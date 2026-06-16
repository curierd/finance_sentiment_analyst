#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import xueqiu comments from collected JSON into the database.

- Dedup by (platform, source_url) — xueqiu comments don't have a stable id
  in the opencli output, so we use URL as the natural key.
- Re-fetches latest 100 comments per stock so we have a broader window.
- Skips hot discussions with no created_at (they're outside our window).
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEDULE_DIR = SCRIPT_DIR.parent
REPO_ROOT = SCHEDULE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.database import get_db  # noqa: E402

CST = timezone(timedelta(hours=8))
WINDOW_START = datetime(2026, 6, 15, 15, 0, 0, tzinfo=CST)
WINDOW_END = datetime(2026, 6, 16, 9, 30, 0, tzinfo=CST)


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_existing_urls(platform):
    conn = get_db()
    rows = conn.execute(
        "SELECT source_url FROM comments WHERE platform = ? AND source_url IS NOT NULL",
        (platform,),
    ).fetchall()
    conn.close()
    return {r["source_url"] for r in rows}


def is_in_window(created_at_str):
    if not created_at_str:
        return False
    try:
        dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        dt_cst = dt.astimezone(CST)
        return WINDOW_START <= dt_cst <= WINDOW_END
    except (ValueError, TypeError):
        return False


def import_xueqiu(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = get_db()
    existing = get_existing_urls("xueqiu")
    log(f"  Already in DB: {len(existing)} xueqiu URLs")

    imported = 0
    skipped_dup = 0
    skipped_window = 0
    skipped_empty = 0
    skipped_no_url = 0

    # Stock comments — only those in our window
    for c in data.get("stock_comments", []):
        ca = c.get("created_at")
        if not is_in_window(ca):
            skipped_window += 1
            continue
        text = (c.get("text") or "").strip()
        if not text:
            skipped_empty += 1
            continue
        url = c.get("url")
        if not url:
            skipped_no_url += 1
            continue
        if url in existing:
            skipped_dup += 1
            continue
        # Use a stable comment_id from the URL (path tail)
        cid = url.rstrip("/").split("/")[-1]
        conn.execute("""
            INSERT INTO comments
                (platform, comment_id, author_name, content, likes,
                 replies, retweets, source_url, symbol, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "xueqiu",
            cid,
            c.get("author", ""),
            text,
            c.get("likes", 0) or 0,
            c.get("replies", 0) or 0,
            c.get("retweets", 0) or 0,
            url,
            c.get("symbol", ""),
            ca,
        ))
        existing.add(url)
        imported += 1

    # Hot discussions — usually no created_at, only insert if within window
    for c in data.get("hot_discussions", []):
        ca = c.get("created_at")
        if not is_in_window(ca):
            skipped_window += 1
            continue
        text = (c.get("text") or "").strip()
        if not text:
            skipped_empty += 1
            continue
        url = c.get("url")
        if not url:
            skipped_no_url += 1
            continue
        if url in existing:
            skipped_dup += 1
            continue
        cid = url.rstrip("/").split("/")[-1]
        conn.execute("""
            INSERT INTO comments
                (platform, comment_id, author_name, content, likes,
                 replies, retweets, source_url, symbol, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "xueqiu",
            cid,
            c.get("author", ""),
            text,
            c.get("likes", 0) or 0,
            c.get("replies", 0) or 0,
            c.get("retweets", 0) or 0,
            url,
            "hot",
            ca,
        ))
        existing.add(url)
        imported += 1

    conn.commit()
    conn.close()

    log(f"  Imported {imported}, dup-skipped {skipped_dup}, "
        f"out-of-window {skipped_window}, no-url {skipped_no_url}, empty {skipped_empty}")
    return imported


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    parser.add_argument("--file", default=None, help="Specific JSON file")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
    else:
        path = REPO_ROOT / "comments" / f"xueqiu_{args.date}.json"

    if not path.exists():
        log(f"File not found: {path}")
        sys.exit(1)

    log(f"Importing from {path}")
    log(f"Window: {WINDOW_START.isoformat()} ~ {WINDOW_END.isoformat()}")
    n = import_xueqiu(path)
    log(f"Done: {n} new xueqiu comments in window")


if __name__ == "__main__":
    main()
