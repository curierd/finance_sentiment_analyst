#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze sentiment for all comments in the database"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import sqlite3
import sys
sys.path.insert(0, ".")
from textcnn_sentiment import SentimentAnalyzer

DB_PATH = "db/comments.db"
BATCH = 50


def main():
    analyzer = SentimentAnalyzer()
    conn = sqlite3.connect(DB_PATH)

    # Process in batches to show progress
    cur = conn.execute("SELECT COUNT(*) FROM comments WHERE sentiment IS NULL")
    total = cur.fetchone()[0]
    print("Analyzing %d comments..." % total)

    offset = 0
    updated = 0
    while True:
        rows = conn.execute(
            "SELECT id, content FROM comments WHERE sentiment IS NULL LIMIT ?",
            (BATCH,)
        ).fetchall()
        if not rows:
            break

        for row_id, content in rows:
            if not content or not content.strip():
                conn.execute(
                    "UPDATE comments SET sentiment='neutral', sentiment_score=0.0 WHERE id=?",
                    (row_id,)
                )
            else:
                result = analyzer.analyze(content)
                score = result['scores']['positive'] - result['scores']['negative']
                conn.execute(
                    "UPDATE comments SET sentiment=?, sentiment_score=? WHERE id=?",
                    (result['sentiment'], score, row_id)
                )
            updated += 1

        offset += len(rows)
        print("  Progress: %d / %d" % (offset, total))
        time_module.sleep(0.05)

    conn.commit()

    # Summary
    cur = conn.execute("SELECT sentiment, COUNT(*) FROM comments GROUP BY sentiment")
    print("\nSentiment distribution:")
    for label, cnt in cur.fetchall():
        print("  %s: %d" % (label, cnt))

    conn.close()
    print("\nDone. Updated %d records." % updated)


if __name__ == "__main__":
    import time as time_module
    main()