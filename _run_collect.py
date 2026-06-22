"""Wrapper: monkey-patch subprocess to find Windows .cmd shims, then run target script.

Usage:
  python _run_collect.py <target_script> [args...]

Example:
  python _run_collect.py jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --date 2026-06-11
"""
import os
import subprocess
import sys

if sys.platform == "win32":
    _orig_run = subprocess.run
    _orig_Popen = subprocess.Popen
    _SEP = ("\\", "/")

    def _needs_shim(cmd):
        if not isinstance(cmd, (list, tuple)) or not cmd:
            return False
        exe = cmd[0]
        if not isinstance(exe, str) or not exe:
            return False
        if any(s in exe for s in _SEP):
            return False
        if exe.lower().endswith((".exe", ".bat", ".cmd", ".com")):
            return False
        return True

    def _fix_kwargs(kw):
        # Force utf-8 for text-mode pipes (Windows default is gbk → crashes on Chinese)
        if kw.get("text") and "encoding" not in kw:
            kw["encoding"] = "utf-8"
        return kw

    def _shim_run(cmd, *a, **kw):
        if _needs_shim(cmd) and not kw.get("shell"):
            cmd = ["cmd.exe", "/c", *cmd]
        _fix_kwargs(kw)
        return _orig_run(cmd, *a, **kw)

    def _shim_Popen(args, *a, **kw):
        if _needs_shim(args) and not kw.get("shell"):
            args = ["cmd.exe", "/c", *args]
        _fix_kwargs(kw)
        return _orig_Popen(args, *a, **kw)

    subprocess.run = _shim_run
    subprocess.Popen = _shim_Popen

# Force UTF-8 stdout/stderr (Windows defaults to GBK which breaks Chinese)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

if len(sys.argv) < 2:
    print("Usage: python _run_collect.py <script> [args...]")
    sys.exit(1)

target = sys.argv[1]
sys.argv = sys.argv[1:]

# Add target's directory to sys.path so sibling imports work
import os as _os
_tdir = _os.path.dirname(_os.path.abspath(target))
if _tdir and _tdir not in sys.path:
    sys.path.insert(0, _tdir)

# Run target script as __main__ via runpy
import runpy
runpy.run_path(target, run_name="__main__")
