#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移本地图片路径：从旧格式 → Docker 兼容的相对路径格式。

Before: comments/images/bilibili/BVxxx/file.jpg  (相对项目根)
After:  images/bilibili/BVxxx/file.jpg            (相对 UPLOAD_DIR)

用法:
  1) 预览（不修改）：python jobs/scripts/migrate_images.py --dry-run
  2) 执行迁移：   python jobs/scripts/migrate_images.py
  3) 迁移后清理： python jobs/scripts/migrate_images.py --cleanup
"""

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent.parent

# Source: legacy images under comments/images/
SRC_IMAGES_DIR = ROOT / "comments" / "images"

# Target: new data/uploads/ directory structure
DST_UPLOADS_DIR = ROOT / "data" / "uploads"

# DB path
DB_PATH = ROOT / "db" / "comments.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def migrate_images(dry_run=False):
    """Copy images to data/uploads/ and update DB paths."""
    conn = get_db()
    
    rows = conn.execute(
        "SELECT id, local_image_path FROM comments "
        "WHERE local_image_path IS NOT NULL AND local_image_path != ''"
    ).fetchall()

    stats = {"total": len(rows), "migrated": 0, "skipped": 0, "missing": 0, "errors": []}

    for row in rows:
        old_path = row["local_image_path"]
        comment_id = row["id"]

        # Only migrate paths that start with "comments/images/"
        if not old_path.startswith("comments/images/"):
            stats["skipped"] += 1
            continue

        # New relative path: strip "comments/" prefix
        new_rel_path = old_path[len("comments/"):]  # e.g. "images/bilibili/BVxxx/file.jpg"

        # Source file on disk
        src_file = ROOT / old_path
        dst_file = DST_UPLOADS_DIR / new_rel_path

        if not src_file.exists():
            print(f"  [MISSING] id={comment_id}: {old_path}")
            stats["missing"] += 1
            # Still update DB to new relative path
            stats["errors"].append(f"id={comment_id}: source file missing, path updated anyway")
        else:
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            stats["migrated"] += 1

        # Update DB
        if not dry_run:
            conn.execute(
                "UPDATE comments SET local_image_path = ? WHERE id = ?",
                (new_rel_path, comment_id),
            )

    if not dry_run:
        conn.commit()
    
    conn.close()
    return stats


def cleanup_legacy_images(dry_run=False):
    """Remove legacy images that have been migrated. Use with caution!"""
    conn = get_db()
    
    # Find all legacy-style paths still in DB
    legacy = conn.execute(
        "SELECT COUNT(*) as cnt FROM comments "
        "WHERE local_image_path LIKE 'comments/images/%'"
    ).fetchone()
    
    if legacy["cnt"] > 0:
        print(f"WARNING: {legacy['cnt']} records still reference legacy paths. "
              "Run migration first.")
        conn.close()
        return

    conn.close()
    
    # Check if legacy dir exists
    if not SRC_IMAGES_DIR.exists():
        print("Legacy images directory not found, nothing to clean up.")
        return

    # Count files in legacy dir
    legacy_files = list(SRC_IMAGES_DIR.rglob("*"))
    file_count = len([f for f in legacy_files if f.is_file()])
    dir_size = sum(f.stat().st_size for f in legacy_files if f.is_file())
    
    print(f"Legacy images directory: {file_count} files, {dir_size / 1024 / 1024:.1f} MB")
    
    if dry_run:
        print("[DRY RUN] Would remove: " + str(SRC_IMAGES_DIR))
    else:
        shutil.rmtree(SRC_IMAGES_DIR)
        print(f"Removed: {SRC_IMAGES_DIR}")


def print_report(stats, dry_run):
    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}Migration Report:")
    print(f"  Total records:     {stats['total']}")
    print(f"  Migrated:          {stats['migrated']}")
    print(f"  Skipped (no match):{stats['skipped']}")
    print(f"  Missing files:     {stats['missing']}")
    if stats["errors"]:
        print(f"  Issues:")
        for e in stats["errors"]:
            print(f"    - {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate image paths for Docker deployment")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--cleanup", action="store_true", 
                        help="Remove legacy comments/images/ after migration")
    args = parser.parse_args()

    if args.cleanup:
        cleanup_legacy_images(dry_run=args.dry_run)
    else:
        stats = migrate_images(dry_run=args.dry_run)
        print_report(stats, args.dry_run)
