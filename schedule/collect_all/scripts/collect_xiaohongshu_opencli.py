#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect Xiaohongshu comments for recent 2 days using `opencli xiaohongshu`.

This bypasses the original `collect_comments.py` which uses
`browser_cookie3.chrome()` (requires admin). `opencli xiaohongshu` carries
its own Playwright session that already passes whoami/login checks.

Per SKILL.md, the first 8 hex chars of a note_id encode the publish
timestamp (Unix seconds), so we can filter by date without needing
`created_at` from the API.

Outputs (matching existing schema for `import_to_db.py`):
  - comments/xiaohongshu_<date>.json
  - jobs/xiaohongshu_comments_collector/intermediate/bloggers.json
  - jobs/xiaohongshu_comments_collector/intermediate/posts_<uid>.json
  - jobs/xiaohongshu_comments_collector/intermediate/comments_<note_id>.json
  - jobs/xiaohongshu_comments_collector/intermediate/today_notes.json
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
JOB_DIR = REPO_ROOT / "jobs" / "xiaohongshu_comments_collector"
BLOGGER_LIST = JOB_DIR / "xiaohongshu-finance-up.md"
COMMENTS_DIR = REPO_ROOT / "comments"
INTERMEDIATE_DIR = JOB_DIR / "intermediate"

CST = timezone(timedelta(hours=8))

# Window: previous trading day 15:00 ~ next trading day 09:30 CST
WINDOW_START = datetime(2026, 6, 19, 15, 0, 0, tzinfo=CST)
WINDOW_END = datetime(2026, 6, 23, 9, 30, 0, tzinfo=CST)
# Also include each date inside the window as a candidate key for note_id matching
DATE_KEYS = []
d = WINDOW_START.date()
end = WINDOW_END.date()
while d <= end:
    DATE_KEYS.append(d.strftime("%Y-%m-%d"))
    d += timedelta(days=1)

OPENCLI = (
    r"C:\Users\sverd\AppData\Roaming\npm\node_modules\@jackwener\opencli\dist\src\main.js"
)
OPENCLI_NODE = shutil.which("node") or "node"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run(cmd, timeout=60):
    # Bypass opencli.cmd shim: cmd.exe interprets '&' in URLs as command chaining.
    # Call the underlying main.js directly via node.
    if cmd and cmd[0] == OPENCLI:
        cmd = [OPENCLI_NODE] + list(cmd)
    env = os.environ.copy()
    env["OPENCLI_WINDOW"] = "background"
    r = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace", env=env,
    )
    return r.returncode, r.stdout, r.stderr


def strip_preamble(s):
    if not s:
        return s
    out, skip = [], True
    for line in s.splitlines():
        if skip and (not line.strip() or line.startswith("Active code page")):
            continue
        skip = False
        out.append(line)
    return "\n".join(out)


def note_id_to_dt(note_id):
    """First 8 hex chars of note_id = Unix seconds → datetime."""
    if not note_id or len(note_id) < 8:
        return None
    try:
        return datetime.fromtimestamp(int(note_id[:8], 16), tz=CST)
    except (ValueError, OverflowError, OSError):
        return None


def parse_blogger_list():
    """Parse user IDs from xiaohongshu-finance-up.md."""
    bloggers = []
    for line in BLOGGER_LIST.read_text(encoding="utf-8").splitlines():
        # | 1 | 小红他叔 | `61acb1f7000000001000aa34` | ...
        m = re.match(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*`?([0-9a-f]{20,})`?\s*\|", line)
        if m:
            bloggers.append({"name": m.group(1).strip(), "user_id": m.group(2).strip()})
    return bloggers


def fetch_user_notes(user_id, limit=10):
    """Returns list of {id, title, type, likes, cover, url} or None on error."""
    rc, out, err = run([OPENCLI, "xiaohongshu", "user", user_id, "--limit", str(limit), "-f", "json"], timeout=60)
    if rc != 0:
        return None, (err or out)[:200]
    try:
        data = json.loads(strip_preamble(out))
    except json.JSONDecodeError as e:
        return None, f"json: {e}"
    if isinstance(data, dict) and data.get("ok") is False:
        return None, data.get("error", {}).get("message", "auth error")
    if not isinstance(data, list):
        return None, f"unexpected: {type(data).__name__}"
    return data, None


def fetch_comments(url):
    """Returns list of comments or None."""
    rc, out, err = run([OPENCLI, "xiaohongshu", "comments", url, "-f", "json"], timeout=60)
    if rc != 0:
        return None, (err or out)[:200]
    try:
        data = json.loads(strip_preamble(out))
    except json.JSONDecodeError as e:
        return None, f"json: {e}"
    if isinstance(data, dict) and data.get("ok") is False:
        return None, data.get("error", {}).get("message", "auth error")
    if not isinstance(data, list):
        return None, f"unexpected: {type(data).__name__}"
    return data, None


def relative_time_to_dt(text, now_cst):
    """Parse '昨天 23:17' / '前天 16:50' / '今天 14:20' / '06-18 09:30' etc."""
    if not text:
        return None
    text = text.strip()
    # Today/yesterday prefixes
    if text.startswith("今天"):
        rest = text.replace("今天", "").strip()
        m = re.match(r"(\d{1,2}):(\d{2})", rest)
        if m:
            return now_cst.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    if text.startswith("昨天"):
        rest = text.replace("昨天", "").strip()
        m = re.match(r"(\d{1,2}):(\d{2})", rest)
        if m:
            return (now_cst - timedelta(days=1)).replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    if text.startswith("前天"):
        rest = text.replace("前天", "").strip()
        m = re.match(r"(\d{1,2}):(\d{2})", rest)
        if m:
            return (now_cst - timedelta(days=2)).replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    # YYYY-MM-DD HH:MM
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})", text)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)), tzinfo=CST)
    return None


def main():
    COMMENTS_DIR.mkdir(exist_ok=True)
    INTERMEDIATE_DIR.mkdir(exist_ok=True)

    bloggers = parse_blogger_list()
    log(f"Found {len(bloggers)} bloggers from {BLOGGER_LIST.name}")
    # Save parsed bloggers
    (INTERMEDIATE_DIR / "bloggers.json").write_text(
        json.dumps(bloggers, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Build per-day results
    by_date = {d: {
        "target_date": d,
        "platform": "小红书",
        "notes": [],
    } for d in DATE_KEYS}

    now_cst = datetime.now(CST)
    errors = []

    for i, b in enumerate(bloggers):
        name, uid = b["name"], b["user_id"]
        log(f"[{i+1}/{len(bloggers)}] {name} ({uid})")
        notes, err = fetch_user_notes(uid, limit=20)
        if err:
            log(f"  ISSUE: notes fetch failed: {err}")
            errors.append({"uid": uid, "stage": "user", "err": err})
            time.sleep(2)
            continue
        log(f"  got {len(notes)} notes")
        (INTERMEDIATE_DIR / f"posts_{uid}.json").write_text(
            json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        for n in notes:
            note_id = n.get("id", "")
            url = n.get("url", "")
            title = n.get("title", "")
            if not url or not note_id:
                continue
            # Filter by note_id timestamp
            ts = note_id_to_dt(note_id)
            if not ts:
                continue
            ts_date = ts.strftime("%Y-%m-%d")
            if ts_date not in by_date:
                continue
            log(f"  -> {ts_date} {title[:30]}...")

            comments, cerr = fetch_comments(url)
            if cerr:
                log(f"    ISSUE: comments failed: {cerr}")
                errors.append({"uid": uid, "note": note_id, "stage": "comments", "err": cerr})
                time.sleep(1)
                continue
            log(f"    {len(comments)} comments")
            (INTERMEDIATE_DIR / f"comments_{note_id}.json").write_text(
                json.dumps(comments, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # Build note entry
            note_entry = {
                "note_id": note_id,
                "title": title,
                "author": name,
                "user_id": uid,
                "likes": int(n.get("likes", 0) or 0),
                "url": url,
                "xsec_token": re.search(r"xsec_token=([^&]+)", url).group(1) if "xsec_token=" in url else "",
                "comments": [],
            }
            for c in comments:
                ctext = (c.get("text") or "").strip()
                if not ctext:
                    continue
                # Best-effort time resolution
                ctime = relative_time_to_dt(c.get("time", ""), now_cst) or ts
                note_entry["comments"].append({
                    "id": f"{note_id}_r{c.get('rank', 0)}",
                    "content": ctext,
                    "author": c.get("author", ""),
                    "like_count": int(c.get("likes", 0) or 0),
                    "create_time": ctime.strftime("%Y-%m-%d %H:%M"),
                    "ip_location": (c.get("time", "").split()[-1] if c.get("time") else ""),
                    "is_reply": bool(c.get("is_reply", False)),
                    "sub_comment_count": 0,
                    "sub_comments": [],
                })
            by_date[ts_date]["notes"].append(note_entry)
            time.sleep(1.5)

        time.sleep(1)

    # Save final files
    for date_str, payload in by_date.items():
        out_file = COMMENTS_DIR / f"xiaohongshu_{date_str}.json"
        out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Saved: {out_file}  notes={len(payload['notes'])}  "
            f"comments={sum(len(n['comments']) for n in payload['notes'])}")

    if errors:
        (INTERMEDIATE_DIR / "errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"Errors: {len(errors)} (saved to errors.json)")


if __name__ == "__main__":
    main()
