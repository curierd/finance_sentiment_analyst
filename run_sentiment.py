#!/usr/bin/env python3
"""Run sentiment analysis on all comments without sentiment."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, '.')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs', 'sentiment_analyzer'))

import sqlite3
from textcnn_sentiment import SentimentAnalyzer

from backend.config import DB_PATH as DB_PATH
BATCH = 50


def main():
    analyzer = SentimentAnalyzer()
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute(
        "SELECT COUNT(*) FROM comments WHERE sentiment IS NULL AND sentiment_fix IS NULL"
    ).fetchone()[0]
    print(f"Analyzing {total} comments...")

    updated = 0
    while True:
        rows = conn.execute(
            "SELECT id, content FROM comments WHERE sentiment IS NULL AND sentiment_fix IS NULL LIMIT ?",
            (BATCH,),
        ).fetchall()
        if not rows:
            break
        for row_id, content in rows:
            if not content or not content.strip():
                conn.execute(
                    "UPDATE comments SET sentiment='中性', sentiment_score=0.0 WHERE id=?",
                    (row_id,),
                )
            else:
                try:
                    result = analyzer.analyze(content)
                    score = result["scores"]["positive"] - result["scores"]["negative"]
                    conn.execute(
                        "UPDATE comments SET sentiment=?, sentiment_score=? WHERE id=?",
                        (result["sentiment"], score, row_id),
                    )
                except Exception as e:
                    print(f"  err id={row_id}: {e}")
            updated += 1
        conn.commit()
        if updated % 200 == 0 or updated == total:
            print(f"  Progress: {updated} / {total}")
    print(f"Done: {updated} updated")

    print("\nFinal sentiment distribution:")
    for r in conn.execute(
        "SELECT sentiment, COUNT(*) FROM comments GROUP BY sentiment"
    ).fetchall():
        print(f"  {r[0]}: {r[1]}")


if __name__ == "__main__":
    main()
