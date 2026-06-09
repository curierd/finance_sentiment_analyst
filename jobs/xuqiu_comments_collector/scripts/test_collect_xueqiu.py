#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for xueqiu comment collector functions"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "jobs" / "xuqiu_comments_collector" / "scripts"))

from collect_xueqiu import (
    load_stock_symbols,
    load_blogger_ids,
    load_blogger_names,
    is_today,
    run_opencli,
)


class TestLoadStockSymbols(unittest.TestCase):
    """Test load_stock_symbols from sections markdown files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sections_dir = Path(self.tmpdir) / "data" / "sections"
        self.sections_dir.mkdir(parents=True)

    def _write_section(self, name, content):
        (self.sections_dir / name).write_text(content, encoding="utf-8")

    @patch("collect_xueqiu.PROJECT_ROOT")
    def test_parses_prefixed_codes_from_laodeng(self, mock_root):
        mock_root.__truediv__ = lambda self, key: Path(self.tmpdir) / key
        mock_root.__rtruediv__ = lambda self, key: Path(key) / Path(self.tmpdir).name
        # Simpler: just patch the sections dir directly
        with patch("collect_xueqiu.PROJECT_ROOT", Path(self.tmpdir)):
            self._write_section("laodeng.md", "SH510050\nSH600519\nSZ000858\n")
            symbols = load_stock_symbols()
            self.assertIn("SH510050", symbols)
            self.assertIn("SH600519", symbols)
            self.assertIn("SZ000858", symbols)

    def test_parses_pure_numeric_codes_from_cpo(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "CPO.md").write_text(
            "## 光模块龙头\n中际旭创(300308)\n新易盛(300502)\n",
            encoding="utf-8",
        )
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertIn("SZ300308", symbols)
            self.assertIn("SZ300502", symbols)

    def test_adds_sh_prefix_for_6x_codes(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "test.md").write_text("工商银行(601398)\n", encoding="utf-8")
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertIn("SH601398", symbols)

    def test_adds_sh_prefix_for_51x_codes(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "test.md").write_text("通信ETF国泰(515880)\n", encoding="utf-8")
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertIn("SH515880", symbols)

    def test_adds_sz_prefix_for_3x_codes(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "test.md").write_text("天孚通信(300394)\n", encoding="utf-8")
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertIn("SZ300394", symbols)

    def test_adds_sz_prefix_for_0x_codes(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "test.md").write_text("光迅通信(002281)\n", encoding="utf-8")
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertIn("SZ002281", symbols)

    def test_adds_sz_prefix_for_159x_codes(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "test.md").write_text("通信ETF银华(159994)\n", encoding="utf-8")
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertIn("SZ159994", symbols)

    def test_skips_comments_and_empty_lines(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "test.md").write_text(
            "# heading\n\nSH600519\n  \n",
            encoding="utf-8",
        )
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertEqual(symbols, ["SH600519"])

    def test_deduplicates_symbols(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "a.md").write_text("SH600519\n", encoding="utf-8")
        (sections_dir / "b.md").write_text("SH600519\n", encoding="utf-8")
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertEqual(symbols.count("SH600519"), 1)

    def test_mixed_formats_in_same_file(self):
        tmpdir = tempfile.mkdtemp()
        sections_dir = Path(tmpdir) / "data" / "sections"
        sections_dir.mkdir(parents=True)
        (sections_dir / "mixed.md").write_text(
            "SH510050\n中际旭创(300308)\n",
            encoding="utf-8",
        )
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertIn("SH510050", symbols)
            self.assertIn("SZ300308", symbols)
            self.assertEqual(len(symbols), 2)

    def test_no_sections_dir_returns_empty(self):
        tmpdir = tempfile.mkdtemp()
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            symbols = load_stock_symbols()
            self.assertEqual(symbols, [])


class TestLoadBloggerIds(unittest.TestCase):
    """Test load_blogger_ids from xueqiu-finance-up.md."""

    def test_extracts_ids_from_table(self):
        tmpdir = tempfile.mkdtemp()
        up_dir = Path(tmpdir) / "jobs" / "xuqiu_comments_collector"
        up_dir.mkdir(parents=True)
        (up_dir / "xueqiu-finance-up.md").write_text(
            "| 1 | 柯中 | 5243796549 | url | trend |\n"
            "| 2 | 闷得而蜜 | 5672579962 | url | tech |\n",
            encoding="utf-8",
        )
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            ids = load_blogger_ids()
            self.assertEqual(ids, ["5243796549", "5672579962"])

    def test_ignores_header_rows(self):
        tmpdir = tempfile.mkdtemp()
        up_dir = Path(tmpdir) / "jobs" / "xuqiu_comments_collector"
        up_dir.mkdir(parents=True)
        (up_dir / "xueqiu-finance-up.md").write_text(
            "| 排名 | 博主 | ID | 主页 | 特点 |\n"
            "|------|------|-----|------|------|\n"
            "| 1 | 柯中 | 5243796549 | url | trend |\n",
            encoding="utf-8",
        )
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            ids = load_blogger_ids()
            self.assertEqual(ids, ["5243796549"])


class TestLoadBloggerNames(unittest.TestCase):
    """Test load_blogger_names from xueqiu-finance-up.md."""

    def test_maps_name_to_id(self):
        tmpdir = tempfile.mkdtemp()
        up_dir = Path(tmpdir) / "jobs" / "xuqiu_comments_collector"
        up_dir.mkdir(parents=True)
        (up_dir / "xueqiu-finance-up.md").write_text(
            "| 1 | 柯中 | 5243796549 | url | trend |\n"
            "| 2 | 闷得而蜜 | 5672579962 | url | tech |\n",
            encoding="utf-8",
        )
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            names = load_blogger_names()
            self.assertEqual(names["柯中"], "5243796549")
            self.assertEqual(names["闷得而蜜"], "5672579962")

    def test_only_extracts_from_5column_hot_table(self):
        # The regex matches 5-column hot tables: | rank | name | id | url | desc |
        # 3-column tables (个股讨论) are not matched by load_blogger_names
        tmpdir = tempfile.mkdtemp()
        up_dir = Path(tmpdir) / "jobs" / "xuqiu_comments_collector"
        up_dir.mkdir(parents=True)
        (up_dir / "xueqiu-finance-up.md").write_text(
            "| 1 | 柯中 | 5243796549 | url | trend |\n"
            "| 博主 | ID | 主页 |\n"
            "|------|-----|------|\n"
            "| 镜鉴集 | 2784573651 | url |\n",
            encoding="utf-8",
        )
        with patch("collect_xueqiu.PROJECT_ROOT", Path(tmpdir)):
            names = load_blogger_names()
            self.assertEqual(names.get("柯中"), "5243796549")
            self.assertNotIn("镜鉴集", names)  # 3-col table not matched


class TestIsToday(unittest.TestCase):
    """Test is_today date matching."""

    def test_matching_date(self):
        self.assertTrue(is_today("2026-06-09T06:00:36.000Z", "2026-06-09"))

    def test_different_date(self):
        self.assertFalse(is_today("2026-06-08T06:00:36.000Z", "2026-06-09"))

    def test_none_date(self):
        self.assertFalse(is_today(None, "2026-06-09"))

    def test_empty_string(self):
        self.assertFalse(is_today("", "2026-06-09"))

    def test_invalid_format(self):
        self.assertFalse(is_today("not-a-date", "2026-06-09"))

    def test_date_only_without_time(self):
        # "2026-06-09" without timezone parses as a date, fromisoformat succeeds
        self.assertTrue(is_today("2026-06-09", "2026-06-09"))

    def test_midnight_boundary(self):
        self.assertTrue(is_today("2026-06-09T00:00:00.000Z", "2026-06-09"))

    def test_end_of_day(self):
        self.assertTrue(is_today("2026-06-09T23:59:59.000Z", "2026-06-09"))


class TestRunOpencli(unittest.TestCase):
    """Test run_opencli with mocked subprocess."""

    @patch("collect_xueqiu.subprocess.run")
    def test_returns_parsed_json_on_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='[{"author": "test"}]'
        )
        result = run_opencli(["xueqiu", "comments", "SH600519", "-f", "json"])
        self.assertEqual(result, [{"author": "test"}])

    @patch("collect_xueqiu.subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        result = run_opencli(["xueqiu", "comments", "INVALID", "-f", "json"], max_retries=1)
        self.assertIsNone(result)

    @patch("collect_xueqiu.subprocess.run")
    def test_returns_none_on_empty_stdout(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = run_opencli(["xueqiu", "comments", "SH600519", "-f", "json"], max_retries=1)
        self.assertIsNone(result)

    @patch("collect_xueqiu.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="opencli", timeout=120)
        result = run_opencli(["xueqiu", "comments", "SH600519", "-f", "json"], max_retries=1)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
