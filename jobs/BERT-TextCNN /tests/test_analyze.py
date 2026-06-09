#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the BERT-TextCNN analyzer library.

Test location: ``jobs/BERT-TextCNN /tests/test_analyze.py`` (co-located with the
module under test). Run via ``unittest discover`` to avoid the trailing-space
package-name issue:

    python -m unittest discover -s "jobs/BERT-TextCNN /tests" -p "test_*.py" -v
"""
import importlib.util
import os
import sys
import unittest


# jobs/BERT-TextCNN /tests/test_analyze.py  →  repo root is 3 dirs up
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANALYZER_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "analyze.py"))
sys.path.insert(0, REPO_ROOT)  # so textcnn_sentiment resolves at import time


def _load_analyzer():
    spec = importlib.util.spec_from_file_location("bert_textcnn_analyze", ANALYZER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ANALYZER = _load_analyzer()
SENTIMENTS = ANALYZER.SENTIMENTS
analyze_text = ANALYZER.analyze_text
analyze_batch = ANALYZER.analyze_batch


# ---------- shared corpus ----------
POS_TEXT = "A股大涨，赚钱了，太开心了！"     # 涨 / 赚钱 → 正面
NEG_TEXT = "又跌了，割肉跑路，心态崩了"     # 跌 / 割肉 / 崩 → 负面
NEU_TEXT = "震荡行情，观望为主"             # 震荡 / 观望 → 中性


class TestAnalyzeText(unittest.TestCase):
    def test_returns_dict_with_expected_keys(self):
        r = analyze_text(POS_TEXT)
        self.assertIsInstance(r, dict)
        self.assertIn("sentiment", r)
        self.assertIn("scores", r)

    def test_sentiment_is_valid_label(self):
        r = analyze_text(POS_TEXT)
        self.assertIn(r["sentiment"], SENTIMENTS)

    def test_scores_contain_all_three_axes(self):
        r = analyze_text(POS_TEXT)
        self.assertEqual(set(r["scores"]), {"positive", "negative", "neutral"})
        for v in r["scores"].values():
            self.assertIsInstance(v, (int, float))

    def test_positive_text(self):
        r = analyze_text(POS_TEXT)
        self.assertEqual(r["sentiment"], "正面")
        self.assertGreater(r["scores"]["positive"], 0)

    def test_negative_text(self):
        r = analyze_text(NEG_TEXT)
        self.assertEqual(r["sentiment"], "负面")
        self.assertGreater(r["scores"]["negative"], 0)

    def test_neutral_text(self):
        r = analyze_text(NEU_TEXT)
        self.assertEqual(r["sentiment"], "中性")

    def test_empty_string_is_neutral(self):
        r = analyze_text("")
        self.assertEqual(r["sentiment"], "中性")
        self.assertEqual(r["scores"], {"positive": 0, "negative": 0, "neutral": 0})

    def test_none_text_is_neutral(self):
        r = analyze_text(None)
        self.assertEqual(r["sentiment"], "中性")

    def test_passes_through_existing_analyzer(self):
        from textcnn_sentiment import SentimentAnalyzer
        az = SentimentAnalyzer()
        r = analyze_text(POS_TEXT, analyzer=az)
        self.assertEqual(r["sentiment"], "正面")

    def test_score_field_is_signed_float(self):
        r = analyze_text(POS_TEXT)
        self.assertIn("score", r)
        self.assertIsInstance(r["score"], float)
        self.assertGreater(r["score"], 0)

    def test_score_sign_matches_sentiment(self):
        self.assertGreater(analyze_text(POS_TEXT)["score"], 0)
        self.assertLess(analyze_text(NEG_TEXT)["score"], 0)
        self.assertEqual(analyze_text(NEU_TEXT)["score"], 0.0)

    def test_empty_text_score_is_zero(self):
        self.assertEqual(analyze_text("")["score"], 0.0)
        self.assertEqual(analyze_text(None)["score"], 0.0)


class TestAnalyzeBatch(unittest.TestCase):
    def test_returns_records_and_stats(self):
        out = analyze_batch([{"content": POS_TEXT}, {"content": NEG_TEXT}, {"content": NEU_TEXT}])
        self.assertIn("records", out)
        self.assertIn("stats", out)
        self.assertEqual(len(out["records"]), 3)
        self.assertEqual(out["stats"]["total"], 3)

    def test_stats_counts_match_sentiments(self):
        records = [{"content": POS_TEXT}] * 2 + [{"content": NEG_TEXT}] * 1 + [{"content": NEU_TEXT}] * 4
        out = analyze_batch(records)
        self.assertEqual(out["stats"]["counts"]["正面"], 2)
        self.assertEqual(out["stats"]["counts"]["负面"], 1)
        self.assertEqual(out["stats"]["counts"]["中性"], 4)
        # pct must sum to 100 (or 0 for empty)
        self.assertAlmostEqual(sum(out["stats"]["pct"].values()), 100.0, places=1)

    def test_records_preserve_input_fields(self):
        records = [{"platform": "bilibili", "author": "A", "likes": 5, "content": POS_TEXT}]
        out = analyze_batch(records)
        rec = out["records"][0]
        self.assertEqual(rec["platform"], "bilibili")
        self.assertEqual(rec["author"], "A")
        self.assertEqual(rec["likes"], 5)
        self.assertEqual(rec["sentiment"], "正面")
        self.assertIn("scores", rec)

    def test_text_key_can_be_customized(self):
        records = [{"msg": POS_TEXT}, {"msg": NEG_TEXT}]
        out = analyze_batch(records, text_key="msg")
        self.assertEqual(out["records"][0]["text"], POS_TEXT)
        self.assertEqual(out["records"][0]["sentiment"], "正面")
        self.assertEqual(out["records"][1]["sentiment"], "负面")
        # original 'msg' key is consumed and replaced with 'text'
        self.assertNotIn("msg", out["records"][0])

    def test_empty_input(self):
        out = analyze_batch([])
        self.assertEqual(out["records"], [])
        self.assertEqual(out["stats"]["total"], 0)
        self.assertEqual(out["stats"]["counts"], {"正面": 0, "中性": 0, "负面": 0})
        self.assertEqual(out["stats"]["pct"], {"正面": 0.0, "中性": 0.0, "负面": 0.0})

    def test_works_with_iterable_not_just_list(self):
        out = analyze_batch(iter([{"content": POS_TEXT}, {"content": NEG_TEXT}]))
        self.assertEqual(out["stats"]["total"], 2)
        self.assertEqual(out["stats"]["counts"]["正面"], 1)
        self.assertEqual(out["stats"]["counts"]["负面"], 1)

    def test_uses_provided_analyzer_instance(self):
        from textcnn_sentiment import SentimentAnalyzer
        az = SentimentAnalyzer()
        out = analyze_batch([{"content": POS_TEXT}, {"content": NEG_TEXT}], analyzer=az)
        # sanity: both records analyzed without raising
        self.assertEqual(len(out["records"]), 2)

    def test_record_with_missing_text_key(self):
        out = analyze_batch([{"platform": "x", "content": ""}])
        self.assertEqual(out["records"][0]["sentiment"], "中性")

    def test_records_have_score_field(self):
        out = analyze_batch([{"content": POS_TEXT}, {"content": NEG_TEXT}])
        for r in out["records"]:
            self.assertIn("score", r)
            self.assertIsInstance(r["score"], float)

    def test_stats_score_sum_and_avg(self):
        records = [{"content": POS_TEXT}] * 2 + [{"content": NEG_TEXT}] * 1
        out = analyze_batch(records)
        s = out["stats"]
        self.assertIn("score_sum", s)
        self.assertIn("score_avg", s)
        self.assertEqual(s["score_sum"], round(2 * out["records"][0]["score"] + out["records"][2]["score"], 2))
        self.assertEqual(s["score_avg"], round(s["score_sum"] / s["total"], 3))

    def test_empty_batch_score_is_zero(self):
        out = analyze_batch([])
        self.assertEqual(out["stats"]["score_sum"], 0.0)
        self.assertEqual(out["stats"]["score_avg"], 0.0)


if __name__ == "__main__":
    unittest.main()
