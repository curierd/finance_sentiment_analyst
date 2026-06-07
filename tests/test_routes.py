#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration tests for comment routes via Flask test client"""

import unittest
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from backend.routes.comment_routes import comment_bp


class TestRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sqlite3, os
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "comments.db")
        conn = sqlite3.connect(db_path)
        cls.test_id = conn.execute("SELECT id FROM comments LIMIT 1").fetchone()[0]
        conn.close()
        app = Flask(__name__)
        app.register_blueprint(comment_bp)
        cls.client = app.test_client()

    def test_get_comments_returns_200(self):
        resp = self.client.get("/api/comments")
        self.assertEqual(resp.status_code, 200)

    def test_get_comments_returns_items(self):
        resp = self.client.get("/api/comments")
        data = resp.get_json()
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_get_comments_filter_platform(self):
        resp = self.client.get("/api/comments?platform=bilibili")
        data = resp.get_json()
        for item in data["items"]:
            self.assertEqual(item["platform"], "bilibili")

    def test_get_comments_filter_locked(self):
        resp = self.client.get("/api/comments?locked=1")
        data = resp.get_json()
        for item in data["items"]:
            self.assertIsNotNone(item.get("sentiment_fix"))

    def test_get_comments_filter_sentiment(self):
        resp = self.client.get("/api/comments?sentiment=正面")
        data = resp.get_json()
        for item in data["items"]:
            effective = item.get("sentiment_fix") or item.get("sentiment")
            self.assertEqual(effective, "正面")

    def test_get_comments_pagination(self):
        resp = self.client.get("/api/comments?page=1&page_size=10")
        data = resp.get_json()
        self.assertLessEqual(len(data["items"]), 10)
        self.assertEqual(data["page"], 1)

    def test_get_single_comment_returns_200(self):
        resp = self.client.get("/api/comments/" + str(self.test_id))
        self.assertEqual(resp.status_code, 200)

    def test_get_single_comment_returns_200_for_missing(self):
        # API returns 200 with null body for missing IDs (not 404)
        resp = self.client.get("/api/comments/999999")
        self.assertEqual(resp.status_code, 200)

    def test_patch_comment_lock(self):
        resp = self.client.patch("/api/comments/" + str(self.test_id),
            json={"sentiment_fix": "负面"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data["sentiment_fix"], "负面")

    def test_patch_comment_rejects_created_at(self):
        resp = self.client.patch("/api/comments/" + str(self.test_id),
            json={"sentiment_fix": "正面", "created_at": "2026-01-01"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("created_at", resp.get_json().get("error", ""))

    def test_patch_comment_unlock(self):
        self.client.patch("/api/comments/" + str(self.test_id),
            json={"sentiment_fix": None},
            content_type="application/json")
        resp = self.client.get("/api/comments/" + str(self.test_id))
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertIsNone(data.get("sentiment_fix"))

    def test_post_comment_create(self):
        resp = self.client.post("/api/comments",
            json={"platform": "xueqiu", "content": "测试评论", "author_name": "测试用户"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertIn("id", data)
        self.assertEqual(data["content"], "测试评论")

    def test_post_comment_rejects_empty_content(self):
        resp = self.client.post("/api/comments",
            json={"platform": "xueqiu", "content": ""},
            content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_delete_comment_returns_success(self):
        # Create then delete
        resp = self.client.post("/api/comments",
            json={"platform": "xueqiu", "content": "待删除评论"},
            content_type="application/json")
        new_id = resp.get_json()["id"]
        del_resp = self.client.delete("/api/comments/" + str(new_id))
        self.assertEqual(del_resp.status_code, 200)

    def test_delete_comment_returns_404_for_missing(self):
        resp = self.client.delete("/api/comments/999999")
        self.assertEqual(resp.status_code, 404)

    def test_get_stats_timeline_returns_200(self):
        resp = self.client.get("/api/stats/timeline")
        self.assertEqual(resp.status_code, 200)

    def test_get_stats_timeline_has_period_keys(self):
        resp = self.client.get("/api/stats/timeline?granularity=day")
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        periods = list(data.keys())
        if periods:
            self.assertIn("total", data[periods[0]])

    def test_get_stats_timeline_granularity(self):
        for g in ("day", "week", "month"):
            resp = self.client.get("/api/stats/timeline?granularity=" + g)
            self.assertEqual(resp.status_code, 200)

    def test_get_stats_returns_200(self):
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)

    def test_get_stats_has_required_fields(self):
        resp = self.client.get("/api/stats")
        data = resp.get_json()
        for key in ("auto", "locked", "like_weighted", "auto_count", "locked_count"):
            self.assertIn(key, data)

    def test_get_up_masters_returns_200(self):
        resp = self.client.get("/api/up_masters")
        self.assertEqual(resp.status_code, 200)

    def test_get_videos_returns_200(self):
        resp = self.client.get("/api/videos")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()