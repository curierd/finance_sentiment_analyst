#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Master orchestration for `schedule/collect_all/expectation.md`.

Tasks (per expectation.md):
  1. Determine login status of all platforms
  2. Quantitative analysis of all platforms' comments, with image collection
  3. Time window: previous trading day close ~ today open

Window (CST):
  - default: previous A-share trading day 15:00:00 ~ today 23:59:59 CST
  - overrides: --today / --window-start / --window-end

Outputs:
  - schedule/collect_all/scripts/  — orchestrator + per-platform scripts
  - schedule/collect_all/intermediate/ — partial dumps, login status
  - schedule/collect_all/output/  — final Excel report
  - schedule/collect_all/issues.md — encountered issues
"""
import json
import io
import os
import shutil
import subprocess
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

CST = timezone(timedelta(hours=8))


def _prev_trading_day(d):
    """Previous A-share trading day for date `d` (Mon-Fri; Sat/Sun → Friday)."""
    wd = d.weekday()  # Mon=0 ... Sun=6
    if wd == 5:  # Sat → Fri
        return d - timedelta(days=1)
    if wd == 6:  # Sun → Fri
        return d - timedelta(days=2)
    if wd == 0:  # Mon → Fri
        return d - timedelta(days=3)
    return d - timedelta(days=1)  # Tue-Fri → previous weekday


def _resolve_window(args):
    """Resolve TODAY / WINDOW_START / WINDOW_END from CLI args or default to
    `prev A-share trading day 15:00` ~ `today 23:59` CST."""
    today_str = getattr(args, "today", None)
    if today_str:
        today_d = datetime.strptime(today_str, "%Y-%m-%d").date()
    else:
        today_d = datetime.now(CST).date()
    prev_d = _prev_trading_day(today_d)
    ws_default = datetime(prev_d.year, prev_d.month, prev_d.day, 15, 0, 0, tzinfo=CST)
    we_default = datetime(today_d.year, today_d.month, today_d.day, 23, 59, 59, tzinfo=CST)

    ws_str = getattr(args, "window_start", None)
    we_str = getattr(args, "window_end", None)
    ws = datetime.fromisoformat(ws_str) if ws_str else ws_default
    we = datetime.fromisoformat(we_str) if we_str else we_default
    return today_d.strftime("%Y-%m-%d"), prev_d.strftime("%Y-%m-%d"), ws, we

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEDULE_DIR = SCRIPT_DIR.parent
INTERMEDIATE_DIR = SCHEDULE_DIR / "intermediate"
ISSUES_FILE = SCHEDULE_DIR / "issues.md"
REPO_ROOT = SCHEDULE_DIR.parent.parent

INTERMEDIATE_DIR.mkdir(exist_ok=True)


def _resolve_tool(name):
    """Resolve tool name to absolute path (handles npm .cmd shims on Windows)."""
    candidates = [name, f"{name}.cmd", f"{name}.exe", f"{name}.bat"]
    for c in candidates:
        p = shutil.which(c)
        if p:
            return p
    return name


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _strip_preamble(s):
    """Skip opencli's `Active code page: 65001` prefix and any blank lines."""
    if not s:
        return s
    lines = s.splitlines()
    out = []
    skip = True
    for line in lines:
        if skip and (not line.strip() or line.startswith("Active code page")):
            continue
        skip = False
        out.append(line)
    return "\n".join(out)


def _parse_simple_yaml(s):
    """Parse opencli's `key: value` YAML output into a dict."""
    out = {}
    for line in s.splitlines():
        line = line.rstrip()
        if not line or line.startswith("Active code page"):
            continue
        # very limited parsing: `key: 'value'` or `key: value`
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if v.startswith("'") and v.endswith("'"):
            v = v[1:-1]
        if v.lower() == "true":
            v = True
        elif v.lower() == "false":
            v = False
        out[k] = v
    return out


def run(cmd, cwd=None, timeout=None, env=None):
    if env is None:
        env = os.environ.copy()
    # On Windows, prepend npm/local bin dirs to PATH so subprocess can find
    # bash-only scripts (opencli is a bash shim, not a real .exe).
    if sys.platform == "win32":
        for p in (
            r"C:\Users\sverd\AppData\Roaming\npm",
            r"C:\Users\sverd\.local\bin",
        ):
            if p not in env.get("PATH", ""):
                env["PATH"] = p + os.pathsep + env.get("PATH", "")

    # Resolve first token to absolute path (handles .cmd shims).
    if isinstance(cmd, list) and cmd:
        resolved = _resolve_tool(cmd[0])
        cmd = [resolved] + list(cmd[1:])

    log(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(
        cmd if isinstance(cmd, list) else cmd.split(),
        cwd=cwd or str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


def check_login():
    """Step 1: Check login status of all 3 platforms. Save to intermediate."""
    log("=== Step 1: Login status check ===")
    status = {}

    # B站 — opencli bilibili whoami  (returns YAML, not JSON)
    r = run(["opencli", "bilibili", "whoami"], timeout=30)
    cleaned = _strip_preamble(r.stdout)
    if r.returncode == 0 and "logged_in" in cleaned:
        data = _parse_simple_yaml(cleaned)
        status["bilibili_opencli"] = {
            "tool": "opencli bilibili",
            "ok": data.get("logged_in") is True,
            "user": data.get("username"),
            "level": data.get("level"),
            "id": data.get("id"),
            "raw_excerpt": cleaned[:300],
        }
    else:
        status["bilibili_opencli"] = {
            "tool": "opencli bilibili",
            "ok": False,
            "stderr": (r.stderr or cleaned)[:300],
        }

    # 雪球 — opencli xueqiu hot (test for valid JSON output)
    r = run(["opencli", "xueqiu", "hot", "--limit", "1", "-f", "json"], timeout=30)
    cleaned = _strip_preamble(r.stdout)
    status["xueqiu"] = {
        "tool": "opencli xueqiu",
        "ok": r.returncode == 0 and cleaned.strip().startswith("["),
    }
    if not status["xueqiu"]["ok"]:
        status["xueqiu"]["stderr"] = (r.stderr or cleaned)[:300]

    # 小红书 — opencli xiaohongshu whoami (returns JSON-ish or text)
    r = run(["opencli", "xiaohongshu", "whoami"], timeout=30)
    xhs_ok = False
    xhs_text = _strip_preamble(r.stdout) if r.stdout else r.stderr
    if r.returncode == 0 and r.stdout:
        try:
            data = json.loads(_strip_preamble(r.stdout))
            xhs_ok = bool(data.get("ok")) and not data.get("error")
        except json.JSONDecodeError:
            xhs_ok = "logged_in" in r.stdout.lower() or "已登录" in r.stdout
    status["xiaohongshu_opencli"] = {
        "tool": "opencli xiaohongshu",
        "ok": xhs_ok,
        "raw_excerpt": (xhs_text or "")[:300],
    }

    # 知乎 — opencli zhihu (no whoami; smoke test with search)
    r = run(["opencli", "zhihu", "search", "A股", "--limit", "1", "-f", "json"], timeout=30)
    cleaned = _strip_preamble(r.stdout)
    status["zhihu"] = {
        "tool": "opencli zhihu",
        "ok": r.returncode == 0 and (cleaned.strip().startswith("{") or cleaned.strip().startswith("[")),
    }
    if not status["zhihu"]["ok"]:
        status["zhihu"]["stderr"] = (r.stderr or cleaned)[:300]

    out_file = INTERMEDIATE_DIR / "login_status.json"
    out_file.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  Saved: {out_file}")
    for k, v in status.items():
        log(f"  {k}: {'OK' if v.get('ok') else 'FAIL'}")
    return status


def collect_bilibili(video_pages=None, limit=None, sleep=None):
    """Step 2a: B站 collection. target_date=TODAY, window_days=1.

    This gives us videos from PREV_TRADING_DAY to TODAY, including all the
    overnight comments posted on PREV_TRADING_DAY evening and TODAY.

    Defaults reduced from 24 UP × 2 pages → 24 UP × 1 page (per issues.md
    06-26: B站单平台 30+ min 仍跑不完，video-pages=1 可提速 50%)。
    """
    vp = video_pages if video_pages is not None else 1
    lim = limit if limit is not None else 50
    sl = sleep if sleep is not None else 1.5
    log(f"=== Step 2a: B站 collection (target={TODAY}, window_days=1, video_pages={vp}) ===")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py"),
        "--date", TODAY,
        "--window-days", "1",
        "--video-pages", str(vp),
        "--limit", str(lim),
        "--sleep", str(sl),
    ]
    r = run(cmd, timeout=3600)
    log(f"  rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-30:]:
            log(f"    {line}")
    if r.returncode != 0:
        log(f"  stderr: {r.stderr[:500]}")
    return r.returncode == 0


def collect_xiaohongshu():
    """Step 2b: 小红书 collection. We use the opencli-based collector
    (`schedule/collect_all/scripts/collect_xiaohongshu_opencli.py`) because
    `jobs/xiaohongshu_comments_collector/scripts/collect_comments.py` requires
    admin to read Chrome cookies. The opencli collector filters by date
    itself from the note_id timestamp.
    """
    log("=== Step 2b: 小红书 collection (opencli, window 06-19 ~ 06-20) ===")
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "collect_xiaohongshu_opencli.py"),
    ]
    r = run(cmd, timeout=1800)
    log(f"  rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-20:]:
            log(f"    {line}")
    if r.returncode != 0:
        log(f"  stderr: {(r.stderr or '')[:500]}")
    return r.returncode == 0


def collect_xueqiu():
    """Step 2c: 雪球 collection. We use the larger limit so we capture
    comments from PREV_TRADING_DAY evening too (the latest 100 per stock)."""
    log(f"=== Step 2c: 雪球 collection ({TODAY}, limit=100) ===")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "jobs/xuqiu_comments_collector/scripts/collect_xueqiu.py"),
        "--date", TODAY,
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


def collect_zhihu():
    """Step 2d: 知乎 collection. `collect_zhihu.py` filters by `--date`
    strictly (created_at == target_date CST), so we run for each date in
    the window. Use a tighter timeout per day to avoid the 30-min hang
    we saw on 06-19."""
    log(f"=== Step 2d: 知乎 collection (window {WINDOW_START.date()} ~ {WINDOW_END.date()}) ===")
    rc_ok = True
    d = WINDOW_START.date()
    end_d = WINDOW_END.date()
    date_list = []
    while d <= end_d:
        date_list.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    for date in date_list:
        log(f"  --- {date} ---")
        cmd = [
            sys.executable,
            str(REPO_ROOT / "jobs/zhihu_comments_collector/scripts/collect_zhihu.py"),
            "--date", date,
        ]
        r = run(cmd, timeout=900)
        log(f"  rc={r.returncode}")
        if r.stdout:
            for line in r.stdout.split("\n")[-15:]:
                log(f"    {line}")
        if r.returncode != 0:
            log(f"  stderr: {r.stderr[:500]}")
            rc_ok = False
    return rc_ok


def import_all():
    """Step 3: Import all 3 platforms' data into SQLite."""
    log("=== Step 3: Import to DB ===")
    success = True

    # Bilibili — re-import (idempotent)
    log("  --- bilibili ---")
    r = run([
        sys.executable,
        str(REPO_ROOT / "jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py"),
        "--import-only",
    ], timeout=600)
    log(f"    rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-20:]:
            log(f"    {line}")

    # Xiaohongshu — import for each day in the window that has a JSON file
    log("  --- xiaohongshu ---")
    comments_dir = REPO_ROOT / "comments"
    pattern = f"xiaohongshu_{TODAY[:7]}-*.json"
    for json_path in sorted(comments_dir.glob(pattern)):
        date_str = json_path.stem.replace("xiaohongshu_", "")
        log(f"  --- xiaohongshu {date_str} ---")
        r = run([
            sys.executable,
            str(REPO_ROOT / "jobs/xiaohongshu_comments_collector/scripts/import_to_db.py"),
            "--date", date_str,
        ], timeout=600)
        log(f"    rc={r.returncode}")
        if r.stdout:
            for line in r.stdout.split("\n")[-20:]:
                log(f"    {line}")

    # Xueqiu — manual import (no automatic import script)
    log("  --- xueqiu ---")
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "import_xueqiu_to_db.py"),
        "--date", TODAY,
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
    r = run([sys.executable, str(REPO_ROOT / "db/update_sentiment.py")], timeout=600)
    log(f"  rc={r.returncode}")
    if r.stdout:
        for line in r.stdout.split("\n")[-30:]:
            log(f"    {line}")
    return r.returncode == 0


def generate_report():
    """Step 5: Generate Excel report."""
    log("=== Step 5: Generate report ===")
    cmd = [
        sys.executable,
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
    parser = argparse.ArgumentParser(description="All-platforms comment collection")
    parser.add_argument("--today", default=None,
                        help="Today date YYYY-MM-DD (default: system date CST)")
    parser.add_argument("--window-start", default=None,
                        help="Window start ISO datetime (default: prev trading day 15:00 CST)")
    parser.add_argument("--window-end", default=None,
                        help="Window end ISO datetime (default: today 23:59:59 CST)")
    parser.add_argument("--check-login", action="store_true",
                        help="Only run login status check")
    parser.add_argument("--collect-only", action="store_true",
                        help="Only run 4-platform collection")
    parser.add_argument("--import-only", action="store_true",
                        help="Only import collected JSONs into DB")
    parser.add_argument("--sentiment-only", action="store_true",
                        help="Only run sentiment analysis")
    parser.add_argument("--report-only", action="store_true",
                        help="Only generate report")
    parser.add_argument("--bilibili-video-pages", type=int, default=None,
                        help="B站 video pages per UP (default: 1)")
    parser.add_argument("--bilibili-limit", type=int, default=None,
                        help="B站 comments per video (default: 50)")
    parser.add_argument("--bilibili-sleep", type=float, default=None,
                        help="B站 sleep between requests (default: 1.5s)")
    parser.add_argument("--skip-bilibili", action="store_true",
                        help="Skip B站 collection (use existing JSON)")
    args = parser.parse_args()

    global TODAY, PREV_TRADING_DAY, WINDOW_START, WINDOW_END
    TODAY, PREV_TRADING_DAY, WINDOW_START, WINDOW_END = _resolve_window(args)

    log(f"=== All-platforms comment collection ===")
    log(f"Window: {WINDOW_START.isoformat()} ~ {WINDOW_END.isoformat()}")
    log(f"Today: {TODAY}  Prev trading day: {PREV_TRADING_DAY}")
    log(f"Output dir: {SCHEDULE_DIR / 'output'}")

    # Clear issues file
    ISSUES_FILE.write_text(
        f"# Schedule/collect_all — Issues ({TODAY})\n\n"
        f"Time window: {WINDOW_START.isoformat()} ~ {WINDOW_END.isoformat()}\n\n",
        encoding="utf-8",
    )

    if args.check_login:
        check_login()
        return

    if args.collect_only:
        if not args.skip_bilibili:
            collect_bilibili(
                video_pages=args.bilibili_video_pages,
                limit=args.bilibili_limit,
                sleep=args.bilibili_sleep,
            )
        else:
            log("=== Step 2a: B站 collection SKIPPED (--skip-bilibili) ===")
        collect_xiaohongshu()
        collect_xueqiu()
        collect_zhihu()
        return

    if args.import_only:
        import_all()
        return

    if args.sentiment_only:
        run_sentiment()
        return

    if args.report_only:
        generate_report()
        return

    # Full pipeline
    check_login()
    if not args.skip_bilibili:
        collect_bilibili(
            video_pages=args.bilibili_video_pages,
            limit=args.bilibili_limit,
            sleep=args.bilibili_sleep,
        )
    else:
        log("=== Step 2a: B站 collection SKIPPED (--skip-bilibili) ===")
    collect_xiaohongshu()
    collect_xueqiu()
    collect_zhihu()
    import_all()
    run_sentiment()
    generate_report()

    log("=== All done ===")


if __name__ == "__main__":
    main()
