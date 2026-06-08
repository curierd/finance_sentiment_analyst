#!/usr/bin/env python3
"""
Import collected comments into the database.
Usage: python import_comments.py [date]
Default date: today (YYYY-MM-DD)
"""

import sys
import json
import datetime
from pathlib import Path

# Add parent directory to path for backend imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import get_db as get_db_connection, set_db_path


def parse_bilibili_time(time_str):
    """Parse Bilibili time format: '2025-09-14 22:29' -> ISO format with seconds"""
    if not time_str:
        return None
    try:
        # Format: '2025-09-14 22:29' -> add ':00' for seconds
        if len(time_str.split(' ')) == 2 and len(time_str.split(':')) == 2:
            return f"{time_str}:00"
        return time_str
    except Exception:
        return time_str

def import_bilibili(db_path, json_path):
    """Import Bilibili comments from JSON file"""
    print(f"Importing Bilibili data from {json_path}...")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Import UP masters
    for up in data.get('ups', []):
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO up_masters (platform, uid, name, source_file)
                VALUES (?, ?, ?, ?)
            ''', ('bilibili', up['uid'], up['name'], 'data/bilibili-finance-up.md'))
        except Exception as e:
            print(f"Warning: Failed to import UP {up['name']}: {e}")

    # Import blacklisted UP masters
    for up in data.get('blacklist', []):
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO up_masters (platform, uid, name, blacklisted, source_file)
                VALUES (?, ?, ?, 1, ?)
            ''', ('bilibili', up['uid'], up['name'], 'data/bilibili-finance-up.md'))
        except Exception as e:
            print(f"Warning: Failed to import blacklisted UP {up['name']}: {e}")

    # Import videos
    for video in data.get('videos', []):
        try:
            bvid = video.get('url', '').split('/video/')[-1] if video.get('url') else None
            if not bvid:
                continue
            stats = json.dumps({
                'plays': video.get('plays', 0),
                'likes': video.get('likes', 0)
            }, ensure_ascii=False)
            cursor.execute('''
                INSERT OR IGNORE INTO videos (platform, video_id, title, up_name, up_uid, stats, pubdate, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('bilibili', bvid, video.get('title', ''), video.get('_up', {}).get('name', ''),
                  video.get('_up', {}).get('uid', ''), stats, video.get('date', ''), video.get('url', '')))
        except Exception as e:
            print(f"Warning: Failed to import video: {e}")

    # Import comments
    imported = 0
    for comment in data.get('comments', []):
        try:
            raw_data = json.dumps(comment, ensure_ascii=False)
            created_at = parse_bilibili_time(comment.get('time', ''))
            cursor.execute('''
                INSERT INTO comments (
                    platform, author_name, content, likes, replies,
                    source_url, video_bvid, video_title, up_name, up_uid,
                    created_at, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'bilibili',
                comment.get('author', ''),
                comment.get('text', ''),
                comment.get('likes', 0),
                comment.get('replies', 0),
                comment.get('_video', {}).get('url', ''),
                comment.get('_video_bvid', ''),
                comment.get('_video', {}).get('title', ''),
                comment.get('_up', {}).get('name', ''),
                comment.get('_up', {}).get('uid', ''),
                created_at,
                raw_data
            ))
            imported += 1
        except Exception as e:
            print(f"Warning: Failed to import comment: {e}")

    conn.commit()
    conn.close()
    print(f"Bilibili: Imported {imported} comments")
    return imported


def import_xueqiu(db_path, json_path):
    """Import Xueqiu comments from JSON file"""
    print(f"Importing Xueqiu data from {json_path}...")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    conn = get_db_connection()
    cursor = conn.cursor()

    imported = 0
    for section, symbols in data.get('comments', {}).items():
        for symbol, comments in symbols.items():
            for comment in comments:
                try:
                    raw_data = json.dumps(comment, ensure_ascii=False)
                    cursor.execute('''
                        INSERT INTO comments (
                            platform, author_name, content, likes, replies, retweets,
                            source_url, symbol, created_at, raw_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        'xueqiu',
                        comment.get('author', ''),
                        comment.get('text', ''),
                        comment.get('likes', 0),
                        comment.get('replies', 0),
                        comment.get('retweets', 0),
                        comment.get('url', ''),
                        symbol,
                        comment.get('created_at', ''),
                        raw_data
                    ))
                    imported += 1
                except Exception as e:
                    print(f"Warning: Failed to import comment: {e}")

    conn.commit()
    conn.close()
    print(f"Xueqiu: Imported {imported} comments")
    return imported


def main():
    # Get date
    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        date = datetime.date.today().isoformat()

    # Paths
    base_dir = Path(__file__).parent.parent.parent
    comments_dir = base_dir / 'comments'
    db_path = base_dir / 'db' / 'comments.db'

    set_db_path(str(db_path))

    total = 0

    # Import Bilibili
    bilibili_path = comments_dir / f'bilibili_{date}.json'
    if bilibili_path.exists():
        total += import_bilibili(str(db_path), str(bilibili_path))
    else:
        print(f"Bilibili file not found: {bilibili_path}")

    # Import Xueqiu
    xueqiu_path = comments_dir / f'xueqiu_{date}.json'
    if xueqiu_path.exists():
        total += import_xueqiu(str(db_path), str(xueqiu_path))
    else:
        print(f"Xueqiu file not found: {xueqiu_path}")

    print(f"\nTotal: Imported {total} comments")


if __name__ == '__main__':
    main()
