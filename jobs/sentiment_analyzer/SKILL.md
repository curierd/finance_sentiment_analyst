---
name: sentiment-analyzer
description: 中文散户评论三分类情绪分析（正面 / 中性 / 负面）。基于 LLM（DeepSeek V4 Pro / OpenAI）。纯库函数，不读库不渲染。
---

# 散户评论情绪分析

## 适用场景
- 批量分析 B站 / 小红书 / 雪球等平台中文财经评论的情绪倾向
- LLM 方案（DeepSeek V3 / OpenAI 兼容 API）
- 输入是已加载好的评论字典列表（调用方决定来源：DB / JSON / HTTP）

## 公开 API

```python
from jobs.sentiment_analyzer.llm_sentiment import SentimentAnalyzer
```

### `SentimentAnalyzer` (LLM)

| 方法 | 输入 | 返回 |
|---|---|---|
| `analyze(text)` | 单条字符串 | `{sentiment, scores: {positive, negative, neutral}}` |
| `analyze_batch(texts)` | 字符串列表 (JSON 数组语义) | 与 `analyze` 同结构的列表，顺序与输入一一对应 |

`analyze_batch` 是**单次 API 请求**批量分析，比循环 `analyze()` 更省 token、更快。

### 通用约定
- `sentiment` ∈ `("正面", "中性", "负面")`
- `score` = `positive - negative`，正=偏多 / 负=偏空 / 0=无信号

注：词典方案 (`textcnn_sentiment.py` / `analyze.py`) 已删除，生产只走 LLM。

## 最小示例

```python
# LLM 单条
from jobs.sentiment_analyzer.llm_sentiment import SentimentAnalyzer
analyzer = SentimentAnalyzer()
result = analyzer.analyze("A股大涨，赚钱了！")
# {'sentiment': '正面', 'scores': {'positive': 0.95, 'negative': 0.0, 'neutral': 0.05}}

# LLM 批量（JSON 数组语义：传入字符串列表，返回同长度结果列表）
analyzer.analyze_batch([
    "A股大涨，赚钱了！",
    "今天又亏麻了，割肉离场",
    "持有不动，等风来",
])
# [
#   {'sentiment': '正面', 'scores': {...}},
#   {'sentiment': '负面', 'scores': {...}},
#   {'sentiment': '中性', 'scores': {...}},
# ]

```

注：词典方案的最小示例已移除（`textcnn_sentiment` / `analyze` 均删除）；批量场景直接调 `SentimentAnalyzer.analyze_batch(strings)`。

## LLM 方案环境变量
- `LLM_API_KEY` 或 `DEEPSEEK_API_KEY` - API 密钥
- `LLM_BASE_URL` - 默认 `https://api.deepseek.com`
- `LLM_MODEL` - 默认 `deepseek-v4-pro`
- `LLM_SOURCE` - `deepseek` 或 `openai`

## `analyze_batch` 行为细节（LLM 版）
- 输入：字符串列表（每条一条评论）。空串视为中性，不占输出 token。
- 输出：长度恒等于输入；任一条解析失败 / 缺失自动回退中性。
- 整批请求异常时所有元素返回中性（不会抛错）。
- `max_tokens` 按 `max(400, 200 * n)` 动态调整，避免长列表被截断。

## 配套脚本

### `schedule/collect_all/scripts/xiaodeng_sentiment.py` — 小登股（科技/小盘）情绪报告

复用 `SentimentAnalyzer` + DB 已有情绪数据，按 symbol 模式（科创/创业/北证）+ 关键词命中窗口内评论，输出 看好 / 中立 / 看跌 三分类报告（md / xlsx / html / json）。

详见 `jobs/sentiment_analyzer/xiaodeng_sentiment.md`。

```bash
python schedule/collect_all/scripts/xiaodeng_sentiment.py
# → schedule/collect_all/output/sentiment-xiaodeng-<TODAY>.{md,xlsx,html,json}
```

### `schedule/collect_all/scripts/xiaodeng_daily.py` — 小登股按天 / 按 ISO 周 / 按平台趋势

复用同一口径 + 同一份 DB sentiment，按 `date(datetime(created_at, '+8 hours'))` 聚合 6 月以来（`DAILY_START = 2026-06-01`）每日 看好 / 中立 / 看跌 + 高赞子集 + 加权得分；同时输出 ISO 周汇总 + 平台 × 天得分矩阵。

详见 `jobs/sentiment_analyzer/xiaodeng_daily.md`。

```bash
python schedule/collect_all/scripts/xiaodeng_daily.py
# → schedule/collect_all/output/sentiment-xiaodeng-daily-<TODAY>.{md,xlsx,html,json}
```

## 常见错误
| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: No module named 'jobs'` | 在脚本顶部 `sys.path.insert(0, repo_root)` |
| `ValueError: 未设置 API_KEY` | 设置 `DEEPSEEK_API_KEY` 环境变量 |
| 词典不命中返回 `中性` | 切到 LLM 方案或补词典 |
| LLM 返回 JSON 被截断、批量结果全中性 | 减小 `n` 或重试；确认 `LLM_MODEL` 可用 |
| `xiaodeng_sentiment.py` 报 `effective_sentiment` 全是空 | 先跑 `python db/update_sentiment.py` 灌情绪再跑本脚本 |
| `xiaodeng_daily.py` 拉到的某天评论数为 0 | 那天没采集或采集日窗口外；正常 |

## 反讽判断（科技 vs 老登语境）

B 站/雪球的科技派/老登派对立话题里，**反讽话术高频出现**，LLM 容易把反讽当正面。判断要点：**科技股语境下反讽 = 看空**。

### 派别分类口径

| 派别 | 关键词 / 板块 | 代表股 / 标的 |
|---|---|---|
| **老登股 / 老登派** | 恒生科技、消费、医药、医疗、银行、证券、保险、红利、白酒、医疗器械 | 中国平安、四大行、美的、阿里、腾讯(在"小登股"口径下也属老登) |
| **科技股 / 小登派** | 科技、AI、半导体、芯片、光模块、PCB、玻璃基板、算力、大模型、GPU、CPU、存储、FPGA、机器人、智能驾驶、创业板(SZ300)、科创板(SH688)、北证(BJ8) | 中芯、寒武纪、海光、中际旭创、京东方 |

注：腾讯在 `data/sections/consumer-tech.md` 里属"消费科技"，**在"小登股"口径下不算硬科技**——见 `xiaodeng_sentiment.md` 关键词集合。

### 触发场景

视频标题/上下文含"老登股 / 好人股 / 红利 / 黑五类 / 消费 / 社零转负 / 泡沫破裂 / 求是发文"等关键词时，评论更可能用反讽表达老登派立场。

### 反讽模式速查表

| 表层措辞（看似正面/中立） | 实际立场 | 正确标签 |
|---|---|---|
| `千万不能碰高位科技，都是高位出货诱惑你接盘` | 看空科技 | **负面** |
| `好人股只剩下时间问题，加仓白酒医药消费` | 看多老登 = 看空科技 | **负面** |
| `饿了吃两块芯片，病了贴光模块，要什么消费要什么就业` | 嘲讽科技万能 = 看空科技 | **负面** |
| `建议所有老登股票都退市，只留创业板和科创板` | 反话，实际持有老登 | **负面** |
| `远离坏人股，站在光里拥抱科技` + `[星星眼]` | 反话，老登派自嘲 | **负面** |
| `千万要珍惜 50 元的中国平安，还会见到 40 元` | 平安派自嘲，暗示继续跌 | **负面** |
| `做时间的朋友` + `[doge]` | 反讽，多用于老登派 | **负面** |

### 易误判为反讽但实际不是的措辞

| 表层措辞 | 真实立场 | 正确标签 |
|---|---|---|
| `感谢红利给科技发的粽子` + `[doge]` | 字面感谢，**真科技派** | **正面** |
| `跟着科技吃香的喝辣的` | 字面科技派乐观 | **正面** |
| `科技大人下周还可以考虑给你一个回调上车的机会` | 科技派自嘲但立场鲜明 | **正面** |

**判别核心**：看"被嘲讽/赞美"的对象是谁。如果字面"赞美科技 + 嘲讽老登"，**通常是真科技派**(立场 = 看多科技)。如果字面"赞美老登 + 嘲讽科技"，**才是反讽**(立场 = 看空科技)。`[doge]` 是中性自嘲符号,不能单独当反讽依据。

### 判别三步法

1. **看 emoji**：`[doge]` `[星星眼]` `[打call]` 大量出现 + 表层正面措辞 → 高度疑似反讽
2. **看对立词**：同一句同时出现"老登/好人/红利/黑五类"+"科技/AI/半导体/光模块" + 表面赞美其中一个 → 立场在反方
3. **看视频语境**：视频若利好老登（社零转负、求是定调等），评论的"赞美科技"= 反讽

### 处置流程

- LLM 标"正面"或"中性"但触发以上模式 → 人工 `UPDATE comments SET sentiment_fix='负面' WHERE id=?`
- 同一段反讽模板被多用户复制时（>10 条相同 content），用 `WHERE content LIKE '%<片段>%'` 批量锁定
- 锁定后 `effective_sentiment = COALESCE(sentiment_fix, sentiment)` 自动用锁定值，下次 `db/update_sentiment.py` 也会跳过
- 累计反讽样本可作为 fine-tune 数据集

