#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for comment service"""

import unittest
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import setup_test_db
from backend.services.comment_service import CommentService


def setUpModule():
    setup_test_db()


class TestCommentService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = CommentService()

    def _get_first_id(self):
        """Get a real comment ID from the isolated test DB."""
        result = self.svc.list_comments({"page_size": 1})
        self.assertGreater(len(result["items"]), 0)
        return result["items"][0]["id"]

    def test_list_comments_returns_pagination(self):
        result = self.svc.list_comments()
        self.assertIn("items", result)
        self.assertIn("total", result)
        self.assertIn("pages", result)

    def test_get_comment_returns_dict(self):
        row_id = self._get_first_id()
        result = self.svc.get_comment(row_id)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["id"], row_id)

    def test_get_comment_returns_none_for_missing(self):
        result = self.svc.get_comment(999999)
        self.assertIsNone(result)

    def test_lock_sentiment_validates_positive(self):
        row_id = self._get_first_id()
        result = self.svc.lock_sentiment(row_id, "正面")
        self.assertIsNotNone(result)
        self.assertEqual(result["sentiment_fix"], "正面")

    def test_lock_sentiment_validates_negative(self):
        row_id = self._get_first_id()
        result = self.svc.lock_sentiment(row_id, "负面")
        self.assertIsNotNone(result)
        self.assertEqual(result["sentiment_fix"], "负面")

    def test_lock_sentiment_validates_neutral(self):
        row_id = self._get_first_id()
        result = self.svc.lock_sentiment(row_id, "中性")
        self.assertIsNotNone(result)
        self.assertEqual(result["sentiment_fix"], "中性")

    def test_lock_sentiment_rejects_invalid(self):
        row_id = self._get_first_id()
        with self.assertRaises(ValueError):
            self.svc.lock_sentiment(row_id, "positive")  # English not allowed

    def test_lock_sentiment_allows_null(self):
        row_id = self._get_first_id()
        result = self.svc.lock_sentiment(row_id, None)
        self.assertIsNone(result["sentiment_fix"])

    def test_get_stats_returns_all_keys(self):
        stats = self.svc.get_stats()
        self.assertIn("auto", stats)
        self.assertIn("locked", stats)
        self.assertIn("like_weighted", stats)

    def test_get_up_masters_returns_list(self):
        result = self.svc.get_up_masters()
        self.assertIsInstance(result, list)

    def test_get_videos_returns_list(self):
        result = self.svc.get_videos()
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
