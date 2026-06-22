---
name: laodeng-sentiment
description: 散户对老登股(主板蓝筹/红利/上证50/沪深300/白酒/银行/保险/煤炭/电力)的看好 / 中立 / 看跌三分类情绪分析。复用 `SentimentAnalyzer` + DB 窗口数据，输出 Markdown / Excel / HTML / JSON 报告。
---

# 老登股情绪分析

## 适用场景
- 在已有 `db/comments.db` 全平台评论 + 情绪数据的基础上，按"老登股"口径筛子集，输出 看好 / 中立 / 看跌 占比 + 平均得分 + 按平台拆分 + 高赞评论样本。
- 与 `xiaodeng_sentiment.md` 配对：小登 = 散户偏好硬科技 / 科创 / 创业 / 北证；老登 = 机构 / 老股民偏好的主板蓝筹 / 红利 / 高股息 / 大盘 ETF。
- "老登股" = 上证主板大票 (`SH600*` / `SH601*` / `SH603*`) ∪ `laodeng.md` 预设的 12 个标的（上证 50/300/500/黄金 ETF + 工建中招交 + 茅台五粮液 + 长江电力 + 中国神华）∪ 关键词兜底（白酒/银行/保险/煤炭/电力/红利/高股息/上证50/沪深300/中字头）。

## 公开入口

```bash
python schedule/collect_all/scripts/laodeng_sentiment.py
```

无 CLI 参数。窗口写死在脚本顶部常量（与 `xiaodeng_sentiment.py` 复用同一组）：

```python
WINDOW_START = datetime(2026, 6, 19, 15, 0, 0, tzinfo=CST)
WINDOW_END   = datetime(2026, 6, 23, 9, 30, 0, tzinfo=CST)
TODAY        = "2026-06-20"
```

要换窗口直接改 `xiaodeng_sentiment.py` 顶部这三个常量；老登脚本跟着同步（或抽到 `schedule/collect_all/scripts/_window.py` 共用）。时间窗口过滤在 `fetch_laodeng()` 内通过 `datetime(created_at) >= datetime(WINDOW_START, '-8 hours')` 把 CST 折算到 UTC。

## 样本筛选

去重合并以下三类（口径比小登更宽，因为主板大票 symbol 段比创业板更分散）：

| 筛选 | 实现 |
|---|---|
| 主板大票模式 | `symbol LIKE 'SH600%' OR symbol LIKE 'SH601%' OR symbol LIKE 'SH603%'`（上证主板，含 600 央企 / 601 大盘股 / 603 民企蓝筹） |
| 预设标的模式 | `symbol IN ('SH510050','SH510300','SH510500','SH518800','SH601398','SH601939','SH601288','SH600036','SH600519','SZ000858','SZ000568','SH600900','SH601088')` — `data/sections/laodeng.md` 12 个标的（精准兜底，覆盖上证 50/300/500/黄金 ETF + 工建中招交 + 茅台五粮液 + 长江电力 + 中国神华） |
| 关键词模式 | `content LIKE '%<kw>%'` 关键词集合（见下） |

```python
KEYWORDS = [
    # 大盘 / 宽基 / 板块结构词
    "上证50", "沪深300", "中证500", "中证1000", "蓝筹", "白马", "权重", "大盘",
    "红利", "高股息", "股息率", "央企", "中字头", "国央企",
    # 行业板块词
    "白酒", "消费", "食品饮料", "银行", "保险", "证券", "金融",
    "煤炭", "电力", "公用事业", "石化", "油气", "地产",
    # 行业内具体股票 / 简称
    "茅台", "五粮液", "泸州老窖", "汾酒",
    "工行", "建行", "中行", "招行", "交行",
    "平安", "人寿", "太保", "新华保险",
    "神华", "长江电力", "中石油", "中石化", "中海油",
    # 风格词（与小登的"结构牛/硬科技"对照）
    "价值投资", "股息", "长线", "防御",
]
```

**口径说明**：严格"老登 / 价值 / 红利"定义。两层排除：
1. `科技 / AI / 半导体 / 芯片 / 光模块 / 算力 / GPU / 大模型 / 寒武纪 / 海光 / 中际旭创 / 京东方` —— 属"小登 / 硬科技"，不是老登股主体。
2. `互联网 / 腾讯 / 蜜雪 / 泡泡玛特 / 潮玩 / 茶饮 / 消费电子` —— 属"消费 / 新经济"细分（参考 `data/sections/consumer-tech.md`），不算老登股主体；如需单独分析走 `consumer-tech.md` 口径。
3. `新能源 / 光伏 / 锂电 / 锂电池 / 新能源车` —— 周期股不算价值蓝筹主体（与小登口径一致排除）。

`data/sections/laodeng.md` 12 个 symbol 是精准兜底；关键词层面对没填 symbol 的 B 站 / 小红书 / 知乎评论提供内容匹配。雪球采集时 `symbol` 字段会填交易所代码，所以 symbol 模式 + 预设 IN 已能覆盖大部分雪球样本。

**与 `xiaodeng_sentiment.py` 的差异**：
- symbol 模式：`SH688*` / `SZ300*` / `BJ8*`（科创 / 创业 / 北证） → `SH600*` / `SH601*` / `SH603*`（上证主板） + `IN(laodeng.md 12 个 symbol)`
- 关键词集合：从硬科技词换成红利 / 蓝筹 / 大盘 / 白酒 / 银行 / 保险 / 煤炭 / 电力词
- 标签映射与加权口径保持完全一致：正面 → 看好 / 中性 → 中立 / 负面 → 看跌

## 情绪来源

`run_llm_sentiment(records)` 优先复用 DB 内已有 `sentiment` / `sentiment_score`（来自 `db/update_sentiment.py` 的批量 LLM 跑批），仅对 `effective_sentiment` 为空的评论才再次调用 `SentimentAnalyzer().analyze_batch()`。`SentimentAnalyzer` 接口细节见 `jobs/sentiment_analyzer/SKILL.md`。

情绪标签映射：
- `正面` → **看好**
- `中性` → **中立**
- `负面` → **看跌**

## 输出

| 路径 | 说明 |
|---|---|
| `schedule/collect_all/output/sentiment-laodeng-<TODAY>.html` | 自包含 HTML（含样式 + 高赞样本） |
| `schedule/collect_all/output/sentiment-laodeng-<TODAY>.xlsx` | Summary + TopComments 双 Sheet |
| `schedule/collect_all/output/sentiment-laodeng-<TODAY>.md` | Markdown 报告 |
| `schedule/collect_all/output/sentiment-laodeng-<TODAY>.json` | 汇总 JSON（breakdown + summary） |

报告结构（Markdown）：
1. 标题 + 窗口 + 样本口径
2. 整体情绪：看好 / 中立 / 看跌 占比 + 平均得分 + 高赞子表
3. 解读：综合得分 → 看好 / 中立 / 看跌（≥+0.05 看好 / ≤-0.05 看跌 / 否则中立）
4. **小登 vs 老登 对照表**（在同一窗口期下，老登股情绪和小登股情绪的方向差 — 用于回答"散户在主板蓝筹和硬科技上是否同向"）
5. 按平台拆分表
6. 高赞评论样本 (likes>10)
7. 数据源说明

## 数据流

```
db/comments.db
   │
   ├── (1) symbol LIKE 'SH600%' OR 'SH601%' OR 'SH603%'                    ──►  ~80 条
   │
   ├── (2) symbol IN (laodeng.md 12 个 symbol)                            ──►  ~30 条
   │
   ├── (3) content LIKE '%<keyword>%' (OR 拼接 ~38 个关键词)               ──►  ~120 条
   │
   └── union (1) ∪ (2) ∪ (3) 去重                                          ──►  ~180 条
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

（小登流程同构，输出落到 `sentiment-xiaodeng-<TODAY>.*`；两份报告之间无 DB 共享，互不依赖；对照表通过 JSON 字段后处理或运行两次取结果拼表实现。）

## 关键设计
- **去重在 SQL 层用 `OR`**：不在 Python 侧 dedup，避免内存放大。
- **三层匹配做兜底**：主板模式 + 预设 IN + 关键词三层去重，避免遗漏 `symbol` 为空（B 站 / 小红书 / 知乎常见）的样本。
- **情绪优先复用 DB**：`db/update_sentiment.py` 已经全量跑过，新评论只要没新增就不要重复花钱打 LLM。
- **标签映射在三处**：`aggregate()` / `render_md` / `render_html` 都有一份 `{"正面": "看好", ...}` 字典；改词必须三处同步。
- **窗口常量复用**：与 `xiaodeng_sentiment.py` 同一组 `WINDOW_START` / `WINDOW_END` / `TODAY`，避免两份日报落在不同窗口期。建议未来抽到 `schedule/collect_all/scripts/_window.py` 共用常量。
- **小登 vs 老登对照**：同窗口期下两份 JSON 的 `overall.score_avg` / `overall.看好_pct` 直接对照即可；如要做表格化对比，运行两份脚本后用 JSON 字段拼一个对照 section。

## 关键文件
- `schedule/collect_all/scripts/laodeng_sentiment.py` — 入口脚本（自包含：取数 + 渲染 + 导出）
- `jobs/sentiment_analyzer/xiaodeng_sentiment.py` — 同结构对照脚本（参考实现）
- `jobs/sentiment_analyzer/xiaodeng_sentiment.md` — 口径定义（参考结构）
- `jobs/sentiment_analyzer/llm_sentiment.py` — 情绪分析器（依赖）
- `data/sections/laodeng.md` — 12 个预设标的清单
- `db/comments.db` — 数据源