#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Master orchestration for `schedule/collect_all/expectation.md`.

Tasks (per expectation.md):
  1. Determine login status of all platforms
  2. Quantitative analysis of all platforms' comments, with image collection
  3. Time window: previous trading day close ~ today open

Window (CST):
  - previous trading day: 2026-06-19 (Fri) close 15:00
  - today: 2026-06-21 (Sun) — market closed; next open 2026-06-23 09:30
  - Window: 2026-06-19 15:00:00 ~ 2026-06-23 09:30:00 CST

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
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

CST = timezone(timedelta(hours=8))
WINDOW_START = datetime(2026, 6, 19, 15, 0, 0, tzinfo=CST)
WINDOW_END = datetime(2026, 6, 23, 9, 30, 0, tzinfo=CST)
TODAY = "2026-06-21"
PREV_TRADING_DAY = "2026-06-19"

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

    # 小红书 — xhs CLI (test with a known note + token)
    test_note = "6a30cd5400000000110198a0"
    test_token = "ABzLri3FHI4eFOQ188uDzch1E4W-e056nPuxpamJxEeLM="
    r = run(["xhs", "comments", test_note, "--xsec-token", test_token, "--json"], timeout=60)
    status["xiaohongshu_xhs"] = {
        "tool": "xhs CLI",
        "ok": r.returncode == 0 and '"ok": true' in r.stdout,
    }
    if not status["xiaohongshu_xhs"]["ok"]:
        status["xiaohongshu_xhs"]["stderr"] = (r.stderr or r.stdout)[:300]

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


def collect_bilibili():
    """Step 2a: B站 collection. target_date=2026-06-21, window_days=1.

    This gives us videos from 2026-06-20 to 2026-06-22, including all the
    overnight comments posted on 06-20 evening and 06-21.
    """
    log("=== Step 2a: B站 collection (target=2026-06-21, window_days=1) ===")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py"),
        "--date", "2026-06-21",
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
    comments from 06-19 evening too (the latest 100 per stock)."""
    log("=== Step 2c: 雪球 collection (2026-06-21, limit=100) ===")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "jobs/xuqiu_comments_collector/scripts/collect_xueqiu.py"),
        "--date", "2026-06-21",
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
    log("=== Step 2d: 知乎 collection (06-19 + 06-20 + 06-21) ===")
    rc_ok = True
    for date in ["2026-06-19", "2026-06-20", "2026-06-21"]:
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
    for json_path in sorted(comments_dir.glob("xiaohongshu_2026-06-*.json")):
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
        "--date", "2026-06-21",
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
        collect_zhihu()
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
    collect_zhihu()
    import_all()
    run_sentiment()
    generate_report()

    log("=== All done ===")


if __name__ == "__main__":
    main()
