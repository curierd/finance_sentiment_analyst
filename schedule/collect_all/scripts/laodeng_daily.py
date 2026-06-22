#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schedule 入口薄壳 — 调用 jobs.sentiment_analyzer.laodeng.laodeng_daily.main()

实现位于 jobs/sentiment_analyzer/laodeng/laodeng_daily.py。
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from jobs.sentiment_analyzer.laodeng.laodeng_daily import main  # noqa: E402

if __name__ == "__main__":
    main()