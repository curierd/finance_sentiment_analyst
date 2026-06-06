# TextCNN 散户情绪分析工具

## 概述

本项目使用 TextCNN 模型对B站金融UP主视频评论进行散户情绪定量分析，将评论分为三类：
- **正面 (乐观)**: 看涨、期待上涨、抄底、买入信号
- **中性**: 观望、提问、无明显倾向
- **负面 (悲观)**: 看跌、恐慌、割肉、卖出信号

## 安装依赖

```bash
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --system
uv pip install jieba scikit-learn --system
```

## 使用方法

### 1. 命令行分析单条评论

```python
from textcnn_sentiment import SentimentAnalyzer

analyzer = SentimentAnalyzer()
result = analyzer.analyze("A股大涨，赚钱了，太开心了！")
print(result)
# {'sentiment': '正面', 'scores': {'positive': 1.0, 'negative': 0, 'neutral': 0}}
```

### 2. 批量分析评论列表

```python
from textcnn_sentiment import analyze_comments, summarize_results

comments = [
    {"message": "又跌了，割肉跑路", "author": {"name": "用户A"}, "like": 10},
    {"message": "观望一下，等机会", "author": {"name": "用户B"}, "like": 5},
    {"message": "满仓干！牛市来了！", "author": {"name": "用户C"}, "like": 20},
]

results = analyze_comments(comments)
summarize_results(results)
```

### 3. 完整分析流程示例

```python
import subprocess
import json

# 1. 获取B站视频评论
result = subprocess.run(
    ['bili', 'video', 'BV1GHEw6rEYL', '--comments', '--json'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
comments = data.get('data', {}).get('comments', [])

# 2. 分析情绪
from textcnn_sentiment import analyze_comments, summarize_results
results = analyze_comments(comments)

# 3. 汇总输出
summarize_results(results)
```

## 输出格式

```
============================================================
散户情绪定量分析报告
============================================================
总评论数: 39
------------------------------------------------------------
正面:    8 ( 20.5%) |█████░░░░░░░░░░░░░░░░░░░░|
中性:   22 ( 56.4%) |██████████████░░░░░░░░░░░░|
负面:    9 ( 23.1%) |█████░░░░░░░░░░░░░░░░░░░░|
------------------------------------------------------------

【高赞评论情绪分布】(点赞>10)
  正面: 4 (22.2%)
  中性: 10 (55.6%)
  负面: 4 (22.2%)

【点赞加权情绪分布】
  正面: 31.2%
  中性: 9.9%
  负面: 58.9%
```

## 情绪词典说明

### 正面词汇
- 上涨/盈利: 涨、涨停、牛市、赚钱、翻倍、抄底、加仓、满仓等
- 价值投资: 价值、低估、基本面、业绩、分红等
- 积极情绪: 支持、看好、信心、乐观、学习等

### 负面词汇
- 下跌/亏损: 跌、暴跌、崩盘、割肉、止损、爆仓、套牢等
- 恐慌/焦虑: 恐慌、焦虑、恐惧、绝望、崩溃、销户等
- 质疑/抱怨: 机构抱团、庄家、割韭菜、抽水、圈钱等
- 讽刺/调侃: 利好白酒、科技骗局、韭、菜、绿等

### 中性词汇
- 观望: 观望、等待、考虑、分析、研究、跟踪等

## 分析维度

| 维度 | 说明 |
|-----|------|
| **普通评论** | 所有评论的情绪简单统计 |
| **高赞评论** | 点赞>10的评论，反映有影响力的声音 |
| **点赞加权** | 按点赞数加权，更反映大众共识 |

## 运行测试

```bash
cd /home/rjh/finance_sentiment_analyst
python3 textcnn_sentiment.py
```

## 文件结构

```
.
├── textcnn_sentiment.py    # 核心分析代码
├── bili_data/
│   └── results/
│       └── 2026-06-05-sentiment-report.md  # 分析报告
└── README_textcnn.md        # 本文档
```

## 注意事项

1. **中文分词**: 使用 jieba 进行分词
2. **否定处理**: 自动处理"不"、"没"等否定词的情感反转
3. **程度词**: 考虑"很"、"太"、"非常"等程度词的增强/减弱效果
4. **采样间隔**: B站API请求需间隔1秒以上防止412风控