---
name: laodeng-daily
description: 老登股(主板蓝筹/红利)情绪按天 / 按 ISO 周 / 按平台趋势。复用 DB 已有 sentiment + `laodeng_sentiment.py` 的口径，输出 Markdown / Excel / HTML / JSON 报告。
---

# 老登股按天情绪趋势

## 适用场景
- 看近 30 天来散户对老登股(主板蓝筹 / 红利 / 高股息 / 大盘 ETF)情绪逐日变化 + 周累计 + 平台 × 天对比。
- 与 `xiaodeng_daily.md` 配对：用于回答"06-15 / 06-17 指数大涨的日子，老登（红利蓝筹）和小登（硬科技）情绪是否同向 / 谁更强 / 谁先反转"。
- 适合跟踪"风格切换"叙事：哪几天散户从小登切到老登、哪几天反向。

## 公开入口

```bash
python schedule/collect_all/scripts/laodeng_daily.py
```

无 CLI 参数。起始日期写死在脚本顶部：

```python
DAILY_START = "2026-05-23"   # 近 30 天（对齐 xiaodeng_daily 6 月窗口起点）
TODAY = "2026-06-20"
```

要追溯更早改 `DAILY_START`；要按周/月聚合改 `render_md()` 里的 `isocalendar()`。

## 样本口径

与 `laodeng_sentiment.py` **完全一致**：

| 筛选 | 实现 |
|---|---|
| 主板大票模式 | `symbol LIKE 'SH600%' OR symbol LIKE 'SH601%' OR symbol LIKE 'SH603%'` |
| 预设标的模式 | `symbol IN (laodeng.md 12 个 symbol)` |
| 关键词模式 | `content LIKE '%<kw>%'` 38 个红利 / 蓝筹 / 白酒 / 银行 / 保险 / 煤炭 / 电力词 |

排除：
1. `科技 / AI / 半导体 / 芯片 / 寒武纪 / 海光 / 光模块 / 算力` —— 小登 / 硬科技类
2. `互联网 / 腾讯 / 蜜雪 / 泡泡玛特 / 消费电子` —— 消费 / 新经济细分
3. `新能源 / 光伏 / 锂电 / 锂电池 / 新能源车` —— 周期股不算价值蓝筹主体

**DB 时区**：评论的 `created_at` 是混合存储（CST naive / UTC ISO+Z）。脚本在 SQL 层用 `date(datetime(created_at, '+8 hours'))` 把 UTC 折算到 CST 日期再 GROUP BY。

## 输出

| 路径 | 说明 |
|---|---|
| `schedule/collect_all/output/sentiment-laodeng-daily-<TODAY>.md` | Markdown（按天 + 按 ISO 周 + 平台 × 天） |
| `schedule/collect_all/output/sentiment-laodeng-daily-<TODAY>.html` | 自包含 HTML |
| `schedule/collect_all/output/sentiment-laodeng-daily-<TODAY>.xlsx` | Daily + Platform×Day 双 Sheet |
| `schedule/collect_all/output/sentiment-laodeng-daily-<TODAY>.json` | 汇总 JSON（daily + platform_daily） |

报告结构（Markdown）：
1. 标题 + 起始日期 + 累计样本 + 加权得分
2. **按天汇总（含赞加权 + 每日变化）**：日期 / 评论数 / 看好-中立-看跌 / 平均得分 / **赞加权得分** / **DoD 变化** / **累计赞加权** / 高赞数
3. **趋势观察**：累计高赞方向、赞加权得分最看多 / 最看空两天、当日反转 / 回落最大、累计赞加权得分变化（since-DAILY_START）
4. **按 ISO 周汇总**：每周评论数 + 评论数加权得分 + **赞加权得分**
5. **按平台 × 天**：每个平台当日得分矩阵（颜色：绿 > +0.05 / 红 < -0.05 / 灰 中性）
6. **小登 vs 老登 当日得分对照**（取 `sentiment-xiaodeng-daily-<TODAY>.json` 的 `daily` 字段对齐日期拼一行对照表 — 用于回答"风格切换"）

## 数据流

```
db/comments.db.comments
   │
   ├── (1) date(datetime(created_at, '+8 hours')) GROUP BY day
   ├── (2) WHERE (SH600* OR SH601* OR SH603* OR symbol IN (laodeng.md) OR keyword 命中)
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
- **三种加权口径**（与 `xiaodeng_daily.py` 完全一致）：
  - `评论数加权得分` = `AVG(sentiment_score)` — 当日每条评论等权平均
  - `赞加权得分` = `Σ(score × likes) / Σ(likes)` — 被点赞越多的评论权重越大，反映"被广泛认同"的方向（**主指标**）
  - `累计赞加权得分` = `Σ_from_start(score × likes) / Σ_from_start(likes)` — 单调反映整体情绪从 05-23 起的累计漂移
- **DoD 变化**：当日赞加权得分 − 前一日赞加权得分；首日显示"—"
- **时区偏移在 SQL**：`'+8 hours'` 是常量；如改时区只改这一处。
- **小登 vs 老登对照**：读 `sentiment-xiaodeng-daily-<TODAY>.json` 的 `daily` 数组，按 `date` 对齐；不存在某日数据时显示"—"。两份日报的窗口起点不同（老登 05-23 / 小登 06-01），对照表只覆盖两者共同日期段（06-01 ~ TODAY）。

## 已知限制
- 5 月底几天（05-23 ~ 05-31）只有雪球评论入库（B 站 / 小红书 06-08 才开始有数据），单平台数据。
- 平台 × 天矩阵里的"—"表示当天该平台无命中评论。
- 起始日期 `2026-05-23` 是硬编码；要追溯到 4 月或更早改 `DAILY_START`。
- 老登股 symbol 命中率比小登低（雪球采集时 symbol 不一定填主板代码）；主要靠关键词 + 预设 IN 兜底，命中率约 60-70%。
- **W21 赞加权得分 = 0.0 是因为该周统计日尚未结束**（含本周六 06-20 后续还在累计）。
- **小登 vs 老登对照**依赖同窗口期已经跑过 `xiaodeng_daily.py`；若小登 JSON 不存在则跳过对照 section。

## 关键文件
- `schedule/collect_all/scripts/laodeng_daily.py` — 入口脚本
- `schedule/collect_all/scripts/laodeng_sentiment.py` — 同期窗口报告（共享 KEYWORDS 口径）
- `schedule/collect_all/scripts/xiaodeng_daily.py` — 小登日报（对照表数据源）
- `jobs/sentiment_analyzer/laodeng_sentiment.md` — 口径定义
- `jobs/sentiment_analyzer/xiaodeng_daily.md` — 小登日报口径（参考结构）
- `jobs/sentiment_analyzer/llm_sentiment.py` — LLM 情绪分析器
- `data/sections/laodeng.md` — 12 个预设标的清单
- `db/comments.db` — 数据源