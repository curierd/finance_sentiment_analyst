# AGENTS.md

## Project structure

```
textcnn_sentiment.py       # Rule-based SentimentAnalyzer (TextCNN class defined but unused)
frontend/server.py         # Flask entry point (also serves SPA, registers comment_bp)
backend/                   # Three-layer: routes/ → services/ → repositories/
  config.py                # DB_PATH from TEST_DN env or db/comments.db
  database.py              # get_db(), set_db_path() for test isolation, row_to_dict()
  api.md                   # Full REST API reference with request/response examples
  SKILL.md                 # Detailed backend usage guide (inserts, queries, locking logic)
frontend/
  index.html               # Single-file vanilla JS SPA (no build tools, API base = '/api')
  requirements.txt         # flask>=3.0.0
db/
  comments.db              # SQLite (WAL mode)
  comments_schema.sql      # Schema: comments, up_masters, videos tables
  import_comments.py       # Reads hardcoded JSON paths, inserts into DB
  update_sentiment.py      # Batch analysis (skips sentiment_fix IS NOT NULL)
tests/
  helpers.py               # setup_test_db() creates temp DB with schema + seed data
  test_comment_repository.py / test_comment_service.py / test_routes.py
data/                      # Platform UP-master preset lists (*-finance-up.md)
jobs/                      # Collection scripts + workflow doc (collect_comments.md)
collect_bilibili.py        # Standalone Bilibili collector
collect_xueqiu.py          # Standalone Xueqiu collector
```

## Key commands

```bash
# Start app (Flask API + SPA on :5000)
cd frontend && pip install -r requirements.txt && python server.py

# Run all tests
python -m unittest tests.test_comment_repository tests.test_comment_service tests.test_routes -v

# Install deps (slim)
pip install flask jieba torch numpy scikit-learn

# Batch sentiment analysis (skips locked rows)
python db/update_sentiment.py

# Import JSON comments into DB
python db/import_comments.py

# Smoke-test sentiment analyzer
python textcnn_sentiment.py
```

## Testing

- `tests/helpers.py` sets `os.environ["TEST_DB_PATH"] = ""` then calls `set_db_path()` to redirect to a temp SQLite with schema + 6 seed rows.
- Each test module calls `setup_test_db()` in `setUpModule` (module-level, once per file).
- Tests never touch `db/comments.db`.
- Repository: `test_comment_repository.py` tests CRUD, filtering, pagination, stats.
- Service: `test_comment_service.py` tests validation (sentiment lock values, required content, platform enum, delete-not-found).
- Routes: `test_routes.py` uses Flask test client, tests HTTP status codes and JSON responses.

## Architecture notes

- **Sentiment lock**: `sentiment_fix IS NOT NULL` → manual lock; `update_sentiment.py` skips these rows; auto-analysis updates `WHERE sentiment IS NULL AND sentiment_fix IS NULL`.
- **Displayed sentiment**: `COALESCE(sentiment_fix, sentiment)`.
- **Platform constraint**: `CHECK(platform IN ('bilibili', 'xiaohongshu', 'xueqiu'))`.
- **Chart image**: `/api/stats/timeline/image` spawns `node .claude/skills/chart-image/scripts/chart.mjs` to render a Vega-Lite donut chart PNG (temp file, deleted after send).
- **API base**: Frontend uses `var API = '/api'` — change the host in `server.py` if switching ports.
- **Bilibili collection**: Wait ≥1s between requests; on 412 error switch to `opencli bilibili`.
- **Collection workflow**: See `jobs/collect_comments.md` for multi-platform collection steps.

## Conventions

- Commit format: `<area>: <description>` (e.g. `frontend: 统计面板增加情绪时间线`).
- No formatter/linter configured — match surrounding code style.
