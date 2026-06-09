#!/usr/bin/env python3
"""
导入收集的评论到数据库
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
from backend.services.comment_service import CommentService


def parse_time(time_str):
    """尝试解析各种时间格式"""
    if not time_str:
        return None

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
            return datetime.strptime(time_str.strip(), fmt)
        except ValueError:
            continue

    return None


def import_bilibili_comments(json_file, repo, service, update_likes=False):
    """导入 B站 评论"""
    print(f"\n导入 B站 评论: {json_file.name}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    comments = data.get('comments', [])
    imported = 0
    skipped = 0
    updated = 0

    for comment in comments:
        try:
            # 提取基本信息
            content = comment.get('text', '')
            author_name = comment.get('author', '')
            like_count = comment.get('likes', 0)
            up_master = comment.get('_up', {}).get('name', '')
            video_title = comment.get('video_title', '')
            time_str = comment.get('time', '')

            # 构建完整内容
            full_content = content
            if video_title:
                full_content = f"[视频: {video_title}]\n{content}"

            # 检查是否已存在 (通过内容和作者判断)
            existing = None
            # 这里简化处理，实际可能需要更复杂的去重逻辑
            # 暂时直接插入

            created_at = parse_time(time_str)

            # 构建评论数据
            comment_data = {
                'platform': 'bilibili',
                'content': full_content,
                'author_name': author_name,
                'up_master': up_master,
                'like_count': like_count,
            }

            if created_at:
                comment_data['created_at'] = created_at

            # 插入数据库
            new_comment = repo.insert(comment_data)
            imported += 1

        except Exception as e:
            print(f"  处理评论时出错: {e}")
            skipped += 1

    print(f"  B站 完成: 导入 {imported}, 跳过 {skipped}, 更新 {updated}")
    return imported, skipped, updated


def import_xiaohongshu_comments(json_file, repo, service, update_likes=False):
    """导入小红书评论"""
    print(f"\n导入小红书评论: {json_file.name}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    comments = data.get('comments', [])
    imported = 0
    skipped = 0
    updated = 0

    for comment in comments:
        try:
            # 提取基本信息
            content = comment.get('text', '')
            author_name = comment.get('author', '')
            like_count = comment.get('likes', 0)
            up_master = comment.get('_author', {}).get('name', '')
            note_title = comment.get('note_title', '')
            time_str = comment.get('time', '')
            is_reply = comment.get('is_reply', False)

            # 构建完整内容
            full_content = content
            prefix_parts = []
            if note_title:
                prefix_parts.append(f"笔记: {note_title}")
            if is_reply:
                prefix_parts.append("回复")

            if prefix_parts:
                full_content = f"[{', '.join(prefix_parts)}]\n{content}"

            created_at = parse_time(time_str)

            # 构建评论数据
            comment_data = {
                'platform': 'xiaohongshu',
                'content': full_content,
                'author_name': author_name,
                'up_master': up_master,
                'like_count': like_count,
            }

            if created_at:
                comment_data['created_at'] = created_at

            # 插入数据库
            new_comment = repo.insert(comment_data)
            imported += 1

        except Exception as e:
            print(f"  处理评论时出错: {e}")
            skipped += 1

    print(f"  小红书完成: 导入 {imported}, 跳过 {skipped}, 更新 {updated}")
    return imported, skipped, updated


def import_xueqiu_comments(json_file, repo, service, update_likes=False):
    """导入雪球评论"""
    print(f"\n导入雪球评论: {json_file.name}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    comments = data.get('comments', [])
    imported = 0
    skipped = 0
    updated = 0

    for comment in comments:
        try:
            # 提取基本信息
            content = comment.get('text', '')
            author_name = comment.get('author', '')
            like_count = comment.get('likes', 0)
            symbol = comment.get('symbol', '')
            time_str = comment.get('created_at', '')

            # 构建完整内容
            full_content = content
            if symbol:
                full_content = f"[股票: {symbol}]\n{content}"

            created_at = parse_time(time_str)

            # 构建评论数据
            comment_data = {
                'platform': 'xueqiu',
                'content': full_content,
                'author_name': author_name,
                'up_master': symbol,  # 用股票代码作为 up_master
                'like_count': like_count,
            }

            if created_at:
                comment_data['created_at'] = created_at

            # 插入数据库
            new_comment = repo.insert(comment_data)
            imported += 1

        except Exception as e:
            print(f"  处理评论时出错: {e}")
            skipped += 1

    print(f"  雪球完成: 导入 {imported}, 跳过 {skipped}, 更新 {updated}")
    return imported, skipped, updated


def main():
    parser = argparse.ArgumentParser(description='导入评论数据到数据库')
    parser.add_argument('files', nargs='*', help='要导入的 JSON 文件')
    parser.add_argument('--date', help='指定日期 (YYYY-MM-DD), 自动查找当天文件')
    parser.add_argument('--dir', default='comments', help='评论文件目录 (默认: comments)')
    parser.add_argument('--update-likes', action='store_true',
                        help='更新现有评论的点赞数 (默认: 跳过重复)')
    args = parser.parse_args()

    # 初始化 repository 和 service
    repo = CommentRepository()
    service = CommentService()

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
    else:
        print("请指定文件或使用 --date 参数")
        parser.print_help()
        return

    if not files_to_process:
        print("没有找到要处理的文件")
        return

    # 处理每个文件
    total_imported = 0
    total_skipped = 0
    total_updated = 0

    for json_file in files_to_process:
        filename = json_file.name

        if filename.startswith('bilibili_'):
            imported, skipped, updated = import_bilibili_comments(
                json_file, repo, service, args.update_likes
            )
        elif filename.startswith('xiaohongshu_'):
            imported, skipped, updated = import_xiaohongshu_comments(
                json_file, repo, service, args.update_likes
            )
        elif filename.startswith('xueqiu_'):
            imported, skipped, updated = import_xueqiu_comments(
                json_file, repo, service, args.update_likes
            )
        else:
            print(f"\n跳过未知文件: {filename}")
            continue

        total_imported += imported
        total_skipped += skipped
        total_updated += updated

    # 总结
    print("\n" + "=" * 50)
    print("导入完成总结:")
    print(f"  导入: {total_imported}")
    print(f"  跳过: {total_skipped}")
    print(f"  更新: {total_updated}")
    print("=" * 50)

    # 显示当前数据库统计
    print("\n当前数据库统计:")
    stats = repo.stats()
    print(f"  总评论数: {stats.get('auto_count', 0) + stats.get('locked_count', 0)}")
    print(f"  自动分析: {stats.get('auto_count', 0)}")
    print(f"  已锁定: {stats.get('locked_count', 0)}")


if __name__ == '__main__':
    main()
