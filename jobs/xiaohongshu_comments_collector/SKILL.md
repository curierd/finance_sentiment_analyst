# 小红书评论收集器

## 工具链

| 工具 | 用途 | 命令 |
|------|------|------|
| `opencli xiaohongshu user` | 获取博主笔记列表（含 xsec_token） | `opencli xiaohongshu <id> --limit 20 -f json` |
| `xhs comments` | 获取笔记全部评论（含子评论、配图、时间戳） | `xhs comments <note_id> --all --xsec-token <token> --json` |
| `xhs sub-comments` | 获取单条评论的完整子评论 | `xhs sub-comments <note_id> <comment_id> --json` |

**不要用** `xhs user-posts` — API 返回 `{"code": -1, "success": false}`。

## 执行流程

### 1. 收集评论

```bash
python jobs/xiaohongshu_comments_collector/scripts/collect_comments.py
```

流程：
1. 从 `xiaohongshu-finance-up.md` 解析博主列表（昵称 + user_id）
2. 用 `opencli xiaohongshu user <id> -f json` 获取每位博主的笔记列表
3. **筛选今日笔记**：笔记 ID 前8位 hex → Unix 时间戳 → 日期
   ```python
   ts = int(note_id[:8], 16)
   date = datetime.fromtimestamp(ts, tz=CST).strftime("%Y-%m-%d")
   ```
4. 从笔记 URL 提取 `xsec_token`（评论 API 必需）
5. 用 `xhs comments <note_id> --all --xsec-token <token> --json` 获取全部评论
6. 对 `sub_comment_has_more=true` 的评论，用 `xhs sub-comments` 追加子评论
7. 归一化评论数据（保留 `pictures` 字段），保存到 `comments/xiaohongshu_<date>.json`

### 2. 导入数据库

```bash
python jobs/xiaohongshu_comments_collector/scripts/import_to_db.py --date 2026-06-09
```

流程：
1. 读取收集的 JSON，遍历每篇笔记的评论+子评论
2. 按 `comment_id` 去重，已存在的仅更新 likes
3. **评论配图**：仅当评论有 `pictures` 字段时下载到 `comments/images/xiaohongshu/comments/`，设置 `local_image_path` 和 `original_url`
4. 无配图的评论：`local_image_path = NULL`，`original_url = NULL`
5. 笔记元数据写入 `videos` 表
6. 评论写入 `comments` 表

### 3. 情绪分析

```bash
python db/update_sentiment.py
```

## 数据格式

### 收集输出 JSON 结构

```json
{
  "target_date": "2026-06-09",
  "platform": "小红书",
  "notes": [
    {
      "note_id": "6a27a55800000000220227d7",
      "title": "为富不仁！",
      "author": "小红他叔",
      "user_id": "61acb1f7000000001000aa34",
      "likes": 121,
      "url": "https://www.xiaohongshu.com/...",
      "xsec_token": "AB7rT7_...",
      "comments": [
        {
          "id": "6a261c19000000002a007b1a",
          "content": "666",
          "author": "momo",
          "author_id": "...",
          "like_count": 5,
          "create_time": "2026-06-08 20:00",
          "create_time_ms": 1780886400000,
          "ip_location": "浙江",
          "sub_comment_count": 2,
          "sub_comments": [...],
          "pictures": [
            {"url_default": "http://sns-webpic-qc.xhscdn.com/.../comment/...", "url_pre": "..."}
          ]
        }
      ]
    }
  ]
}
```

### DB 字段映射

| JSON 字段 | DB 字段 | 说明 |
|-----------|---------|------|
| `id` | `comment_id` | 平台评论 ID |
| `content` | `content` | 加前缀 `[笔记: xxx]` / `[回复]` |
| `author` | `author_name` | 评论者昵称 |
| `like_count` | `likes` | 点赞数 |
| `create_time` | `created_at` | `2026-06-08 20:00` 格式 |
| `pictures[0].url_default` | `original_url` | 评论配图原始链接 |
| 下载到本地 | `local_image_path` | `comments/images/xiaohongshu/comments/<id>.jpg` |
| `note_id` | `video_bvid` | 笔记 ID |
| `note_title` | `video_title` | 笔记标题 |
| 博主昵称 | `up_name` | 笔记作者 |
| 博主 ID | `up_uid` | 笔记作者 ID |
| — | `platform` | 固定 `xiaohongshu` |

## 评论配图规则

- 评论配图 ≠ 笔记封面 ≠ 评论者头像
- 只有评论自带 `pictures` 字段才有配图（约 2-5% 的评论有配图）
- 无配图评论：`local_image_path = NULL`，`original_url = NULL`
- 配图下载到 `comments/images/xiaohongshu/comments/<comment_id>.jpg`
- 原始 URL 备份到 `original_url` 字段

## 限流与注意事项

- **请求间隔 ≥1.2s**，禁止并发
- `xhs comments` 需要 `--xsec-token`，否则报错；token 从 `opencli user` 返回的笔记 URL 中提取
- `opencli xiaohongshu user` 对部分用户报 "Malformed user snapshot: user store was not found"，约 50% 博主受影响，无法绕过
- 笔记 ID 时间戳解码规则：前8位 hex = Unix 时间戳，用于按日期筛选（opencli 不返回日期字段）
- 子评论：`xhs comments --all` 自动翻页获取顶级评论，但子评论只返回部分；`sub_comment_has_more=true` 时需调用 `xhs sub-comments` 补全

## 目录结构

```
jobs/xiaohongshu_comments_collector/
├── expection.md                    # 任务定义
├── SKILL.md                        # 本文件
├── issues.md                       # 运行问题记录
├── xiaohongshu-finance-up.md       # 博主列表
├── intermediate/                   # 中间文件
│   ├── bloggers.json
│   ├── posts_<user_id>.json
│   ├── today_notes.json
│   └── comments_<note_id>.json
└── scripts/
    ├── collect_comments.py          # 步骤1: 收集评论
    ├── import_to_db.py              # 步骤2: 导入数据库
    ├── fix_comment_pictures.py      # 补丁: 修复历史评论配图
    ├── fix_comment_images.py        # (废弃) 旧的头像修复脚本
    └── update_via_api.py            # (废弃) 旧的 API 更新脚本
