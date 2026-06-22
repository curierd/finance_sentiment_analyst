#!/usr/bin/env python3
# DeepSeek 余额查询（纯 Python，跨平台：Linux / macOS / Windows）
#
# 用法：
#   python check_balance.py
#
# Key 解析顺序（按这个顺序找，找到就停）：
#   1. 当前进程 os.environ['DEEPSEEK_API_KEY']
#      —— 用户在启动 Claude 之前 export 过；或 Linux/macOS 正常场景
#   2. 平台特定 fallback：
#      - Windows:  User scope / Machine scope（subprocess 调 powershell 读取）
#      - Linux/macOS:  ~/.bashrc / ~/.zshrc / ~/.profile / ~/.bash_profile 中
#                    的 `export DEEPSEEK_API_KEY=...` 行
#        （覆盖从桌面启动器启动 Claude、没 source rc 的场景）
#
# 找不到任何来源则 exit 2。
#
# 安全：脚本只回显 key 前 7 位 + 长度，绝不打印完整 key。

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

try:
    # Python 3.10+ 风格
    from typing import Optional
except ImportError:  # pragma: no cover
    Optional = None  # type: ignore


API_URL = 'https://api.deepseek.com/user/balance'
TIMEOUT = 30

# 用于从 shell rc 文件里抠出 export 的值；非贪婪，且支持单/双引号包裹
_EXPORT_RE = re.compile(
    r"""^\s*export\s+DEEPSEEK_API_KEY\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s#]+))""",
    re.MULTILINE,
)


def _from_environ() -> Optional[str]:
    return os.environ.get('DEEPSEEK_API_KEY')


def _from_windows_scopes() -> Optional[str]:
    """通过一次性 PowerShell 探针读 Windows User / Machine scope。"""
    if sys.platform != 'win32':
        return None
    ps_probe = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$u = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User');"
        "if ($u) { Write-Output $u; exit 0 };"
        "$m = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'Machine');"
        "if ($m) { Write-Output $m; exit 0 };"
        "exit 1"
    )
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_probe],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or '').strip() or None


def _from_posix_rcfiles() -> Optional[str]:
    """从常见的 POSIX shell rc 文件里抠 `export DEEPSEEK_API_KEY=...`。"""
    if sys.platform == 'win32':
        return None
    candidates = ['.bashrc', '.zshrc', '.profile', '.bash_profile']
    home = os.path.expanduser('~')
    for name in candidates:
        path = os.path.join(home, name)
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except (OSError, IOError):
            continue
        m = _EXPORT_RE.search(content)
        if m:
            return m.group(1) or m.group(2) or m.group(3)
    return None


def resolve_api_key() -> Optional[str]:
    for source in (_from_environ, _from_windows_scopes, _from_posix_rcfiles):
        try:
            key = source()
        except Exception:
            # 单个来源失败不应该让整个解析崩，跳到下一个
            continue
        if key:
            return key
    return None


def fetch_balance(api_key: str) -> dict:
    req = urllib.request.Request(API_URL, method='GET')
    req.add_header('Authorization', f'Bearer {api_key}')
    req.add_header('Accept', 'application/json')
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main() -> int:
    api_key = resolve_api_key()
    if not api_key:
        print('ERROR: DEEPSEEK_API_KEY not found in any source', file=sys.stderr)
        if sys.platform == 'win32':
            print('  checked: os.environ, Windows User scope, Windows Machine scope', file=sys.stderr)
            print('  fix: 系统属性 → 高级 → 环境变量 添加 DEEPSEEK_API_KEY', file=sys.stderr)
        else:
            print('  checked: os.environ, ~/.bashrc, ~/.zshrc, ~/.profile, ~/.bash_profile', file=sys.stderr)
            print('  fix: export DEEPSEEK_API_KEY=sk-...  或写入 ~/.bashrc / ~/.zshrc', file=sys.stderr)
        return 2

    prefix = api_key[:7]
    print(f'[auth] key prefix={prefix} len={len(api_key)}')

    try:
        data = fetch_balance(api_key)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'HTTP ERROR {e.code}: {e.reason}', file=sys.stderr)
        print(f'BODY: {body}', file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f'NETWORK ERROR: {e.reason}', file=sys.stderr)
    except Exception as e:
        print(f'UNEXPECTED ERROR: {e}', file=sys.stderr)
        return 1

    print('=== RAW JSON ===')
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print()
    print('=== SUMMARY ===')
    available = data.get('is_available')
    print(f'  Account available: {"yes" if available else "NO"}')
    for info in data.get('balance_infos', []):
        print(f'  currency={info.get("currency")}  '
              f'total={info.get("total_balance")}  '
              f'granted={info.get("granted_balance")}  '
              f'topped_up={info.get("topped_up_balance")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())