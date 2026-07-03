#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remove collector-injected prefix brackets from existing xiaohongshu comments.

Old `import_to_db.py` prepended:
  - 主评论:  "[笔记: <title>]\n"
  - 子评论:  "[笔记: <title>][回复]\n" 或 "[回复] "

These are collector noise, not user content. The video title still lives in
`videos.title` and `comments.video_title`; reply relationships are encoded
in the JSON's `is_reply` field. This script strips the leading brackets so
the historical rows match what the (now-fixed) importer will produce going
forward.

Scope: only matches these prefixes at the very start of the content;
other brackets inside comment text (e.g. user emoji like `[完啦R]` /
`[辣眼]`) are left alone.

Edge case — "junk rows": a small number of historical rows have NO real
comment text after the prefix (the collector mis-recorded the note title as
a comment). For those rows stripping the prefix would leave the row with
empty content. We refuse to do that in one pass and instead log them as
`--junk-action=...` candidates:
  * skip (default) — leave content as-is, log id
  * blank           — set content = '' (keeps row, no content)
  * drop            — DELETE the row (only when sentiment_fix IS NULL)
  * drop+reset      — DELETE and ignore locked rows safely

Important: this script does NOT re-run sentiment analysis. The 13 junk
rows kept by default still carry whatever (likely spurious) sentiment the
LLM assigned against the note title. If a refresh is desired, run
`db/update_sentiment.py` afterwards; that script already skips rows with
`sentiment_fix IS NOT NULL` so manual locks are preserved.
"""
import sys, io, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
sys.path.insert(0, ".")

import sqlite3

DB_PATH = os.environ.get("DB_PATH", "db/comments.db")

# Order matters:
#   1. "[笔记: ...][回复]\n"  (子评论 + 有标题)
#   2. "[笔记: ...]\n"        (主评论 + 有标题)
#   3. "[回复] "              (子评论 + 无标题)
# Each pattern includes the trailing whitespace so the stripped content
# starts at the first user character.
PREFIX_PATTERNS = [
    re.compile(r"^\[笔记:[^\]]*\]\[回复\][\s]*"),
    re.compile(r"^\[笔记:[^\]]*\][\s]*"),
    re.compile(r"^\[回复\][\s]*"),
]


def strip_prefix(content: str) -> tuple[str, bool]:
    if not content:
        return content, False
    for pat in PREFIX_PATTERNS:
        m = pat.match(content)
        if m:
            return content[m.end():], True
    return content, False


def main(dry_run=False, limit=None, junk_action="skip"):
    if junk_action not in {"skip", "blank", "drop"}:
        raise SystemExit(f"unknown --junk-action: {junk_action}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT id, content, sentiment_fix FROM comments "
        "WHERE platform='xiaohongshu' AND ("
        "  content LIKE '[笔记:%' OR content LIKE '[回复]%'"
        ")"
    )
    rows = cur.fetchall()
    if limit:
        rows = rows[:limit]

    updated = 0
    junk_skipped = 0
    junk_actioned = 0
    examples_printed = 0
    for row_id, content, sentiment_fix in rows:
        new, changed = strip_prefix(content)
        if not changed:
            continue

        if new.strip():
            # Normal case: real user content after prefix → strip only.
            if examples_printed < 3:
                print(f"  id={row_id}")
                print(f"    before: {content[:120]!r}")
                print(f"    after : {new[:120]!r}")
                examples_printed += 1
            if not dry_run:
                conn.execute("UPDATE comments SET content=? WHERE id=?", (new, row_id))
            updated += 1
            continue

        # Junk row: prefix IS the content.
        if junk_action == "skip":
            junk_skipped += 1
            if examples_printed < 3:
                print(f"  [junk-skip] id={row_id} content={content[:60]!r}")
                examples_printed += 1
            continue

        if junk_action == "blank":
            if examples_printed < 3:
                print(f"  [junk-blank] id={row_id} content={content[:60]!r}")
                examples_printed += 1
            if not dry_run:
                conn.execute("UPDATE comments SET content='' WHERE id=?", (row_id,))
            junk_actioned += 1
            continue

        if junk_action == "drop":
            if sentiment_fix:
                junk_skipped += 1
                print(f"  [junk-DROP-SKIP] id={row_id} has sentiment_fix={sentiment_fix!r}; refusing to drop")
                continue
            if examples_printed < 3:
                print(f"  [junk-drop] id={row_id} content={content[:60]!r}")
                examples_printed += 1
            if not dry_run:
                conn.execute("DELETE FROM comments WHERE id=?", (row_id,))
            junk_actioned += 1

    if not dry_run:
        conn.commit()

    remaining = conn.execute(
        "SELECT COUNT(*) FROM comments WHERE platform='xiaohongshu' AND ("
        "  content LIKE '[笔记:%' OR content LIKE '[回复]%'"
        ")"
    ).fetchone()[0]

    conn.close()
    print()
    print(f"Matched: {len(rows)}  |  Updated: {updated}  |  "
          f"Junk {junk_action}: {junk_actioned} (skipped-locked-or-policy: {junk_skipped})  |  "
          f"Remaining prefix rows: {remaining}")
    if dry_run:
        print("(dry-run — no writes committed)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Strip [笔记:...] / [回复] prefixes from 小红书 comments"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max rows to process (debug)")
    parser.add_argument("--junk-action", choices=["skip", "blank", "drop"],
                        default="skip",
                        help="How to handle rows whose content was JUST the prefix "
                             "(no real user text). default: skip")
    args = parser.parse_args()
    main(dry_run=args.dry_run, limit=args.limit, junk_action=args.junk_action)