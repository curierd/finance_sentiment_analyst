#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for collect_zhihu.py — parser, extractors, and date filtering."""

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import collect_zhihu as cz

CST = timezone(timedelta(hours=8))


class TestParseSearchTerms(unittest.TestCase):
    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("")
            fname = f.name
        try:
            result = cz.parse_search_terms(Path(fname))
            self.assertEqual(result, [])
        finally:
            os.unlink(fname)

    def test_terms_with_categories(self):
        content = "## 今日行情\nA股\n今日A股\n\n## 投资讨论\nA股投资\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(content)
            fname = f.name
        try:
            result = cz.parse_search_terms(Path(fname))
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]["category"], "今日行情")
            self.assertEqual(result[0]["query"], "A股")
            self.assertEqual(result[2]["category"], "投资讨论")
            self.assertEqual(result[2]["query"], "A股投资")
        finally:
            os.unlink(fname)

    def test_skip_comments_and_empty_lines(self):
        content = "# 标题\n## 类别1\n词1\n\n\n## 类别2\n\n词2\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(content)
            fname = f.name
        try:
            result = cz.parse_search_terms(Path(fname))
            self.assertEqual(len(result), 2)
        finally:
            os.unlink(fname)

    def test_file_not_found(self):
        result = cz.parse_search_terms(Path("/nonexistent/file.md"))
        self.assertEqual(result, [])


class TestExtractAnswerId(unittest.TestCase):
    def test_standard_url(self):
        url = "https://www.zhihu.com/question/2046291720967558887/answer/2048069807761840029"
        self.assertEqual(cz._extract_answer_id(url), "2048069807761840029")

    def test_answer_id_from_search_result(self):
        url = "https://www.zhihu.com/question/2047304908106371408/answer/2047718871499534342"
        self.assertEqual(cz._extract_answer_id(url), "2047718871499534342")

    def test_no_answer(self):
        url = "https://www.zhihu.com/question/2046291720967558887"
        self.assertIsNone(cz._extract_answer_id(url))

    def test_empty_url(self):
        self.assertIsNone(cz._extract_answer_id(""))


class TestExtractQuestionId(unittest.TestCase):
    def test_standard_url(self):
        url = "https://www.zhihu.com/question/2046291720967558887/answer/2048069807761840029"
        self.assertEqual(cz._extract_question_id(url), "2046291720967558887")

    def test_no_question(self):
        url = "https://www.zhihu.com/other/123"
        self.assertIsNone(cz._extract_question_id(url))


class TestExtractAnswerIds(unittest.TestCase):
    def test_extracts_only_answers(self):
        results = [
            {"type": "answer", "title": "怎么看A股", "author": "用户1", "votes": 5,
             "url": "https://www.zhihu.com/question/123/answer/456"},
            {"type": "question", "title": "A股问题", "author": "", "votes": 0,
             "url": "https://www.zhihu.com/question/789"},
            {"type": "answer", "title": "怎么看A股", "author": "用户2", "votes": 10,
             "url": "https://www.zhihu.com/question/123/answer/999"},
        ]
        result = cz.extract_answer_ids(results)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["answer_id"], "456")
        self.assertEqual(result[1]["answer_id"], "999")
        self.assertEqual(result[0]["question_id"], "123")

    def test_empty_list(self):
        result = cz.extract_answer_ids([])
        self.assertEqual(result, [])

    def test_duplicate_answers(self):
        results = [
            {"type": "answer", "title": "T", "author": "A", "votes": 1,
             "url": "https://www.zhihu.com/question/1/answer/100"},
            {"type": "answer", "title": "T", "author": "B", "votes": 2,
             "url": "https://www.zhihu.com/question/2/answer/100"},
        ]
        result = cz.extract_answer_ids(results)
        self.assertEqual(len(result), 1)


class TestIsTodayCST(unittest.TestCase):
    def setUp(self):
        self.today = date.today().isoformat()

    def test_today_utc_morning(self):
        utc_str = f"{self.today}T00:30:00.000Z"
        self.assertTrue(cz.is_today_cst(utc_str, self.today))

    def test_today_utc_evening(self):
        utc_str = f"{self.today}T12:00:00.000Z"
        self.assertTrue(cz.is_today_cst(utc_str, self.today))

    def test_yesterday_utc_late(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        utc_str = f"{yesterday}T18:00:00.000Z"
        self.assertTrue(cz.is_today_cst(utc_str, self.today))

    def test_tomorrow_utc_early(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        utc_str = f"{tomorrow}T15:00:00.000Z"
        self.assertFalse(cz.is_today_cst(utc_str, self.today))

    def test_past_date(self):
        self.assertFalse(cz.is_today_cst("2026-01-01T08:00:00.000Z", self.today))

    def test_empty_string(self):
        self.assertFalse(cz.is_today_cst("", self.today))

    def test_invalid_date(self):
        self.assertFalse(cz.is_today_cst("not-a-date", self.today))

    def test_no_z_suffix(self):
        utc_str = f"{self.today}T08:00:00+00:00"
        self.assertTrue(cz.is_today_cst(utc_str, self.today))


class TestExtractImageUrls(unittest.TestCase):
    def test_simple_url(self):
        content = "文字 https://example.com/img.jpg 更多文字"
        result = cz.extract_image_urls(content)
        self.assertIn("https://example.com/img.jpg", result)

    def test_img_tag(self):
        content = '文字 <img src="https://example.com/photo.png" /> 文字'
        result = cz.extract_image_urls(content)
        self.assertIn("https://example.com/photo.png", result)

    def test_no_images(self):
        content = "纯文字内容，没有图片链接"
        result = cz.extract_image_urls(content)
        self.assertEqual(result, [])

    def test_deduplication(self):
        content = "https://example.com/a.jpg https://example.com/a.jpg"
        result = cz.extract_image_urls(content)
        self.assertEqual(len(result), 1)


class TestCollectZhihuScript(unittest.TestCase):
    def test_module_can_be_imported(self):
        self.assertTrue(hasattr(cz, "main"))
        self.assertTrue(hasattr(cz, "parse_search_terms"))
        self.assertTrue(hasattr(cz, "extract_answer_ids"))
        self.assertTrue(hasattr(cz, "fetch_comments"))
        self.assertTrue(hasattr(cz, "is_today_cst"))
        self.assertTrue(hasattr(cz, "import_comments"))


if __name__ == "__main__":
    unittest.main()
