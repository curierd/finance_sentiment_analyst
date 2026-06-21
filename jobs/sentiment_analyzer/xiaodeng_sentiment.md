---
name: xiaodeng-sentiment
description: 散户对科技股 / 小盘股（小登股）的看好 / 中立 / 看跌三分类情绪分析。复用 `SentimentAnalyzer` + DB 窗口数据，输出 Markdown / Excel / HTML / JSON 报告。
---

# 小登股情绪分析

## 适用场景
- 在已有 `db/comments.db` 全平台评论 + 情绪数据的基础上，按"小登股"口径筛子集，输出 看好 / 中立 / 看跌 占比 + 平均得分 + 按平台拆分 + 高赞评论样本。
- "小登股" = 散户偏好的科技 / 成长 / 创业板 / 科创板股票+ 科技关键词 + symbol 科创/创业/北证代码段。

## 公开入口

```bash
python schedule/collect_all/scripts/xiaodeng_sentiment.py
```

无 CLI 参数。窗口写死在脚本顶部常量：

```python
WINDOW_START = datetime(2026, 6, 19, 15, 0, 0, tzinfo=CST)
WINDOW_END   = datetime(2026, 6, 23, 9, 30, 0, tzinfo=CST)
TODAY        = "2026-06-20"
```

要换窗口直接改这三个常量；时间窗口过滤在 `fetch_xiaodeng()` 内通过 `datetime(created_at) >= datetime(WINDOW_START, '-8 hours')` 把 CST 折算到 UTC。

## 样本筛选

去重合并以下两类：

| 筛选 | 实现 |
|---|---|
| symbol 模式 | `symbol LIKE 'SH688%' OR symbol LIKE 'SZ300%' OR symbol LIKE 'BJ8%'`（科创板 / 创业板 / 北交所） |
| 关键词模式 | `content LIKE '%<kw>%'` 关键词集合（见下） |

```python
KEYWORDS = [
    # 直接科技关键词
    "科技", "AI", "人工智能", "半导体", "芯片",
    "光模块", "PCB", "印制电路", "玻璃基板",
    "算力", "大模型", "GPU", "CPU", "存储", "FPGA",
    "机器人", "智能驾驶", "自动驾驶",
    # 板块/市场结构词
    "创业板", "科创板", "科创", "小盘", "成长",
    "结构牛", "硬科技",
    # 行业内具体股票（中芯 = 半导体龙头，不在互联网/潮玩范围）
    "中芯", "寒武纪", "海光", "中际旭创", "京东方",
]
```

**口径说明**：严格硬科技定义。两层排除：
1. `互联网平台股（腾讯）` / `潮玩/茶饮（蜜雪、泡泡玛特）` / 泛指词 `互联网` / `消费电子` —— 属"老登/消费"，不是硬科技。
2. `新能源` / `光伏` / `锂电` / `锂电池` / `新能源车` —— 属传统制造业 / 周期股，**不算新兴科技股主体**。

`consumer-tech.md` 里的腾讯/蜜雪/泡泡玛特从关键词集合中剔除；如需单独分析互联网/潮玩或新能源/光伏，另起一个口径脚本（参考 `data/sections/consumer-tech.md`）。

DB 的 `symbol` 字段是雪球采集时填的（B 站 / 小红书 / 知乎通常为空），所以 keyword 兜底是必要的。

## 情绪来源

`run_llm_sentiment(records)` 优先复用 DB 内已有 `sentiment` / `sentiment_score`（来自 `db/update_sentiment.py` 的批量 LLM 跑批），仅对 `effective_sentiment` 为空的评论才再次调用 `SentimentAnalyzer().analyze_batch()`。`SentimentAnalyzer` 接口细节见 `jobs/sentiment_analyzer/SKILL.md`。

情绪标签映射：
- `正面` → **看好**
- `中性` → **中立**
- `负面` → **看跌**

## 输出

| 路径 | 说明 |
|---|---|
| `schedule/collect_all/output/sentiment-xiaodeng-<TODAY>.html` | 自包含 HTML（含样式 + 高赞样本） |
| `schedule/collect_all/output/sentiment-xiaodeng-<TODAY>.xlsx` | Summary + TopComments 双 Sheet |

报告结构（Markdown）：
1. 标题 + 窗口 + 样本口径
2. 整体情绪：看好 / 中立 / 看跌 占比 + 平均得分 + 高赞子表
3. 解读：综合得分 → 看好 / 中立 / 看跌（≥+0.05 看好 / ≤-0.05 看跌 / 否则中立）
4. 按平台拆分表
5. 高赞评论样本 (likes>10)
6. 数据源说明

## 数据流

```
db/comments.db
   │
   ├── (1) symbol pattern LIKE 'SH688%' OR 'SZ300%' OR 'BJ8%'   ──►  176 条
   │
   ├── (2) content LIKE '%<keyword>%' (OR 拼接 31 个关键词)     ──►  212 条
   │
   └── union (1) ∪ (2) 去重                                      ──►  265 条
                                       │
                                       ▼
                          COALESCE(sentiment_fix, sentiment)
                                       │
                                       ▼
                       正面/中性/负面 → 看好/中立/看跌
                                       │
                                       ▼
             ┌────────────┬───────────┴──────────┬────────────┐
             ▼            ▼                      ▼            ▼
          Markdown       Excel                 HTML          JSON
```

## 关键设计
- **去重在 SQL 层用 `OR`**：不在 Python 侧 dedup，避免内存放大。
- **情绪优先复用 DB**：`db/update_sentiment.py` 已经全量跑过，新评论只要没新增就不要重复花钱打 LLM。
- **标签映射在三处**：`aggregate()` / `render_md` / `render_html` 都有一份 `{"正面": "看好", ...}` 字典；改词必须三处同步。
- **窗口内 DB 写时区**：DB 的 `created_at` 是混合存储（CST naive / UTC ISO+Z），脚本通过 `'-8 hours'` 偏移把 UTC 折算到 CST 过滤。

## 关键文件
- `schedule/collect_all/scripts/xiaodeng_sentiment.py` — 入口脚本（自包含：取数 + 渲染 + 导出）
- `jobs/sentiment_analyzer/llm_sentiment.py` — 情绪分析器（依赖）
- `db/comments.db` — 数据源