#!/usr/bin/env python3
"""
收集李大霄今天发布的视频评论
"""

import json
import subprocess
import sys
import time
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


def get_comments(bvid, video_title):
    """获取单个视频的评论"""
    print(f"\n获取视频评论: {video_title} ({bvid})")
    try:
        result = subprocess.run(
            ['opencli', 'bilibili', 'comments', bvid, '--limit', '50', '-f', 'json'],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            comments = json.loads(result.stdout)
            print(f"  成功获取 {len(comments)} 条评论")
            return comments
        else:
            print(f"  失败: {result.stderr}")
    except Exception as e:
        print(f"  异常: {e}")
    return []


def import_comment(comment, video_title, video_bvid):
    """导入单条评论到数据库"""
    try:
        content = comment.get('text', '')
        if not content:
            return None

        author_name = comment.get('author', '')
        likes = comment.get('likes', 0)
        time_str = comment.get('time', '')
        created_at = parse_time(time_str)

        # 构建额外内容
        extra_parts = []
        if video_title:
            extra_parts.append(f"视频: {video_title}")

        full_content = content
        if extra_parts:
            full_content = f"[{', '.join(extra_parts)}]\n{content}"

        # 构建数据
        comment_data = {
            'platform': 'bilibili',
            'content': full_content,
            'author_name': author_name,
            'likes': likes,
            'up_name': '李大霄',
            'up_uid': '2137589551',
            'video_title': video_title,
            'video_bvid': video_bvid,
        }

        if created_at:
            comment_data['created_at'] = created_at

        return comment_data

    except Exception as e:
        print(f"  处理评论时出错: {e}")
        return None


def main():
    print("=" * 60)
    print("收集李大霄今天发布的视频评论")
    print("=" * 60)

    # 李大霄今天发布的视频
    videos = [
        {
            "title": "调整时更应重视防御",
            "bvid": "BV1MCEM6DEEW",
            "date": "2026-06-08"
        },
        {
            "title": "稳定力量出手了",
            "bvid": "BV1mZEN6CECD",
            "date": "2026-06-08"
        },
        {
            "title": "韩国启动救市",
            "bvid": "BV1LpEK64Ezf",
            "date": "2026-06-08"
        }
    ]

    repo = CommentRepository()
    all_comments_data = []
    total_imported = 0

    for video in videos:
        # 获取评论
        comments = get_comments(video['bvid'], video['title'])

        # 保存评论数据
        for comment in comments:
            comment['_video'] = video
            comment['_up'] = {'uid': '2137589551', 'name': '李大霄'}
            all_comments_data.append(comment)

        # 导入到数据库
        for comment in comments:
            comment_data = import_comment(comment, video['title'], video['bvid'])
            if comment_data:
                repo.insert(comment_data)
                total_imported += 1

        # 请求间隔
        time.sleep(2)

    # 保存到JSON文件
    today = datetime.now().strftime('%Y-%m-%d')
    output_file = project_root / 'comments' / f'lidaxiao_{today}.json'

    output_data = {
        "target_date": today,
        "platform": "B站",
        "up": {"uid": "2137589551", "name": "李大霄"},
        "videos": videos,
        "comments": all_comments_data
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"完成!")
    print(f"  收集到 {len(all_comments_data)} 条评论")
    print(f"  导入到数据库 {total_imported} 条评论")
    print(f"  保存到: {output_file}")
    print("=" * 60)

    # 验证导入的数据
    print("\n验证导入的数据:")
    import sqlite3
    conn = sqlite3.connect(project_root / 'db/comments.db')
    cursor = conn.execute('''
        SELECT id, created_at, video_title
        FROM comments
        WHERE up_name = '李大霄'
        ORDER BY id DESC
        LIMIT 10
    ''')
    for row in cursor:
        print(f"  {row}")
    conn.close()


if __name__ == '__main__':
    main()
