# Backend SKILL —金融评论情绪分析后端

## 快速使用

```bash
# 启动API服务
cd frontend && python server.py
# → http://localhost:5000
```

## 三层架构

```
routes/ (HTTP层)     — Flask Blueprint，接收请求
services/  (业务逻辑层)  — CommentService，校验与编排
repositories/ (数据访问层) — CommentRepository，SQL查询
database.py            — SQLite连接封装
config.py             — DB路径配置
```

## 数据访问

```python
from backend.repositories.comment_repository import CommentRepository
repo = CommentRepository()

# 分页查询
result = repo.find_all({"platform": "xueqiu", "page": 1, "page_size": 50})

# 单条查询
row = repo.find_by_id(869)

# 统计
stats = repo.stats()
# → {"auto": {...}, "locked": {...}, "like_weighted": {...}, "auto_count": N, "locked_count": N}

# 锁定情绪
updated = repo.update_sentiment_fix(comment_id, "负面")

# 解除锁定
repo.update_sentiment_fix(comment_id, None)
```

## 业务逻辑

```python
from backend.services.comment_service import CommentService
svc = CommentService()

# 校验后锁定（无效值抛 ValueError）
svc.lock_sentiment(comment_id, "正面")

# 列表/统计/UP主/视频
svc.list_comments({"locked": "1", "sentiment": "负面"})
svc.get_stats()
svc.get_up_masters()
svc.get_videos()
```

## 路由（HTTP层）

所有路由注册在 `backend/routes/comment_routes.py`，通过 `frontend/server.py` 的 `app.register_blueprint(comment_bp)` 挂载。

### 路由列表

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/api/comments` | platform, up_name, video_title, sentiment, author, locked, page, page_size | 分页列表 |
| GET | `/api/comments/<id>` | — | 单条 |
| PATCH | `/api/comments/<id>` | body: `{sentiment_fix}` | 锁定/解锁 |
| GET | `/api/stats` | — | 聚合统计 |
| GET | `/api/up_masters` | — | UP主列表 |
| GET | `/api/videos` | — | 视频列表 |

## 数据库约束

- `comments.sentiment` CHECK IN (`正面`, `中性`, `负面`)
- `comments.sentiment_fix` CHECK IN (`正面`, `中性`, `负面`)
- 自动分析跳过条件: `WHERE sentiment IS NULL AND sentiment_fix IS NULL`
- 显示有效情绪: `COALESCE(sentiment_fix, sentiment)`

## 测试

```bash
# 全部测试（38个）
python -m unittest tests.test_comment_repository tests.test_comment_service tests.test_routes -v

# 分层测试
python -m unittest tests.test_comment_repository -v   # repository层
python -m unittest tests.test_comment_service -v # service层
python -m unittest tests.test_routes -v             # HTTP层
```

## 依赖

```
flask>=3.0.0
```