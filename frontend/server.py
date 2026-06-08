#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask API server — wires routes to backend layers"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
from flask import Flask, send_from_directory

# Ensure backend is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.routes.comment_routes import comment_bp

app = Flask(__name__, static_folder=".")
app.register_blueprint(comment_bp)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.route("/comments/images/<path:filepath>")
def serve_comment_image(filepath):
    return send_from_directory(os.path.join(PROJECT_ROOT, "comments", "images"), filepath)


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)