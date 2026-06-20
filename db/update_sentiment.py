#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze sentiment for all comments in the database (LLM-based)"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import sqlite3
import importlib.util
sys.path.insert(0, ".")

# 默认模型选择：DeepSeek（便宜且中文强）
_LLM_SOURCE = os.environ.get("LLM_SOURCE", "deepseek")
if _LLM_SOURCE == "deepseek":
    os.environ.setdefault("LLM_BASE_URL", "https://api.deepseek.com")
    os.environ.setdefault("LLM_MODEL", "deepseek-v4-pro")
elif _LLM_SOURCE == "openai":
    os.environ.setdefault("LLM_BASE_URL", "https://api.openai.com/v1")
    os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")

_spec = importlib.util.spec_from_file_location(
    "llm_sentiment", "jobs/sentiment_analyzer/llm_sentiment.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SentimentAnalyzer = _mod.SentimentAnalyzer

DB_PATH = "db/comments.db"
BATCH = 20


def main(dry_run=False, limit=None):
    analyzer = SentimentAnalyzer()
    conn = sqlite3.connect(DB_PATH)

    cur = conn.execute(
        "SELECT COUNT(*) FROM comments WHERE sentiment IS NULL AND sentiment_fix IS NULL"
    )
    total = cur.fetchone()[0]
    if limit and limit < total:
        total = limit
    print("Analyzing %d comments (skipping locked rows)..." % total)
    print("  Model: %s  |  Base: %s" % (analyzer.model, analyzer.base_url))

    offset = 0
    updated = 0
    while True:
        query = (
            "SELECT id, content FROM comments "
            "WHERE sentiment IS NULL AND sentiment_fix IS NULL "
            "LIMIT ?"
        )
        rows = conn.execute(query, (BATCH,)).fetchall()
        if not rows or (limit and offset >= limit):
            break

        for row_id, content in rows:
            if limit and updated >= limit:
                break
            if not content or not content.strip():
                conn.execute(
                    "UPDATE comments SET sentiment='中性', sentiment_score=0.0 WHERE id=?",
                    (row_id,)
                )
            else:
                result = analyzer.analyze(content)
                score = round(result['scores']['positive'] - result['scores']['negative'], 4)
                if not dry_run:
                    conn.execute(
                        "UPDATE comments SET sentiment=?, sentiment_score=? WHERE id=?",
                        (result['sentiment'], score, row_id)
                    )
            updated += 1

        offset += len(rows)
        if not dry_run:
            conn.commit()
        print("  Progress: %d / %d" % (min(updated, total), total))
        time_module.sleep(1.0)  # API rate limit: 1s between batches

    if not dry_run:
        conn.commit()

    cur = conn.execute(
        "SELECT COALESCE(sentiment_fix, sentiment) as s, COUNT(*) FROM comments GROUP BY s"
    )
    print("\nSentiment distribution:")
    for label, cnt in cur.fetchall():
        print("  %s: %d" % (label, cnt))

    conn.close()
    mode = "Dry-run" if dry_run else "Done"
    print("\n%s. Processed %d records." % (mode, updated))


if __name__ == "__main__":
    import time as time_module
    import argparse

    parser = argparse.ArgumentParser(description="Batch sentiment analysis via LLM")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without writing to DB")
    parser.add_argument("--limit", type=int, default=None, help="Max comments to process")
    args = parser.parse_args()
    main(dry_run=args.dry_run, limit=args.limit)