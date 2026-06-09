---
name: bert-textcnn-analyzer
description: 中文散户评论三分类情绪分析（正面 / 中性 / 负面）。基于 textcnn_sentiment.SentimentAnalyzer（BERT-TextCNN + 中文金融词典规则）。纯库函数，不读库不渲染。
---

# BERT-TextCNN 散户评论情绪分析

## 适用场景
- 批量分析 B站 / 小红书 / 雪球等平台中文财经评论的情绪倾向
- 零模型权重，依赖 jieba + torch + 词典规则
- 输入是已加载好的评论字典列表（调用方决定来源：DB / JSON / HTTP）

## 公开 API

```python
from textcnn_sentiment import SentimentAnalyzer
from jobs.BERT-TextCNN .analyze import analyze_text, analyze_batch, SENTIMENTS
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
import sqlite3
from jobs.BERT-TextCNN .analyze import analyze_batch

records = [dict(r) for r in sqlite3.connect("db/comments.db").execute(
    "SELECT id, platform, content FROM comments WHERE platform=? LIMIT 50",
    ("bilibili",))]

result = analyze_batch(records)
print(result["stats"])
# {'total': 50, 'counts': {...}, 'pct': {...}, 'score_sum': 1.5, 'score_avg': 0.03}
```

## 性能注意
- jieba 词典首次加载约 0.9s；同进程内**复用** `SentimentAnalyzer` 实例以避免重复
- 词典规则确定性：同输入同结果，便于缓存与测试

## 扩展点
- 新增情绪类别：扩展 `textcnn_sentiment.{POSITIVE,NEGATIVE,NEUTRAL}_WORDS` 与 `SENTIMENTS`
- 替换底层模型：把 `analyzer.analyze` 换成 BERT 微调预测，保持返回结构即可
- 业务加权：调用方在 `result["records"]` 上按 `likes` / `replies` 加权 `score`

## 常见错误
| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: No module named 'jobs'` | 在脚本顶部 `sys.path.insert(0, repo_root)` |
| 目录名 `BERT-TextCNN ` 尾随空格导致 import 失败 | 用 `importlib.util.spec_from_file_location` 加载 |
| 词典不命中返回 `中性` | 在 `textcnn_sentiment` 词典中补词；或切到 BERT 模型 |
