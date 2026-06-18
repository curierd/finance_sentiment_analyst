#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comment service — business logic layer (uses adapter pattern)."""

from backend.adapters.sqlite.comment_repository import CommentRepository


class CommentService:
    def __init__(self):
        self.repo = CommentRepository()

    def list_comments(self, filters=None):
        return self.repo.find_all(filters)

    def get_comment(self, comment_id):
        return self.repo.find_by_id(comment_id)

    def lock_sentiment(self, comment_id, sentiment_fix):
        if sentiment_fix not in ("正面", "负面", "中性", None):
            raise ValueError("Invalid sentiment_fix value")
        return self.repo.update_sentiment_fix(comment_id, sentiment_fix)

    def update_image(self, comment_id, local_image_path=None, original_url=None):
        comment = self.repo.find_by_id(comment_id)
        if not comment:
            raise ValueError("Comment not found")
        return self.repo.update_image(comment_id, local_image_path, original_url)

    def get_stats(self, filters=None):
        return self.repo.stats(filters)

    def get_up_masters(self):
        return self.repo.find_up_masters()

    def get_videos(self):
        return self.repo.find_videos()

    def create_comment(self, data):
        if not data.get("content"):
            raise ValueError("content is required")
        if data.get("platform") not in ("bilibili", "xueqiu", "xiaohongshu", "zhihu", None):
            raise ValueError("Invalid platform value")
        return self.repo.insert(data)

    def delete_comment(self, comment_id):
        deleted = self.repo.delete(comment_id)
        if not deleted:
            raise ValueError("Comment not found")
        return deleted

    def analyze_sentiment(self, filters=None):
        import sys, os, importlib.util

        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        spec = importlib.util.spec_from_file_location(
            "analyze",
            os.path.join(repo_root, "jobs", "sentiment_analyzer", "analyze.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        records = self.repo.find_unlocked_ids_by_filter(filters)
        if not records:
            return {"total_matched": 0, "locked_skipped": 0, "analyzed": 0, "stats": None}

        result = mod.analyze_batch(records)
        updates = [(r["sentiment"], r["score"], r["id"]) for r in result["records"]]
        self.repo.batch_update_sentiment(updates)

        return {
            "analyzed": result["stats"]["total"],
            "stats": result["stats"],
        }

    def get_stats_by_date(self, granularity="day", filters=None):
        if granularity not in ("day", "week", "month"):
            granularity = "day"
        return self.repo.stats_by_date(granularity, filters)
