#!/usr/bin/env bash
# ============================================================
# 金融评论情绪分析系统 — 前后端启动脚本
# 单进程 Flask 应用：同时提供 REST API 和前端 SPA
# ============================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

echo "=== 金融评论情绪分析系统 ==="
echo "项目目录: $PROJECT_ROOT"
echo ""

# ---- 检查依赖 ----
check_and_install() {
    if ! python -c "import flask" 2>/dev/null; then
        echo "[依赖] 检测到 flask 未安装，正在安装..."
        pip install flask>=3.0.0
    else
        echo "[依赖] flask 已安装 ($(python -c 'import importlib.metadata; print(importlib.metadata.version("flask"))' 2>/dev/null || echo 'ok'))"
    fi
}

check_and_install

# ---- 检查数据库 ----
if [ -f "$PROJECT_ROOT/db/comments.db" ]; then
    echo "[数据库] comments.db 已存在"
else
    echo "[数据库] ⚠️  comments.db 不存在，首次启动时将自动创建"
fi

echo ""
echo "[启动] 正在启动 Flask 服务 (端口 5000)..."
echo "[访问] http://localhost:5000"
echo ""

# ---- 启动 Flask ----
cd "$PROJECT_ROOT/frontend"
exec python server.py
