# 金融评论情绪分析 — API 文档

## 基础信息

- **Base URL**: `http://localhost:5000`
- **Content-Type**: `application/json`
- **架构**: 前后端分离，Flask REST API

---

## 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/comments` | 分页查询评论列表 |
| POST | `/api/comments` | 新增评论 |
| GET | `/api/comments/<id>` | 获取单条评论 |
| PATCH | `/api/comments/<id>` | 锁定/解锁情绪 |
| PATCH | `/api/comments/<id>/image` | 更新评论配图路径 |
| POST | `/api/comments/<id>/image/upload` | 上传评论配图文件 |
| DELETE | `/api/comments/<id>` | 删除评论 |
| GET | `/api/stats` | 情绪统计聚合 |
| GET | `/api/stats/timeline` | 按时间线情绪聚合 |
| GET | `/api/up_masters` | UP主列表 |
| GET | `/api/videos` | 视频列表 |

---

## POST /api/comments

新增一条评论。

### Request Body

```json
{
  "platform": "xueqiu",
  "content": "测试评论内容",
  "author_name": "测试用户",
  "likes": 0,
  "video_title": "可选",
  "symbol": "SH600519"
}
```

`platform` 可选值：`bilibili` / `xueqiu` / `xiaohongshu`（允许 null）。

### Response

`201 Created`

```json
{
  "id": 1234,
  "platform": "xueqiu",
  "content": "测试评论内容",
  ...
}
```

`content` 为空返回 `400`。

---

## GET /api/comments

分页查询评论，支持多维过滤。

### Query Parameters

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `platform` | string | — | 平台：`bilibili` / `xueqiu` / `xiaohongshu` |
| `up_name` | string | — | UP主名称（模糊匹配） |
| `video_title` | string | — | 视频标题（模糊匹配） |
| `sentiment` | string | — | 情绪：`正面` / `中性` / `负面`（显示用 COALESCE） |
| `author` | string | — | 作者名（模糊匹配） |
| `locked` | string | — | `0`=仅自动分析，`1`=仅已锁定 |
| `page` | int | 1 | 页码 |
| `page_size` | int | 50 | 每页条数 |

### Response

```json
{
  "items": [
    {
      "id": 869,
      "platform": "xueqiu",
      "author_name": "投资随感录",
      "content": "平安兴业同一天分红...",
      "likes": 2,
      "sentiment": "正面",
      "sentiment_score": 0.8,
      "sentiment_fix": null,
      ...
    }
  ],
  "total": 672,
  "page": 1,
  "page_size": 50,
  "pages": 14
}
```

---

## GET /api/comments/<id>

获取单条评论详情。

### Response

```json
{
  "id": 869,
  "platform": "xueqiu",
  "author_name": "投资随感录",
  "content": "平安兴业同一天分红...",
  "likes": 2,
  "sentiment": "正面",
  "sentiment_score": 0.8,
  "sentiment_fix": null,
  ...
}
```

未查到返回 `null`。

---

## PATCH /api/comments/<id>

手动锁定评论的情绪判定。锁定后 `update_sentiment.py` 自动分析时会跳过该条。

### Request Body

```json
{
  "sentiment_fix": "正面"
}
```

可选值：`"正面"` / `"中性"` / `"负面"` / `null`（解除锁定）

### Response

```json
{
  "id": 869,
  "sentiment_fix": "正面",
  "sentiment": "正面",
  ...
}
```

无效值返回 `400`。

---

## PATCH /api/comments/<id>/image

更新评论的配图路径。

### Request Body

```json
{
  "local_image_path": "comments/images/bilibili/comment_123.jpg",
  "original_url": "https://example.com/original.jpg"
}
```

至少提供 `local_image_path` 或 `original_url` 之一。

### Response

```json
{
  "id": 123,
  "local_image_path": "comments/images/bilibili/comment_123.jpg",
  "original_url": "https://example.com/original.jpg",
  ...
}
```

评论不存在返回 `404`，无有效字段返回 `400`。

---

## POST /api/comments/<id>/image/upload

上传配图文件，自动保存到 `comments/images/<platform>/` 目录并更新 `local_image_path`。

### Request

`Content-Type: multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | file | 是 | 图片文件 |
| `original_url` | string | 否 | 原始图片 URL |

### Response

```json
{
  "id": 123,
  "local_image_path": "comments/images/bilibili/comment_123.jpg",
  "original_url": "https://example.com/original.jpg",
  ...
}
```

评论不存在返回 `404`，未提供文件返回 `400`。

---

## DELETE /api/comments/<id>

删除指定评论。

### Response

```json
{ "success": true }
```

评论不存在返回 `404`。

---

## GET /api/stats/timeline

按时间粒度聚合情绪统计，以评论发布时间（`created_at`）为准。

### Query Parameters

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `granularity` | `day` | 粒度：`day` / `week` / `month` |

### Response

```json
{
  "2026-06-05": {
    "total": 107,
    "positive": 23,
    "neutral": 63,
    "negative": 21
  },
  "2026-06-06": {
    "total": 110,
    "positive": 57,
    "neutral": 48,
    "negative": 5
  }
}
```

无效值返回 `400`。

---

## GET /api/stats

情绪统计聚合。

### Response

```json
{
  "auto": {
    "正面": 185,
    "中性": 391,
    "负面": 96
  },
  "locked": {
    "正面": 3,
    "中性": 20,
    "负面": 5
  },
  "auto_count": 644,
  "locked_count": 28,
  "like_weighted": {
    "中性": 73.8,
    "正面": 16.6,
    "负面": 9.6
  }
}
```

- `auto`: 未锁定评论的情绪分布
- `locked`: 已手动锁定评论的情绪分布
- `like_weighted`: 点赞加权百分比（自动分析且 likes > 0 的评论）

---

## GET /api/up_masters

获取去重的 UP主列表。

### Response

```json
[
  { "up_name": "投资随感录", "up_uid": "...", "platform": "xueqiu" },
  ...
]
```

---

## GET /api/videos

获取去重的视频/帖子标题列表。

### Response

```json
[
  { "video_title": "平安银行分红分析", "video_bvid": "...", "platform": "bilibili" },
  ...
]
```

---

## 启动方式

```bash
cd frontend
pip install -r requirements.txt
python server.py
# → http://localhost:5000
```