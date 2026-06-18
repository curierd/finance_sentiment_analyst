"""
散户评论情绪分析 (sentiment_analyzer)

纯库函数模块 — 不直接访问数据库、不生成 HTML。
调用方负责准备数据 (list[dict]) 与结果展示。

公开 API:
    analyze_text(text, *, analyzer=None) -> dict
    analyze_batch(records, *, text_key="content", analyzer=None) -> dict
"""
from collections import Counter
from typing import Any, Iterable

import importlib.util
import os as _os

_spec = importlib.util.spec_from_file_location(
    "textcnn_sentiment",
    _os.path.join(_os.path.dirname(__file__), "textcnn_sentiment.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SentimentAnalyzer = _mod.SentimentAnalyzer

SENTIMENTS: tuple[str, ...] = ("正面", "中性", "负面")


def _analyzer(analyzer: SentimentAnalyzer | None) -> SentimentAnalyzer:
    return analyzer if analyzer is not None else SentimentAnalyzer()


def _empty_counts() -> dict[str, int]:
    return {s: 0 for s in SENTIMENTS}


def _score(scores: dict[str, float]) -> float:
    """综合情绪分:positive - negative。范围与词典命中次数相关,正=偏多,负=偏空。"""
    return round(float(scores.get("positive", 0)) - float(scores.get("negative", 0)), 2)


def _stats(records: list[dict]) -> dict[str, Any]:
    """按情绪类别聚合统计;records 元素须含 'sentiment' 与 'score' 字段。"""
    cnt = Counter(r["sentiment"] for r in records)
    total = sum(cnt.values())
    pct = {s: round(cnt.get(s, 0) / total * 100, 1) if total else 0.0 for s in SENTIMENTS}
    score_sum = round(sum(float(r.get("score", 0)) for r in records), 2)
    return {
        "total": total,
        "counts": {**_empty_counts(), **dict(cnt)},
        "pct": pct,
        "score_sum": score_sum,
        "score_avg": round(score_sum / total, 3) if total else 0.0,
    }


def analyze_text(text: str, *, analyzer: SentimentAnalyzer | None = None) -> dict[str, Any]:
    """分析单条文本。

    Returns:
        {"sentiment": "正面"|"中性"|"负面",
         "scores": {"positive","negative","neutral"},
         "score":  float}  # 综合分 = positive - negative
    """
    a = _analyzer(analyzer).analyze(text or "")
    return {"sentiment": a["sentiment"], "scores": a["scores"], "score": _score(a["scores"])}


def analyze_batch(
    records: Iterable[dict],
    *,
    text_key: str = "content",
    analyzer: SentimentAnalyzer | None = None,
) -> dict[str, Any]:
    """批量分析评论记录。

    保留输入记录的全部字段,并追加 ``text`` / ``sentiment`` / ``scores`` / ``score``。

    Args:
        records: 可迭代的字典序列,每项需含 text_key 指定的文本字段。
        text_key: 文本字段名 (默认 "content")。
        analyzer: 复用已有 SentimentAnalyzer 实例;为空则新建。

    Returns:
        {
          "records": [{...原字段, "text", "sentiment", "scores", "score"}, ...],
          "stats":   {"total","counts","pct","score_sum","score_avg"}
        }
    """
    az = _analyzer(analyzer)
    out: list[dict] = []
    for r in records:
        item = dict(r or {})
        text = str(item.pop(text_key, "") or "")
        a = az.analyze(text)
        item["text"] = text
        item["sentiment"] = a["sentiment"]
        item["scores"] = a["scores"]
        item["score"] = _score(a["scores"])
        out.append(item)
    return {"records": out, "stats": _stats(out)}
