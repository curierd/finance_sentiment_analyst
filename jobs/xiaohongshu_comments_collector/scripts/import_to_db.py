#!/usr/bin/env python3
"""
Import xiaohongshu comments from collected JSON into the database.
Handles:
- Deduplication by comment_id
- Updates likes for existing comments
- Downloads comment-attached pictures (pictures field)
- Sets local_image_path / original_url only for comments with pictures
"""

import io
import json
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.repositories.comment_repository import CommentRepository
from backend.services.comment_service import CommentService
from backend.database import get_db

IMG_DIR = project_root / "comments" / "images" / "xiaohongshu" / "comments"


def find_by_platform_comment_id(platform, comment_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id, likes FROM comments WHERE platform = ? AND comment_id = ?",
        (platform, comment_id)
    ).fetchone()
    conn.close()
    return row


def update_likes(db_id, new_likes):
    conn = get_db()
    conn.execute("UPDATE comments SET likes = ? WHERE id = ?", (new_likes, db_id))
    conn.commit()
    conn.close()


def insert_note_video(note_info):
    conn = get_db()
    note_id = note_info["note_id"]
    platform = "xiaohongshu"
    existing = conn.execute(
        "SELECT id FROM videos WHERE platform = ? AND video_id = ?",
        (platform, note_id)
    ).fetchone()
    if existing:
        conn.close()
        return existing["id"]
    conn.execute("""
        INSERT INTO videos (platform, video_id, title, up_name, up_uid, url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        platform,
        note_id,
        note_info.get("title", ""),
        note_info.get("author", ""),
        note_info.get("user_id", ""),
        note_info.get("url", ""),
    ))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return new_id


def download_image(url, local_path):
    if local_path.exists() and local_path.stat().st_size > 0:
        return True
    try:
        subprocess.run(
            ["curl", "-sL", "--max-time", "15", "-o", str(local_path), url],
            timeout=20,
        )
        return local_path.exists() and local_path.stat().st_size > 0
    except Exception:
        return False


def process_comment_pictures(comment, note_id):
    """Download comment pictures and return (local_image_path, original_url) or (None, None)."""
    pictures = comment.get("pictures", [])
    if not pictures:
        return None, None

    # Use the first picture
    pic = pictures[0]
    url = pic.get("url_default", "") or pic.get("url_pre", "")
    if not url:
        return None, None

    comment_id = comment.get("id", note_id)
    filename = f"{comment_id}.jpg"
    local_path = IMG_DIR / filename
    rel_path = f"comments/images/xiaohongshu/comments/{filename}"

    if download_image(url, local_path):
        return rel_path, url
    return None, None


def import_xiaohongshu_data(json_path, update_likes_flag=True):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    repo = CommentRepository()
    svc = CommentService()
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    notes = data.get("notes", [])
    total_imported = 0
    total_updated = 0
    total_sub_imported = 0
    total_skipped = 0
    total_pics = 0

    for note in notes:
        note_id = note["note_id"]
        note_title = note.get("title", "")
        author_name = note.get("author", "")
        user_id = note.get("user_id", "")
        url = note.get("url", "")

        insert_note_video(note)

        # Collect all comments (top-level + sub)
        all_comments = []
        for c in note.get("comments", []):
            all_comments.append((c, False))
            for sc in c.get("sub_comments", []):
                all_comments.append((sc, True))

        for c, is_sub in all_comments:
            comment_id = c.get("id", "")
            content = c.get("content", "")
            cmt_author = c.get("author", "")
            likes = int(c.get("like_count", 0))
            created_at = c.get("create_time", "")

            if is_sub:
                full_content = f"[笔记: {note_title}][回复]\n{content}" if note_title else f"[回复] {content}"
            else:
                full_content = f"[笔记: {note_title}]\n{content}" if note_title else content

            # Dedup
            existing = find_by_platform_comment_id("xiaohongshu", comment_id) if comment_id else None
            if existing:
                if update_likes_flag and likes > (existing["likes"] or 0):
                    update_likes(existing["id"], likes)
                    total_updated += 1
                else:
                    total_skipped += 1
                continue

            # Download comment pictures if any
            local_img, original_url = process_comment_pictures(c, note_id)
            if local_img:
                total_pics += 1

            comment_data = {
                "platform": "xiaohongshu",
                "comment_id": comment_id,
                "author_name": cmt_author,
                "content": full_content,
                "likes": likes,
                "replies": int(c.get("sub_comment_count", 0)),
                "source_url": url,
                "local_image_path": local_img,
                "original_url": original_url,
                "video_bvid": note_id,
                "video_title": note_title,
                "up_name": author_name,
                "up_uid": user_id,
                "created_at": created_at,
            }
            repo.insert(comment_data)
            if is_sub:
                total_sub_imported += 1
            else:
                total_imported += 1

        note_total = total_imported + total_sub_imported
        print(f"  Note '{note_title[:30]}': total_imported={note_total}, pics={total_pics}")

    return total_imported, total_sub_imported, total_updated, total_skipped, total_pics


def analyze_new_comments():
    """Run sentiment analysis on unlocked xiaohongshu comments."""
    from backend.database import get_db
    conn = get_db()
    new_count = conn.execute(
        "SELECT COUNT(*) FROM comments WHERE platform = 'xiaohongshu' "
        "AND sentiment IS NULL AND sentiment_fix IS NULL"
    ).fetchone()[0]
    conn.close()

    if new_count == 0:
        print("  Sentiment: all comments already analyzed, skipping")
        return {"analyzed": 0, "stats": None}

    print(f"  Sentiment: analyzing {new_count} new comments...")
    svc = CommentService()
    return svc.analyze_sentiment(filters={"platform": "xiaohongshu"})


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import xiaohongshu comments to DB")
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD, auto-finds file")
    parser.add_argument("--file", default=None, help="Specific JSON file path")
    args = parser.parse_args()

    if args.file:
        json_path = Path(args.file)
    elif args.date:
        json_path = project_root / "comments" / f"xiaohongshu_{args.date}.json"
    else:
        print("Specify --date or --file")
        sys.exit(1)

    if not json_path.exists():
        print(f"File not found: {json_path}")
        sys.exit(1)

    print(f"Importing from {json_path}")
    imported, sub_imported, updated, skipped, pics = import_xiaohongshu_data(json_path)

    print(f"\n{'='*50}")
    print(f"Import complete:")
    print(f"  Top-level comments: {imported}")
    print(f"  Sub-comments: {sub_imported}")
    print(f"  Likes updated: {updated}")
    print(f"  Skipped (dupes): {skipped}")
    print(f"  Comment pictures: {pics}")
    print(f"  Total new: {imported + sub_imported}")
    print(f"{'='*50}")

    if imported + sub_imported > 0:
        print(f"\n--- Step 4: Sentiment Analysis ---")
        sa_result = analyze_new_comments()
        if sa_result and sa_result.get("analyzed"):
            s = sa_result.get("stats", {})
            print(f"  Analyzed: {sa_result['analyzed']} comments")
            if s:
                print(f"  Sentiment dist: {s.get('counts', {})}")

    repo = CommentRepository()
    stats = repo.stats(filters={"platform": "xiaohongshu"})
    total = stats.get("auto_count", 0) + stats.get("locked_count", 0)
    print(f"\nXiaohongshu DB: {total} comments, sentiment: {stats.get('auto', {})}")


if __name__ == "__main__":
    main()
