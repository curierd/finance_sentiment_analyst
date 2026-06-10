#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask API server — wires routes to backend layers, serves SPA and static files."""

import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure backend is importable BEFORE importing any backend.* modules
# (the Flask reloader re-execs this script in a fresh interpreter, so the
# path must be set up first thing — not after the imports that need it).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, send_from_directory, render_template_string
from backend.config import UPLOAD_DIR, IMAGE_URL_PREFIX, DB_PATH
from backend.routes.comment_routes import comment_bp

app = Flask(__name__, static_folder=".")
app.register_blueprint(comment_bp)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.route("/")
def index():
    """Serve the SPA with injected config."""
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject IMAGE_URL_PREFIX before the closing </head> tag
    config_script = (
        '<script>'
        'window.IMAGE_URL_PREFIX = ' + repr(IMAGE_URL_PREFIX) + ';'
        '</script>'
    )
    html = html.replace("</head>", config_script + "\n</head>")
    return html


# Serve images from uploads directory
@app.route("/uploads/<path:filepath>")
def serve_upload_file(filepath):
    """Serve uploaded images from UPLOAD_DIR (Docker path)."""
    return send_from_directory(UPLOAD_DIR, filepath)


# Backward-compat: serve legacy comments/ directory
@app.route("/comments/<path:filepath>")
def serve_comment_file(filepath):
    """Serve legacy images from comments/ dir or UPLOAD_DIR fallback."""
    legacy_dir = os.path.join(PROJECT_ROOT, "comments")
    target_dir = legacy_dir if os.path.isdir(legacy_dir) else UPLOAD_DIR
    return send_from_directory(target_dir, filepath)


@app.route("/health")
def health():
    """Health check endpoint for Docker."""
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "uploads_dir": os.path.isdir(UPLOAD_DIR),
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
