# 实现和运行中遇到的问题

记录 expectation.md 任务在实现与执行过程中遇到的所有问题、根因与处置方式。

## 2026-06-08 17:20 — 首次运行 `collect_bilibili_today.py`

### 结果概览

- 目标日期：`2026-06-08`
- UP 主列表：18 个，黑名单 2 个（已正确跳过）
- 当日命中视频：2 个，来自 2 个 UP 主
  - `老宇投资` (UID 52764688) — `BV1TrEK65EwB` 30 评论
  - `海螺复盘` (UID 471949556) — `BV1aRET6WEMC` 30 评论
- 错误数：0
- 写入：`comments/bilibili_2026-06-08.json`、`intermediate/bilibili_2026-06-08.partial.json`
- 导入数据库：60/60

### 问题 1：`bili user-videos` 触发 412 风险控制

- **现象**：`bili user-videos 1844633907 --json` 返回 `ok: false`，错误码 `network_error`，原始 HTML 中提示 `错误号: 412 / 触发哔哩哔哩安全风控策略`。
- **根因**：B 站官方 API 限制未登录 / 低频 cookie 的 user-videos 端点。
- **处置**：脚本内置 `bili` → `opencli bilibili user-videos` 降级，`opencli` 走 WBI 签名未受同样限制。
- **建议**：后续默认直接使用 `opencli bilibili user-videos`，`bili` 仅作为登录态可用时的备选。

### 问题 2：16/18 UP 主当天未发布新视频

- **现象**：当日仅 2 个 UP 主有新视频，最早视频日期多为 `None` / `2025-xx-xx` / `2021-02-16`。
- **根因**：期望中“今日发布”窗口过窄，UP 主多为非日更；且部分 UP（如 `李大霄`、`小司聊理财`）通过 `bili` 的 `user-videos` 端点拿不到任何记录（412 之外，部分 UID 在 `opencli` 端返回 `None` 日期）。
- **建议**：
  1. 扩大“今日”窗口到 ±1 天，或改为“过去 N 小时”。
  2. 对返回 `None` 日期的 UP 单独排查，可能需要登录态或换 `bili user` 接口拿投稿列表。

### 问题 3：`user-videos` 列表里 `date` 字段在不同 CLI 中命名不一致

- **现象**：`bili user-videos` 输出含 `pubdate`（秒时间戳）、`opencli bilibili user-videos` 输出含 `date`（`YYYY-MM-DD`）。脚本里用 `normalize_video()` 做兼容，但日志里仍出现 `最早 None`。
- **根因**：两个 CLI 的 JSON 字段命名规范不统一，且部分记录 `pubdate` 缺失。
- **建议**：让 `opencli` 的 `user-videos` 命令输出 `date` 字段统一为 `YYYY-MM-DD`，并对 `pubdate` 缺失的记录补 `''` 或 `None` 显式标注。

### 问题 4：上一次运行产物被覆盖

- **现象**：`comments/bilibili_2026-06-08.json` 之前由 `jobs/scripts/collect_all_platforms.py` 写入（360 视频 / 436 评论，无日期过滤），本次脚本只采集“当日”导致文件被覆盖为 2 视频 / 60 评论。
- **处置**：执行前已 `cp ... bilibili_2026-06-08.json.bak.1780910238` 备份。
- **建议**：所有“按日期”脚本输出文件名应带 hash 或时间戳后缀，或在覆盖前提示用户确认；并在 `collect_all_platforms.py` 增加 `--date-filter` 开关。

### 问题 5：部分 UP 的 `earliest_seen` 输出 `None`

- **现象**：日志 `[2/18] [UP] 量化投资邢不行啊 (UID=133578883) [INFO] 当天无新视频 (最早 None)`。
- **根因**：`opencli bilibili user-videos 133578883` 实际能返回记录，但每条记录的 `date` 字段为 `''` 或缺失，`normalize_video` 过滤掉了。
- **建议**：记录“earliest”应回退到 `bili user-videos`（若可用）或 `opencli bilibili video <bvid>` 取单条详情。

## 后续待办

- [ ] 把"当日"窗口做成可配置（`--window-hours N`，默认 24）。
- [ ] `collect_all_platforms.py` 改为不覆盖已有 `comments/<platform>_<date>.json`，而是合并 / 跳过。
- [ ] 给 `opencli bilibili user-videos` 的 schema 文档加字段对照表，避免脚本里手工写 `pubdate` / `date` 兼容。
- [ ] 评估是否需要给 `bili` 添加自动降频 / cookie 刷新逻辑（见 `bili login status`）。

## 2026-06-08 17:54 — 接入评论配图 (方案 2：opencli + 私有 adapter)

### 改动

- **私有 opencli adapter**：`~/.opencli/clis/bilibili/comments-raw.js`。复用官方 `/x/v2/reply/main` + WBI 签名（inlined, 内置 `utils.js` 的子路径未通过 package exports 暴露），返回 `pics[]` 字段。
- **`collect_bilibili_today.py` 增强**：
  - 改用 `comments-raw` 取评论；
  - 新增 `attach_images()` 批量下载 `pics[]` 到 `comments/images/bilibili/<bvid>/<rpid>_<idx>.<ext>`；
  - 每条 comment 记录 `images: [{original_url, local_path, downloaded, reason}]`，把首张成功图写到 `local_image_path` / `original_url`；
  - 把 `rpid` 写为 `comment_id`，便于去重。
- **`backend/repositories/comment_repository.py`**：扩展 `insert()` 接受 `local_image_path` / `original_url` 两个新字段（schema 已有该列，repository 原本未写入）。**46 个单元测试全部通过**。

### 结果 (重跑 17:54)

- 5 个视频 (3 李大霄 + 1 海螺复盘 + 1 老宇投资)，150 条评论，**34 张图全部下载成功**。
- DB: `comments WHERE platform='bilibili' AND local_image_path IS NOT NULL` = 30 行（多图评论只取首图入库，原始 34 张全在 JSON 与文件系统留作审计）。
- 新增 `comments/images/bilibili/<BVID>/<rpid>_<idx>.<ext>` 文件树，34 个文件，~2MB。

### 新发现的问题

- **问题 6：`bili` 与 `opencli` 的 `user-videos` 字段命名差太多**。`bili` 返回 `{bvid, title, url, owner, stats: {view,like,...}}` **没有 `date` 字段**；`opencli` 返回 `{rank, title, plays, likes, date, url}`。原先按 spec "使用 opencli bilibili 和 bili" 优先调 `bili`，结果 0 命中（所有 entry 的 `date` 都是空）。**修复**：脚本改为 `opencli` 优先，`bili` 仅作 fallback。
- **问题 7：`bili` 的 412 风控有窗口期**。`doctor` 报告 Browser Bridge 偶发掉线，`bili` 第一次跑返回 `ok:false / 412`，随后冷却几分钟又能正常返回（cookie 状态不稳）。建议在脚本里加重试 + 冷却。
- **问题 8：opencli 私有 adapter 加载路径**。`utils.js` 不能通过 `@jackwener/opencli/clis/bilibili/utils.js` 导入（package.json `exports` 不暴露子路径）。**修复**：把 WBI 签名 + WBI keys 获取 + `apiGet` 等内联进 `comments-raw.js`。代价是代码重复 ~80 行。
- **问题 9：opencli 的 `EnvHttpProxyAgent` 警告走 stderr**，不影响 JSON 解析（stdout 干净），但若脚本未来要做 `stdout, _ = ...` 拆 JSON 需注意 `subprocess.run` 默认 `text=True` 不会混入。无需修复，留备注。
- **问题 10：re-import 会产生重复行**。本次重跑前已 `DELETE FROM comments WHERE platform='bilibili' AND comment_id IS NULL` 清理 586 条旧行（上次 `comment_id` 留空），新行带 rpid。后续跑可在 `import_comments` 前加 `INSERT OR IGNORE` 逻辑（schema 没建唯一索引，可后续补 `(platform, comment_id)` 上 partial unique）。

## 后续待办（新增）

- [ ] 在 `comments` 表上加 `UNIQUE(platform, comment_id)` partial index（`comment_id IS NOT NULL` 时去重）。
- [ ] 把方案 2 抽成 `--with-images` 开关，默认 off（裸评论 50 条 ~3s，带图 50 条 ~20s）。
- [ ] 把 `comments-raw.js` 提到公开包（PR 给 opencli upstream），避免 utils.js 重复实现。
- [2026-06-08 17:45:12] 采集为空: 0 个 2026-06-08 视频 (UP=18)
- [2026-06-08 17:45:53] bili user-videos 失败, UID=1584562031: {'cmd': 'bili user-videos', 'rc': 1, 'stderr': ''}; 尝试 opencli
- [2026-06-08 17:46:05] bili user-videos 失败, UID=1971825778: {'cmd': 'bili user-videos', 'rc': 1, 'stderr': ''}; 尝试 opencli
- [2026-06-08 17:46:33] 采集为空: 0 个 2026-06-08 视频 (UP=18)
- [2026-06-08 17:54:09] 采集成功: 5 视频, 150 评论
- [2026-06-08 18:01:45] 采集为空: 0 个 2026-06-08 视频 (UP=18)
- [2026-06-09 10:45:25] 采集为空: 0 个 2026-06-09 视频 (UP=18)
- [2026-06-09 11:34:41] 采集为空: 0 个 2026-06-09 视频 (UP=18)
- [2026-06-09 14:00:25] 采集成功: 1 视频, 30 评论
- [2026-06-09 14:09:05] 采集成功: 12 视频, 288 评论
- [2026-06-10 10:44:30] 采集为空: 0 个 2026-06-10 视频 (UP=18)
- [2026-06-10 10:49:15] 采集成功: 10 视频, 227 评论

## 2026-06-10 10:48 — 加 `--window-days` 窗口 + 入库去重

### 改动
- `collect_bilibili_today.py`：
  - 新增 `--window-days N`（默认 0 = 仅 target_date，1 = ±1 天）。
  - 新增 `is_in_window()` helper；视频过滤从 `== target_date` 改为窗口判断。
  - `import_comments()` 改为按 `(platform, comment_id)` 去重：先查 DB 已存在的 comment_id 集合，命中即跳过；新增的也实时进集合（同一批内重复保护）。
  - JSON envelope 增加 `window_days` 字段 + 动态 `filter` 描述。

### 跑 (2026-06-10, --window-days 1)
- 命中视频 10 个（5 个 UP 主：马男聊投资 / 刘老师の炒股笔记 / 投资笔记-原创 / 强龙投资日记 / 老宇投资 / 李大霄×3 / 海螺复盘 / 淘沙博士）
- 评论 227 条；导入 219，跳过 8 (comment_id 已在 DB)；错误 0
- 强龙投资日记 视频 "2026.6.9，选g唯二" 0 评论 (脚本内已正确处理)
- 写入 `comments/bilibili_2026-06-10.json`（旧空文件已备份为 `.bak.empty`）

### 新发现：opencli `user-videos` 视频日期与评论时间错位
- 现象：脚本输出 "当天无新视频" 窗口 [2026-06-09, 2026-06-10] 内，10 个视频的 `opencli date` 字段全部是 `2026-06-10`，但 227 条评论的 `time` 字段全部是 `2026-06-09 xx:xx` (CST)。
- 例：马男聊投资 `BV1vNEE64EHs` (`date=2026-06-10`) 第一条评论 `time=2026-06-09 11:27`。
- 推测：`opencli bilibili user-videos` 的 `date` 字段是视频被加入"最近发布"列表的日期（晚于实际发布时间），或 CLI 内部有 +1 天偏移；`comments-raw` 的 `time` 字段是真实评论时间（CST）。
- 影响：本次 `target_date=2026-06-10` 的"今日"窗口没有抓到任何 06-10 实际评论（全部 227 条都来自 06-09 实际评论）。改用 ±1 天窗口后，6-09 实际评论可入库，但视频元数据的 `date` 与评论时间存在 1 天错位。
- 建议：
  1. 给 `opencli bilibili user-videos` 加 `pubdate` (秒时间戳) 输出，并修正 `date` 字段。
  2. 脚本内可加 fallback：用每条视频的评论 time 分布回推真实发布日，与 opencli date 取 min。
  3. 若 opencli 不修，文档化"date 字段可能晚于真实发布日 0~1 天"，`--window-days` 默认建议为 1。


## 2026-06-10 10:55 — opencli 调用加 `--window background` 防浏览器抢焦点

### 改动
- `collect_bilibili_today.py` 的两个 opencli 调用都加 `--window background`：
  - `fetch_videos_opencli()` (`user-videos`)
  - `fetch_comments()` (`comments-raw`)
- 不改 `bili` 调用路径 — `bili` 走 `browser-cookie3` 读本地浏览器 cookie DB，不启动浏览器窗口。

### 原理
- opencli `Strategy.COOKIE` 的命令需要 Browser Bridge (`chrome + opencli 扩展`)。当 bridge 拿不到 cookie 时 opencli 会启动/前台化一个 Chrome 窗口去抓 `bilibili.com` 的登录态，默认 `--window foreground` 会把窗口拉到最前。
- 加 `--window background` 后任何新打开/前台化的 Chrome 窗口都退到后台，不抢焦点、不打扰用户。

### 验证
- `opencli bilibili user-videos 52764688 --limit 2 --window background -f json` → 返回正常 JSON
- `opencli bilibili comments-raw BV1ndE76eE7V --limit 2 --window background -f json` → 返回正常 JSON

### 后续可考虑
- 加 `--site-session ephemeral` (默认 persistent) 让命令结束后立即释放 tab lease，避免 Chrome 长期持有 bilibili tab。
- 配合 doctor 报告的"Extension 不稳定"问题：可以加 `OPENCLI_BROWSER_CONNECT_TIMEOUT=10` 快速失败，自动 fallback 到 `bili` 兜底（`bili user-videos` 不需要浏览器）。
