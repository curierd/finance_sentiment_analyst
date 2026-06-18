#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect comments from today's bilibili videos for the finance UP list.

Workflow (per jobs/bilibili_comments_collector/expectation.md):
- Read UP list from ../bilibili-finance-up.md (markdown table).
- Skip blacklisted UPs (## up黑名单 section).
- For each active UP, fetch recent videos (bili user-videos, fall back to
  opencli bilibili user-videos on 412 risk control).
- Filter videos where date == target_date (default = today).
- For each matching video, fetch comments via opencli bilibili comments.
- Sleep >= 1.5 s between requests; never concurrent.
- Save final JSON to <repo>/comments/bilibili_<date>.json.
- Save partial progress to <repo>/intermediate/bilibili_<date>.partial.json.
- Import into SQLite via backend CommentRepository (skip if 0 comments).
- Log errors into the JSON envelope.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
JOB_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = JOB_DIR.parent.parent

UP_LIST_FILE = JOB_DIR / "bilibili-finance-up.md"
COMMENTS_DIR = PROJECT_ROOT / "comments"
INTERMEDIATE_DIR = PROJECT_ROOT / "intermediate"
ISSUES_FILE = JOB_DIR / "issues.md"

sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = __import__("io").TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
sys.path.insert(0, str(PROJECT_ROOT))

from backend.repositories.comment_repository import CommentRepository  # noqa: E402
from bilibili_image_downloader import download_images_for_comments  # noqa: E402


def log_issue(text):
    """Append a timestamped note to issues.md."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"- [{ts}] {text}\n"
    if not ISSUES_FILE.exists():
        ISSUES_FILE.write_text("# 实现和运行中遇到的问题\n\n", encoding="utf-8")
    with ISSUES_FILE.open("a", encoding="utf-8") as f:
        f.write(line)


def parse_up_list(path):
    """Parse the markdown-table UP list; return (ups, blacklist)."""
    ups, blacklist = [], []
    section = "ups"
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("##"):
                if "黑名单" in line or "blacklist" in line.lower():
                    section = "blacklist"
                else:
                    section = "ups"
                continue
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) < 3:
                continue
            if "排名" in cells[0] or set(line.replace("|", "").strip()) <= set("-: "):
                continue
            try:
                int(cells[0])
            except ValueError:
                continue
            uid, name = cells[2], cells[1]
            entry = {"uid": uid, "name": name}
            (blacklist if section == "blacklist" else ups).append(entry)
    return ups, blacklist


def _resolve_tool(name):
    """Resolve a tool to a Windows-executable path on Windows. The npm
    `opencli` is a bash script without an extension that subprocess.run on
    Windows cannot find — use the .cmd shim instead.
    """
    if os.name != "nt":
        return name
    if os.path.isabs(name) or "\\" in name or "/" in name:
        return name
    if name == "python3":
        return sys.executable
    for ext in ("", ".cmd", ".exe", ".bat"):
        candidate = shutil.which(name + ext)
        if candidate:
            return candidate
    return name


def _strip_preamble(text):
    """Strip Windows preamble lines like 'Active code page: 65001' that
    the opencli.CMD shim emits before stdout. The first valid JSON value
    starts at the first line beginning with '{' or '['.
    """
    if not text:
        return text
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(("{", "[")):
            return "".join(lines[i:])
    return text


def run(cmd, timeout=120):
    env = os.environ.copy()
    env["OPENCLI_WINDOW"] = "background"
    if isinstance(cmd, list) and cmd:
        cmd = [_resolve_tool(c) if i == 0 else c for i, c in enumerate(cmd)]
    r = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env,
        encoding="utf-8", errors="replace",
    )
    return r.returncode, _strip_preamble(r.stdout), r.stderr


def is_in_window(date_str, target_date_str, window_days):
    """Return True iff date_str is within ±window_days of target_date_str."""
    if not date_str or window_days < 0:
        return False
    try:
        d = date.fromisoformat(date_str)
        target = date.fromisoformat(target_date_str)
    except ValueError:
        return False
    return abs((d - target).days) <= window_days


def fetch_videos_bili(uid, limit=30):
    """Try `bili user-videos` first. Return (list, error_dict_or_none)."""
    rc, out, err = run(["bili", "user-videos", str(uid), "-n", str(limit), "--json"])
    if rc != 0:
        return None, {"cmd": "bili user-videos", "rc": rc, "stderr": err.strip()[:200]}
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return None, {"cmd": "bili user-videos", "json_error": str(e)}
    if isinstance(data, dict) and data.get("ok") is False:
        return None, {"cmd": "bili user-videos", "api_error": data.get("error", {})}
    videos = data if isinstance(data, list) else data.get("videos", data.get("data", []))
    if isinstance(videos, dict):
        videos = videos.get("videos", videos.get("data", []))
    return videos, None


def fetch_videos_opencli(uid, limit=30):
    """Fallback to `opencli bilibili user-videos`."""
    rc, out, err = run(
        ["opencli", "bilibili", "user-videos", str(uid),
         "--limit", str(limit), "-f", "json"]
    )
    if rc != 0:
        return None, {"cmd": "opencli bilibili user-videos", "rc": rc, "stderr": err.strip()[:200]}
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return None, {"cmd": "opencli bilibili user-videos", "json_error": str(e)}
    return data, None


def normalize_video(v, up, source="opencli"):
    """Map CLI output to a canonical video record."""
    url = v.get("url") or v.get("arcurl") or ""
    bvid = v.get("bvid") or ""
    if not bvid and "/video/" in url:
        bvid = url.split("/video/")[-1].split("?")[0].split("/")[0]
    pub = (
        v.get("pubdate")
        or v.get("created")
        or v.get("date")
        or (str(v.get("publish_time")) if v.get("publish_time") else "")
        or ""
    )
    date_str = pub[:10] if pub else ""
    plays = v.get("plays") or v.get("play") or (v.get("stats") or {}).get("view")
    likes = v.get("likes") or v.get("like") or (v.get("stats") or {}).get("like") or 0
    return {
        "rank": v.get("rank"),
        "title": v.get("title"),
        "bvid": bvid,
        "url": url or (f"https://www.bilibili.com/video/{bvid}" if bvid else ""),
        "date": date_str,
        "plays": plays,
        "likes": likes,
        "_up": up,
        "_source": source,
    }


def fetch_comments(bvid, limit=50):
    """Fetch comments via opencli bilibili comments. The legacy private
    `comments-raw` adapter was removed in opencli >= 1.8.4; fall back to the
    public `comments` command which returns rank/rpid/author/text/likes/replies/time
    (no pics[]).
    """
    rc, out, err = run(
        ["opencli", "bilibili", "comments", bvid,
         "--limit", str(limit), "-f", "json"]
    )
    if rc != 0:
        return None, {"cmd": "opencli bilibili comments", "rc": rc, "stderr": err.strip()[:200]}
    try:
        return json.loads(out), None
    except json.JSONDecodeError as e:
        return None, {"cmd": "opencli bilibili comments", "json_error": str(e)}


def _ext_from_url(url, default=".jpg"):
    # 兼容旧调用; 主逻辑在 bilibili_image_downloader.ext_from_url
    from bilibili_image_downloader import ext_from_url
    return ext_from_url(url, default)


def attach_images(comments, bvid, image_root, errors):
    """Thin wrapper around bilibili_image_downloader.download_images_for_comments."""
    download_images_for_comments(
        comments, bvid, image_root, errors=errors, project_root=PROJECT_ROOT
    )


def save_partial(data, partial_path):
    with partial_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _existing_comment_ids(platform, comment_ids):
    """Return set of comment_ids already in DB for this platform."""
    if not comment_ids:
        return set()
    from backend.database import get_db
    conn = get_db()
    placeholders = ",".join("?" * len(comment_ids))
    rows = conn.execute(
        f"SELECT comment_id FROM comments "
        f"WHERE platform = ? AND comment_id IN ({placeholders})",
        [platform] + list(comment_ids),
    ).fetchall()
    conn.close()
    return {r["comment_id"] for r in rows}


def import_comments(comments, ups_seen, errors):
    if not comments:
        print("\n[INFO] 0 条评论, 跳过导入")
        return 0, 0
    print(f"\n[IMPORT] 导入数据库 ({len(comments)} 条评论)...")
    repo = CommentRepository()
    candidates = [c.get("comment_id") or c.get("rpid") for c in comments
                  if c.get("comment_id") or c.get("rpid")]
    existing = _existing_comment_ids("bilibili", candidates)
    if existing:
        print(f"[IMPORT] 已存在 {len(existing)} 条 (按 comment_id 去重)")
    imported, skipped = 0, 0
    for c in comments:
        try:
            text = (c.get("text") or "").strip()
            if not text:
                skipped += 1
                continue
            # Map rpid -> comment_id for the new opencli `comments` format
            # (legacy `comments-raw` used comment_id directly)
            cid = c.get("comment_id") or c.get("rpid")
            if cid and cid in existing:
                skipped += 1
                continue
            video = c.get("_video") or {}
            up = c.get("_up") or {}
            video_title = video.get("title") or ""
            extra = f"[视频: {video_title}]\n" if video_title else ""
            row = {
                "platform": "bilibili",
                "comment_id": cid,
                "content": extra + text,
                "author_name": c.get("author", "") or "",
                "likes": c.get("likes", 0) or 0,
                "up_name": up.get("name", "") or "",
                "up_uid": up.get("uid", "") or "",
                "video_title": video_title,
                "video_bvid": c.get("_video_bvid") or video.get("bvid") or "",
                "local_image_path": c.get("local_image_path"),
                "original_url": c.get("original_url"),
            }
            time_str = c.get("time", "")
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    row["created_at"] = datetime.strptime(time_str, fmt).isoformat()
                    break
                except (ValueError, TypeError):
                    continue
            repo.insert(row)
            if cid:
                existing.add(cid)
            imported += 1
        except Exception as e:
            errors.append({"stage": "import", "comment": c.get("text", "")[:80], "error": str(e)})
            skipped += 1
    print(f"[IMPORT] 完成: 导入 {imported}, 跳过 {skipped}")
    return imported, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="目标日期 YYYY-MM-DD (默认: 今天)")
    parser.add_argument("--limit", type=int, default=50, help="每视频评论上限")
    parser.add_argument("--video-pages", type=int, default=3,
                        help="每个 UP 主拉取的视频页数 (1页=20个)")
    parser.add_argument("--sleep", type=float, default=1.5, help="请求间隔秒数")
    parser.add_argument("--window-days", type=int, default=0,
                        help="日期窗口 (target ± N 天), 0=仅 target_date (默认)")
    parser.add_argument("--import-only", action="store_true",
                        help="跳过采集, 仅从已有 JSON 导入数据库")
    parser.add_argument("--no-import", action="store_true", help="采集但不入库")
    args = parser.parse_args()

    target_date = args.date
    print(f"[RUN] 目标日期 = {target_date}")
    print(f"[RUN] UP列表: {UP_LIST_FILE}")

    if not UP_LIST_FILE.exists():
        print(f"[FATAL] UP list not found: {UP_LIST_FILE}")
        sys.exit(1)

    COMMENTS_DIR.mkdir(exist_ok=True)
    INTERMEDIATE_DIR.mkdir(exist_ok=True)
    ups, blacklist = parse_up_list(UP_LIST_FILE)
    print(f"[RUN] UP主 {len(ups)} 个, 黑名单 {len(blacklist)} 个")

    data = {
        "target_date": target_date,
        "platform": "bilibili",
        "sources": [str(UP_LIST_FILE.relative_to(PROJECT_ROOT))],
        "ups": ups,
        "blacklist": blacklist,
        "videos": [],
        "comments": [],
        "ups_with_today_videos": [],
        "errors": [],
        "request_policy": {"sleep_seconds": args.sleep, "concurrent": False},
        "filter": (
            f"videos where |date - target_date| <= {args.window_days} day(s)"
            if args.window_days else "videos where date == target_date"
        ),
        "window_days": args.window_days,
    }

    if not args.import_only:
        blacklist_uids = {u["uid"] for u in blacklist}
        for idx, up in enumerate(ups, 1):
            if up["uid"] in blacklist_uids:
                print(f"\n[{idx}/{len(ups)}] [SKIP] 黑名单: {up['name']}")
                continue
            print(f"\n[{idx}/{len(ups)}] [UP] {up['name']} (UID={up['uid']})")
            # opencli 优先 (有 date 字段); bili 作为兜底 (无 date)
            raw, err = fetch_videos_opencli(up["uid"], limit=20 * args.video_pages)
            used_source = "opencli"
            if err is not None or not raw:
                log_issue(f"opencli user-videos 失败 UID={up['uid']} ({up['name']}): {err}; 尝试 bili")
                print("  [FALLBACK] opencli -> bili")
                time.sleep(args.sleep)
                raw, err = fetch_videos_bili(up["uid"], limit=20 * args.video_pages)
                used_source = "bili"
                if err is not None:
                    data["errors"].append({"up": up, "stage": "videos", **err})
                    print(f"  [ERR] {err}")
                    time.sleep(args.sleep)
                    continue
            if not raw:
                print("  [INFO] 视频列表为空")
                time.sleep(args.sleep)
                continue
            today_videos = []
            earliest_seen = None
            no_date_count = 0
            for v in raw:
                nv = normalize_video(v, up, source=used_source)
                if not nv["date"]:
                    no_date_count += 1
                    continue
                if earliest_seen is None or nv["date"] < earliest_seen:
                    earliest_seen = nv["date"]
                if is_in_window(nv["date"], target_date, args.window_days):
                    today_videos.append(nv)
            if not today_videos:
                msg = f"  [INFO] 窗口内无新视频 (最早 {earliest_seen}"
                if no_date_count:
                    msg += f", {no_date_count} 条无日期 ({used_source})"
                msg += ")"
                print(msg)
                if used_source == "bili" and no_date_count == len(raw):
                    log_issue(f"bili 兜底无 date 字段, UID={up['uid']} ({up['name']})")
                time.sleep(args.sleep)
                continue
            data["ups_with_today_videos"].append(up["uid"])
            print(f"  [HIT] {len(today_videos)} 个 {target_date} 视频")
            for v in today_videos:
                print(f"    - {v['title'][:40]}... (BV={v['bvid']})")
                data["videos"].append(v)
                comments, cerr = fetch_comments(v["bvid"], args.limit)
                time.sleep(args.sleep)
                if cerr:
                    data["errors"].append({"video": v, "stage": "comments", **cerr})
                    print(f"      [ERR] {cerr}")
                    continue
                if not comments:
                    print("      [INFO] 0 评论")
                    continue
                for c in comments:
                    c["_up"] = up
                    c["_video"] = v
                    c["_video_bvid"] = v["bvid"]
                attach_images(comments, v["bvid"], COMMENTS_DIR / "images" / "bilibili", data["errors"])
                data["comments"].extend(comments)
                pic_count = sum(len(c.get("images") or []) for c in comments)
                ok_count = sum(
                    1 for c in comments for img in (c.get("images") or []) if img.get("downloaded")
                )
                print(f"      [+] {len(comments)} 评论, {ok_count}/{pic_count} 图下载成功")
            time.sleep(args.sleep)
            save_partial(data, INTERMEDIATE_DIR / f"bilibili_{target_date}.partial.json")

    final_path = COMMENTS_DIR / f"bilibili_{target_date}.json"
    with final_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] {final_path}")
    print(f"[STATS] videos={len(data['videos'])}  comments={len(data['comments'])}  "
          f"errors={len(data['errors'])}")

    if data["comments"]:
        log_issue(f"采集成功: {len(data['videos'])} 视频, {len(data['comments'])} 评论")
    else:
        log_issue(f"采集为空: 0 个 {target_date} 视频 (UP={len(ups)})")

    if args.no_import:
        print("[DONE] --no-import, 跳过数据库导入")
        return

    if args.import_only or data["comments"]:
        imported, skipped = import_comments(
            data["comments"], data.get("ups_with_today_videos", []), data["errors"])
        with final_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if imported > 0:
            print("\n--- Sentiment Analysis ---")
            from backend.services.comment_service import CommentService
            from backend.database import get_db
            conn = get_db()
            new_count = conn.execute(
                "SELECT COUNT(*) FROM comments WHERE platform = 'bilibili' "
                "AND sentiment IS NULL AND sentiment_fix IS NULL"
            ).fetchone()[0]
            conn.close()
            if new_count > 0:
                print(f"  Analyzing {new_count} new comments...")
                svc = CommentService()
                result = svc.analyze_sentiment(filters={"platform": "bilibili"})
                if result and result.get("analyzed"):
                    s = result.get("stats", {})
                    print(f"  Analyzed: {result['analyzed']}, dist: {s.get('counts', {})}")
            else:
                print("  All comments already analyzed, skipping")

    print("\n[DONE]")


if __name__ == "__main__":
    main()
