---
name: xiaodeng-daily
description: 小登股(硬科技)情绪按天 / 按 ISO 周 / 按平台趋势。复用 DB 已有 sentiment + `xiaodeng_sentiment.py` 的口径，输出 Markdown / Excel / HTML / JSON 报告。
---

# 小登股按天情绪趋势

## 适用场景
- 看 6 月以来散户对硬科技股(小登股)情绪逐日变化 + 周累计 + 平台 × 天对比。
- 适合回答"06-15 / 06-17 这种指数大涨的日子散户怎么看科技股"。

## 公开入口

```bash
python schedule/collect_all/scripts/xiaodeng_daily.py
```

无 CLI 参数。起始日期写死在脚本顶部：

```python
DAILY_START = "2026-06-01"   # 6 月以来
TODAY = "2026-06-20"
```

要追溯更早改 `DAILY_START`；要按周/月聚合改 `render_md()` 里的 `isocalendar()`。

## 样本口径

与 `xiaodeng_sentiment.py` **完全一致**：

| 筛选 | 实现 |
|---|---|
| symbol 模式 | `symbol LIKE 'SH688%' OR symbol LIKE 'SZ300%' OR symbol LIKE 'BJ8%'`（科创板 / 创业板 / 北交所） |
| 关键词模式 | `content LIKE '%<kw>%'` 30 个硬科技词 |

排除：
1. `互联网 / 腾讯 / 蜜雪 / 泡泡玛特 / 消费电子` —— 老登/消费类
2. `新能源 / 光伏 / 锂电 / 锂电池 / 新能源车` —— 周期股不算新兴科技

**DB 时区**：评论的 `created_at` 是混合存储（CST naive / UTC ISO+Z）。脚本在 SQL 层用 `date(datetime(created_at, '+8 hours'))` 把 UTC 折算到 CST 日期再 GROUP BY。

## 输出

| 路径 | 说明 |
|---|---|
| `schedule/collect_all/output/sentiment-xiaodeng-daily-<TODAY>.md` | Markdown（按天 + 按 ISO 周 + 平台 × 天） |
| `schedule/collect_all/output/sentiment-xiaodeng-daily-<TODAY>.html` | 自包含 HTML |
| `schedule/collect_all/output/sentiment-xiaodeng-daily-<TODAY>.xlsx` | Daily + Platform×Day 双 Sheet |
| `schedule/collect_all/output/sentiment-xiaodeng-daily-<TODAY>.json` | 汇总 JSON（daily + platform_daily） |

报告结构（Markdown）：
1. 标题 + 起始日期 + 累计样本 + 加权得分
2. **按天汇总（含赞加权 + 每日变化）**：日期 / 评论数 / 看好-中立-看跌 / 平均得分 / **赞加权得分** / **DoD 变化** / **累计赞加权** / 高赞数
3. **趋势观察**：累计高赞方向、赞加权得分最看多 / 最看空两天、当日反转 / 回落最大、累计赞加权得分变化（since-June）
4. **按 ISO 周汇总**：每周评论数 + 评论数加权得分 + **赞加权得分**
5. **按平台 × 天**：每个平台当日得分矩阵（颜色：绿 > +0.05 / 红 < -0.05 / 灰 中性）

## 数据流

```
db/comments.db.comments
   │
   ├── (1) date(datetime(created_at, '+8 hours')) GROUP BY day
   ├── (2) WHERE symbol OR keyword 命中
   └── (3) COALESCE(sentiment_fix, sentiment) → 正面/中性/负面
       │
       ├──► 按天汇总 (daily)
       │       │
       │       ▼
       │   按 ISO 周汇总 (weekly)
       │
       └──► 按 (day, platform) GROUP BY (platform_daily)
                                       │
                                       ▼
             ┌────────────┬───────────┴──────────┬────────────┐
             ▼            ▼                      ▼            ▼
          Markdown       Excel                 HTML          JSON
```

## 关键设计
- **复用 DB 已有情绪**：本脚本只读 `sentiment` / `sentiment_score`，不调 LLM。要让某天有数据，前提是 `db/update_sentiment.py` 已经跑过。
- **聚合在 SQL 层**：`GROUP BY d` / `GROUP BY d, platform`；不在 Python 侧 reduce。
- **三种加权口径**：
  - `评论数加权得分` = `AVG(sentiment_score)` — 当日每条评论等权平均
  - `赞加权得分` = `Σ(score × likes) / Σ(likes)` — 被点赞越多的评论权重越大，反映"被广泛认同"的方向（**主指标**）
  - `累计赞加权得分` = `Σ_from_start(score × likes) / Σ_from_start(likes)` — 单调反映整体情绪从 06-01 起的累计漂移
- **DoD 变化**：当日赞加权得分 − 前一日赞加权得分；首日显示"—"
- **时区偏移在 SQL**：`'+8 hours'` 是常量；如改时区只改这一处。

## 已知限制
- 6 月初几天（06-01 ~ 06-07）只有雪球评论入库（B 站 / 小红书 06-08 才开始有数据），单平台数据。
- 平台 × 天矩阵里的"—"表示当天该平台无命中评论。
- 起始日期 `2026-06-01` 是硬编码；要追溯到 5 月或更早改 `DAILY_START`。
- **W25 赞加权得分 = 0.0 是因为该周统计日尚未结束**（含本周六 06-20 后续还在累计）。

## 关键文件
- `schedule/collect_all/scripts/xiaodeng_daily.py` — 入口脚本
- `schedule/collect_all/scripts/xiaodeng_sentiment.py` — 同期窗口报告（共享 KEYWORDS 口径）
- `jobs/sentiment_analyzer/xiaodeng_sentiment.md` — 口径定义
- `jobs/sentiment_analyzer/llm_sentiment.py` — LLM 情绪分析器
- `db/comments.db` — 数据源