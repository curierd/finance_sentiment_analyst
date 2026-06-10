#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
备份 SQLite 数据库和图片。

用法:
  - 备份全部:    python jobs/scripts/backup.py
  - 仅备份 DB:   python jobs/scripts/backup.py --db-only
  - 仅备份图片:  python jobs/scripts/backup.py --images-only
  - 指定输出目录: python jobs/scripts/backup.py --output /mnt/backups
"""

import argparse
import os
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "db" / "comments.db"
UPLOADS_DIR = ROOT / "data" / "uploads"
BACKUP_DIR = ROOT / "data" / "backup"


def backup_database(output_dir: Path):
    """Use SQLite .backup API for safe, consistent backup."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = output_dir / f"comments_{timestamp}.db"

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        return None

    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(backup_path))
    src.backup(dst)
    dst.close()
    src.close()

    size_mb = backup_path.stat().st_size / 1024 / 1024
    print(f"  DB backed up → {backup_path} ({size_mb:.1f} MB)")
    return backup_path


def backup_images(output_dir: Path):
    """Tar-gzip the uploads directory."""
    if not UPLOADS_DIR.exists():
        print(f"WARNING: Uploads dir not found at {UPLOADS_DIR}, skipping.")
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    archive_path = output_dir / f"uploads_{timestamp}.tar.gz"

    with tarfile.open(archive_path, "w:gz") as tar:
        # Archive relative to parent so paths inside are "uploads/..."
        tar.add(str(UPLOADS_DIR), arcname=UPLOADS_DIR.name)

    size_mb = archive_path.stat().st_size / 1024 / 1024
    print(f"  Images backed up → {archive_path} ({size_mb:.1f} MB)")
    return archive_path


def rotate_backups(output_dir: Path, keep: int = 30):
    """Delete backups older than `keep` days."""
    cutoff = datetime.now().timestamp() - keep * 86400
    removed = 0
    for f in output_dir.glob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    if removed:
        print(f"  Rotated: removed {removed} old backup(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup SQLite DB and images")
    parser.add_argument("--db-only", action="store_true", help="Only backup database")
    parser.add_argument("--images-only", action="store_true", help="Only backup images")
    parser.add_argument("--output", type=str, help="Override output directory")
    parser.add_argument("--keep", type=int, default=30, 
                        help="Days to keep backups (default: 30)")
    args = parser.parse_args()

    output = Path(args.output) if args.output else BACKUP_DIR
    output.mkdir(parents=True, exist_ok=True)

    print(f"Backup started at {datetime.now().isoformat()}")
    print(f"Output directory: {output}")

    if not args.images_only:
        backup_database(output)

    if not args.db_only:
        backup_images(output)

    rotate_backups(output, keep=args.keep)
    print("Backup complete.")
