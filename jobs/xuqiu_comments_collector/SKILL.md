# Xueqiu Collector — 雪球评论采集

## 快速使用

```bash
# 采集今日评论（默认limit=50/股）
python jobs/xuqiu_comments_collector/scripts/collect_xueqiu.py

# 指定日期和数量
python jobs/xuqiu_comments_collector/scripts/collect_xueqiu.py --date 2026-06-09 --limit 30
```

## 数据源

| 来源 | 文件 | 说明 |
|------|------|------|
| 板块股票 | `data/sections/laodeng.md` | 每行一个SH/SZ前缀代码 |
| 板块股票 | `data/sections/CPO.md` | 名称(代码)格式，自动加前缀 |
| 博主列表 | `jobs/xuqiu_comments_collector/xueqiu-finance-up.md` | 29位财经博主ID与名称 |

## 采集流程

1. **股票讨论** — `opencli xueqiu comments <symbol> --limit N -f json` 逐股票采集
2. **热门动态** — `opencli xueqiu hot --limit 50 -f json`
3. **整理今日评论** — 按日期过滤，标记博主评论
4. **保存结果** — `comments/xueqiu_{date}.json` + `intermediate/xueqiu_{date}.partial.json`

## opencli 命令参考

```bash
# 股票讨论动态
opencli xueqiu comments SH600519 --limit 50 -f json

# 热门动态
opencli xueqiu hot --limit 50 -f json

# 股票实时行情
opencli xueqiu stock SH600519 -f json

# 搜索
opencli xueqiu search 茅台 -f json
```

## 输出格式

`comments/xueqiu_{date}.json` 结构：

```json
{
  "target_date": "2026-06-09",
  "platform": "雪球",
  "sections": { "laodeng": [...], "CPO": [...] },
  "blogger_ids": ["5243796549", ...],
  "blogger_names": {"柯中": "5243796549", ...},
  "stock_comments": [...],
  "hot_discussions": [...],
  "comments": [
    {
      "author": "用户A",
      "text": "评论内容",
      "likes": 10,
      "replies": 2,
      "retweets": 0,
      "created_at": "2026-06-09T06:00:36.000Z",
      "url": "https://xueqiu.com/xxx/yyy",
      "symbol": "SH600519",
      "is_blogger": false
    }
  ]
}
```

## 导入数据库

```python
from backend.repositories.comment_repository import CommentRepository
repo = CommentRepository()

for c in comments:
    repo.insert({
        "platform": "xueqiu",
        "content": c["text"],
        "author_name": c["author"],
        "likes": c["likes"],        # 注意: 字段名是 likes, 不是 like_count
        "replies": c["replies"],
        "retweets": c["retweets"],
        "source_url": c["url"],
        "symbol": c["symbol"],
        "created_at": c["created_at"],
    })
```

## 注意事项

- 请求间隔 ≥1.5秒，不并发，防止触发雪球风控(412/403)
- `opencli xueqiu hot` 返回的数据没有 `created_at` 字段
- `load_blogger_names()` 只匹配5列热门表格，3列个股讨论表格不匹配
- 纯数字股票代码(如CPO.md中的`300308`)会根据首位自动加SH/SZ前缀

## 测试

```bash
python -m unittest jobs.xuqiu_comments_collector.scripts.test_collect_xueqiu -v
```

## 已知限制

详见 `jobs/xuqiu_comments_collector/issues.md`：
- 热门动态无时间戳
- 无 opencli user_timeline 命令（无法直接采集博主个人发帖）
- 无法采集帖子子评论
