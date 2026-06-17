#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Master orchestration for `schedule/collect_all/expectation.md`.

Tasks (per expectation.md):
  1. Determine login status of all platforms
  2. Quantitative analysis of all platforms' comments, with image collection
  3. Time window: previous trading day close ~ today open

Window (CST):
  - previous trading day: 2026-06-15 (Mon) close 15:00
  - today: 2026-06-16 (Tue) open 09:30
  - Window: 2026-06-15 15:00:00 ~ 2026-06-16 09:30:00 CST

Outputs:
  - schedule/collect_all/scripts/  — orchestrator + per-platform scripts
  - schedule/collect_all/intermediate/ — partial dumps, login status
  - schedule/collect_all/output/  — final Excel report
  - schedule/collect_all/issues.md — encountered issues
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
WINDOW_START = datetime(2026, 6, 15, 15, 0, 0, tzinfo=CST)
WINDOW_END = datetime(2026, 6, 16, 9, 30, 0, tzinfo=CST)
TODAY = "2026-06-16"
PREV_TRADING_DAY = "2026-06-15"

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEDULE_DIR = SCRIPT_DIR.parent
INTERMEDIATE_DIR = SCHEDULE_DIR / "intermediate"
ISSUES_FILE = SCHEDULE_DIR / "issues.md"
REPO_ROOT = SCHEDULE_DIR.parent

INTERMEDIATE_DIR.mkdir(exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run(cmd, cwd=None, timeout=None, env=None):
    if env is None:
        env = os.environ.copy()
    log(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(
        cmd if isinstance(cmd, list) else cmd.split(),
        cwd=cwd or str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def check_login():
    """Step 1: Check login status of all 3 platforms. Save to intermediate."""
    log("=== Step 1: Login status check ===")
    status = {}

    # B站 — opencli bilibili whoami
    r = run(["opencli", "bilibili", "whoami"], timeout=30)
    if r.returncode == 0 and "logged_in" in r.stdout:
        try:
            data = json.loads(r.stdout)
            status["bilibili_opencli"] = {
                "tool": "opencli bilibili",
                "ok": data.get("logged_in") is True,
                "user": data.get("username"),
                "level": data.get("level"),
                "id": data.get("id"),
                "raw": data,
            }
        except json.JSONDecodeError:
            status["bilibili_opencli"] = {"tool": "opencli bilibili", "ok": False, "raw": r.stdout}
    else:
        status["bilibili_opencli"] = {"tool": "opencli bilibili", "ok": False, "stderr": r.stderr}

    # B站 — bili CLI (no whoami; check by listing a user's videos)
    r = run(["bili", "user-videos", "52764688", "-n", "1", "--json"], timeout=30)
    status["bilibili_bili"] = {
        "tool": "bili CLI",
        "ok": r.returncode == 0 and r.stdout.strip().startswith(("{", "[")),
    }
    if not status["bilibili_bili"]["ok"]:
        status["bilibili_bili"]["stderr"] = r.stderr[:200]

    # 雪球 — opencli xueqiu hot (test for valid JSON output)
    r = run(["opencli", "xueqiu", "hot", "--limit", "1", "-f", "json"], timeout=30)
    status["xueqiu"] = {
        "tool": "opencli xueqiu",
        "ok": r.returncode == 0 and r.stdout.strip().startswith("["),
    }
    if not status["xueqiu"]["ok"]:
        status["xueqiu"]["stderr"] = r.stderr[:200]

    # 小红书 — opencli xiaohongshu whoami
    r = run(["opencli", "xiaohongshu", "whoami"], timeout=30)
    xhs_ok = False
    xhs_user = None
    if r.returncode == 0:
        try:
            data = json.loads(r.stdout)
            if data.get("ok") and not data.get("error"):
                xhs_ok = True
                # try to find user info
            else:
                # logged out
                pass
        except json.JSONDecodeError:
            pass
    status["xiaohongshu_opencli"] = {
        "tool": "opencli xiaohongshu",
        "ok": xhs_ok,
        "raw": r.stdout[:200] if r.returncode == 0 else r.stderr[:200],
    }

    # 小红书 — xhs CLI (test with a known note + token)
    test_note = "6a30cd5400000000110198a0"
    test_token = "ABzLri3FHI4eFOQ188uDzch1E4W-e056nPuxpamJxEeLM="
    r = run(["xhs", "comments", test_note, "--xsec-token", test_token, "--json"], timeout=60)
    status["xiaohongshu_xhs"] = {
        "tool": "xhs CLI",
        "ok": r.returncode == 0 and '"ok": true' in r.stdout,
    }
    if not status["xiaohongshu_xhs"]["ok"]:
        status["xiaohongshu_xhs"]["stderr"] = (r.stderr or r.stdout)[:200]

    out_file = INTERMEDIATE_DIR / "login_status.json"
    out_file.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  Saved: {out_file}")
    for k, v in status.items():
        log(f"  {k}: {'OK' if v.get('ok') else 'FAIL'}")
    return status


def collect_bilibili():
    """Step 2a: B站 collection. target_date=2026-06-16, window_days=1.

    This gives us videos from 2026-06-15 to 2026-06-17, including all the
    overnight comments posted on 06-15 evening and 06-16 morning.
    """
    log("=== Step 2a: B站 collection (target=2026-06-16, window_days=1) ===")
    cmd = [
        "python3",
        str(REPO_ROOT / "jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py"),
        "--date", "2026-06-16",
        "--window-days", "1",
        "--video-pages", "2",
        "--limit", "50",
        "--sleep", "1.5",
    ]
    r = run(cmd, timeout=1800)
    log(f"  rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-30:]:
            log(f"    {line}")
    if r.returncode != 0:
        log(f"  stderr: {r.stderr[:500]}")
    return r.returncode == 0


def collect_xiaohongshu():
    """Step 2b: 小红书 collection. We need both 06-15 and 06-16 dates."""
    log("=== Step 2b: 小红书 collection (06-15 + 06-16) ===")
    for date in ["2026-06-15", "2026-06-16"]:
        log(f"  --- {date} ---")
        cmd = [
            "python3",
            str(REPO_ROOT / "jobs/xiaohongshu_comments_collector/scripts/collect_comments.py"),
            "--date", date,
        ]
        r = run(cmd, timeout=1800)
        log(f"  rc={r.returncode}")
        if r.stdout:
            for line in r.stdout.split("\n")[-20:]:
                log(f"    {line}")
        if r.returncode != 0:
            log(f"  stderr: {r.stderr[:500]}")
    return True


def collect_xueqiu():
    """Step 2c: 雪球 collection. We use the larger limit so we capture
    comments from 06-15 evening too (the latest 100 per stock)."""
    log("=== Step 2c: 雪球 collection (2026-06-16, limit=100) ===")
    cmd = [
        "python3",
        str(REPO_ROOT / "jobs/xuqiu_comments_collector/scripts/collect_xueqiu.py"),
        "--date", "2026-06-16",
        "--limit", "100",
    ]
    r = run(cmd, timeout=1800)
    log(f"  rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-20:]:
            log(f"    {line}")
    if r.returncode != 0:
        log(f"  stderr: {r.stderr[:500]}")
    return r.returncode == 0


def import_all():
    """Step 3: Import all 3 platforms' data into SQLite."""
    log("=== Step 3: Import to DB ===")
    success = True

    # Bilibili — re-import (idempotent)
    log("  --- bilibili ---")
    r = run([
        "python3",
        str(REPO_ROOT / "jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py"),
        "--import-only",
    ], timeout=600)
    log(f"    rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-20:]:
            log(f"    {line}")

    # Xiaohongshu — import for 06-15 and 06-16
    for date in ["2026-06-15", "2026-06-16"]:
        log(f"  --- xiaohongshu {date} ---")
        r = run([
            "python3",
            str(REPO_ROOT / "jobs/xiaohongshu_comments_collector/scripts/import_to_db.py"),
            "--date", date,
        ], timeout=600)
        log(f"    rc={r.returncode}")
        if r.stdout:
            for line in r.stdout.split("\n")[-20:]:
                log(f"    {line}")

    # Xueqiu — manual import (no automatic import script)
    log("  --- xueqiu ---")
    cmd = [
        "python3",
        str(SCRIPT_DIR / "import_xueqiu_to_db.py"),
        "--date", "2026-06-16",
    ]
    r = run(cmd, timeout=300)
    log(f"    rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-20:]:
            log(f"    {line}")
    if r.returncode != 0:
        log(f"    stderr: {r.stderr[:500]}")
        success = False

    return success


def run_sentiment():
    """Step 4: Run sentiment analysis on all unlocked comments."""
    log("=== Step 4: Sentiment analysis ===")
    r = run(["python3", str(REPO_ROOT / "db/update_sentiment.py")], timeout=600)
    log(f"  rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-30:]:
            log(f"    {line}")
    return r.returncode == 0


def generate_report():
    """Step 5: Generate Excel report."""
    log("=== Step 5: Generate report ===")
    cmd = [
        "python3",
        str(SCRIPT_DIR / "generate_report.py"),
        "--date", TODAY,
        "--window-start", WINDOW_START.isoformat(),
        "--window-end", WINDOW_END.isoformat(),
    ]
    r = run(cmd, timeout=300)
    log(f"  rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-30:]:
            log(f"    {line}")
    return r.returncode == 0


def main():
    log(f"=== All-platforms comment collection ===")
    log(f"Window: {WINDOW_START.isoformat()} ~ {WINDOW_END.isoformat()}")
    log(f"Output dir: {SCHEDULE_DIR / 'output'}")

    # Clear issues file
    ISSUES_FILE.write_text(
        f"# Schedule/collect_all — Issues ({TODAY})\n\n"
        f"Time window: {WINDOW_START.isoformat()} ~ {WINDOW_END.isoformat()}\n\n",
        encoding="utf-8",
    )

    if "--check-login" in sys.argv:
        check_login()
        return

    if "--collect-only" in sys.argv:
        collect_bilibili()
        collect_xiaohongshu()
        collect_xueqiu()
        return

    if "--import-only" in sys.argv:
        import_all()
        return

    if "--sentiment-only" in sys.argv:
        run_sentiment()
        return

    if "--report-only" in sys.argv:
        generate_report()
        return

    # Full pipeline
    check_login()
    collect_bilibili()
    collect_xiaohongshu()
    collect_xueqiu()
    import_all()
    run_sentiment()
    generate_report()

    log("=== All done ===")


if __name__ == "__main__":
    main()
