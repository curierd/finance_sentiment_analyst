#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B站评论配图下载器 — 库 + CLI 双形态。

可作为 Python 模块被 collect_bilibili_today.py 等脚本调用，也可以作为
独立命令行工具批量下载单个 BVID 视频的评论配图。

依赖
----
- Python 3.10+ (用 pathlib.Path 和 type hints)
- 可选: opencli (`pip install @jackwener/opencli`) — 仅 CLI 模式需要
  用于拉取评论 JSON；库模式只依赖标准库。

库 API
----
    from bilibili_image_downloader import (
        download_image,                # 单张下载
        download_images_for_comments,  # 批量: 把 pics[] 写到本地并补充元数据
        fetch_comments_with_pics,      # 一步到位: 拉评论 + 下载
        check_rpids_have_pics,         # 探测: 哪些 rpid 有可下载的配图 (不下)
    )

CLI 用法
--------
    # 1) 直接拉单个 BVID 的评论配图
    python bilibili_image_downloader.py BV1aRET6WEMC \\
        --output-dir comments/images/bilibili \\
        --limit 50

    # 2) 从已有的 comments.json (含 pics[] 字段) 二次补图
    python bilibili_image_downloader.py --from-json comments/bilibili_2026-06-08.json

    # 3) 探测: 给定 rpid 列表, 报告哪些有图 (不下)
    python bilibili_image_downloader.py --check-pics BV1aRET6WEMC 302012650305 302012560417 99999999

    # 4) 探测: 从已有 JSON 抽 rpid 自动检查
    python bilibili_image_downloader.py --check-pics --from-json comments/bilibili_2026-06-08.json \\
        --show-urls --save-json pic_check.json

    # 5) 在 Python 里复用
    python -c "
    from bilibili_image_downloader import fetch_comments_with_pics, check_rpids_have_pics
    from pathlib import Path

    # 探测
    res = check_rpids_have_pics('BV1aRET6WEMC', [302012650305, 302012560417])
    print('有图:', res['with_pics'])
    print('缺失/无图:', res['missing'])

    # 下载
    comments, stats = fetch_comments_with_pics(
        'BV1aRET6WEMC', Path('comments/images/bilibili'), limit=30
    )
    print(f'图 {stats.downloaded}/{stats.total} 成功, 跳过 {stats.skipped}')
    "
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

DEFAULT_UA = "Mozilla/5.0 (compatible; bilibili-image-downloader/1.0)"
USER_AGENT = "Mozilla/5.0"
TIMEOUT = 20
MMX_VISION_TIMEOUT = 60
MMX_DEFAULT_PROMPT = (
    "这张图片是什么内容？请用一两句话描述。"
    "重点关注金融、股票、财经、行情、K线、新闻标题、表情包文字等与评论语境相关的信息。"
    "如果只是普通表情包或风景,简略说明即可。"
)


def ext_from_url(url: str, default: str = ".jpg") -> str:
    """从 URL 推断文件扩展名。"""
    path = url.split("?")[0]
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        return "." + name.rsplit(".", 1)[-1].lower()[:4]
    return default


def download_image(
    url: str,
    dest: Path,
    *,
    timeout: int = TIMEOUT,
    user_agent: str = USER_AGENT,
    overwrite: bool = False,
) -> tuple[bool, str]:
    """单张图片下载到 `dest`。

    Parameters
    ----------
    url : 图片 URL (B 站 .bfs/new_dyn 域名)
    dest : 本地目标路径 (父目录会自动创建)
    timeout : HTTP 超时秒数
    user_agent : 请求 UA
    overwrite : True 时覆盖已存在文件；False 时跳过

    Returns
    -------
    (ok, reason) — ok=True 时 reason 是字节数描述；ok=False 时 reason 是错误摘要
    """
    if dest.exists() and not overwrite:
        return True, f"skipped (exists, {dest.stat().st_size} bytes)"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            f.write(data)
        return True, f"{len(data)} bytes"
    except Exception as e:
        return False, str(e)[:120]


@dataclass
class ImageRecord:
    original_url: str
    local_path: Optional[str] = None
    downloaded: bool = False
    reason: Optional[str] = None
    size_bytes: int = 0
    description: Optional[str] = None


@dataclass
class DownloadStats:
    comments_scanned: int = 0
    comments_with_pics: int = 0
    total: int = 0
    downloaded: int = 0
    failed: int = 0
    skipped: int = 0
    records: list[ImageRecord] = field(default_factory=list)


def download_images_for_comments(
    comments: list[dict],
    bvid: str,
    image_root: Path,
    errors: Optional[list[dict]] = None,
    *,
    project_root: Optional[Path] = None,
) -> DownloadStats:
    """把一批 comment 字典里的 `pics[]` 全部下载到 `image_root/<bvid>/`。

    每个 comment 会被原地添加 `images: [ImageRecord]`，并把首张成功
    下载的图片路径写入 `local_image_path` / `original_url` (供
    CommentRepository.insert() 使用)。

    Parameters
    ----------
    comments : opencli bilibili comments-raw 的输出, 每条含 rpid/text/pics
    bvid : 用于本地目录分组
    image_root : 根目录, 默认 <repo>/comments/images/bilibili
    errors : 可选, 失败会 append 到这里 (供上层 JSON envelope 留档)
    project_root : 用来计算 local_path 的相对路径

    Returns
    -------
    DownloadStats 汇总 (含每条 ImageRecord)
    """
    stats = DownloadStats(comments_scanned=len(comments))
    project_root = project_root or image_root.parent.parent.parent  # images/bilibili → repo

    for c in comments:
        rpid = c.get("rpid")
        if rpid is not None:
            c["comment_id"] = str(rpid)
        pics = c.get("pics") or []
        if not pics:
            c["images"] = []
            continue
        stats.comments_with_pics += 1
        images: list[dict] = []
        for idx, url in enumerate(pics):
            ext = ext_from_url(url)
            local = image_root / bvid / f"{rpid}_{idx}{ext}"
            ok, reason = download_image(url, local)
            rec = ImageRecord(
                original_url=url,
                local_path=str(local.relative_to(project_root)) if ok and local.exists() else None,
                downloaded=ok and local.exists(),
                reason=None if ok else reason,
                size_bytes=local.stat().st_size if ok and local.exists() else 0,
            )
            if not ok and errors is not None:
                errors.append({"stage": "image_download", "rpid": rpid, "url": url, "error": reason})
            stats.records.append(rec)
            stats.total += 1
            if rec.downloaded:
                if "skipped" in (reason or ""):
                    stats.skipped += 1
                else:
                    stats.downloaded += 1
            else:
                stats.failed += 1
            images.append(asdict(rec))
        c["images"] = images
        first_ok = next((i for i in images if i.get("downloaded")), None)
        if first_ok:
            c["local_image_path"] = first_ok["local_path"]
            c["original_url"] = first_ok["original_url"]
    return stats


def fetch_comments_with_pics(
    bvid: str,
    image_root: Path,
    *,
    limit: int = 50,
    errors: Optional[list[dict]] = None,
    project_root: Optional[Path] = None,
    cli_path: str = "opencli",
) -> tuple[list[dict], DownloadStats]:
    """一步到位: 调 `opencli bilibili comments-raw` + 下载配图。

    Returns
    -------
    (comments, stats)
    """
    cmd = [cli_path, "bilibili", "comments-raw", bvid, "--limit", str(limit), "-f", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed (rc={proc.returncode}): {proc.stderr[:200]}")
    comments = json.loads(proc.stdout)
    stats = download_images_for_comments(
        comments, bvid, image_root, errors=errors, project_root=project_root
    )
    return comments, stats


def check_rpids_have_pics(
    bvid: str,
    rpids: list[int] | int | None = None,
    *,
    limit: int = 50,
    cli_path: str = "opencli",
    include_urls: bool = True,
) -> dict:
    """判断给定的 rpid 在该视频评论里是否有可下载的配图 (不下载, 仅探测)。

    工作流程: 调一次 `opencli bilibili comments-raw`, 拿回 comment 列表,
    然后筛选 `rpid in 传入集合 AND pics[]` 非空的项。

    Parameters
    ----------
    bvid : 视频 BV 号
    rpids : 要检查的 rpid 集合; 传 None / 0 表示检查该视频所有有图的评论
    limit : opencli 单次拉取的评论上限 (max 50)
    include_urls : True 时返回的图片 URL 列表; False 时仅返回 rpid 集合 (更轻)

    Returns
    -------
    {
        "bvid": str,
        "checked": int,        # 传入的 rpids 数量 (None 时为 0)
        "with_pics": list[int],# 在传入集合里且有图的 rpid (None 时为全部)
        "missing":  list[int], # 在传入集合里但没找到 (或无图)
        "total_in_video": int, # 视频里总共有图的 rpid 数
        "urls": {rpid: [url, ...]} if include_urls else {}
    }
    """
    cmd = [cli_path, "bilibili", "comments-raw", bvid, "--limit", str(limit), "-f", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed (rc={proc.returncode}): {proc.stderr[:200]}")
    comments = json.loads(proc.stdout)

    all_with_pics: dict[int, list[str]] = {
        c["rpid"]: c.get("pics") or [] for c in comments if c.get("pics")
    }
    total_with_pics = len(all_with_pics)

    if rpids is None:
        with_pics_list = sorted(all_with_pics.keys())
        missing_list: list[int] = []
        checked_count = 0
    else:
        if isinstance(rpids, int):
            rpids = [rpids]
        rpids_set = set(int(r) for r in rpids)
        with_pics_list = sorted(rpids_set & set(all_with_pics.keys()))
        missing_list = sorted(rpids_set - set(all_with_pics.keys()))
        checked_count = len(rpids_set)

    urls: dict[int, list[str]] = {}
    if include_urls:
        urls = {r: list(all_with_pics.get(r, [])) for r in with_pics_list}

    return {
        "bvid": bvid,
        "checked": checked_count,
        "with_pics": with_pics_list,
        "missing": missing_list,
        "total_in_video": total_with_pics,
        "urls": urls,
    }


# -----------------------------------------------------------------------------
# mmx vision 图像理解 (mmx-cli-cn)
# -----------------------------------------------------------------------------

def _resolve_mmx() -> str:
    """Resolve `mmx` to a Windows-executable path (no-extension bash shim)."""
    if os.name == "nt":
        for ext in ("", ".cmd", ".exe", ".bat"):
            candidate = shutil.which("mmx" + ext)
            if candidate:
                return candidate
    return "mmx"


def _strip_preamble(text: str) -> str:
    """Strip Windows cmd shim preamble like 'Active code page: 65001' that
    appears before the real stdout. The first meaningful line starts after
    the preamble.
    """
    if not text:
        return text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "Active code page" in line:
            continue
        if line.strip() == "":
            continue
        return "\n".join(lines[i:])
    return text


def describe_image_with_mmx(
    image_path: Path,
    *,
    prompt: str = MMX_DEFAULT_PROMPT,
    timeout: int = MMX_VISION_TIMEOUT,
    cli: str = "mmx",
) -> dict:
    """Call `mmx vision describe` to understand a single image.

    Returns a dict: {"ok": bool, "description": str, "error": str|None}.
    """
    if not image_path.exists():
        return {"ok": False, "description": "", "error": f"image not found: {image_path}"}
    cmd = [cli, "vision", "describe", "--image", str(image_path),
           "--prompt", prompt, "--output", "text", "--quiet", "--non-interactive"]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=env,
        )
    except FileNotFoundError as e:
        return {"ok": False, "description": "", "error": f"mmx not found ({e})"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "description": "", "error": f"mmx vision timeout ({timeout}s)"}
    if proc.returncode != 0:
        return {"ok": False, "description": "", "error": (proc.stderr or proc.stdout).strip()[:200]}
    description = _strip_preamble(proc.stdout or "").strip()
    if not description:
        return {"ok": False, "description": "", "error": "mmx returned empty description"}
    return {"ok": True, "description": description, "error": None}


def describe_images_for_comments(
    comments: list[dict],
    *,
    project_root: Optional[Path] = None,
    prompt: str = MMX_DEFAULT_PROMPT,
    errors: Optional[list[dict]] = None,
    sleep_seconds: float = 0.0,
) -> dict:
    """Walk `comments[*].images[*]`, call mmx vision describe on every downloaded
    image, and write the description back to the ImageRecord (and the first one
    onto the parent comment as `image_description`).

    Skips comments without downloaded images and images already described
    (idempotent on re-run).

    Returns
    -------
    {
        "scanned": int, "described": int, "failed": int, "skipped": int,
        "errors": list[dict]
    }
    """
    project_root = project_root or Path(__file__).resolve().parent.parent.parent.parent
    cli = _resolve_mmx()
    stats = {"scanned": 0, "described": 0, "failed": 0, "skipped": 0, "errors": []}
    for c in comments:
        images = c.get("images") or []
        for img in images:
            stats["scanned"] += 1
            if not img.get("downloaded"):
                stats["skipped"] += 1
                continue
            if img.get("description"):
                stats["skipped"] += 1
                continue
            local_rel = img.get("local_path")
            if not local_rel:
                stats["skipped"] += 1
                continue
            local_abs = (project_root / local_rel).resolve()
            res = describe_image_with_mmx(local_abs, prompt=prompt, cli=cli)
            if res["ok"]:
                img["description"] = res["description"]
                stats["described"] += 1
            else:
                img["description"] = None
                stats["failed"] += 1
                err_entry = {
                    "stage": "image_describe",
                    "rpid": c.get("rpid"),
                    "path": local_rel,
                    "error": res["error"],
                }
                stats["errors"].append(err_entry)
                if errors is not None:
                    errors.append(err_entry)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
        first_described = next(
            (i.get("description") for i in images if i.get("description")), None
        )
        if first_described:
            c["image_description"] = first_described
    return stats


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def _cli_from_json(args) -> int:
    """从已有 comments.json 补图模式。"""
    src = Path(args.from_json)
    if not src.exists():
        print(f"[FATAL] {src} not found", file=sys.stderr)
        return 1
    with src.open("r", encoding="utf-8") as f:
        data = json.load(f)
    bvid = args.bvid or data.get("bvid") or "unknown"
    image_root = Path(args.output_dir)
    errors: list[dict] = []
    stats = download_images_for_comments(
        data.get("comments", []), bvid, image_root, errors=errors
    )
    with src.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[STATS] scanned={stats.comments_scanned} with_pics={stats.comments_with_pics} "
          f"downloaded={stats.downloaded} skipped={stats.skipped} failed={stats.failed}")
    return 0 if stats.failed == 0 else 2


def _cli_check_pics(args) -> int:
    """--check-pics: 判断 rpid 是否有可下载的配图 (不下载)。"""
    if args.from_json:
        # 从 JSON 抽 rpids, 按 bvid 分组
        src = Path(args.from_json)
        if not src.exists():
            print(f"[FATAL] {src} not found", file=sys.stderr)
            return 1
        with src.open("r", encoding="utf-8") as f:
            data = json.load(f)
        per_bvid: dict[str, set[int]] = {}
        for c in data.get("comments", []):
            rpid = c.get("rpid")
            bv = c.get("_video_bvid") or (c.get("_video") or {}).get("bvid")
            if rpid is not None and bv:
                per_bvid.setdefault(bv, set()).add(rpid)
        if not per_bvid:
            print("[FATAL] JSON 里没找到带 bvid 的评论", file=sys.stderr)
            return 1
        results = []
        for bvid, rpid_set in per_bvid.items():
            results.append(check_rpids_have_pics(bvid, sorted(rpid_set), limit=args.limit, include_urls=True))
    else:
        if not args.bvid:
            print("[FATAL] --check-pics 需要 BVID (除非配合 --from-json)", file=sys.stderr)
            return 1
        bvid = args.bvid
        rpids = [int(r) for r in (args.rpids or [])] if args.rpids else None
        results = [check_rpids_have_pics(bvid, rpids, limit=args.limit, include_urls=True)]

    for result in results:
        print(f"[CHECK] bvid={result['bvid']}")
        print(f"  传入 rpid: {result['checked']}")
        print(f"  有图:     {len(result['with_pics'])}  {result['with_pics'][:10]}{'...' if len(result['with_pics'])>10 else ''}")
        if result["checked"] > 0:
            print(f"  未找到/无图: {len(result['missing'])}  {result['missing'][:10]}{'...' if len(result['missing'])>10 else ''}")
        print(f"  该视频共 {result['total_in_video']} 条评论带图")
        if args.show_urls and result["urls"]:
            for rpid, urls in list(result["urls"].items())[:args.url_max]:
                print(f"  rpid={rpid}: {len(urls)} 图")
                for u in urls[:2]:
                    print(f"    {u[:90]}{'...' if len(u)>90 else ''}")
        print()

    if args.save_json:
        out = Path(args.save_json)
        with out.open("w", encoding="utf-8") as f:
            json.dump(results if len(results) > 1 else results[0], f, ensure_ascii=False, indent=2)
        print(f"[SAVE] {out}")
    return 0


def _cli_fetch(args) -> int:
    """拉单个 BVID 的评论 + 配图。"""
    image_root = Path(args.output_dir)
    errors: list[dict] = []
    comments, stats = fetch_comments_with_pics(
        args.bvid, image_root,
        limit=args.limit,
        errors=errors,
    )
    out_json = Path(args.save_json) if args.save_json else None
    if out_json:
        payload = {
            "bvid": args.bvid,
            "comments": comments,
            "stats": {
                "comments_scanned": stats.comments_scanned,
                "comments_with_pics": stats.comments_with_pics,
                "downloaded": stats.downloaded,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "total": stats.total,
            },
            "errors": errors,
        }
        with out_json.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[SAVE] {out_json}")
    print(f"[STATS] comments={stats.comments_scanned} with_pics={stats.comments_with_pics} "
          f"downloaded={stats.downloaded} skipped={stats.skipped} failed={stats.failed}")
    return 0 if stats.failed == 0 else 2


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="B 站评论配图下载器 (库 + CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("bvid", nargs="?", help="BVID, 例如 BV1aRET6WEMC")
    parser.add_argument("rpids", nargs="*", type=int,
                        help="(配合 --check-pics) 要检查的 rpid 列表")
    parser.add_argument("--limit", type=int, default=50, help="评论数 (默认 50)")
    parser.add_argument("--output-dir", default="comments/images/bilibili",
                        help="图片根目录 (默认: comments/images/bilibili)")
    parser.add_argument("--from-json", help="从已有 comments.json 补图模式")
    parser.add_argument("--save-json", help="保存含图信息的 JSON 到此路径")
    parser.add_argument("--check-pics", action="store_true",
                        help="只探测, 不下载: 报告哪些 rpid 有可下载的配图")
    parser.add_argument("--show-urls", action="store_true",
                        help="(配合 --check-pics) 打印每个有图 rpid 的 URL")
    parser.add_argument("--url-max", type=int, default=5,
                        help="(--show-urls 时) 最多展示几个 rpid 的 URL")
    args = parser.parse_args(argv)

    if args.check_pics:
        return _cli_check_pics(args)
    if args.from_json:
        return _cli_from_json(args)
    if not args.bvid:
        parser.error("bvid is required (除非使用 --check-pics / --from-json)")
    return _cli_fetch(args)


if __name__ == "__main__":
    sys.exit(main())
