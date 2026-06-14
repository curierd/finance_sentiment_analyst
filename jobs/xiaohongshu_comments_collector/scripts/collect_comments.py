#!/usr/bin/env python3
"""
Xiaohongshu comments collector — collects comments from today's notes
by finance bloggers listed in xiaohongshu-finance-up.md.

Strategy:
1. Use `opencli xiaohongshu user <id> -f json` to get each blogger's recent notes
2. Decode note ID timestamps (first 8 hex chars) to filter today's notes
3. Extract xsec_token from the note URLs
4. Use `xhs comments <note_id> --all --xsec-token <token> --json` for full comment collection
5. Use `xhs sub-comments` for deeper sub-comment pagination when needed

Rate-limit: ≥1s between requests, no concurrency.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

SCRIPT_DIR = Path(__file__).resolve().parent
JOB_DIR = SCRIPT_DIR.parent
BASE_DIR = JOB_DIR.parent.parent
INTERMEDIATE_DIR = JOB_DIR / "intermediate"
COMMENTS_DIR = BASE_DIR / "comments"
ISSUES_FILE = JOB_DIR / "issues.md"

CST = timezone(timedelta(hours=8))
TODAY = datetime.now(CST).strftime("%Y-%m-%d")
RATE_LIMIT = 1.2

# Allow --date override
if "--date" in sys.argv:
    idx = sys.argv.index("--date")
    if idx + 1 < len(sys.argv):
        TODAY = sys.argv[idx + 1]

blogger_list_path = JOB_DIR / "xiaohongshu-finance-up.md"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def log_issue(msg):
    ts = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    with open(ISSUES_FILE, "a", encoding="utf-8") as f:
        f.write(f"- [{ts}] {msg}\n")
    log(f"ISSUE: {msg}")


def run_cmd(cmd, timeout=90):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Filter out noisy Node.js warnings
            stderr_lines = [l for l in stderr.split("\n")
                           if l and "UNDICI-EHPA" not in l and "trace-warnings" not in l]
            if stderr_lines:
                log(f"  stderr: {'; '.join(stderr_lines[:3])}")
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        log_issue(f"Timeout: {cmd[:80]}")
        return None
    except Exception as e:
        log_issue(f"Error: {cmd[:80]} — {e}")
        return None


def parse_bloggers(filepath):
    bloggers = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r"\|\s*`([a-f0-9]{24})`\s*\|", line)
            if m:
                user_id = m.group(1)
                parts = [p.strip() for p in line.split("|")]
                name = parts[2] if len(parts) >= 3 else user_id
                bloggers.append((name, user_id))
    return bloggers


def note_id_to_date(note_id):
    """Decode the first 8 hex chars of a Xiaohongshu note ID to a date string."""
    try:
        ts = int(note_id[:8], 16)
        dt = datetime.fromtimestamp(ts, tz=CST)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return None


def extract_xsec_token_from_url(url):
    """Extract xsec_token from a Xiaohongshu URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    token = params.get("xsec_token", [None])[0]
    if token:
        return unquote(token)
    return None


def fetch_user_notes(user_id):
    """Fetch user's recent notes via opencli. Returns list of note dicts with id, title, likes, url."""
    out = run_cmd(f"opencli xiaohongshu user {user_id} --limit 20 -f json", timeout=45)
    if not out:
        return None
    try:
        data = json.loads(out)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", [])
        return []
    except json.JSONDecodeError:
        log_issue(f"JSON parse error for opencli user {user_id}")
        return None


def fetch_comments(note_id, xsec_token):
    """Fetch all comments via xhs CLI with xsec_token. Returns list of comment dicts."""
    cmd = f'xhs comments {note_id} --xsec-token "{xsec_token}" --all --json'
    out = run_cmd(cmd, timeout=120)
    if not out:
        return None
    try:
        data = json.loads(out)
        if not data.get("ok"):
            log_issue(f"xhs comments error for {note_id}: {data.get('error', {}).get('message', 'unknown')}")
            return None
        comments = data.get("data", {}).get("comments", [])
        return comments
    except json.JSONDecodeError:
        log_issue(f"JSON parse error for xhs comments {note_id}")
        return None


def fetch_subcomments(note_id, comment_id, xsec_token=None):
    """Fetch sub-comments for a specific comment."""
    cmd = f"xhs sub-comments {note_id} {comment_id} --json"
    out = run_cmd(cmd, timeout=30)
    if not out:
        return []
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            return data.get("data", {}).get("comments", data.get("comments", []))
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        return []


def ms_to_datetime(ms):
    """Convert millisecond timestamp to readable datetime string."""
    if not ms:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=CST)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return ""


def normalize_comment(c, note_id):
    """Normalize a comment dict to a standard format."""
    user_info = c.get("user_info", {})
    sub_comments = c.get("sub_comments", [])

    # Recursively normalize sub-comments
    norm_subs = [normalize_comment(sc, note_id) for sc in sub_comments]

    # Extract comment pictures (not all comments have them)
    pictures = c.get("pictures", [])
    picture_urls = []
    for pic in pictures:
        url_default = pic.get("url_default", "")
        url_pre = pic.get("url_pre", "")
        if url_default:
            picture_urls.append({"url_default": url_default, "url_pre": url_pre})

    return {
        "id": c.get("id", ""),
        "note_id": note_id,
        "content": c.get("content", ""),
        "author": user_info.get("nickname", ""),
        "author_id": user_info.get("user_id", ""),
        "author_avatar": user_info.get("image", ""),
        "like_count": int(c.get("like_count", 0)),
        "create_time": ms_to_datetime(c.get("create_time")),
        "create_time_ms": c.get("create_time", 0),
        "ip_location": c.get("ip_location", ""),
        "sub_comment_count": int(c.get("sub_comment_count", 0)),
        "sub_comments": norm_subs,
        "pictures": picture_urls,
    }


def normalize_note(note_raw, author_name, user_id, xsec_token):
    """Normalize a note from opencli user output to our standard format."""
    note_id = note_raw.get("id", "")
    title = note_raw.get("title", "")
    url = note_raw.get("url", "")
    likes = note_raw.get("likes", "0")

    # Extract cover image
    cover = note_raw.get("cover", "")
    image_list = []
    if cover:
        image_list.append({"url_original": cover})

    return {
        "note_id": note_id,
        "title": title,
        "author": author_name,
        "user_id": user_id,
        "likes": int(likes) if likes else 0,
        "url": url,
        "xsec_token": xsec_token,
        "cover_original": cover,
        "image_list": image_list,
    }


def main():
    log(f"=== Xiaohongshu Comments Collector — {TODAY} ===")

    # Clear issues file for this run
    with open(ISSUES_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Issues — {TODAY}\n\n")

    bloggers = parse_bloggers(blogger_list_path)
    log(f"Found {len(bloggers)} bloggers")

    if not bloggers:
        log_issue("No bloggers found")
        sys.exit(1)

    # Step 1: Fetch each blogger's recent notes, filter for today
    all_today_notes = []
    for i, (name, user_id) in enumerate(bloggers):
        log(f"[{i+1}/{len(bloggers)}] {name} ({user_id})")
        notes = fetch_user_notes(user_id)
        time.sleep(RATE_LIMIT)

        if not notes:
            log_issue(f"Could not fetch notes for {name} ({user_id})")
            continue

        # Filter for today using note ID timestamp decoding
        for note in notes:
            note_id = note.get("id", "")
            if not note_id or len(note_id) < 8:
                continue
            note_date = note_id_to_date(note_id)
            if note_date != TODAY:
                continue

            url = note.get("url", "")
            xsec_token = extract_xsec_token_from_url(url)
            if not xsec_token:
                log_issue(f"No xsec_token for {name}'s note {note_id}")
                continue

            norm = normalize_note(note, name, user_id, xsec_token)
            all_today_notes.append(norm)
            log(f"  Today's note: {norm['title'][:50]} (likes={norm['likes']})")

        # Save intermediate per-blogger
        with open(INTERMEDIATE_DIR / f"posts_{user_id}.json", "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)

    log(f"Found {len(all_today_notes)} notes published today")

    # Save today's notes intermediate
    with open(INTERMEDIATE_DIR / "today_notes.json", "w", encoding="utf-8") as f:
        json.dump(all_today_notes, f, ensure_ascii=False, indent=2)

    if not all_today_notes:
        log("No notes found for today.")
        output = {
            "target_date": TODAY,
            "platform": "小红书",
            "sources": [str(blogger_list_path)],
            "notes": [],
        }
        with open(COMMENTS_DIR / f"xiaohongshu_{TODAY}.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return

    # Step 2: Collect comments for each note
    for i, note in enumerate(all_today_notes):
        note_id = note["note_id"]
        xsec_token = note["xsec_token"]
        title = note["title"]
        log(f"[{i+1}/{len(all_today_notes)}] Comments: {title[:40]}... ({note_id})")

        comments = fetch_comments(note_id, xsec_token)
        time.sleep(RATE_LIMIT)

        if comments is None:
            log_issue(f"Failed to fetch comments for {note_id}")
            note["comments"] = []
            note["comment_count"] = 0
            continue

        # Fetch deeper sub-comments for comments that have more
        for c in comments:
            if c.get("sub_comment_has_more") and c.get("id"):
                sub = fetch_subcomments(note_id, c["id"])
                time.sleep(RATE_LIMIT)
                if sub:
                    # Merge: existing sub_comments + newly fetched
                    existing = c.get("sub_comments", [])
                    existing_ids = {s.get("id") for s in existing}
                    for s in sub:
                        if s.get("id") not in existing_ids:
                            existing.append(s)
                    c["sub_comments"] = existing

        # Normalize all comments
        norm_comments = [normalize_comment(c, note_id) for c in comments]
        note["comments"] = norm_comments
        note["comment_count"] = len(norm_comments)

        # Save intermediate per-note
        with open(INTERMEDIATE_DIR / f"comments_{note_id}.json", "w", encoding="utf-8") as f:
            json.dump(norm_comments, f, ensure_ascii=False, indent=2)

        total_subs = sum(len(c.get("sub_comments", [])) for c in norm_comments)
        log(f"  {len(norm_comments)} comments, {total_subs} sub-comments")

    # Step 3: Save final output
    output = {
        "target_date": TODAY,
        "platform": "小红书",
        "sources": [str(blogger_list_path)],
        "notes": all_today_notes,
    }

    output_path = COMMENTS_DIR / f"xiaohongshu_{TODAY}.json"
    if output_path.exists():
        backup_path = COMMENTS_DIR / f"xiaohongshu_{TODAY}.json.bak.{int(time.time())}"
        shutil.copy2(output_path, backup_path)
        log(f"Backed up to {backup_path.name}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_comments = sum(n["comment_count"] for n in all_today_notes)
    total_subs = sum(
        len(c.get("sub_comments", []))
        for n in all_today_notes
        for c in n.get("comments", [])
    )
    log(f"=== Done! {len(all_today_notes)} notes, {total_comments} comments, {total_subs} sub-comments ===")
    log(f"Output: {output_path}")


if __name__ == "__main__":
    main()
