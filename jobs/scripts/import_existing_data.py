#!/usr/bin/env python3
"""
导入已收集的评论数据到数据库
"""

import argparse
import json
import os
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


def import_bilibili_data(json_file, repo):
    """导入 B站 数据"""
    print(f"\n导入 B站 数据: {json_file.name}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    comments = data.get('comments', [])
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

    print(f"  B站 完成: 导入 {imported}, 跳过 {skipped}")
    return imported, skipped


def import_xiaohongshu_data(json_file, repo):
    """导入小红书数据"""
    print(f"\n导入小红书数据: {json_file.name}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    comments = data.get('comments', [])
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

            # 从 _author 字段提取
            if not up_name and '_author' in comment:
                up_name = comment['_author'].get('name', '')
                up_uid = comment['_author'].get('uid', '')

            # 提取笔记信息
            note_title = comment.get('note_title', '')
            source_url = comment.get('note_url', '')

            # 构建额外内容
            extra_parts = []
            if note_title:
                extra_parts.append(f"笔记: {note_title}")
            if comment.get('is_reply'):
                extra_parts.append("回复")

            full_content = content
            if extra_parts:
                full_content = f"[{', '.join(extra_parts)}]\n{content}"

            # 解析时间
            time_str = comment.get('time', '') or comment.get('created_at', '')
            created_at = parse_time(time_str)

            # 构建数据
            comment_data = {
                'platform': 'xiaohongshu',
                'content': full_content,
                'author_name': author_name,
                'likes': likes,
                'up_name': up_name,
                'up_uid': up_uid,
                'video_title': note_title,  # 复用 video_title 字段存笔记标题
                'source_url': source_url,
            }

            if created_at:
                comment_data['created_at'] = created_at

            # 插入
            repo.insert(comment_data)
            imported += 1

        except Exception as e:
            print(f"  错误: {e}")
            skipped += 1

    print(f"  小红书完成: 导入 {imported}, 跳过 {skipped}")
    return imported, skipped


def import_xueqiu_data(json_file, repo):
    """导入雪球数据"""
    print(f"\n导入雪球数据: {json_file.name}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 处理不同的数据结构
    comments_list = []

    # 结构1: 直接 comments 数组
    if isinstance(data.get('comments'), list):
        comments_list = data['comments']
    # 结构2: comments 是对象，包含 sections
    elif isinstance(data.get('comments'), dict):
        comments_dict = data['comments']
        for section_name, section_data in comments_dict.items():
            if isinstance(section_data, dict):
                for symbol, symbol_comments in section_data.items():
                    if isinstance(symbol_comments, list):
                        for c in symbol_comments:
                            c['_symbol'] = symbol
                            c['_section'] = section_name
                            comments_list.append(c)
            elif isinstance(section_data, list):
                for c in section_data:
                    c['_section'] = section_name
                    comments_list.append(c)

    imported = 0
    skipped = 0

    for comment in comments_list:
        try:
            content = comment.get('text', '') or comment.get('content', '')
            if not content:
                skipped += 1
                continue

            # 提取信息
            author_name = comment.get('author', '') or comment.get('author_name', '')
            likes = comment.get('likes', 0) or comment.get('like_count', 0)
            replies = comment.get('replies', 0)
            retweets = comment.get('retweets', 0)
            symbol = comment.get('symbol', '') or comment.get('_symbol', '')
            source_url = comment.get('url', '')

            # 构建额外内容
            extra_parts = []
            if symbol:
                extra_parts.append(f"股票: {symbol}")
            if comment.get('_section'):
                extra_parts.append(f"板块: {comment['_section']}")

            full_content = content
            if extra_parts:
                full_content = f"[{', '.join(extra_parts)}]\n{content}"

            # 解析时间
            time_str = comment.get('created_at', '') or comment.get('time', '')
            created_at = parse_time(time_str)

            # 构建数据
            comment_data = {
                'platform': 'xueqiu',
                'content': full_content,
                'author_name': author_name,
                'likes': likes,
                'replies': replies,
                'retweets': retweets,
                'symbol': symbol,
                'source_url': source_url,
            }

            if created_at:
                comment_data['created_at'] = created_at

            # 插入
            repo.insert(comment_data)
            imported += 1

        except Exception as e:
            print(f"  错误: {e}")
            skipped += 1

    print(f"  雪球完成: 导入 {imported}, 跳过 {skipped}")
    return imported, skipped


def main():
    parser = argparse.ArgumentParser(description='导入评论数据到数据库')
    parser.add_argument('files', nargs='*', help='要导入的 JSON 文件')
    parser.add_argument('--date', help='指定日期 (YYYY-MM-DD), 自动查找当天文件')
    parser.add_argument('--dir', default='comments', help='评论文件目录 (默认: comments)')
    parser.add_argument('--all', action='store_true', help='导入 comments 目录下所有文件')
    args = parser.parse_args()

    # 初始化 repository
    repo = CommentRepository()

    # 确定要处理的文件
    files_to_process = []

    if args.files:
        # 使用指定的文件
        for f in args.files:
            file_path = Path(f)
            if file_path.exists():
                files_to_process.append(file_path)
            else:
                print(f"文件不存在: {f}")
    elif args.date:
        # 查找指定日期的文件
        data_dir = project_root / args.dir
        for platform in ['bilibili', 'xiaohongshu', 'xueqiu']:
            file_path = data_dir / f"{platform}_{args.date}.json"
            if file_path.exists():
                files_to_process.append(file_path)
            else:
                print(f"文件不存在: {file_path}")
    elif args.all:
        # 导入所有文件
        data_dir = project_root / args.dir
        if data_dir.exists():
            for json_file in data_dir.glob('*.json'):
                files_to_process.append(json_file)
            # 按名称排序
            files_to_process.sort()
    else:
        print("请指定文件、使用 --date 参数或 --all 参数")
        parser.print_help()
        return

    if not files_to_process:
        print("没有找到要处理的文件")
        return

    # 显示要处理的文件
    print(f"\n准备处理 {len(files_to_process)} 个文件:")
    for f in files_to_process:
        print(f"  - {f.name}")

    # 处理每个文件
    total_imported = 0
    total_skipped = 0

    for json_file in files_to_process:
        filename = json_file.name.lower()

        if 'bilibili' in filename:
            imported, skipped = import_bilibili_data(json_file, repo)
        elif 'xiaohongshu' in filename or 'xhs' in filename:
            imported, skipped = import_xiaohongshu_data(json_file, repo)
        elif 'xueqiu' in filename:
            imported, skipped = import_xueqiu_data(json_file, repo)
        else:
            print(f"\n跳过未知文件: {filename}")
            continue

        total_imported += imported
        total_skipped += skipped

    # 总结
    print("\n" + "=" * 50)
    print("导入完成总结:")
    print(f"  导入: {total_imported}")
    print(f"  跳过: {total_skipped}")
    print("=" * 50)

    # 显示当前数据库统计
    print("\n当前数据库统计:")
    stats = repo.stats()
    print(f"  总评论数: {stats.get('auto_count', 0) + stats.get('locked_count', 0)}")
    print(f"  自动分析: {stats.get('auto_count', 0)}")
    print(f"  已锁定: {stats.get('locked_count', 0)}")


if __name__ == '__main__':
    main()
