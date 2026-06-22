> 💾 ****Docker 单机存储方案（评论 SQLite + 图片本地落盘）****
  目标：小型量化/舆情分析应用，Linux 单机 Docker 部署，不用 CDN，数据可持久化、可备份、可迁移。

## 总体思路

- **结构化数据（评论、情绪、视频/博主元信息）**：通过“数据库适配器（Adapter）”访问底层存储（当前用 SQLite，未来可平滑换 Postgres/MySQL）。
- **静态图片（抓取/上传的图片）**：保存为宿主机目录下的文件（按日期/哈希组织）。
- **容器内只读写挂载卷**：容器随时可重建，数据不丢。

---


## 数据库适配器模式（为未来扩展准备）


### 目标

- 现在：单机 SQLite（WAL）
- 未来：无需改业务逻辑即可切换到 Postgres/MySQL（或新增只读分析库等）

### 结构（建议）

- `domain/`：业务模型与用例（不依赖具体数据库）
- `ports/`：接口（Repository/UnitOfWork）
- `adapters/`：具体实现
  - `sqlite/`：SQLite 适配器（当前）
  - `postgres/`：Postgres 适配器（未来）

### 最小接口（示例）

```python
from typing import Protocol, Optional

class CommentRepo(Protocol):
	def add(self, c) -> None: ...
	def get(self, id: int): ...
	def list(self, *, platform: Optional[str]=None, symbol: Optional[str]=None,
			 start: Optional[str]=None, end: Optional[str]=None,
			 sentiment: Optional[str]=None, limit: int=200) -> list: ...

class UnitOfWork(Protocol):
	comments: CommentRepo
	def __enter__(self): ...
	def __exit__(self, exc_type, exc, tb): ...
	def commit(self) -> None: ...
	def rollback(self) -> None: ...
```

### 配置方式

- 用环境变量选择数据库实现：
  - `DB_DRIVER=sqlite` 或 `DB_DRIVER=postgres`
  - `DB_DSN=...`（SQLite 文件路径或 Postgres DSN）

---


## 目录规划（宿主机）

建议把持久化数据统一放在项目目录下的 `data/`：
- `./data/sqlite/`：SQLite 数据文件
- `./data/uploads/`：图片与静态文件
- `./data/backup/`：手工/定时备份产物（可选）
示例：
- `./data/sqlite/comments.db`
- `./data/uploads/images/2026/06/xxxx.webp`

---


## docker-compose.yml（核心）

> 下面示例体现“适配器模式”的配置：用 `DB_DRIVER` + `DB_DSN` 来选择底层数据库。
> - SQLite：挂载 `./data/sqlite` 到容器内，并把 `DB_DSN` 指向数据库文件
> - 未来上 Postgres：新增 `db` 服务并改环境变量即可（业务代码不变）
```yaml
services:
  app:
    image: your-app-image:latest
    container_name: quant_app
    environment:
      # 数据库适配器
      DB_DRIVER: sqlite
      DB_DSN: file:/app/data/comments.db?mode=rwc&cache=shared&timeout=30

      # 上传目录
      UPLOAD_DIR: /app/uploads

    volumes:
      # 1) SQLite 文件持久化（读写）
      - ./data/sqlite:/app/data

      # 2) 图片持久化（读写）
      - ./data/uploads:/app/uploads

    ports:
      - "8000:8000"
    restart: unless-stopped
```

---


## SQLite 并发与可靠性配置（强烈建议）


### 1) PRAGMA（建库/初始化时执行一次）

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;  -- 单机常用折中；如更保守可用 FULL
```

### 2) 应用侧建议

- **写入尽量短事务**（不要在一个事务里做太多网络 IO）。
- 设置 busy timeout（避免“database is locked”）：
  - SQLite 连接参数或执行：`PRAGMA busy_timeout = 5000;`

---


## 图片存储规范（简单且不踩坑）

- 存“相对路径”到数据库，例如：`images/2026/06/uuid.webp`
- 文件名建议用 `uuid` 或内容哈希（sha256）避免重名
- 目录按日期分层，避免单目录文件过多
示例落盘：
- 宿主机：`./data/uploads/images/2026/06/8a3f....webp`
- 容器内：`/app/uploads/images/2026/06/8a3f....webp`

---


## 备份与迁移（最简可执行）


### 1) 备份 SQLite（推荐用 sqlite3 .backup）

在宿主机执行：
```bash
mkdir -p ./data/backup
sqlite3 ./data/sqlite/comments.db ".backup './data/backup/comments_$(date +%F).db'"
```

### 2) 备份图片

```bash
tar -czf ./data/backup/uploads_$(date +%F).tar.gz -C ./data uploads
```

### 3) 迁移到新机器

把以下目录拷走即可：
- `./data/sqlite/`
- `./data/uploads/`
（可选）`./data/backup/`

---


## 常见注意事项

- 不建议把图片以 BLOB 存 SQLite：会让备份/查询/锁冲突变糟。
- WAL 模式下会出现 `comments.db-wal` / `comments.db-shm` 文件：它们也是数据库的一部分，**必须一起持久化**（本方案用目录挂载即可自动包含）。
- 如果未来并发和数据量明显变大：可以把结构化数据迁移到 Postgres，但图片目录仍然可复用。
- **第一次迁移数据时，务必修改图片路径地址**：旧库里 `local_image_path` 可能是开发机/旧机器的绝对路径（例如 `/Users/xxx/...` 或 `D:\images\...`），上线到 Docker 后实际位置是容器内 `/app/uploads/...`、对外访问是 `/uploads/...`。建议步骤：
  1. 把旧图片文件统一拷贝/重组到 `./data/uploads/images/YYYY/MM/` 目录。
  1. 用一次性脚本把 `comments.local_image_path`（或新表 `comment_images.local_path`）改写为**相对路径**，例如 `images/2026/06/xxx.webp`。
  1. 应用读取时统一拼接 `UPLOAD_DIR` 或对外 URL 前缀（如 `/uploads/`），后续换机器/换域名都不用再改库。
  1. 迁移前先用 `sqlite3 .backup` 备份数据库，并在测试库上跑一遍 UPDATE 脚本确认无误。