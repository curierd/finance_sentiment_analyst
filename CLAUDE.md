# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Install dependencies

```bash
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --system
uv pip install jieba scikit-learn numpy --system
```

### Run the sentiment analyzer smoke test

```bash
python textcnn_sentiment.py
```

### Quick single-comment check

```bash
python -c "from textcnn_sentiment import SentimentAnalyzer; print(SentimentAnalyzer().analyze('A股大涨，赚钱了！'))"
```

### Run unit tests

```bash
python -m unittest tests.test_comment_repository tests.test_comment_service tests.test_routes -v
```

### Start the Flask API + frontend

```bash
cd frontend && pip install -r requirements.txt && python server.py
# → http://localhost:5000
```

### Batch-update sentiment in the database

```bash
python db/update_sentiment.py
```

### Fetch platform data

```bash
# Bilibili
bili video <BV_ID> --comments --json
bili video <BV_ID> --comments --json --ai

# Xueqiu (opencli)
opencli xueqiu --comments

# Xiaohongshu (xhs CLI)
xhs collect <note_id>
```

When collecting Bilibili data, wait ≥1 s between requests to avoid 412 risk-control. On 412, switch to `opencli bilibili`.

## Architecture

### Sentiment analysis core (`textcnn_sentiment.py`)

- `TextCNN` is a PyTorch CNN text classifier (defined but not used by the current executable path)
- The working analyzer is the rule-based `SentimentAnalyzer` — edits to classification behavior start in `POSITIVE_WORDS`, `NEGATIVE_WORDS`, `NEUTRAL_WORDS` or the scoring logic in `analyze()`
- `analyze()` scores tokens, handles one-token-back negation and degree modifiers (很/太/非常 intensify ×1.5, 有点/有些 reduce ×0.5), returns `sentiment`, numeric `scores`, and `tokens`
- `analyze_comments(comments)` — batch adapter for Bilibili-style dicts (`message`, `author.name`, `like`); skips empty messages, truncates display to 50 chars
- `summarize_results(results)` — prints quantitative report with overall counts, high-like (like > 10) distribution, and like-weighted sentiment

### Backend — Flask three-layer architecture

```
backend/
├── config.py          # DB_PATH configuration
├── database.py        # sqlite3 connection helper; supports TEST_DB_PATH override for tests
├── repositories/      # Data access layer (raw SQL)
├── services/          # Business logic layer
└── routes/            # HTTP layer (Flask Blueprint → comment_bp)
frontend/server.py     # Registers comment_bp, serves the SPA
```

- Routes in `backend/routes/comment_routes.py` expose the REST API documented in `backend/api.md`
- `/api/stats/timeline/image` generates a stacked bar PNG via the `chart-image` skill (`.claude/skills/chart-image/scripts/chart.mjs`)
- `database.py` provides `set_db_path()` for test isolation — tests set `TEST_DB_PATH` before importing

### Database

- SQLite at `db/comments.db`; schema in `db/comments_schema.sql`
- `sentiment_fix IS NOT NULL` marks manually locked comments — `db/update_sentiment.py` skips these during batch analysis

## Data and workflow files

- `finance-up.md` is the active root UP-owner list for collection; includes cookie credentials, skip conditions, and a blacklist
- `bili_data/finance-up.md` — stored copy under the data directory
- `bili_data/results/2026-06-05-sentiment-report.md` — example finished report showing expected Markdown report shape and interpretation of normal / high-like / like-weighted sentiment