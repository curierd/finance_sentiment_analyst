#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for comment repository"""

import unittest
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.repositories.comment_repository import CommentRepository


class TestCommentRepository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = CommentRepository()

    def test_find_all_returns_pagination_keys(self):
        result = self.repo.find_all()
        for key in ("items", "total", "page", "page_size", "pages"):
            self.assertIn(key, result)

    def test_find_all_page_1_has_50_or_fewer_items(self):
        result = self.repo.find_all({"page": 1, "page_size": 50})
        self.assertLessEqual(len(result["items"]), 50)
        self.assertEqual(result["page"], 1)

    def test_find_all_filters_by_platform(self):
        result = self.repo.find_all({"platform": "bilibili"})
        for item in result["items"]:
            self.assertEqual(item["platform"], "bilibili")

    def test_find_all_filters_by_sentiment(self):
        result = self.repo.find_all({"sentiment": "正面"})
        for item in result["items"]:
            effective = item.get("sentiment_fix") or item.get("sentiment")
            self.assertEqual(effective, "正面")

    def test_find_all_filters_by_locked_0(self):
        result = self.repo.find_all({"locked": "0"})
        for item in result["items"]:
            self.assertIsNone(item.get("sentiment_fix"))

    def test_find_all_filters_by_locked_1(self):
        result = self.repo.find_all({"locked": "1"})
        for item in result["items"]:
            self.assertIsNotNone(item.get("sentiment_fix"))

    def test_find_all_author_filter(self):
        result = self.repo.find_all({"author": "投资随感录"})
        self.assertGreater(result["total"], 0)
        for item in result["items"]:
            self.assertIn("投资随感录", item.get("author_name", ""))

    def test_find_by_id_returns_none_for_missing(self):
        row = self.repo.find_by_id(999999)
        self.assertIsNone(row)

    def test_find_by_id_returns_valid_row(self):
        # Use a real ID from the DB
        import sqlite3
        conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "comments.db"))
        row_id = conn.execute("SELECT id FROM comments LIMIT 1").fetchone()[0]
        conn.close()
        row = self.repo.find_by_id(row_id)
        self.assertIsInstance(row, dict)
        self.assertEqual(row["id"], row_id)

    def test_stats_returns_required_keys(self):
        stats = self.repo.stats()
        for key in ("auto", "locked", "locked_count", "auto_count", "like_weighted"):
            self.assertIn(key, stats)
        self.assertIsInstance(stats["auto"], dict)
        self.assertIsInstance(stats["like_weighted"], dict)

    def test_stats_like_weighted_sums_to_100(self):
        stats = self.repo.stats()
        lw = stats["like_weighted"]
        total = sum(lw.values())
        self.assertAlmostEqual(total, 100.0, delta=0.2)

    def test_find_up_masters_returns_list(self):
        result = self.repo.find_up_masters()
        self.assertIsInstance(result, list)

    def test_find_videos_returns_list(self):
        result = self.repo.find_videos()
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()