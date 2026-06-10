---
name: zhihu-comments-collector
description: 从知乎搜索 A 股相关话题，抓取今日回答的评论（含子评论），配图下载到本地，写入 `comments/zhihu_<date>.json` 并入库。使用 `opencli zhihu` 命令，`OPENCLI_WINDOW=background` 全局不抢焦点。
---

# 知乎 A 股评论采集器

## 适用场景
- 每日抓取知乎 A 股相关话题下的回答评论
- 搜索词配置在 `zhihu-search-terms.md`
- 评论配图下载到 `static/zhihu/comments/<answer_id>/<id>_<idx>.<ext>`

## 公开入口

```bash
python jobs/zhihu_comments_collector/scripts/collect_zhihu.py [FLAGS]
```

## CLI 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--date` | 今天 | 目标日期 `YYYY-MM-DD` (北京时间) |
| `--limit` | 20 | 每回答评论上限 |
| `--replies-limit` | 10 | 每评论子回复上限 |
| `--search-limit` | 20 | 每搜索词结果上限 |
| `--sleep` | 1.5 | 请求间隔秒数（防风控） |
| `--import-only` | off | 跳过采集，仅从已有 JSON 入库 |
| `--no-import` | off | 采集但不入库 |
| `--no-download` | off | 不下载配图 |

## 常用调用

```bash
# 抓今天
python jobs/zhihu_comments_collector/scripts/collect_zhihu.py

# 抓指定日期
python jobs/zhihu_comments_collector/scripts/collect_zhihu.py --date 2026-06-09

# 调试: 不入库不下载
python jobs/zhihu_comments_collector/scripts/collect_zhihu.py --no-import --no-download
```

## 数据流

```
zhihu-search-terms.md  ──parse_search_terms──▶  queries[]
                                                    │
                                                    ▼
opencli zhihu search <query> --type all -f json
                                                    │
                                              extract answer IDs from URLs
                                                    │
                                                    ▼
opencli zhihu answer-comments <id> --limit N --replies-limit M -f json
                                                    │
                                            filter by created_at (today CST)
                                                    │
                                                    ▼
                                      download_images (extract from content)
                                                    │
                                                    ▼
                      comments/zhihu_<date>.json   (audit / 备份)
                                 + static/zhihu/comments/<answer_id>/*   (本地)
                                                    │
                                                    ▼
                           CommentRepository.insert()   (去重 by comment_id)
```

## 关键设计

- **搜索驱动**: 无预设UP主列表，通过搜索词发现当日热门讨论
- **`OPENCLI_WINDOW=background`**: `run()` 全局注入环境变量，所有 opencli 子进程自动 background 窗口
- **入库去重**: `_existing_comment_ids()` 一次查DB，命中 `(platform, comment_id)` 跳过
- **时区处理**: Zhihu `created_at` 为 UTC，转换为北京时间（CST = UTC+8）过滤
- **子评论支持**: `--replies-limit` 控制每个顶层评论的子回复数量
- **去重答案**: 同一次采集可能搜到相同回答，按 `answer_id` 去重

## 输出文件

- `comments/zhihu_<date>.json` — 全量数据（答案 + 评论 + 错误 + 元信息）
- `static/zhihu/comments/<answer_id>/<id>_<idx>.<ext>` — 评论配图
- `intermediate/zhihu_<date>.partial.json` — 每次搜索词循环结束落盘

## 常见错误

| 现象 | 原因 / 处理 |
|---|---|
| 搜索返回空 | 关键词太窄；尝试更宽泛的搜索词 |
| answer-comments 返回空 | 回答可能无评论；正常跳过 |
| 浏览器弹出抢焦点 | 检查 `run()` 是否注入 `OPENCLI_WINDOW=background` |
| 配图下载失败 | 知乎图片可能有防盗链；记录到 errors 继续 |
| DB 写入报 platform CHECK 约束 | 运行 `python db/migrate_add_zhihu.py` 迁移数据库 |

## 扩展点

- **新增搜索词**: 编辑 `zhihu-search-terms.md`，添加到对应分类下
- **支持热门话题**: 可接入 `opencli zhihu hot` 自动发现财经热点
- **支持推荐流**: 可接入 `opencli zhihu recommend` 发现热帖

## 关键文件

- `expectation.md` — 任务定义（采集目标 / 注意事项）
- `zhihu-search-terms.md` — 搜索关键词列表
- `issues.md` — 历次运行问题、根因、处置（按日期分段）
- `scripts/collect_zhihu.py` — 入口脚本
