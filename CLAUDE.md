# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

金融评论情绪分析（Finance Sentiment Analyst）— 多平台（B 站 / 雪球 / 小红书 / 知乎）财经评论采集、情绪分析、人工锁定修正、统计面板的端到端系统。三层 Flask 后端 + Vanilla JS SPA + LLM 情绪分析 + 平台采集脚本集。

## Commands

### Install dependencies

```bash
# LLM 方案只要这些；词典规则方案额外需要 torch + jieba
pip install flask openai jieba scikit-learn numpy
# torch (CPU) — 仅当你需要 jobs/sentiment_analyzer/textcnn_sentiment.py 里的 TextCNN 模型类时
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

LLM 环境变量（`db/update_sentiment.py` 默认走 DeepSeek）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_API_KEY` 或 `DEEPSEEK_API_KEY` | — | API 密钥（必填） |
| `LLM_BASE_URL` | `https://api.deepseek.com` | API 地址 |
| `LLM_MODEL` | `deepseek-v4-pro` | 模型名称 |
| `LLM_SOURCE` | `deepseek` | `deepseek` 或 `openai`（决定默认 base/model） |
| `TEST_DB_PATH` | — | 测试覆盖默认 DB 路径（见 Testing） |

### Start the Flask API + frontend

```bash
cd frontend && pip install -r requirements.txt && python server.py
# → http://localhost:5000 （host=0.0.0.0, debug=True 自动 reload）
```

### Run unit tests

```bash
# 后端三层（repository / service / routes）
python -m unittest tests.test_comment_repository tests.test_comment_service tests.test_routes -v

# 情绪分析纯库测试（无 DB）
python -m unittest discover -s jobs/sentiment_analyzer/tests -p "test_*.py" -v
```

### Batch-update sentiment in the database

```bash
python db/update_sentiment.py
# LLM 批量分析；跳过 sentiment_fix IS NOT NULL 的行；批量大小 BATCH=20
```

### Sentiment analyzer smoke tests

```bash
# LLM 方案（推荐生产用）
python -c "from jobs.sentiment_analyzer.llm_sentiment import SentimentAnalyzer; print(SentimentAnalyzer().analyze('A股大涨，赚钱了！'))"

# 词典规则方案（无 API key 时）
python jobs/sentiment_analyzer/textcnn_sentiment.py
```

### Collect platform data

```bash
# B 站（双路：opencli + bili fallback；≥1.5s 防 412 风控）
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --window-days 1
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --import-only
python jobs/bilibili_comments_collector/scripts/bilibili_image_downloader.py   # 仅下载历史配图

# 雪球（目录名保留拼写 xuqiu）
python jobs/xuqiu_comments_collector/scripts/collect_xueqiu.py

# 小红书
python jobs/xiaohongshu_comments_collector/scripts/collect_comments.py
python jobs/xiaohongshu_comments_collector/scripts/fix_comment_pictures.py     # 历史配图修复
python jobs/xiaohongshu_comments_collector/scripts/import_to_db.py             # 仅入库

# 知乎
python jobs/zhihu_comments_collector/scripts/collect_zhihu.py

# 全平台统一调度（写入 schedule/collect_all/output/）
python schedule/collect_all/scripts/run_all.py
python schedule/collect_all/scripts/import_xueqiu_to_db.py
python schedule/collect_all/scripts/generate_report.py

# DB 维护 / 数据迁移
python jobs/scripts/init_db.py            # 初始化 / 迁移 DB（按 db/comments_schema.sql）
python jobs/scripts/backup.py             # 备份 db/comments.db
python jobs/scripts/migrate_images.py     # 历史图片迁移
```

When collecting Bilibili data, wait ≥1.5 s between requests. On 412 risk-control errors, switch to `opencli bilibili` (the opencli collector handles its own backoff).

## Architecture

### Sentiment analysis core (`jobs/sentiment_analyzer/`)

三个实现并存，按精度/成本挑选：

| 模块 | 实现 | 用途 |
|------|------|------|
| `llm_sentiment.py` | OpenAI 兼容 LLM（默认 DeepSeek V3） | **生产用** — `db/update_sentiment.py` 默认调用 |
| `analyze.py` | 纯库函数包装（`analyze_text` / `analyze_batch`） | 批量任务 / 无 LLM 时的兜底 |
| `textcnn_sentiment.py` | 词典规则 `SentimentAnalyzer`（含未启用的 `TextCNN` 模型类） | 离线 / 演示 / 词典维护 |

公开 API（详见 `jobs/sentiment_analyzer/SKILL.md`）：

```python
from jobs.sentiment_analyzer.llm_sentiment import SentimentAnalyzer
from jobs.sentiment_analyzer.analyze import analyze_text, analyze_batch, SENTIMENTS

# SENTIMENTS = ("正面", "中性", "负面")  — 全程使用中文标签
# score = positive - negative，正=偏多 / 负=偏空 / 0=无信号
# analyze_batch 保留输入记录全部字段，并追加 text/sentiment/scores/score
```

`analyze.py` 通过 `importlib.util.spec_from_file_location` 载入 `textcnn_sentiment.py`，规避包路径问题。词典不命中时回退 `中性`。

### Backend — Flask three-layer architecture

```
backend/
├── config.py          # DB_PATH / UPLOAD_DIR / IMAGE_URL_PREFIX
├── database.py        # sqlite3 连接；set_db_path() 用于测试隔离；row_to_dict()
├── repositories/      # 数据访问层（comment_repository.py — 原始 SQL）
├── services/          # 业务逻辑层（comment_service.py — 校验 / 编排）
├── routes/            # HTTP 层（comment_routes.py — Flask Blueprint `comment_bp`）
└── api.md             # 完整 REST API 参考

frontend/
├── server.py          # 注册 comment_bp；serve SPA + /uploads/<path>
└── index.html         # 单文件 vanilla JS SPA（无构建工具；`var API = '/api'`）
```

- `frontend/server.py` 在导入任何 `backend.*` 之前先 `sys.path.insert(0, repo_root)`，否则 Flask reloader 在子进程里找不到包（文件里有注释）。
- 所有 CLI 脚本（`db/update_sentiment.py`、`jobs/scripts/*`、`schedule/collect_all/scripts/*`）同样先 `sys.path.insert(0, ".")`。后端 **不是** 可安装包，永远从仓库根目录运行。
- `/api/stats/timeline/image` 通过 `node .claude/skills/chart-image/scripts/chart.mjs` 生成 Vega-Lite 堆叠柱状图 PNG（临时文件，发送后删除；需要 `node` 在 PATH）。
- 完整端点参考见 `backend/api.md`：`/api/comments` (GET/POST/PATCH/DELETE)、`/api/stats`、`/api/stats/timeline`、`/api/up_masters`、`/api/videos`、`/api/comments/<id>/image`、`/api/comments/<id>/image/upload`。

### Database (`db/comments.db`)

- SQLite WAL 模式；schema 见 `db/comments_schema.sql`
- 三张表：`comments` / `up_masters` / `videos`
- `comments.platform` 约束：`'bilibili' | 'xiaohongshu' | 'xueqiu' | 'zhihu'`（注意 API 文档老版本只列前三个，schema 已扩展）
- `sentiment` / `sentiment_fix` 约束：`'正面' | '中性' | '负面'`（中文）
- **锁定语义**：`sentiment_fix IS NOT NULL` → 人工锁定；`db/update_sentiment.py` 自动跳过；查询显示用 `COALESCE(sentiment_fix, sentiment)`
- 索引：常用过滤列 + `idx_comments_high_likes`（部分索引 `WHERE likes > 10`）+ `idx_comments_platform_sentiment`（点赞加权聚合）
- `raw_data` 列存原始平台 JSON 供审计

### Collection jobs (`jobs/`)

每个平台一个独立子目录，统一提供 `SKILL.md` / `expect*.md` / `issues.md`：

```
jobs/
├── bilibili_comments_collector/      collect_bilibili_today.py + bilibili_image_downloader.py
├── xuqiu_comments_collector/         collect_xueqiu.py  （目录名保留拼写 xuqiu）
├── xiaohongshu_comments_collector/   collect_comments.py + fix_comment_pictures.py + import_to_db.py
├── zhihu_comments_collector/         collect_zhihu.py
├── sentiment_analyzer/               三个分析器实现 + SKILL.md + tests/
└── scripts/                          init_db.py / backup.py / migrate_images.py（DB 维护）
```

每个 collector 子目录都有一份 `<platform>-finance-up.md` 预设表（`uid|name` 格式 + `## up黑名单` 段落）。**注意**：B 站的活动 UP 列表是 `jobs/bilibili_comments_collector/bilibili-finance-up.md`，**不是** `data/bilibili-finance-up.md`（后者已被弃用，文件不存在）。

采集产物：`comments/<platform>_<YYYY-MM-DD>.json`（最终）+ `intermediate/<platform>_<YYYY-MM-DD>.partial.json`（过程中）。图片存到 `comments/images/<platform>/<bvid>/<rpid>_<idx>.<ext>`，DB 写入 `local_image_path`。

### Schedule orchestrator (`schedule/collect_all/`)

全平台调度器，按 `expectation.md` 跑：

```
schedule/collect_all/
├── expectation.md                   任务规格（窗口：上一交易日收盘 ~ 今日开盘，CST）
├── issues.md                        每次运行追加
├── intermediate/                    部分 dump + 登录状态
├── output/                          最终 Markdown 报告
└── scripts/
    ├── run_all.py                   主调度器（login → 全平台采集 → 报告）
    ├── import_xueqiu_to_db.py       雪球 JSON → DB
    └── generate_report.py           聚合 → Markdown 报告
```

`run_all.py` 在 Windows 上需要把 `C:\Users\sverd\AppData\Roaming\npm`、`C:\Users\sverd\.local\bin` 加进 `PATH`，因为 npm 全局安装的 `opencli` 是无扩展名的 bash 脚本。脚本里有 `_resolve_tool()` 处理 `.cmd` shim。

## Data files

| 路径 | 用途 |
|------|------|
| `data/sections/CPO.md` / `laodeng.md` / `consumer-tech.md` | 雪球股票代码分组清单（symbol preset） |
| `data/sqlite/` | 备份/导出的 SQLite 文件 |
| `data/uploads/` | 上传图片（Docker 部署时挂载） |
| `comments/*.json` | 各平台每日采集快照 |
| `comments/images/<platform>/` | 配图本地缓存 |
| `intermediate/*.partial.json` | collector 中间产物 |
| `schedule/collect_all/output/` | Markdown 报告产物 |

## Testing

- `tests/helpers.py::setup_test_db()` 设 `os.environ["TEST_DB_PATH"] = ""` 后调用 `backend.database.set_db_path()`，把测试切到临时 SQLite（含 schema + 6 条 seed）。
- 每个测试模块在 `setUpModule` 调一次 `setup_test_db()`，从不接触 `db/comments.db`。
- 跑单个文件即可：`python -m unittest tests.test_routes -v`（不需要三件套同时跑）。
- `jobs/sentiment_analyzer/tests/test_analyze.py` 走 `importlib.util` 加载 `analyze.py`，不连 DB。

## Conventions

- **Commit format**: `<area>: <description>`（例：`frontend: 统计面板增加情绪时间线`）
- 无 formatter / linter — 改代码时匹配周边风格
- 所有输出 JSON 强制 `ensure_ascii=False` + UTF-8；脚本入口统一 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')` 防止 GBK 崩溃
- 注释 / schema / 情绪标签 / UI 文案一律中文；不要把 `正面/中性/负面` 改成英文
- 模块入口脚本顶部一律 `sys.path.insert(0, repo_root)`（Flask reloader 的兼容性要求）

## Operational notes

- B 站采集优先用 `opencli bilibili`（自带 backoff）；`bili` 直连需 ≥1.5s 间隔、412 时切 opencli
- `db/update_sentiment.py` 默认走 DeepSeek；切 OpenAI：`LLM_SOURCE=openai`
- 容器化部署：`Dockerfile` / `docker-compose.yml` / `docker_storage.md`；`/uploads/<path>` 与 `/comments/<path>` 路由做向后兼容
- 上一交易日窗口判断在 `schedule/collect_all/scripts/run_all.py`（CST 时区；`WINDOW_START` / `WINDOW_END` 按当前日期调整）