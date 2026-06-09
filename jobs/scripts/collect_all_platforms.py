#!/usr/bin/env python3
"""
收集三个平台（B站、小红书、雪球）的财经评论
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.repositories.comment_repository import CommentRepository


def load_up_list(file_path):
    """加载 UP 主列表"""
    ups = []
    blacklist = []
    current_list = ups

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if line.lower().startswith('blacklist') or line.lower().startswith('黑名单'):
                    current_list = blacklist
                    continue

                # 解析 UP 主信息
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2:
                    up_info = {
                        'uid': parts[0],
                        'name': parts[1]
                    }
                    if len(parts) > 2:
                        up_info['extra'] = parts[2:]
                    current_list.append(up_info)
    except FileNotFoundError:
        print(f"警告: 文件 {file_path} 未找到")

    return ups, blacklist


def load_sections_list(file_path):
    """加载板块股票列表"""
    symbols = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # 假设每行是股票代码
                symbols.append(line)
    except FileNotFoundError:
        print(f"警告: 文件 {file_path} 未找到")

    return symbols


def run_opencli_command(cmd_args, max_retries=3):
    """运行 opencli 命令，带重试机制"""
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                return json.loads(result.stdout) if result.stdout else []
            else:
                print(f"命令失败 (尝试 {attempt + 1}/{max_retries}): {result.stderr}")
        except Exception as e:
            print(f"命令异常 (尝试 {attempt + 1}/{max_retries}): {e}")

        if attempt < max_retries - 1:
            time.sleep(2)  # 重试前等待

    return None


def collect_bilibili(target_date, ups, blacklist, output_dir, intermediate_dir):
    """收集 B站 评论"""
    print("\n===== 开始收集 B站 评论 =====")

    platform = 'bilibili'
    data = {
        'target_date': target_date,
        'platform': platform,
        'sources': ['data/bilibili-finance-up.md'],
        'ups': ups,
        'blacklist': blacklist,
        'videos': [],
        'comments': []
    }

    # 黑名单 UID 集合
    blacklist_uids = set(u['uid'] for u in blacklist)

    for up in ups:
        if up['uid'] in blacklist_uids:
            print(f"跳过黑名单 UP 主: {up['name']}")
            continue

        print(f"\n处理 UP 主: {up['name']} (UID: {up['uid']})")

        # 获取 UP 主的视频列表
        videos_result = run_opencli_command([
            'opencli', 'bilibili', 'user-videos', up['uid'],
            '--limit', '10',
            '-f', 'json'
        ])

        time.sleep(1.5)  # 请求间隔

        if not videos_result:
            continue

        for video in videos_result:
            video_info = {
                'rank': video.get('rank'),
                'title': video.get('title'),
                'plays': video.get('plays'),
                'likes': video.get('likes'),
                'date': video.get('date'),
                'url': video.get('url'),
                '_up': {'uid': up['uid'], 'name': up['name']}
            }
            data['videos'].append(video_info)

            # 从 URL 中提取 bvid
            url = video.get('url', '')
            bvid = None
            if '/video/' in url:
                bvid = url.split('/video/')[-1].split('?')[0]

            if bvid:
                print(f"  收集视频评论: {video.get('title', '')[:30]}... (BV: {bvid})")

                # 获取评论
                comments_result = run_opencli_command([
                    'opencli', 'bilibili', 'comments', bvid,
                    '--limit', '50',
                    '-f', 'json'
                ])

                time.sleep(1.5)  # 请求间隔

                if comments_result:
                    for comment in comments_result:
                        comment_data = {
                            'video_bvid': bvid,
                            'video_title': video.get('title'),
                            'author': comment.get('author'),
                            'text': comment.get('text'),
                            'likes': comment.get('likes', 0),
                            'replies': comment.get('replies', 0),
                            'time': comment.get('time'),
                            '_up': {'uid': up['uid'], 'name': up['name']}
                        }
                        data['comments'].append(comment_data)

    # 保存中间文件
    intermediate_file = intermediate_dir / f"{platform}_{target_date}.partial.json"
    with open(intermediate_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n中间文件已保存: {intermediate_file}")

    # 保存最终文件
    output_file = output_dir / f"{platform}_{target_date}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"最终文件已保存: {output_file}")

    return data


def collect_xiaohongshu(target_date, ups, output_dir, intermediate_dir):
    """收集小红书评论"""
    print("\n===== 开始收集 小红书 评论 =====")

    platform = 'xiaohongshu'
    data = {
        'target_date': target_date,
        'platform': platform,
        'sources': ['data/xiaohongshu-finance-up.md'],
        'ups': ups,
        'notes': [],
        'comments': []
    }

    for up in ups:
        print(f"\n处理博主: {up.get('name', 'Unknown')} (ID: {up.get('uid', 'N/A')})")

        # 获取博主的笔记列表
        user_id = up.get('uid', '')
        if user_id:
            notes_result = run_opencli_command([
                'opencli', 'xiaohongshu', 'user', user_id,
                '--limit', '10',
                '-f', 'json'
            ])

            time.sleep(1.5)  # 请求间隔

            if notes_result:
                for note in notes_result:
                    note_info = {
                        'id': note.get('id'),
                        'title': note.get('title'),
                        'type': note.get('type'),
                        'likes': note.get('likes'),
                        'url': note.get('url'),
                        '_author': up
                    }
                    data['notes'].append(note_info)

                    note_url = note.get('url')
                    if note_url:
                        print(f"  收集笔记评论: {note.get('title', '')[:30]}...")

                        # 获取评论
                        comments_result = run_opencli_command([
                            'opencli', 'xiaohongshu', 'comments', note_url,
                            '--limit', '50',
                            '--with-replies', 'true',
                            '-f', 'json'
                        ])

                        time.sleep(1.5)  # 请求间隔

                        if comments_result:
                            for comment in comments_result:
                                comment_data = {
                                    'note_id': note.get('id'),
                                    'note_title': note.get('title'),
                                    'note_url': note_url,
                                    'author': comment.get('author'),
                                    'text': comment.get('text'),
                                    'likes': comment.get('likes', 0),
                                    'time': comment.get('time'),
                                    'is_reply': comment.get('is_reply', False),
                                    'reply_to': comment.get('reply_to'),
                                    '_author': up
                                }
                                data['comments'].append(comment_data)

    # 保存中间文件
    intermediate_file = intermediate_dir / f"{platform}_{target_date}.partial.json"
    with open(intermediate_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n中间文件已保存: {intermediate_file}")

    # 保存最终文件
    output_file = output_dir / f"{platform}_{target_date}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"最终文件已保存: {output_file}")

    return data


def collect_xueqiu(target_date, up_symbols, section_symbols, output_dir, intermediate_dir):
    """收集雪球评论"""
    print("\n===== 开始收集 雪球 评论 =====")

    platform = 'xueqiu'

    # 合并所有股票代码
    all_symbols = list(set(up_symbols + section_symbols))

    data = {
        'target_date': target_date,
        'platform': platform,
        'sources': [
            'data/xueqiu-finance-up.md',
            'data/sections/CPO.md',
            'data/sections/laodeng.md'
        ],
        'symbols': all_symbols,
        'stocks': [],
        'comments': []
    }

    for symbol in all_symbols:
        print(f"\n处理股票: {symbol}")

        # 获取股票信息
        stock_result = run_opencli_command([
            'opencli', 'xueqiu', 'stock', symbol,
            '-f', 'json'
        ])

        time.sleep(1.5)  # 请求间隔

        if stock_result:
            stock_info = {}
            for item in stock_result:
                stock_info[item.get('field', '')] = item.get('value')
            data['stocks'].append({
                'symbol': symbol,
                'info': stock_info
            })

        # 获取股票评论
        print(f"  收集讨论...")
        comments_result = run_opencli_command([
            'opencli', 'xueqiu', 'comments', symbol,
            '--limit', '50',
            '-f', 'json'
        ])

        time.sleep(1.5)  # 请求间隔

        if comments_result:
            for comment in comments_result:
                comment_data = {
                    'symbol': symbol,
                    'author': comment.get('author'),
                    'text': comment.get('text'),
                    'likes': comment.get('likes', 0),
                    'replies': comment.get('replies', 0),
                    'retweets': comment.get('retweets', 0),
                    'created_at': comment.get('created_at'),
                    'url': comment.get('url')
                }
                data['comments'].append(comment_data)

    # 保存中间文件
    intermediate_file = intermediate_dir / f"{platform}_{target_date}.partial.json"
    with open(intermediate_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n中间文件已保存: {intermediate_file}")

    # 保存最终文件
    output_file = output_dir / f"{platform}_{target_date}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"最终文件已保存: {output_file}")

    return data


def import_to_database(platform_data, platform_name):
    """导入数据到数据库"""
    print(f"\n===== 导入 {platform_name} 数据到数据库 =====")

    repo = CommentRepository()
    imported_count = 0
    skipped_count = 0

    comments = platform_data.get('comments', [])
    print(f"共有 {len(comments)} 条评论待导入")

    for comment in comments:
        try:
            # 构建评论数据
            comment_data = {
                'platform': platform_name,
                'content': comment.get('text', ''),
                'author_name': comment.get('author', ''),
                'like_count': comment.get('likes', 0),
            }

            # 添加额外信息到 metadata 或内容中
            extra_info = []
            if 'video_title' in comment:
                extra_info.append(f"视频: {comment['video_title']}")
            if 'note_title' in comment:
                extra_info.append(f"笔记: {comment['note_title']}")
            if 'symbol' in comment:
                extra_info.append(f"股票: {comment['symbol']}")

            if extra_info:
                comment_data['content'] = f"[{', '.join(extra_info)}]\n{comment_data['content']}"

            # 添加时间信息
            time_str = comment.get('time') or comment.get('created_at')
            if time_str:
                comment_data['created_at'] = time_str

            # 添加 UP 主信息
            if '_up' in comment:
                comment_data['up_master'] = comment['_up'].get('name', '')
            elif '_author' in comment:
                comment_data['up_master'] = comment['_author'].get('name', '')

            # 导入数据库
            repo.insert(comment_data)
            imported_count += 1

        except Exception as e:
            print(f"导入评论时出错: {e}")
            skipped_count += 1

    print(f"导入完成: 成功 {imported_count} 条, 跳过 {skipped_count} 条")
    return imported_count, skipped_count


def main():
    parser = argparse.ArgumentParser(description='收集三个平台的财经评论')
    parser.add_argument('--date', help='目标日期 (YYYY-MM-DD), 默认为今天')
    parser.add_argument('--platform', choices=['bilibili', 'xiaohongshu', 'xueqiu', 'all'],
                        default='all', help='指定平台 (默认: 全部)')
    parser.add_argument('--import-only', action='store_true',
                        help='仅从现有 JSON 文件导入数据库')
    args = parser.parse_args()

    # 设置目标日期
    if args.date:
        target_date = args.date
    else:
        target_date = datetime.now().strftime('%Y-%m-%d')

    print(f"目标日期: {target_date}")

    # 确保输出目录存在
    output_dir = project_root / 'comments'
    intermediate_dir = project_root / 'intermediate'
    output_dir.mkdir(exist_ok=True)
    intermediate_dir.mkdir(exist_ok=True)

    # 加载 UP 主列表
    bilibili_ups, bilibili_blacklist = load_up_list(project_root / 'data' / 'bilibili-finance-up.md')
    xiaohongshu_ups, _ = load_up_list(project_root / 'data' / 'xiaohongshu-finance-up.md')
    xueqiu_ups, _ = load_up_list(project_root / 'data' / 'xueqiu-finance-up.md')

    # 加载板块股票列表
    cpo_symbols = load_sections_list(project_root / 'data' / 'sections' / 'CPO.md')
    laodeng_symbols = load_sections_list(project_root / 'data' / 'sections' / 'laodeng.md')

    # 提取雪球股票代码 (假设 UP 主列表中的 uid 是股票代码)
    xueqiu_symbols = [u['uid'] for u in xueqiu_ups]

    all_data = {}

    if args.import_only:
        # 仅导入模式
        print("\n===== 仅导入模式 =====")
        platforms_to_import = []
        if args.platform == 'all':
            platforms_to_import = ['bilibili', 'xiaohongshu', 'xueqiu']
        else:
            platforms_to_import = [args.platform]

        for platform in platforms_to_import:
            json_file = output_dir / f"{platform}_{target_date}.json"
            if json_file.exists():
                print(f"\n加载 {platform} 数据: {json_file}")
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                import_to_database(data, platform)
            else:
                print(f"文件不存在: {json_file}")

        return

    # 收集数据
    if args.platform == 'all' or args.platform == 'bilibili':
        bilibili_data = collect_bilibili(
            target_date, bilibili_ups, bilibili_blacklist,
            output_dir, intermediate_dir
        )
        all_data['bilibili'] = bilibili_data
        import_to_database(bilibili_data, 'bilibili')

    if args.platform == 'all' or args.platform == 'xiaohongshu':
        xiaohongshu_data = collect_xiaohongshu(
            target_date, xiaohongshu_ups,
            output_dir, intermediate_dir
        )
        all_data['xiaohongshu'] = xiaohongshu_data
        import_to_database(xiaohongshu_data, 'xiaohongshu')

    if args.platform == 'all' or args.platform == 'xueqiu':
        xueqiu_data = collect_xueqiu(
            target_date, xueqiu_symbols, cpo_symbols + laodeng_symbols,
            output_dir, intermediate_dir
        )
        all_data['xueqiu'] = xueqiu_data
        import_to_database(xueqiu_data, 'xueqiu')

    # 总结
    print("\n" + "=" * 50)
    print("收集完成总结:")
    for platform, data in all_data.items():
        print(f"  {platform}: {len(data.get('comments', []))} 条评论")
    print("=" * 50)


if __name__ == '__main__':
    main()
