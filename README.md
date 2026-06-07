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
├── tests/ # 单元测试（38个，覆盖三层）
│   ├── test_comment_repository.py
│   ├── test_comment_service.py
│   └── test_routes.py
├── collect_bilibili.py       # B站评论采集
├── collect_xueqiu.py         # 雪球评论采集
└── collect_comments.md        # 采集任务说明
```

## 快速开始

### 1. 安装依赖

```bash
pip install flask jieba torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu numpy scikit-learn
```

### 2. 启动服务

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

## REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/comments` | 分页查询评论 |
| GET | `/api/comments/<id>` | 单条评论 |
| PATCH | `/api/comments/<id>` | 锁定/解锁情绪 |
| GET | `/api/stats` | 情绪统计 |
| GET | `/api/up_masters` | UP主列表 |
| GET | `/api/videos` | 视频列表 |

详见 [backend/api.md](backend/api.md)。

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