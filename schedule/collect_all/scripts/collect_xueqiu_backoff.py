#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雪球采集指数退避包装。

检测 opencli 输出的风控特征（AUTH_REQUIRED / stale page / rate limit），
按 60s → 120s → 240s 退避重试同一只股票。

直接 patch jobs/xuqiu_comments_collector/scripts/collect_xueqiu.py 的
run_opencli 函数，避免改原脚本（保留原 issues.md 风格）。
"""
import os
import re
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "jobs" / "xuqiu_comments_collector" / "scripts"))

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "collect_xueqiu",
    REPO_ROOT / "jobs" / "xuqiu_comments_collector" / "scripts" / "collect_xueqiu.py",
)
cx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cx)

RISK_PATTERNS = [
    r"AUTH_REQUIRED",
    r"stale page identity",
    r"Page not found",
    r"rate.?limit",
    r"风控",
    r"too many requests",
    r"412",
    r"429",
]
RISK_RE = re.compile("|".join(RISK_PATTERNS), re.IGNORECASE)


def is_risk_signal(text: str) -> bool:
    if not text:
        return False
    return bool(RISK_RE.search(text))


BACKOFF_SECONDS = [60, 120, 240]  # 3 次风控重试


def run_opencli_backoff(args, max_retries=4):
    """覆盖 collect_xueqiu.run_opencli：风控信号 → 指数退避。"""
    cmd = [cx._resolve_tool("opencli")] + list(args)
    env = os.environ.copy()
    env["OPENCLI_WINDOW"] = "background"
    if sys.platform == "win32":
        for p in (
            r"C:\Users\sverd\AppData\Roaming\npm",
            r"C:\Users\sverd\.local\bin",
        ):
            if p not in env.get("PATH", ""):
                env["PATH"] = p + os.pathsep + env.get("PATH", "")

    attempt = 0
    while attempt <= max_retries:
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                encoding="utf-8", errors="replace", env=env,
            )
        except Exception as e:
            print(f"  [attempt {attempt+1}] 异常: {e}")
            r = None

        if r is not None:
            cleaned = cx._strip_preamble(r.stdout) if r.stdout else ""
            stderr = r.stderr or ""
            combined = cleaned + "\n" + stderr
            if r.returncode == 0 and cleaned.strip():
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    pass

            risk = is_risk_signal(combined)
            if risk and attempt < max_retries:
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                snippet = combined[:200].replace("\n", " ")
                print(f"  [attempt {attempt+1}] 风控信号: {snippet}")
                print(f"  退避 {wait}s ...")
                time.sleep(wait)
                attempt += 1
                continue

            if not risk:
                # 非风控失败 → 沿用原 2 次重试 + 3s 短间隔
                if attempt < max_retries:
                    print(f"  [attempt {attempt+1}] 非风控失败，3s 后重试: {stderr[:120]}")
                    time.sleep(3)
                    attempt += 1
                    continue

        # 用尽重试
        print(f"  [exhausted] {args}")
        return None
    return None


def main():
    # patch collect_xueqiu.run_opencli
    cx.run_opencli = run_opencli_backoff
    return cx.main()


if __name__ == "__main__":
    sys.exit(main() or 0)