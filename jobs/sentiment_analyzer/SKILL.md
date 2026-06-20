---
name: sentiment-analyzer
description: 中文散户评论三分类情绪分析（正面 / 中性 / 负面）。基于 LLM（DeepSeek V4 Pro / OpenAI）或 textcnn_sentiment 词典规则。纯库函数，不读库不渲染。
---

# 散户评论情绪分析

## 适用场景
- 批量分析 B站 / 小红书 / 雪球等平台中文财经评论的情绪倾向
- 支持 LLM 方案（DeepSeek V3）和词典规则方案
- 输入是已加载好的评论字典列表（调用方决定来源：DB / JSON / HTTP）

## 公开 API

```python
# LLM 方案（推荐）
from jobs.sentiment_analyzer.llm_sentiment import SentimentAnalyzer

# 词典方案
from jobs.sentiment_analyzer.analyze import analyze_text, analyze_batch, SENTIMENTS
```

### LLM 方案 (`SentimentAnalyzer`)

| 方法 | 输入 | 返回 |
|---|---|---|
| `analyze(text)` | 单条字符串 | `{sentiment, scores: {positive, negative, neutral}}` |
| `analyze_batch(texts)` | 字符串列表 (JSON 数组语义) | 与 `analyze` 同结构的列表，顺序与输入一一对应 |

`analyze_batch` 是**单次 API 请求**批量分析，比循环 `analyze()` 更省 token、更快。

### 词典方案 (`analyze.py` 包装函数)

| 函数 | 返回 |
|---|---|
| `analyze_text(text, *, analyzer=None)` | `{sentiment, scores: {positive, negative, neutral}, score}` |
| `analyze_batch(records, *, text_key="content", analyzer=None)` | `{records: [...], stats: {total, counts, pct, score_sum, score_avg}}` |

### 通用约定
- `sentiment` ∈ `SENTIMENTS = ("正面", "中性", "负面")`
- `score` = `positive - negative`，正=偏多 / 负=偏空 / 0=无信号
- `analyze_batch`（词典版）保留输入记录全部字段，并追加 `text` / `sentiment` / `scores` / `score`

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

# 词典方案
import sqlite3
from jobs.sentiment_analyzer.analyze import analyze_batch

records = [dict(r) for r in sqlite3.connect("db/comments.db").execute(
    "SELECT id, platform, content FROM comments WHERE platform=? LIMIT 50",
    ("bilibili",))]

result = analyze_batch(records)
print(result["stats"])
# {'total': 50, 'counts': {...}, 'pct': {...}, 'score_sum': 1.5, 'score_avg': 0.03}
```

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

## 常见错误
| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: No module named 'jobs'` | 在脚本顶部 `sys.path.insert(0, repo_root)` |
| `ValueError: 未设置 API_KEY` | 设置 `DEEPSEEK_API_KEY` 环境变量 |
| 词典不命中返回 `中性` | 切到 LLM 方案或补词典 |
| LLM 返回 JSON 被截断、批量结果全中性 | 减小 `n` 或重试；确认 `LLM_MODEL` 可用 |
