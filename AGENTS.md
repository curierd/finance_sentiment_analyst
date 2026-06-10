# AGENTS.md

## Project structure

```
textcnn_sentiment.py         # Rule-based SentimentAnalyzer (TextCNN class defined but unused)
frontend/
  server.py                  # Flask entry point: registers comment_bp, serves SPA on 0.0.0.0:5000, debug=True
  index.html                 # Single-file vanilla JS SPA (no build tools, API base = '/api')
  requirements.txt           # flask>=3.0.0
backend/                     # Three-layer: routes/ → services/ → repositories/
  config.py                  # DB_PATH from TEST_DB_PATH env or db/comments.db
  database.py                # get_db(), set_db_path() for test isolation, row_to_dict()
  repositories/comment_repository.py
  services/comment_service.py
  routes/comment_routes.py   # comment_bp Blueprint
  api.md                     # Full REST API reference
db/
  comments.db                # SQLite (WAL mode)
  comments_schema.sql        # Schema: comments, up_masters, videos tables
  import_comments.py         # Reads hardcoded comments/*-comments.json paths, inserts into DB
  update_sentiment.py        # Batch analysis (skips sentiment_fix IS NOT NULL)
tests/
  helpers.py                 # setup_test_db() — temp DB with schema + 6 seed rows
  test_comment_repository.py / test_comment_service.py / test_routes.py
data/
  xiaohongshu-finance-up.md  # XHS UP-master preset (one per line, see Format)
  xueqiu-finance-up.md       # Xueqiu symbol preset
  sections/                  # Xueqiu stock-symbol lists (CPO.md, laodeng.md)
jobs/
  collect_comments.md        # Multi-platform collection workflow spec
  bilibili.md                # Bilibili-only collection spec + opencli command reference
  bilibili_comments_collector/bilibili-finance-up.md  # Active B站 UP-master list (NOT under data/)
  BERT-TextCNN/             # Library + SKILL.md
    analyze.py               # Pure library: analyze_text/analyze_batch (no DB, no HTML; returns sentiment+score)
    SKILL.md                 # API + examples + pitfalls for the analyzer
    tests/test_analyze.py    # 23 unit tests; run with `unittest discover -s jobs/BERT-TextCNN/tests`
  scripts/
    collect_all_platforms.py # All-platform collector (opencli), ≥1.5s sleep, --import-only mode
    import_existing_data.py  # Import comments/*.json → DB (supports --date / --all / file args)
    collect_lidaxiao.py      # Standalone lidaxiao (lida xiao) collector
    fix_bilibili_time.py     # Post-process B站 timestamps
    import_comments.py       # Older duplicate of db/import_comments.py
```

## Key commands

```bash
# Start app (Flask API + SPA on :5000, debug auto-reload)
cd frontend && pip install -r requirements.txt && python server.py

# Run all tests
python -m unittest tests.test_comment_repository tests.test_comment_service tests.test_routes -v
python -m unittest discover -s jobs/BERT-TextCNN/tests -p "test_*.py" -v

# Install full deps (torch CPU build required by textcnn_sentiment.py)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install jieba scikit-learn numpy flask

# Batch sentiment analysis (skips locked rows)
python db/update_sentiment.py

# Import JSON comments into DB (older hardcoded-path script)
python db/import_comments.py

# Import any/all JSON in comments/ — preferred for new data
python jobs/scripts/import_existing_data.py --all
python jobs/scripts/import_existing_data.py --date 2026-06-08

# Collect + import in one shot
python jobs/scripts/collect_all_platforms.py --platform all
python jobs/scripts/collect_all_platforms.py --platform bilibili --import-only

# Smoke-test sentiment analyzer
python textcnn_sentiment.py
python -c "from textcnn_sentiment import SentimentAnalyzer; print(SentimentAnalyzer().analyze('A股大涨，赚钱了！'))"
```

## Testing

- `tests/helpers.py` sets `os.environ["TEST_DB_PATH"] = ""` then calls `set_db_path()` to redirect to a temp SQLite with schema + 6 seed rows.
- Each test module calls `setup_test_db()` in `setUpModule` (module-level, once per file).
- Tests never touch `db/comments.db`.
- Repository: `test_comment_repository.py` — CRUD, filtering, pagination, stats.
- Service: `test_comment_service.py` — validation (sentiment lock values, required content, platform enum, delete-not-found).
- Routes: `test_routes.py` — Flask test client, HTTP status codes and JSON.
- Analyzer: `jobs/BERT-TextCNN/tests/test_analyze.py` — pure-Python unit tests for `jobs/BERT-TextCNN/analyze.py` (no DB, loaded via `importlib.util`).
- A single test module can be run with `python -m unittest tests.test_routes -v` (don't need all three).

## Architecture notes

- **Backend import path**: `frontend/server.py` does `sys.path.insert(0, repo_root)` then imports `backend.routes.comment_routes`. CLI scripts (`db/update_sentiment.py`, `jobs/scripts/*.py`) do the same. Backend is **not** a package install — always run from the repo root or with the root on `PYTHONPATH`.
- **Sentiment lock**: `sentiment_fix IS NOT NULL` → manual lock; `db/update_sentiment.py` skips these rows; auto-analysis updates `WHERE sentiment IS NULL AND sentiment_fix IS NULL`.
- **Displayed sentiment**: `COALESCE(sentiment_fix, sentiment)`.
- **Platform constraint**: `CHECK(platform IN ('bilibili', 'xiaohongshu', 'xueqiu'))`.
- **Chart image**: `/api/stats/timeline/image` spawns `node .claude/skills/chart-image/scripts/chart.mjs` to render a Vega-Lite PNG (temp file, deleted after send). Requires `node` on PATH.
- **API base**: Frontend uses `var API = '/api'` in `index.html` — same-origin only; switching ports requires changing the host/port in `frontend/server.py` and `index.html`.
- **Sentiment values** are Chinese: `正面` / `中性` / `负面` (not English). Validation enforces these exact strings.
- **Bilibili collection**: `time.sleep(1.5)` between requests (in `collect_all_platforms.py`); the older `jobs/bilibili.md` says ≥1s. On 412 risk-control errors, switch to `opencli bilibili` (the opencli collector handles its own backoff).
- **opencli adapters**: 雪球 `opencli xueqiu`, 小红书 `opencli xiaohongshu`, B站 `opencli bilibili` (subcommands: `user-videos`, `comments`).
- **Active B站 UP-list location**: `jobs/bilibili_comments_collector/bilibili-finance-up.md` (NOT `data/bilibili-finance-up.md` — that path is hardcoded in `collect_all_platforms.py` but the file does not exist there yet, so the collector warns and continues with an empty list).
- **Preset list format** (`*.md`): lines `uid|name`; a `黑名单` or `blacklist` line starts a blacklist section (see `collect_all_platforms.py:load_up_list`).
- **Collection workflow**: see `jobs/collect_comments.md`. Outputs go to `comments/{platform}_YYYY-MM-DD.json` (final) and `intermediate/{platform}_YYYY-MM-DD.partial.json` (mid-run); local image paths plus raw_data blob for audit.

## Conventions

- Commit format: `<area>: <description>` (e.g. `frontend: 统计面板增加情绪时间线`).
- No formatter/linter configured — match surrounding code style.
- All output JSON uses `ensure_ascii=False` and `utf-8`; never `gbk`.
- Comments are mostly Chinese (Mandarin) — schema fields, sentiment labels, and UI text are in Chinese.
