---
name: sentiment-analyzer
description: 中文散户评论三分类情绪分析（正面 / 中性 / 负面）。基于 LLM（DeepSeek/OpenAI）或 textcnn_sentiment 词典规则。纯库函数，不读库不渲染。
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

| 函数 | 返回 |
|---|---|
| `analyze_text(text, *, analyzer=None)` | `{sentiment, scores: {positive, negative, neutral}, score}` |
| `analyze_batch(records, *, text_key="content", analyzer=None)` | `{records: [...], stats: {total, counts, pct, score_sum, score_avg}}` |

- `sentiment` ∈ `SENTIMENTS = ("正面", "中性", "负面")`
- `score` = `positive - negative`，正=偏多 / 负=偏空 / 0=无信号
- `analyze_batch` 保留输入记录全部字段，并追加 `text` / `sentiment` / `scores` / `score`

## 最小示例

```python
# LLM 方案
from jobs.sentiment_analyzer.llm_sentiment import SentimentAnalyzer
analyzer = SentimentAnalyzer()
result = analyzer.analyze("A股大涨，赚钱了！")

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
- `LLM_MODEL` - 默认 `deepseek-chat`
- `LLM_SOURCE` - `deepseek` 或 `openai`

## 常见错误
| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: No module named 'jobs'` | 在脚本顶部 `sys.path.insert(0, repo_root)` |
| `ValueError: 未设置 API_KEY` | 设置 `DEEPSEEK_API_KEY` 环境变量 |
| 词典不命中返回 `中性` | 切到 LLM 方案或补词典 |
