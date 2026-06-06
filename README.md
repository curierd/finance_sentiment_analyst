# 散户情绪分析工具

使用 TextCNN 模型对B站金融UP主视频评论进行散户情绪定量分析。

## 功能

- 抓取B站视频评论
- TextCNN 情绪分类（正面/中性/负面）
- 多维度情绪统计（普通评论、高赞评论、点赞加权）
- 中文分词 +否定词/程度词处理

## 快速开始

```python
from textcnn_sentiment import SentimentAnalyzer

analyzer = SentimentAnalyzer()
result = analyzer.analyze("A股大涨，赚钱了！")
# {'sentiment': '正面', 'scores': {...}}
```

## 项目结构

```
.
├── textcnn_sentiment.py    # 核心分析代码
├── bili_data/              # B站数据
└── README_textcnn.md       # 详细文档
```

## 详见

- [详细文档](README_textcnn.md)
- [UP主列表](finance-up.md)