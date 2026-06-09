#!/usr/bin/env python3
"""
Re-fetch comments for 6/8 notes to extract the `pictures` field,
download comment-attached images locally, and update the DB via backend-api.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.comment_service import CommentService
from backend.database import get_db

INTERMEDIATE_DIR = project_root / "jobs" / "xiaohongshu_comments_collector" / "intermediate"
IMG_DIR = project_root / "comments" / "images" / "xiaohongshu" / "comments"

# 6/8 notes: note_id -> xsec_token
NOTES = {
    "6a264e1500000000220195f0": "ABbHxdgR6SIuxRM2s_GWWkTMeEPLBDQzkIFMCPhEWkzis%3D",
    "6a261d7c000000002202109d": "ABbHxdgR6SIuxRM2s_GWWkTN9U5xj5Kz-lQlq3XwJ5iBo%3D",
    "6a25fd31000000003502522d": "AB7rT7_vfg0QV4gZzUeZ8OydrGSzEzo-tyODfBPS__hRk%3D",
    "6a268afa0000000022014a8e": None,  # will extract from intermediate
    "6a262db40000000020038d66": None,
    "6a267e4d000000000702c46f": None,
}


def load_tokens():
    """Load xsec_tokens from intermediate/today_notes.json for the 6/8 notes."""
    # Check for the 6/8 intermediate file
    for name in ["today_notes_2026-06-08.json", "today_notes.json"]:
        p = INTERMEDIATE_DIR / name
        if p.exists():
            with open(p) as f:
                notes = json.load(f)
            for n in notes:
                nid = n.get("note_id", "")
                if nid in NOTES and NOTES[nid] is None:
                    NOTES[nid] = n.get("xsec_token", "")
            return
    print("Warning: could not find intermediate file for tokens")


def fetch_comments(note_id, xsec_token):
    """Fetch all comments with pictures via xhs CLI."""
    cmd = f'xhs comments {note_id} --xsec-token "{xsec_token}" --all --json'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)
    if not data.get("ok"):
        return None
    return data["data"].get("comments", [])


def walk_comments(comments):
    """Yield (comment_id, pictures_list) for all comments including sub-comments."""
    for c in comments:
        cid = c.get("id", "")
        pics = c.get("pictures", [])
        if cid:
            yield cid, pics
        for sc in c.get("sub_comments", []):
            scid = sc.get("id", "")
            spics = sc.get("pictures", [])
            if scid:
                yield scid, spics


def download_image(url, local_path):
    """Download image to local path."""
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


def main():
    load_tokens()
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    svc = CommentService()

    # Map: comment_id -> list of {url_default, local_path}
    comment_pictures = {}

    for note_id, token in NOTES.items():
        if not token:
            print(f"Skip {note_id}: no token")
            continue
        print(f"Fetching comments for {note_id}...")
        comments = fetch_comments(note_id, token)
        time.sleep(1.2)
        if not comments:
            print(f"  No comments returned")
            continue

        pic_count = 0
        for cid, pics in walk_comments(comments):
            if pics:
                comment_pictures[cid] = pics
                pic_count += 1
        print(f"  {len(list(walk_comments(comments)))} comments, {pic_count} with pictures")

    if not comment_pictures:
        print("No comment pictures found. Done.")
        return

    print(f"\nFound {len(comment_pictures)} comments with pictures")

    # Download pictures
    total_images = 0
    downloaded = 0
    # comment_id -> (local_path, original_url) for the FIRST picture
    comment_image_map = {}

    for cid, pics in comment_pictures.items():
        for i, pic in enumerate(pics):
            url = pic.get("url_default", "")
            if not url:
                url = pic.get("url_pre", "")
            if not url:
                continue
            total_images += 1
            # Use comment_id as filename
            suffix = f"_{i}" if i > 0 else ""
            filename = f"{cid}{suffix}.jpg"
            local_path = IMG_DIR / filename
            rel_path = f"comments/images/xiaohongshu/comments/{filename}"

            if download_image(url, local_path):
                downloaded += 1
                # Store the first picture for DB update
                if i == 0:
                    comment_image_map[cid] = (rel_path, url)
            else:
                print(f"  Failed to download: {filename}")

            time.sleep(0.3)

    print(f"Downloaded {downloaded}/{total_images} images")

    # Update DB: only update comments that have pictures
    # First, clear the wrong avatar images for these comments
    # Then set the correct comment picture
    conn = get_db()
    rows = conn.execute("""
        SELECT id, comment_id FROM comments
        WHERE platform = 'xiaohongshu'
          AND comment_id IS NOT NULL
    """).fetchall()
    conn.close()

    # Build comment_id -> db_id map
    cid_to_dbid = {r["comment_id"]: r["id"] for r in rows}

    updated = 0
    cleared = 0
    errors = 0

    # For 6/8 comments: if a comment has pictures -> set image
    # If a comment does NOT have pictures -> clear the wrong avatar image
    note_ids = list(NOTES.keys())
    conn = get_db()
    all_june8 = conn.execute(f"""
        SELECT id, comment_id FROM comments
        WHERE platform = 'xiaohongshu'
          AND video_bvid IN ({','.join('?' * len(note_ids))})
    """, note_ids).fetchall()
    conn.close()

    for r in all_june8:
        db_id = r["id"]
        cid = r["comment_id"]

        if cid in comment_image_map:
            local_path, original_url = comment_image_map[cid]
            try:
                svc.update_image(db_id, local_image_path=local_path, original_url=original_url)
                updated += 1
            except ValueError as e:
                print(f"  Error updating {db_id}: {e}")
                errors += 1
        else:
            # No picture — clear the previous wrong image
            try:
                svc.update_image(db_id, local_image_path=None, original_url=None)
                cleared += 1
            except ValueError:
                errors += 1

    print(f"\n{'='*50}")
    print(f"DB update complete:")
    print(f"  Comments with pictures set: {updated}")
    print(f"  Comments cleared (no picture): {cleared}")
    print(f"  Errors: {errors}")
    print(f"{'='*50}")

    # Verify
    conn = get_db()
    with_pic = conn.execute(f"""
        SELECT COUNT(*) FROM comments
        WHERE platform = 'xiaohongshu'
          AND video_bvid IN ({','.join('?' * len(note_ids))})
          AND local_image_path IS NOT NULL
    """, note_ids).fetchone()[0]
    without_pic = conn.execute(f"""
        SELECT COUNT(*) FROM comments
        WHERE platform = 'xiaohongshu'
          AND video_bvid IN ({','.join('?' * len(note_ids))})
          AND local_image_path IS NULL
    """, note_ids).fetchone()[0]
    conn.close()
    print(f"6/8 xiaohongshu comments: {with_pic} with image, {without_pic} without image")


if __name__ == "__main__":
    main()
