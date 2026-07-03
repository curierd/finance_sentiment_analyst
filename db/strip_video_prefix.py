#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remove the leading "[视频: ...]" title prefix that B站 comments carry.

The bilibili collector sometimes prepends the video title in `[视频: ...]`
brackets at the start of each comment, which is noise for sentiment analysis
and the frontend display. This script strips the prefix in place.

Scope: only matches `[视频:` at the very start of the content. Other brackets
inside comment text (e.g. `[辣眼]`, `[已修改]`, `[哭惹]`, `[完啦]`) are
deliberately left alone — they are user text / emoji / watermarks, not
collector-injected noise.
"""
import sys, io, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
sys.path.insert(0, ".")

import sqlite3

DB_PATH = os.environ.get("DB_PATH", "db/comments.db")

# Anchor at start of content; non-greedy match until the closing ']'.
PREFIX_RE = re.compile(r"^\[视频:[^\]]*\]")


def strip_prefix(content: str) -> tuple[str, bool]:
    """Strip a single leading `[视频: ...]` block. Returns (new, changed)."""
    if not content:
        return content, False
    m = PREFIX_RE.match(content)
    if not m:
        return content, False
    new = content[m.end():].lstrip()
    return new, True


def main(dry_run=False, limit=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT id, content FROM comments "
        "WHERE platform='bilibili' AND content LIKE '[视频:%'"
    )
    rows = cur.fetchall()
    if limit:
        rows = rows[:limit]

    updated = 0
    examples_printed = 0
    for row_id, content in rows:
        new, changed = strip_prefix(content)
        if not changed:
            continue
        # Guard against emptying the row — skip if the rest is just whitespace.
        if not new.strip():
            print(f"  skip id={row_id} (would become empty): {content[:60]!r}")
            continue
        if examples_printed < 3:
            print(f"  id={row_id}")
            print(f"    before: {content[:120]!r}")
            print(f"    after : {new[:120]!r}")
            examples_printed += 1
        if not dry_run:
            conn.execute("UPDATE comments SET content=? WHERE id=?", (new, row_id))
        updated += 1

    if not dry_run:
        conn.commit()

    # Summary count after update
    remaining = conn.execute(
        "SELECT COUNT(*) FROM comments WHERE platform='bilibili' AND content LIKE '[视频:%'"
    ).fetchone()[0]

    conn.close()
    print()
    print(f"Matched: {len(rows)}  |  Updated: {updated}  |  Remaining prefix rows: {remaining}")
    if dry_run:
        print("(dry-run — no writes committed)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Strip leading [视频: ...] prefix from B站 comments")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to process (debug)")
    args = parser.parse_args()
    main(dry_run=args.dry_run, limit=args.limit)