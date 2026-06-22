# Finance Sentiment Analyst — 项目长期记忆

## 架构
- 三层架构：routes → services → adapters/sqlite (适配器模式)
- 适配器接口定义：`backend/domain/repositories.py` (CommentRepo + UnitOfWork Protocol)
- SQLite 实现：`backend/adapters/sqlite/comment_repository.py`
- 数据库配置通过环境变量：`DB_DRIVER`, `DB_DSN`, `UPLOAD_DIR`, `IMAGE_URL_PREFIX`

## Docker
- 镜像：`finance-sentiment:latest`，端口 8000
- 卷挂载：`./data/sqlite` → `/app/data`，`./data/uploads` → `/app/uploads`
- 入口点：先运行 `init_db.py` 建表，再启动 gunicorn
- 非 root 用户 `app`

## 图片
- 存储规范：`UPLOAD_DIR/images/<platform>/<filename>`（相对路径存 DB）
- 前端通过 `window.IMAGE_URL_PREFIX` 拼接 URL
- 迁移脚本：`jobs/scripts/migrate_images.py`（comments/images/ → images/）

## 测试
- 50 个测试全部通过，运行方式见 AGENTS.md
