#!/usr/bin/env python3
"""
修复 B站 评论时间问题
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.repositories.comment_repository import CommentRepository


def parse_time(time_str):
    """尝试解析各种时间格式"""
    if not time_str:
        return None

    # 处理 ISO 格式时间
    if time_str.endswith('Z'):
        try:
            dt = datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%S.%fZ')
            return dt.isoformat()
        except ValueError:
            try:
                dt = datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%SZ')
                return dt.isoformat()
            except ValueError:
                pass

    # 其他常见格式
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y/%m/%d',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(time_str.strip(), fmt)
            return dt.isoformat()
        except ValueError:
            continue

    return None


def fix_bilibili_comments(json_file):
    """修复 B站 评论"""
    print(f"读取文件: {json_file}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    comments = data.get('comments', [])
    print(f"找到 {len(comments)} 条评论")

    repo = CommentRepository()

    # 删除之前导入的 B站 评论
    print("\n删除之前导入的 B站 评论...")
    import sqlite3
    conn = sqlite3.connect(project_root / 'db/comments.db')
    cursor = conn.execute('DELETE FROM comments WHERE platform = "bilibili"')
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"删除了 {deleted} 条记录")

    # 重新导入
    print("\n重新导入 B站 评论...")
    imported = 0
    skipped = 0

    for comment in comments:
        try:
            content = comment.get('text', '') or comment.get('content', '')
            if not content:
                skipped += 1
                continue

            # 提取信息
            author_name = comment.get('author', '') or comment.get('author_name', '')
            likes = comment.get('likes', 0) or comment.get('like_count', 0)
            up_name = comment.get('up_master', '') or comment.get('up_name', '')
            up_uid = ''

            # 从 _up 字段提取
            if not up_name and '_up' in comment:
                up_name = comment['_up'].get('name', '')
                up_uid = comment['_up'].get('uid', '')

            # 提取视频信息
            video_title = comment.get('video_title', '')
            video_bvid = comment.get('video_bvid', '') or comment.get('_video_bvid', '')
            if not video_bvid and '_video' in comment:
                video_bvid = comment['_video'].get('url', '').split('/video/')[-1].split('?')[0] if '/video/' in comment['_video'].get('url', '') else ''

            # 从视频信息构建额外内容
            extra_parts = []
            if video_title:
                extra_parts.append(f"视频: {video_title}")

            full_content = content
            if extra_parts:
                full_content = f"[{', '.join(extra_parts)}]\n{content}"

            # 解析时间
            time_str = comment.get('time', '') or comment.get('created_at', '')
            created_at = parse_time(time_str)

            # 构建数据
            comment_data = {
                'platform': 'bilibili',
                'content': full_content,
                'author_name': author_name,
                'likes': likes,
                'up_name': up_name,
                'up_uid': up_uid,
                'video_title': video_title,
                'video_bvid': video_bvid,
            }

            if created_at:
                comment_data['created_at'] = created_at

            # 插入
            repo.insert(comment_data)
            imported += 1

        except Exception as e:
            print(f"  错误: {e}")
            skipped += 1

    print(f"\n完成! 导入: {imported}, 跳过: {skipped}")

    # 验证
    print("\n验证数据...")
    import sqlite3
    conn = sqlite3.connect(project_root / 'db/comments.db')
    cursor = conn.execute('SELECT id, created_at FROM comments WHERE platform = "bilibili" LIMIT 10')
    print("前10条记录:")
    for row in cursor:
        print(row)
    conn.close()


if __name__ == '__main__':
    json_file = project_root / 'comments' / 'bilibili_2026-06-08.json'
    fix_bilibili_comments(json_file)
