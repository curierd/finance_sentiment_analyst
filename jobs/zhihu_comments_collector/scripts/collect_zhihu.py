#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect comments from today's Zhihu answers about A股 topics.

Workflow (per expectation.md):
- Read search terms from ../zhihu-search-terms.md.
- For each term, search Zhihu via opencli zhihu search.
- Extract answer IDs from search result URLs.
- Dedup answers across search terms.
- For each answer, fetch comments via opencli zhihu answer-comments (with replies).
- Filter comments where created_at is today (CST timezone).
- Download images embedded in comment content.
- Save final JSON to <repo>/comments/zhihu_<date>.json.
- Save partial progress to <repo>/intermediate/zhihu_<date>.partial.json.
- Import into SQLite via backend CommentRepository.
- Sleep >= 1 s between requests; never concurrent.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
JOB_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = JOB_DIR.parent.parent

SEARCH_TERMS_FILE = JOB_DIR / "zhihu-search-terms.md"
COMMENTS_DIR = PROJECT_ROOT / "comments"
INTERMEDIATE_DIR = PROJECT_ROOT / "intermediate"
IMAGES_DIR = PROJECT_ROOT / "data" / "uploads" / "images"
ISSUES_FILE = JOB_DIR / "issues.md"

sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = __import__("io").TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
sys.path.insert(0, str(PROJECT_ROOT))

from backend.repositories.comment_repository import CommentRepository  # noqa: E402

CST = timezone(timedelta(hours=8))


def log_issue(text):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"- [{ts}] {text}\n"
    if not ISSUES_FILE.exists():
        ISSUES_FILE.write_text("# 实现和运行中遇到的问题\n\n", encoding="utf-8")
    with ISSUES_FILE.open("a", encoding="utf-8") as f:
        f.write(line)


def parse_search_terms(path):
    terms = []
    if not path.exists():
        return terms
    current_category = ""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("##"):
                current_category = line.lstrip("#").strip()
                continue
            if line.startswith("#"):
                continue
            terms.append({"category": current_category, "query": line})
    return terms


def run(cmd, timeout=120):
    env = os.environ.copy()
    env.setdefault("OPENCLI_WINDOW", "background")
    if os.name == "nt" and isinstance(cmd, list) and cmd:
        ps_cmd = subprocess.list2cmdline(cmd)
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=timeout, env=env,
            encoding="utf-8", errors="replace",
        )
    else:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
            encoding="utf-8", errors="replace",
        )
    return r.returncode, r.stdout, r.stderr


def search_zhihu(query, limit=20):
    rc, out, err = run(
        ["opencli", "zhihu", "search", query,
         "--type", "all", "--limit", str(limit), "-f", "json"]
    )
    if rc != 0:
        return None, {"cmd": "opencli zhihu search", "query": query, "rc": rc, "stderr": err.strip()[:200]}
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return None, {"cmd": "opencli zhihu search", "query": query, "json_error": str(e)}
    if isinstance(data, dict) and data.get("ok") is False:
        error_info = data.get("error", {})
        if error_info.get("code") == "EMPTY_RESULT":
            return [], None
        return None, {"cmd": "opencli zhihu search", "query": query, "api_error": error_info}
    return data if isinstance(data, list) else [], None


def extract_answer_ids(search_results):
    answers = {}
    for item in search_results:
        if item.get("type") != "answer":
            continue
        url = item.get("url", "")
        aid = _extract_answer_id(url)
        if not aid:
            continue
        qid = _extract_question_id(url)
        if aid not in answers:
            answers[aid] = {
                "answer_id": aid,
                "question_id": qid,
                "title": item.get("title", ""),
                "author": item.get("author", ""),
                "votes": item.get("votes", 0),
                "url": url,
            }
    return list(answers.values())


def _extract_answer_id(url):
    m = re.search(r"/answer/(\d+)", url)
    return m.group(1) if m else None


def _extract_question_id(url):
    m = re.search(r"/question/(\d+)", url)
    return m.group(1) if m else None


def fetch_comments(answer_id, limit=20, replies_limit=10):
    rc, out, err = run(
        ["opencli", "zhihu", "answer-comments", str(answer_id),
         "--limit", str(limit), "--replies-limit", str(replies_limit), "-f", "json"]
    )
    if rc != 0:
        return None, {"cmd": "opencli zhihu answer-comments", "answer_id": answer_id, "rc": rc, "stderr": err.strip()[:200]}
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return None, {"cmd": "opencli zhihu answer-comments", "answer_id": answer_id, "json_error": str(e)}
    if isinstance(data, dict) and data.get("ok") is False:
        error_info = data.get("error", {})
        if error_info.get("code") == "EMPTY_RESULT":
            return [], None
        return None, {"cmd": "opencli zhihu answer-comments", "answer_id": answer_id, "api_error": error_info}
    return data if isinstance(data, list) else [], None


def is_today_cst(created_at_str, target_date_str):
    if not created_at_str:
        return False
    try:
        created_at_str = created_at_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(created_at_str)
        dt_cst = dt_utc.astimezone(CST)
        return dt_cst.strftime("%Y-%m-%d") == target_date_str
    except (ValueError, TypeError):
        return False


def extract_image_urls(content):
    urls = re.findall(r'https?://[^\s<>"]+?\.(?:jpg|jpeg|png|gif|webp)[^\s<>"]*', content, re.IGNORECASE)
    img_tags = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    urls.extend(img_tags)
    seen = set()
    result = []
    for u in urls:
        u = u.strip()
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def download_image(url, dest_dir, comment_id, idx=0):
    """Download image, compute SHA256 hash, save to date-layered dir.
    Returns (relative_path, True) or (error_str, False)."""
    ext = ".jpg"
    parsed = urlparse(url)
    path_part = parsed.path or ""
    for e in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        if e in path_part.lower():
            ext = e
            break
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.zhihu.com/",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        file_hash = hashlib.sha256(data).hexdigest()
        today = date.today().strftime("%Y/%m")
        hash_dir = IMAGES_DIR / today
        hash_dir.mkdir(parents=True, exist_ok=True)
        dest_path = hash_dir / f"{file_hash}{ext}"
        dest_path.write_bytes(data)
        return str(dest_path.relative_to(PROJECT_ROOT)), True
    except Exception as e:
        return str(e), False


def download_images_for_comment(comment, answer_id, errors_list):
    content = comment.get("content", "")
    urls = extract_image_urls(content)
    if not urls:
        return None, None
    comment_id = comment.get("id", "unknown")
    local_paths = []
    original_urls = []
    for idx, url in enumerate(urls):
        local_path, ok = download_image(url, IMAGES_DIR, comment_id, idx)
        if ok:
            local_paths.append(local_path)
            original_urls.append(url)
        else:
            errors_list.append({
                "stage": "image_download",
                "comment_id": comment_id,
                "url": url,
                "error": local_path,
            })
    return local_paths[0] if local_paths else None, original_urls[0] if original_urls else None


def save_partial(data, partial_path):
    with partial_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _existing_comment_ids(platform, comment_ids):
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


def import_comments(comments, answers, errors):
    if not comments:
        print("\n[INFO] 0 条评论, 跳过导入")
        return 0, 0
    print(f"\n[IMPORT] 导入数据库 ({len(comments)} 条评论)...")
    repo = CommentRepository()
    candidates = [c.get("comment_id") for c in comments if c.get("comment_id")]
    existing = _existing_comment_ids("zhihu", candidates)
    if existing:
        print(f"[IMPORT] 已存在 {len(existing)} 条 (按 comment_id 去重)")
    imported, skipped = 0, 0
    for c in comments:
        try:
            content_text = (c.get("content") or "").strip()
            if not content_text:
                skipped += 1
                continue
            cid = c.get("comment_id")
            if cid and cid in existing:
                skipped += 1
                continue
            answer = c.get("_answer") or {}
            question_title = answer.get("title", "")
            answer_author = answer.get("author", "")
            extra = f"[问题: {question_title}]\n" if question_title else ""
            row = {
                "platform": "zhihu",
                "comment_id": cid,
                "content": extra + content_text,
                "author_name": c.get("author", "") or "",
                "likes": c.get("likes", 0) or 0,
                "up_name": answer_author,
                "up_uid": "",
                "video_title": question_title,
                "video_bvid": answer.get("answer_id") or "",
                "source_url": c.get("url") or answer.get("url") or "",
                "local_image_path": c.get("local_image_path"),
                "original_url": c.get("original_url"),
            }
            created_at = c.get("created_at", "")
            if created_at:
                try:
                    created_at = created_at.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(created_at)
                    row["created_at"] = dt.isoformat()
                except (ValueError, TypeError):
                    pass
            repo.insert(row)
            if cid:
                existing.add(cid)
            imported += 1
        except Exception as e:
            errors.append({"stage": "import", "comment": c.get("content", "")[:80], "error": str(e)})
            skipped += 1
    print(f"[IMPORT] 完成: 导入 {imported}, 跳过 {skipped}")
    return imported, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="目标日期 YYYY-MM-DD (北京时间, 默认: 今天)")
    parser.add_argument("--limit", type=int, default=20, help="每回答评论上限")
    parser.add_argument("--replies-limit", type=int, default=10, help="每评论子回复上限")
    parser.add_argument("--search-limit", type=int, default=20, help="每搜索词结果上限")
    parser.add_argument("--sleep", type=float, default=1.5, help="请求间隔秒数")
    parser.add_argument("--import-only", action="store_true",
                        help="跳过采集, 仅从已有 JSON 导入数据库")
    parser.add_argument("--no-import", action="store_true", help="采集但不入库")
    parser.add_argument("--no-download", action="store_true", help="不下载配图")
    args = parser.parse_args()

    target_date = args.date
    print(f"[RUN] 目标日期(北京时间) = {target_date}")
    print(f"[RUN] 搜索词文件: {SEARCH_TERMS_FILE}")

    COMMENTS_DIR.mkdir(exist_ok=True)
    INTERMEDIATE_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "target_date": target_date,
        "platform": "zhihu",
        "search_terms_file": str(SEARCH_TERMS_FILE.relative_to(PROJECT_ROOT)),
        "answers": [],
        "comments": [],
        "errors": [],
        "request_policy": {"sleep_seconds": args.sleep, "concurrent": False},
        "filter": f"comments where created_at (CST) == {target_date}",
    }

    if args.import_only:
        final_path = COMMENTS_DIR / f"zhihu_{target_date}.json"
        if not final_path.exists():
            print(f"[FATAL] JSON not found: {final_path}")
            sys.exit(1)
        with final_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        import_comments(data["comments"], data.get("answers", []), data["errors"])
        return

    terms = parse_search_terms(SEARCH_TERMS_FILE)
    if not terms:
        print("[FATAL] 搜索词列表为空")
        sys.exit(1)
    print(f"[RUN] 搜索词 {len(terms)} 个")

    all_answers = {}
    seen_answer_ids = set()

    for idx, term in enumerate(terms, 1):
        query = term["query"]
        category = term["category"]
        print(f"\n[{idx}/{len(terms)}] [SEARCH] {query} ({category})")

        results, err = search_zhihu(query, args.search_limit)
        time.sleep(args.sleep)

        if err:
            data["errors"].append(err)
            print(f"  [ERR] {err}")
            continue

        if not results:
            print("  [INFO] 无搜索结果")
            continue

        answers = extract_answer_ids(results)
        new_answers = [a for a in answers if a["answer_id"] not in seen_answer_ids]
        print(f"  [HIT] 搜索结果 {len(results)} 条, 新答案 {len(new_answers)} 个")
        for a in new_answers:
            seen_answer_ids.add(a["answer_id"])
            all_answers[a["answer_id"]] = a

        save_partial(data, INTERMEDIATE_DIR / f"zhihu_{target_date}.partial.json")

    print(f"\n[SUMMARY] 去重后答案: {len(all_answers)} 个")

    if not all_answers:
        print("[INFO] 无答案可采集")
    else:
        answer_list = list(all_answers.values())
        for idx, answer in enumerate(answer_list, 1):
            aid = answer["answer_id"]
            print(f"\n[{idx}/{len(answer_list)}] [ANSWER] {answer['title'][:40]}... by {answer['author']} (aid={aid})")

            comments, cerr = fetch_comments(aid, args.limit, args.replies_limit)
            time.sleep(args.sleep)

            if cerr:
                data["errors"].append(cerr)
                print(f"  [ERR] {cerr}")
                continue

            if not comments:
                print("  [INFO] 0 评论")
                continue

            today_comments = [c for c in comments if is_today_cst(c.get("created_at", ""), target_date)]
            if not today_comments:
                print(f"  [INFO] {len(comments)} 条评论, 但无今日 ({target_date}) 评论")
                continue

            print(f"  [HIT] {len(today_comments)} 条今日评论 (共 {len(comments)} 条)")

            for c in today_comments:
                c["_answer"] = answer
                c["comment_id"] = c.get("id", "")

                if not args.no_download:
                    local_path, original_url = download_images_for_comment(c, aid, data["errors"])
                    if local_path:
                        c["local_image_path"] = local_path
                    if original_url:
                        c["original_url"] = original_url

            data["answers"].append(answer)
            data["comments"].extend(today_comments)
            save_partial(data, INTERMEDIATE_DIR / f"zhihu_{target_date}.partial.json")

    final_path = COMMENTS_DIR / f"zhihu_{target_date}.json"
    with final_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] {final_path}")
    print(f"[STATS] answers={len(data['answers'])}  comments={len(data['comments'])}  errors={len(data['errors'])}")

    if data["comments"]:
        log_issue(f"采集成功: {len(data['answers'])} 答案, {len(data['comments'])} 评论")
    else:
        log_issue(f"采集为空: {len(data['answers'])} 答案, 无今日评论")

    if args.no_import:
        print("[DONE] --no-import, 跳过数据库导入")
        return

    import_comments(data["comments"], data.get("answers", []), data["errors"])
    with final_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n[DONE]")


if __name__ == "__main__":
    main()
