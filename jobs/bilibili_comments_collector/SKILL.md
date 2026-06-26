---
name: bilibili-comments-collector
description: 从 B站财经 UP 主列表 (`bilibili-finance-up.md`) 抓取指定日期窗口的视频与评论，配图下载到本地，写入 `comments/bilibili_<date>.json` 并入库。`opencli bilibili` + `bili` 双路取数，`OPENCLI_WINDOW=background` 环境变量全局不抢焦点。
---

# B 站财经 UP 评论采集器

## 适用场景
- 每日/隔日抓取 18 个财经 UP 主（个人，含黑名单 2 个）当日窗口内的视频评论
- 视频列表来自 `jobs/bilibili_comments_collector/bilibili-finance-up.md`（markdown 表格，`## up黑名单` 段落会被自动跳过）
- 评论配图下载到 `comments/images/bilibili/<bvid>/<rpid>_<idx>.<ext>`，首张写入 DB `local_image_path`

## 公开入口

```bash
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py [FLAGS]
```

## CLI 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--date` | 今天 | 目标日期 `YYYY-MM-DD` |
| `--window-days` | 0 | 日期窗口 `target ± N` 天；0 = 仅 target_date |
| `--limit` | 50 | 每视频评论上限（受 opencli 限制 max 50） |
| `--video-pages` | 3 | 每 UP 拉取的视频页数（1 页=20 个） |
| `--sleep` | 1.5 | 请求间隔秒数（防风控） |
| `--import-only` | off | 跳过采集，仅从已有 JSON 入库 |
| `--no-import` | off | 采集但不入库 |
| `--describe-images` | on | 使用 `mmx vision describe` 理解评论配图（mmx-cli-cn） |
| `--no-describe-images` | off | 跳过 mmx vision 图片理解 |
| `--describe-sleep` | 0.2 | mmx vision 调用间隔秒数 |

## 常用调用

```bash
# 抓今天 (±0 天)
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py

# 抓 ±1 天 (推荐: 日更 UP 少时)
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --window-days 1

# 抓指定日期窗口
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --date 2026-06-09 --window-days 1

# 重新入库 (修改 schema / 重跑分析前)
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --import-only

# 调试: 不入库只生成 JSON
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --no-import
```

## 数据流

```
bilibili-finance-up.md  ──(parse_up_list)──▶  ups[] / blacklist[]
                                                  │
                                                  ▼
opencli bilibili user-videos  ──fallback──▶  bili user-videos
                                                  │
                                       is_in_window(date, target, N)
                                                  │
                                                  ▼
opencli bilibili comments-raw  (含 pics[])
                                                  │
                                                  ▼
                                  download_images_for_comments
                                                  │
                                                  ▼
                     comments/bilibili_<date>.json   (audit / 备份)
                                  + comments/images/bilibili/<bvid>/*   (本地)
                                                  │
                                                  ▼
                          CommentRepository.insert()   (去重 by comment_id)
```

## 关键设计

- **取数双路**：`opencli` 优先（`Strategy.COOKIE`，带 `date` 字段），失败时降级到 `bili`（`browser-cookie3` 读本地 Chrome cookie，无日期字段仅作兜底）
- **`OPENCLI_WINDOW=background`**：`run()` 全局注入环境变量，所有 opencli 子进程自动 background 窗口，避免 `Strategy.COOKIE` 在拿不到 bridge 时启动/前台化 Chrome 抢焦点
- **入库去重**：`_existing_comment_ids()` 一次查 DB，命中 `(platform, comment_id)` 跳过；同批内重复即时加入集合防自冲
- **图片下载**：`pics[]` 全量下载到 `comments/images/bilibili/<bvid>/<rpid>_<idx>.<ext>`，DB `local_image_path` 只存首张成功图，`original_url` 备份原 URL

## 图片理解 (mmx-cli-cn)

每条带配图的评论下载完成后，会调用 `mmx vision describe` (MiniMax VLM)
对每张图做语义理解，结果写回 JSON 并作为 `image_description` 字段附在
comment 上，供后续情绪分析结合图片语境。

### 调用方式

```bash
mmx vision describe --image <path> --prompt "<问题>" --output text --quiet
```

底层由 `bilibili_image_downloader.describe_images_for_comments()` 驱动：

- 默认 prompt 偏向"金融/股票/财经/行情/K线/新闻标题/表情包文字"
- 描述写回 `comment.images[*].description`；首张有描述的图再镜像到 `comment.image_description`
- 走 `subprocess.run` + `mmx` 进程模型；Windows 下自动解析 `.cmd` shim
- 失败/空描述只写 `errors[]`，不中断整个采集
- 已描述的图跳过（idempotent，可重复跑补全）

### CLI 用法

```bash
# 默认开: 采集时自动理解配图
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py

# 关闭 (例如只做下载不入语义)
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --no-describe-images

# 已有 JSON 补跑 (--import-only 也会触发)
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --date 2026-06-09 --import-only

# 调高 mmx 调用间隔 (限流/避免配额突刺)
python jobs/bilibili_comments_collector/scripts/collect_bilibili_today.py --describe-sleep 1.0
```

### JSON 输出

```json
{
  "rpid": 302012560417,
  "text": "哈哈哈哈这图太准了",
  "images": [
    {
      "original_url": "https://...302012560417.jpg",
      "local_path": "comments/images/bilibili/BV.../302012560417_0.jpg",
      "downloaded": true,
      "size_bytes": 56875,
      "description": "一张讽刺中国股民的搞笑表情包..."
    }
  ],
  "image_description": "一张讽刺中国股民的搞笑表情包..."
}
```

### 库 API

```python
from bilibili_image_downloader import describe_image_with_mmx, describe_images_for_comments

# 单张
print(describe_image_with_mmx(Path("comments/images/bilibili/BV.../rpid_0.jpg")))

# 批量 (与 download_images_for_comments 同样的入参习惯)
stats = describe_images_for_comments(comments, project_root=Path("."))
print(stats["described"], stats["failed"])
```

## 输出文件

- `comments/bilibili_<date>.json` — 全量数据（视频 + 评论 + 错误 + 元信息）
- `comments/bilibili_<date>.json.bak.<ts>` — 覆盖前自动备份
- `comments/images/bilibili/<bvid>/*.{jpg,png}` — 评论配图
- `intermediate/bilibili_<date>.partial.json` — 每次 UP 循环结束落盘

## 常见错误

| 现象 | 原因 / 处理 |
|---|---|
| `bili user-videos` 返回 412 | 风控窗口期；脚本已自动降级到 `opencli`，但若都失败可 `bili login` 刷新 cookie |
| 当日 0 命中视频 | UP 主多为非日更；改用 `--window-days 1` 或更大窗口 |
| 评论 `time` 全部晚于视频 `date` 一天 | opencli `user-videos` 的 `date` 字段疑似 +1 天错位（详见 `issues.md` 2026-06-10 段） |
| 重跑导致评论重复 | 已有 `(platform, comment_id)` 去重；如需重导整批先 `DELETE FROM comments WHERE platform='bilibili' AND created_at LIKE '<date>%'` |
| 浏览器弹出抢焦点 | 检查 `run()` 是否注入 `OPENCLI_WINDOW=background` 环境变量 |
| `opencli bilibili comments-raw` 不在 | 私有 adapter 在 `~/.opencli/clis/bilibili/comments-raw.js`，丢失则用 `jobs/bilibili_comments_collector/issues.md` 内的源恢复 |
| `mmx: command not found` (图片理解) | 先 `pip install @minimax/mmx-cli-cn` 或确保 `mmx` 在 PATH；Windows 下用 `where mmx` 检查 `.cmd` shim |
| mmx vision 超时 / 配额耗尽 | 单张图失败会写进 `errors[]`；整体流程继续；调高 `--describe-sleep` 避开限流 |

## 扩展点

- **新增 UP 主**：编辑 `bilibili-finance-up.md`，加到 `## 个人UP主` 表格（不要写进 `## up黑名单` 段）
- **新增黑名单**：编辑 `bilibili-finance-up.md`，加到 `## up黑名单` 表格
- **支持其他平台**：复制 `scripts/collect_bilibili_today.py` 改 opencli 命令，套同样的 `is_in_window` + `_existing_comment_ids` 模式
- **配图按需下载**：当前默认下载所有 `pics[]`；要做开关改 `attach_images()` 的调用

## 关键文件

- `expectation.md` — 任务定义（采集目标 / 注意事项）
- `bilibili-finance-up.md` — UP 主列表 + 黑名单
- `issues.md` — 历次运行问题、根因、处置（按日期分段）
- `scripts/collect_bilibili_today.py` — 入口脚本
- `scripts/bilibili_image_downloader.py` — 配图下载 + `mmx vision describe` 图片理解
- `~/.opencli/clis/bilibili/comments-raw.js` — 私有 opencli adapter（含 pics 字段）
