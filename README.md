# 金融评论情绪分析

多平台（B站、雪球、小红书）评论抓取与情绪分析工具，支持手动锁定修正、统计面板与 REST API。

## 功能

- **多平台采集** — B站（bili CLI）、雪球（opencli）、小红书（xhs CLI）
- **情绪分析** — TextCNN / 规则-based 两种模式
- **手动锁定** — `sentiment_fix` 字段锁定修正值，绕过自动分析
- **统计面板** — 前端可视化：情绪分布 / 点赞加权 / 平台分布
- **前后端分离** — Flask REST API + Vanilla JS SPA

## 项目结构

```
.
├── textcnn_sentiment.py       # 情绪分析核心（规则 + TextCNN）
├── backend/ # 后端三层架构
│   ├── config.py              # 路径/DB配置
│   ├── database.py           # SQLite连接
│   ├── repositories/          # 数据访问层
│   ├── services/             # 业务逻辑层
│   ├── routes/               # HTTP层（Flask Blueprint）
│   ├── requirements.txt
│   └── api.md                # REST API文档
├── frontend/                  # 前端
│   ├── server.py              # Flask服务（注册Blueprint）
│   ├── index.html             # SPA页面
│   └── requirements.txt
├── db/                        # 数据库
│   ├── comments.db            # SQLite数据文件
│   ├── comments_schema.sql    # 建表语句
│   ├── import_comments.py     # 导入脚本
│   └── update_sentiment.py # 批量分析脚本
├── tests/                    # 单元测试（覆盖三层）
│   ├── test_comment_repository.py
│   ├── test_comment_service.py
│   └── test_routes.py
├── collect_bilibili.py       # B站评论采集
└── collect_xueqiu.py         # 雪球评论采集
```

## 快速开始

### 1. 安装依赖

```bash
pip install flask jieba torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu numpy
```

### 2. 启动服务（前后端一体）

```bash
cd frontend
pip install -r requirements.txt
python server.py
# → http://localhost:5000
```

### 3. 批量运行情绪分析

```bash
python db/update_sentiment.py
```

### 4. 运行测试

```bash
python -m unittest tests.test_comment_repository tests.test_comment_service tests.test_routes -v
```

---

## Backend 使用

### 架构概览

三层架构 + Flask Blueprint，由 `frontend/server.py` 统一注册：

```
routes/  ──HTTP层── 解析参数 / 返回JSON
   ↓
services/ ──业务层── 编排、校验、聚合
   ↓
repositories/ ──数据层── 原始SQL，仅与 sqlite3 交互
   ↓
database.py ── sqlite3 连接（支持 TEST_DB_PATH 覆盖）
```

### 启动方式

后端没有独立 entry point，由 `frontend/server.py` 引导：

```bash
cd frontend
python server.py
# Flask 监听 0.0.0.0:5000，debug=True 自动 reload
```

如需仅作为 API 服务调用（不挂载 SPA），可在自定义脚本中：

```python
from flask import Flask
from backend.routes.comment_routes import comment_bp

app = Flask(__name__)
app.register_blueprint(comment_bp)
app.run(port=5000)
```

### REST API 速查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/comments` | 分页查询，支持 `platform` / `up_name` / `sentiment` / `locked` / `page` / `page_size` 等过滤 |
| POST | `/api/comments` | 新增评论（`content` 为空返回 400） |
| GET | `/api/comments/<id>` | 单条评论 |
| PATCH | `/api/comments/<id>` | 锁定/解锁情绪（`sentiment_fix` ∈ {正面/中性/负面/null}） |
| DELETE | `/api/comments/<id>` | 删除评论 |
| GET | `/api/stats` | 情绪分布 + 点赞加权聚合 |
| GET | `/api/stats/timeline` | 按 `granularity=day/week/month` 时间线聚合 |
| GET | `/api/stats/timeline/image` | 返回 PNG 堆叠柱状图（通过 `chart-image` skill 生成） |
| GET | `/api/up_masters` | 去重 UP主列表 |
| GET | `/api/videos` | 去重视频/帖子列表 |

完整请求/响应示例见 [backend/api.md](backend/api.md)。

常用示例：

```bash
# 拉取雪球平台、正面、第一页
curl 'http://localhost:5000/api/comments?platform=xueqiu&sentiment=正面&page=1&page_size=20'

# 手动锁定情绪
curl -X PATCH http://localhost:5000/api/comments/869 \
  -H 'Content-Type: application/json' \
  -d '{"sentiment_fix":"正面"}'

# 解除锁定
curl -X PATCH http://localhost:5000/api/comments/869 \
  -H 'Content-Type: application/json' \
  -d '{"sentiment_fix":null}'

# 全局情绪统计
curl http://localhost:5000/api/stats

# 按周聚合时间线
curl 'http://localhost:5000/api/stats/timeline?granularity=week'
```

### 测试隔离

`backend/database.py` 提供 `set_db_path()`,测试通过环境变量 `TEST_DB_PATH` 切换至临时库,不污染 `db/comments.db`：

```bash
python -m unittest tests.test_comment_repository tests.test_comment_service tests.test_routes -v
```

---

## Frontend 使用

### 启动

前端是单文件 SPA(`frontend/index.html`),由 `frontend/server.py` 同进程托管：

```bash
cd frontend
pip install -r requirements.txt
python server.py
# 浏览器打开 http://localhost:5000
```

### 界面功能

| 区域 | 功能 |
|------|------|
| 顶部 tabs | 平台切换：全部 / B站 / 雪球 / 小红书 |
| 顶部 stats bar | 实时显示总数 / 自动 / 锁定 / 点赞加权占比 |
| 左侧 sidebar | 情绪过滤(正面/中性/负面)、锁定状态(自动/已锁)、UP主/作者/标题搜索 |
| 主区卡片网格 | 评论卡片,显示平台、作者、内容、点赞、情绪 badge |
| 卡片操作 | 单击情绪 badge → 锁定为该情绪;点 ✕ → 解除锁定 |
| 统计面板 | 情绪分布、点赞加权、平台分布、情绪时间线(stats/timeline 接口驱动) |

### 数据流

```
浏览器 ──fetch('/api/...')── Flask Blueprint ── services ── repositories ── SQLite
                ↓
        异步刷新 stats-bar / cards
```

所有 API 请求基于 `var API = '/api'`(`index.html` 顶部),开发时改后端端口需同步修改 host。

### 修改前端

`frontend/index.html` 是无构建工具的 vanilla JS + 内联 CSS。直接编辑保存,浏览器刷新即可。

---

## 运维 & 数据更新

### 批量情绪重算

```bash
python db/update_sentiment.py
# 跳过 sentiment_fix IS NOT NULL 的行
```

### 导入新评论

```bash
python db/import_comments.py
# 读取硬编码路径：comments/bilibili-comments.json + 雪球 JSON
```

### 平台采集 CLI

| 平台 | 命令 | 备注 |
|------|------|------|
| B站 | `bili video <BVID> --comments --json` | 间隔 ≥1s,触发 412 切 `opencli bilibili` |
| 雪球 | `opencli xueqiu --comments` | |
| 小红书 | `xhs collect <note_id>` | |

## 数据库

- **表**: `comments` — 评论主表，含 `platform` / `sentiment` / `sentiment_fix` / `sentiment_score`
- **约束**: `sentiment` / `sentiment_fix` 仅允许 `正面/中性/负面`
- **锁定逻辑**: `sentiment_fix IS NOT NULL` → 自动分析跳过

## 情绪分析核心

```python
from textcnn_sentiment import SentimentAnalyzer

analyzer = SentimentAnalyzer()
result = analyzer.analyze("A股大涨，赚钱了！")
# {'sentiment': '正面', 'scores': {'positive': ..., 'negative': ..., 'neutral': ...}}
```