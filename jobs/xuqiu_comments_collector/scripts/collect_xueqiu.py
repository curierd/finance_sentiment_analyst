#!/usr/bin/env python3
"""
雪球评论采集脚本 - 采集指定股票和博主的今日评论
用法: python collect_xueqiu.py [--date YYYY-MM-DD] [--limit N]
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
COMMENTS_DIR = PROJECT_ROOT / "comments"
INTERMEDIATE_DIR = PROJECT_ROOT / "intermediate"


def _resolve_tool(name):
    """Resolve tool name to absolute path (handles npm .cmd shims on Windows)."""
    for c in (name, f"{name}.cmd", f"{name}.exe", f"{name}.bat"):
        p = shutil.which(c)
        if p:
            return p
    return name


def _strip_preamble(s):
    """Skip opencli's `Active code page: 65001` prefix and any blank lines."""
    if not s:
        return s
    out, skip = [], True
    for line in s.splitlines():
        if skip and (not line.strip() or line.startswith("Active code page")):
            continue
        skip = False
        out.append(line)
    return "\n".join(out)


def load_stock_symbols():
    """从 sections 文件加载股票代码，返回 (所有代码列表, {section: [代码]})"""
    all_symbols = []
    sections = {}
    sections_dir = PROJECT_ROOT / "data" / "sections"
    for section_file in sorted(sections_dir.glob("*.md")):
        section_name = section_file.stem
        symbols = []
        with open(section_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 匹配带前缀的股票代码 (SH/SZ + 6位数字, HK + 5位数字)
                match = re.search(r'([A-Z]{2}\d{5,6})', line)
                if match:
                    symbols.append(match.group(1))
                    continue
                # 匹配纯数字代码 (CPO.md 格式: 名称(代码))
                match = re.search(r'\((\d{5,6})\)', line)
                if match:
                    code = match.group(1)
                    # 5位数字以0开头 → HK
                    if len(code) == 5 and code.startswith('0'):
                        symbols.append(f"HK{code}")
                    elif code.startswith(('6', '51', '58')):
                        symbols.append(f"SH{code}")
                    elif code.startswith(('0', '3', '15')):
                        symbols.append(f"SZ{code}")
                    else:
                        symbols.append(f"SZ{code}")
        sections[section_name] = symbols
        all_symbols.extend(symbols)
    return list(set(all_symbols)), sections


def load_blogger_ids():
    """从 xueqiu-finance-up.md 加载博主ID"""
    blogger_ids = []
    up_file = PROJECT_ROOT / "jobs" / "xuqiu_comments_collector" / "xueqiu-finance-up.md"
    with open(up_file, "r", encoding="utf-8") as f:
        for line in f:
            # 匹配表格中的数字ID
            match = re.search(r'\|\s*(\d{10})\s*\|', line)
            if match:
                blogger_ids.append(match.group(1))
    return blogger_ids


def load_blogger_names():
    """从 xueqiu-finance-up.md 加载博主名称到ID的映射"""
    name_to_id = {}
    up_file = PROJECT_ROOT / "jobs" / "xuqiu_comments_collector" / "xueqiu-finance-up.md"
    with open(up_file, "r", encoding="utf-8") as f:
        for line in f:
            # 匹配表格行: | 排名 | 博主 | ID | ...
            match = re.search(r'\|\s*[^|]+\|\s*([^|]+)\|\s*(\d{10})\s*\|', line)
            if match:
                name = match.group(1).strip()
                uid = match.group(2)
                name_to_id[name] = uid
    return name_to_id


def run_opencli(args, max_retries=2):
    """运行 opencli 命令（OPENCLI_WINDOW=background 防止抢焦点），返回 JSON 结果"""
    cmd = [_resolve_tool("opencli")] + list(args)
    env = os.environ.copy()
    env["OPENCLI_WINDOW"] = "background"
    if sys.platform == "win32":
        for p in (
            r"C:\Users\sverd\AppData\Roaming\npm",
            r"C:\Users\sverd\.local\bin",
        ):
            if p not in env.get("PATH", ""):
                env["PATH"] = p + os.pathsep + env.get("PATH", "")
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                encoding="utf-8", errors="replace", env=env,
            )
            if result.returncode == 0 and result.stdout.strip():
                cleaned = _strip_preamble(result.stdout)
                return json.loads(cleaned)
            else:
                print(f"  命令失败 (attempt {attempt+1}/{max_retries}): {result.stderr[:200]}")
        except Exception as e:
            print(f"  命令异常 (attempt {attempt+1}/{max_retries}): {e}")
        if attempt < max_retries - 1:
            time.sleep(3)
    return None


def is_today(date_str, target_date):
    """检查日期字符串是否是目标日期"""
    if not date_str:
        return False
    try:
        # 格式: 2026-06-09T06:00:36.000Z
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d") == target_date
    except (ValueError, TypeError):
        return False


def normalize_symbol_for_xueqiu(symbol):
    """将 sections 中的股票代码转为雪球 API 接受的格式"""
    # HK 前缀代码 → 纯数字（雪球 API 不接受 HK 前缀）
    if symbol.startswith("HK"):
        return symbol[2:]
    return symbol


def collect_stock_comments(symbols, target_date, limit=50):
    """收集股票评论"""
    all_comments = []

    for i, symbol in enumerate(symbols):
        api_symbol = normalize_symbol_for_xueqiu(symbol)
        print(f"[{i+1}/{len(symbols)}] 采集 {symbol} 讨论动态...")

        comments = run_opencli([
            "xueqiu", "comments", api_symbol,
            "--limit", str(limit),
            "-f", "json"
        ])

        time.sleep(1.5)

        if not comments:
            print(f"  无数据")
            continue

        today_count = 0
        for c in comments:
            c["symbol"] = symbol
            if is_today(c.get("created_at"), target_date):
                today_count += 1
        all_comments.extend(comments)
        print(f"  获取 {len(comments)} 条, 今日 {today_count} 条")

    return all_comments


def collect_hot_discussions(target_date, limit=50):
    """收集热门动态"""
    print(f"采集雪球热门动态 (limit={limit})...")

    hot = run_opencli([
        "xueqiu", "hot",
        "--limit", str(limit),
        "-f", "json"
    ])

    time.sleep(1.5)

    if not hot:
        print("  无数据")
        return []

    print(f"  获取 {len(hot)} 条热门动态")

    # 尝试获取热门帖子的子评论
    all_hot_comments = []
    for item in hot:
        url = item.get("url", "")
        # 从 URL 提取 statusId
        # URL 格式: https://xueqiu.com/{user_id}/{status_id}
        if url:
            parts = url.rstrip("/").split("/")
            if len(parts) >= 2:
                status_id = parts[-1]
                # 尝试获取帖子详情/评论（通过 comments 命令不行，这是股票评论命令）
                # hot 帖子没有直接的 opencli 子评论命令，先保存帖子本身
                pass
        all_hot_comments.append(item)

    return all_hot_comments


def main():
    target_date = datetime.now().strftime("%Y-%m-%d")
    if len(sys.argv) > 1:
        # 支持 --date YYYY-MM-DD
        for i, arg in enumerate(sys.argv):
            if arg == "--date" and i + 1 < len(sys.argv):
                target_date = sys.argv[i + 1]
            elif arg == "--limit" and i + 1 < len(sys.argv):
                pass  # handled below

    limit = 50
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    print(f"=== 雪球评论采集 ===")
    print(f"目标日期: {target_date}")
    print(f"每股票评论数: {limit}")

    # 确保目录存在
    COMMENTS_DIR.mkdir(exist_ok=True)
    INTERMEDIATE_DIR.mkdir(exist_ok=True)

    # 加载数据
    stock_symbols, sections = load_stock_symbols()
    blogger_ids = load_blogger_ids()
    blogger_names = load_blogger_names()

    print(f"\n股票代码: {len(stock_symbols)} 个")
    print(f"博主ID: {len(blogger_ids)} 个")
    print(f"博主名称: {len(blogger_names)} 个")

    # 中间数据结构
    data = {
        "target_date": target_date,
        "platform": "雪球",
        "sources": ["data/xueqiu-finance-up.md"] + [
            f"data/sections/{name}.md" for name in sorted(sections.keys())
        ],
        "sections": sections,
        "blogger_ids": blogger_ids,
        "blogger_names": blogger_names,
        "stock_comments": [],
        "hot_discussions": [],
        "comments": [],
    }

    # 1. 收集股票评论
    print("\n--- 步骤1: 采集股票讨论 ---")
    stock_comments = collect_stock_comments(stock_symbols, target_date, limit)
    data["stock_comments"] = stock_comments

    # 保存中间文件
    intermediate_file = INTERMEDIATE_DIR / f"xueqiu_{target_date}.partial.json"
    with open(intermediate_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n中间文件已保存: {intermediate_file}")

    # 2. 收集热门动态
    print("\n--- 步骤2: 采集热门动态 ---")
    hot = collect_hot_discussions(target_date, limit=50)
    data["hot_discussions"] = hot

    # 3. 整理今日评论
    print("\n--- 步骤3: 整理今日评论 ---")

    # 从股票评论中筛选今日评论
    today_comments = []
    blogger_id_set = set(blogger_ids)
    blogger_name_set = set(blogger_names.keys())

    for c in stock_comments:
        if is_today(c.get("created_at"), target_date):
            author = c.get("author", "")
            is_blogger = author in blogger_name_set
            comment_data = {
                "author": author,
                "text": c.get("text", ""),
                "likes": c.get("likes", 0),
                "replies": c.get("replies", 0),
                "retweets": c.get("retweets", 0),
                "created_at": c.get("created_at"),
                "url": c.get("url"),
                "symbol": c.get("symbol"),
                "is_blogger": is_blogger,
            }
            if is_blogger:
                comment_data["blogger_id"] = blogger_names[author]
            today_comments.append(comment_data)

    # 从热门动态中筛选今日评论
    for item in hot:
        author = item.get("author", "")
        is_blogger = author in blogger_name_set
        comment_data = {
            "author": author,
            "text": item.get("text", ""),
            "likes": item.get("likes", 0),
            "replies": item.get("replies", 0),
            "retweets": 0,
            "created_at": None,
            "url": item.get("url"),
            "symbol": "hot",
            "is_blogger": is_blogger,
            "source": "hot",
        }
        if is_blogger:
            comment_data["blogger_id"] = blogger_names[author]
        today_comments.append(comment_data)

    data["comments"] = today_comments

    # 统计
    total = len(today_comments)
    blogger_count = sum(1 for c in today_comments if c.get("is_blogger"))
    print(f"今日评论总数: {total}")
    print(f"博主评论数: {blogger_count}")
    print(f"非博主评论数: {total - blogger_count}")

    # 保存最终结果
    output_file = COMMENTS_DIR / f"xueqiu_{target_date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n最终文件已保存: {output_file}")

    # 更新中间文件
    with open(intermediate_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


if __name__ == "__main__":
    main()
