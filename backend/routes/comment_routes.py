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
    sentiment_fix = data.get("sentiment_fix")
    try:
        return jsonify(get_service().lock_sentiment(comment_id, sentiment_fix))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@comment_bp.route("/api/comments/<int:comment_id>", methods=["DELETE"])
def delete_comment(comment_id):
    try:
        get_service().delete_comment(comment_id)
        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@comment_bp.route("/api/stats", methods=["GET"])
def get_stats():
    return jsonify(get_service().get_stats())


@comment_bp.route("/api/stats/timeline", methods=["GET"])
def get_stats_timeline():
    granularity = request.args.get("granularity", "day")
    if granularity not in ("day", "week", "month"):
        granularity = "day"
    return jsonify(get_service().get_stats_by_date(granularity))


@comment_bp.route("/api/up_masters", methods=["GET"])
def get_up_masters():
    return jsonify(get_service().get_up_masters())


@comment_bp.route("/api/videos", methods=["GET"])
def get_videos():
    return jsonify(get_service().get_videos())