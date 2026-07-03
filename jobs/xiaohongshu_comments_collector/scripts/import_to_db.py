#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 collect_comments.py 落盘的 JSON 入库。

调用方式（仓库根目录）：

    python jobs/xiaohongshu_comments_collector/scripts/import_to_db.py \\
        --date 2026-06-29

逻辑（使用 backend-api skill 的 CommentRepository）：
  1. 读 `comments/xiaohongshu_<date>.json`
  2. 每条笔记 upsert 到 `videos` 表（platform=xiaohongshu, video_id=note_id）
  3. 每条评论：
       - 若 (platform, comment_id) 已存在 → 只更新 likes（如果新值更大）
       - 否则插入 comments 行，写入 local_image_path / original_url / source_url
  4. 完成后调用 db/update_sentiment.py 风格的批量情绪分析入口；
     这里只跑 `analyze_sentiment`（同步），让前端面板立刻有数据。
"""
import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
JOB_DIR = SCRIPT_DIR.parent
REPO_ROOT = JOB_DIR.parent.parent

# backend 不是可安装包；从仓库根运行
sys.path.insert(0, str(REPO_ROOT))

from backend.database import get_db  # noqa: E402
from backend.repositories.comment_repository import CommentRepository  # noqa: E402
from backend.services.comment_service import CommentService  # noqa: E402

COMMENTS_DIR = REPO_ROOT / "comments"


def find_by_platform_comment_id(platform, comment_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id, likes FROM comments WHERE platform = ? AND comment_id = ?",
        (platform, comment_id),
    ).fetchone()
    conn.close()
    return row


def update_likes(db_id, new_likes):
    conn = get_db()
    conn.execute("UPDATE comments SET likes = ? WHERE id = ?", (new_likes, db_id))
    conn.commit()
    conn.close()


def upsert_note_video(note):
    """把笔记 upsert 到 videos 表。返回 video_pk。"""
    platform = "xiaohongshu"
    note_id = note["note_id"]
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM videos WHERE platform = ? AND video_id = ?",
        (platform, note_id),
    ).fetchone()
    if existing:
        pk = existing["id"]
    else:
        cur = conn.execute(
            """INSERT INTO videos
                 (platform, video_id, title, up_name, up_uid, url)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                platform,
                note_id,
                note.get("title", ""),
                note.get("author", ""),
                note.get("user_id", ""),
                note.get("url", ""),
            ),
        )
        pk = cur.lastrowid
        conn.commit()
    conn.close()
    return pk


def build_content(note, c, is_sub):
    """返回评论原文 — 不再加任何方括号前缀。

    历史版本会把笔记标题写进 `[笔记: ...]`、子评论加 `[回复]` 前缀。
    这些都是 collector 注入的噪声，且父子关系已通过 `is_reply` 字段区分，
    故全部去除。视频标题仍存于 `videos.title` 与 comments.video_title 字段。
    """
    return c.get("content", "")


def import_one(json_path, update_likes_flag=True, run_sentiment=False):
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    repo = CommentRepository()
    svc = CommentService()
    notes = payload.get("notes", [])

    inserted = updated = skipped = sub_inserted = 0
    target_date = payload.get("target_date", "")

    for note in notes:
        upsert_note_video(note)
        for c in note.get("comments", []):
            comment_id = c.get("id", "")
            content = build_content(note, c, is_sub=False)
            likes = int(c.get("like_count", 0) or 0)
            created_at = c.get("create_time", "")
            # 同笔记内子评论不在 opencli 路径下提供（CLI 返回平坦列表），
            # 仍走主循环；is_reply 仅作元数据。
            existing = (find_by_platform_comment_id("xiaohongshu", comment_id)
                        if comment_id else None)
            if existing:
                if update_likes_flag and likes > (existing["likes"] or 0):
                    update_likes(existing["id"], likes)
                    updated += 1
                else:
                    skipped += 1
                continue
            repo.insert({
                "platform": "xiaohongshu",
                "comment_id": comment_id,
                "author_name": c.get("author", ""),
                "content": content,
                "likes": likes,
                "replies": int(c.get("sub_comment_count", 0) or 0),
                "source_url": note.get("url", ""),
                "local_image_path": note.get("local_image_path"),
                "original_url": note.get("cover_url"),
                "video_bvid": note["note_id"],
                "video_title": note.get("title", ""),
                "up_name": note.get("author", ""),
                "up_uid": note.get("user_id", ""),
                "created_at": created_at,
            })
            inserted += 1

    print(f"[{target_date}] inserted={inserted} updated={updated} "
          f"sub_inserted={sub_inserted} skipped={skipped}")

    if run_sentiment:
        from jobs.sentiment_analyzer.llm_sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        rows = repo.find_unlocked_ids_by_filter({"platform": "xiaohongshu",
                                                  "date_from": f"{target_date} 00:00",
                                                  "date_to":   f"{target_date} 23:59"})
        updates = []
        for r in rows:
            try:
                result = analyzer.analyze(r["content"])
            except Exception as e:
                print(f"  sentiment err id={r['id']}: {e}")
                continue
            # 兼容两种字段：score（旧）/ scores['positive'] - scores['negative']（新）
            if "score" in result:
                score = float(result["score"])
            else:
                s = result.get("scores", {})
                score = float(s.get("positive", 0)) - float(s.get("negative", 0))
            updates.append((result["sentiment"], score, r["id"]))
        if updates:
            repo.batch_update_sentiment(updates)
            print(f"  sentiment updated: {len(updates)}")
    return inserted, updated, sub_inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Import xiaohongshu JSON → DB")
    parser.add_argument("--date", required=True,
                        help="目标日期 YYYY-MM-DD（文件名后缀）")
    parser.add_argument("--no-like-update", action="store_true",
                        help="不要用新 likes 覆盖旧值")
    parser.add_argument("--sentiment", action="store_true",
                        help="导入后立刻跑 LLM 情绪分析（仅本次新增行）")
    args = parser.parse_args()

    json_path = COMMENTS_DIR / f"xiaohongshu_{args.date}.json"
    if not json_path.exists():
        print(f"ERROR: {json_path} not found")
        return 1
    import_one(json_path, update_likes_flag=not args.no_like_update,
               run_sentiment=args.sentiment)
    return 0


if __name__ == "__main__":
    sys.exit(main())