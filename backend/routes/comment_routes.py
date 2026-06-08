#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comment routes — HTTP layer"""

from flask import Blueprint, jsonify, request

comment_bp = Blueprint("comments", __name__)


def get_service():
    from backend.services.comment_service import CommentService
    return CommentService()


@comment_bp.route("/api/comments", methods=["GET"])
def get_comments():
    filters = {
        "platform": request.args.get("platform"),
        "up_name": request.args.get("up_name"),
        "video_title": request.args.get("video_title"),
        "sentiment": request.args.get("sentiment"),
        "author": request.args.get("author"),
        "locked": request.args.get("locked"),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
        "page": int(request.args.get("page", 1)),
        "page_size": int(request.args.get("page_size", 50)),
    }
    # Remove None values
    filters = {k: v for k, v in filters.items() if v is not None and v != ""}
    return jsonify(get_service().list_comments(filters))


@comment_bp.route("/api/comments/<int:comment_id>", methods=["GET"])
def get_comment(comment_id):
    return jsonify(get_service().get_comment(comment_id))


@comment_bp.route("/api/comments", methods=["POST"])
def create_comment():
    data = request.get_json() or {}
    try:
        return jsonify(get_service().create_comment(data)), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@comment_bp.route("/api/comments/<int:comment_id>", methods=["PATCH"])
def update_comment(comment_id):
    data = request.get_json()
    if "created_at" in data:
        return jsonify({"error": "created_at cannot be modified"}), 400
    sentiment_fix = data.get("sentiment_fix")
    try:
        return jsonify(get_service().lock_sentiment(comment_id, sentiment_fix))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@comment_bp.route("/api/comments/<int:comment_id>/image", methods=["PATCH"])
def update_comment_image(comment_id):
    data = request.get_json() or {}
    local_image_path = data.get("local_image_path")
    original_url = data.get("original_url")
    if local_image_path is None and original_url is None:
        return jsonify({"error": "At least one of local_image_path or original_url is required"}), 400
    try:
        return jsonify(get_service().update_image(comment_id, local_image_path, original_url))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@comment_bp.route("/api/comments/<int:comment_id>/image/upload", methods=["POST"])
def upload_comment_image(comment_id):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    import os
    from werkzeug.utils import secure_filename

    # Resolve platform to pick subdirectory
    try:
        comment = get_service().get_comment(comment_id)
    except Exception:
        comment = None
    if not comment:
        return jsonify({"error": "Comment not found"}), 404

    platform = comment.get("platform") or "other"
    image_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "comments", "images", platform,
    )
    os.makedirs(image_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"comment_{comment_id}{ext}"
    save_path = os.path.join(image_dir, filename)
    file.save(save_path)

    local_image_path = os.path.relpath(save_path, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    original_url = request.form.get("original_url")

    try:
        return jsonify(get_service().update_image(comment_id, local_image_path, original_url))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@comment_bp.route("/api/comments/<int:comment_id>", methods=["DELETE"])
def delete_comment(comment_id):
    try:
        get_service().delete_comment(comment_id)
        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@comment_bp.route("/api/stats", methods=["GET"])
def get_stats():
    filters = {
        "platform": request.args.get("platform"),
        "up_name": request.args.get("up_name"),
        "video_title": request.args.get("video_title"),
        "sentiment": request.args.get("sentiment"),
        "author": request.args.get("author"),
        "locked": request.args.get("locked"),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
    }
    filters = {k: v for k, v in filters.items() if v is not None and v != ""}
    return jsonify(get_service().get_stats(filters))


@comment_bp.route("/api/stats/timeline", methods=["GET"])
def get_stats_timeline():
    granularity = request.args.get("granularity", "day")
    if granularity not in ("day", "week", "month"):
        granularity = "day"
    filters = {
        "platform": request.args.get("platform"),
        "up_name": request.args.get("up_name"),
        "video_title": request.args.get("video_title"),
        "sentiment": request.args.get("sentiment"),
        "author": request.args.get("author"),
        "locked": request.args.get("locked"),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
    }
    filters = {k: v for k, v in filters.items() if v is not None and v != ""}
    return jsonify(get_service().get_stats_by_date(granularity, filters))


@comment_bp.route("/api/stats/timeline/image", methods=["GET"])
def get_stats_timeline_image():
    granularity = request.args.get("granularity", "day")
    if granularity not in ("day", "week", "month"):
        granularity = "day"
    filters = {
        "platform": request.args.get("platform"),
        "up_name": request.args.get("up_name"),
        "video_title": request.args.get("video_title"),
        "sentiment": request.args.get("sentiment"),
        "author": request.args.get("author"),
        "locked": request.args.get("locked"),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
    }
    filters = {k: v for k, v in filters.items() if v is not None and v != ""}
    data = get_service().get_stats_by_date(granularity, filters)

    import subprocess, json, os, tempfile

    chart_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                               ".claude", "skills", "chart-image", "scripts", "chart.mjs")
    spec_base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             ".claude", "skills", "chart-image", "scripts", "donut_labeled_spec.json")
    periods = sorted(data.keys())
    if not periods:
        return "No data", 404

    total_pos = sum(data[p].get("positive", 0) for p in periods)
    total_neu = sum(data[p].get("neutral", 0) for p in periods)
    total_neg = sum(data[p].get("negative", 0) for p in periods)
    if total_pos == 0 and total_neu == 0 and total_neg == 0:
        return "No data", 404

    gran_label = {"day": "日", "week": "周", "month": "月"}.get(granularity, granularity)
    chart_data = [
        {"category": "正面", "count": total_pos},
        {"category": "中性", "count": total_neu},
        {"category": "负面", "count": total_neg},
    ]

    # Build spec with data embedded
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": 520,
        "height": 360,
        "background": "#0f1117",
        "padding": {"left": 10, "right": 10, "top": 10, "bottom": 10},
        "title": {
            "text": "情绪时间线（" + gran_label + "）",
            "color": "#e0e3f0",
            "fontSize": 16,
            "fontWeight": "bold",
            "anchor": "middle"
        },
        "data": {"values": chart_data},
        "transform": [
            {"joinaggregate": [{"op": "sum", "field": "count", "as": "total"}]},
            {"calculate": "datum.count + ' (' + format(datum.count / datum.total, '.1%') + ')'", "as": "label"}
        ],
        "layer": [
            {
                "mark": {"type": "arc", "innerRadius": 72, "stroke": "#0f1117", "strokeWidth": 2},
                "encoding": {
                    "theta": {"field": "count", "type": "quantitative", "stack": True},
                    "color": {
                        "field": "category", "type": "nominal",
                        "scale": {"domain": ["正面", "中性", "负面"], "range": ["#34d399", "#94a3b8", "#f87171"]},
                        "legend": {"labelColor": "#e0e3f0", "titleColor": "#8890a8", "symbolStrokeColor": "#8890a8", "orient": "right"}
                    },
                    "order": {"field": "count", "type": "quantitative", "sort": "descending"}
                }
            },
            {
                "mark": {"type": "text", "radius": 108, "fontSize": 13, "fontWeight": "bold", "color": "#e0e3f0"},
                "encoding": {
                    "text": {"field": "label", "type": "nominal"},
                    "theta": {"field": "count", "type": "quantitative", "stack": True},
                    "color": {"value": "#e0e3f0"},
                    "order": {"field": "count", "type": "quantitative", "sort": "descending"}
                }
            }
        ],
        "config": {"font": "Helvetica, Arial, sans-serif", "view": {"stroke": None}}
    }

    tmp_spec = os.path.join(tempfile.gettempdir(), "sentiment_spec.json")
    tmp_path = os.path.join(tempfile.gettempdir(), "sentiment_timeline.png")
    try:
        with open(tmp_spec, "w", encoding="utf-8") as f:
            json.dump(spec, f)
        proc = subprocess.run([
            "node", chart_script, "--spec", tmp_spec, "--output", tmp_path
        ], capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return "Chart generation failed: " + proc.stderr, 500
        from flask import send_file
        return send_file(tmp_path, mimetype="image/png")
    finally:
        for p in (tmp_spec, tmp_path):
            try:
                os.remove(p)
            except Exception:
                pass


@comment_bp.route("/api/up_masters", methods=["GET"])
def get_up_masters():
    return jsonify(get_service().get_up_masters())


@comment_bp.route("/api/videos", methods=["GET"])
def get_videos():
    return jsonify(get_service().get_videos())