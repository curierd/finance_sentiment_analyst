"""
TextCNN 中文文本分类 - 散户情绪分析
使用CNN进行三分类：正面、中性、负面
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import jieba
import re
from collections import Counter

# ============ 1. 语料库准备（简化的中文金融情感词典）============

# 正面词汇
POSITIVE_WORDS = [
    # 上涨/盈利相关
    '涨', '涨停', '牛市', '盈利', '赚钱', '翻倍', '暴富', '抄底', '加仓', '满仓',
    '买入', '做多', '看多', '利好', '吃肉', '发财', '大赚', '赚麻了', '盆满钵满',
    '暴击', '爽', '起飞', '创新高', '突破', '反弹', '回本', '解套',

    # 价值投资/长期
    '价值', '低估', '基本面', '业绩', '分红', '高股息', '稳健', '长期',

    # 积极情绪
    '支持', '点赞', '厉害', '牛', '强', '稳', '看好', '信心', '乐观',
    '学习', '感谢', '分享', '干货', '有用', '收藏'
]

# 负面词汇
NEGATIVE_WORDS = [
    # 下跌/亏损相关
    '跌', '暴跌', '崩盘', '割肉', '止损', '空仓', '清仓', '跑路', '爆仓',
    '亏损', '亏钱', '亏麻了', '血亏', '套牢', '接盘', '腰斩', '踩雷',
    '卖出', '做空', '看空', '利空', '凉凉', '废了', '崩了', '跌停',

    # 恐慌/焦虑
    '恐慌', '焦虑', '害怕', '恐惧', '绝望', '崩溃', '无奈', '无语',
    '摆烂', '躺平', '销户', '清仓跑路', '天台', '跳楼',

    # 质疑/抱怨
    '骗', '坑', '黑', '割韭菜', '机构抱团', '庄家', '内幕', '老鼠仓',
    '减持', '抽水', '圈钱', '造假', '骗人',

    # 讽刺/调侃 (负面)
    '利好白酒', '科技骗局', '故事大王', '韭', '菜', '绿', '割', '死',
    '笑话', '可笑', '讽刺', '搞笑', '幽默',
    # 否定正面词（反转）
    '不可能', '不会', '别想', '想太多', '做梦'
]

# 中性词汇
NEUTRAL_WORDS = [
    '观望', '等待', '考虑', '分析', '研究', '跟踪', '关注',
    '震荡', '波动', '整理', '盘整', '横盘', '不确定', '可能', '也许',
    '学习', '请教', '请问', '问一下', '讨论', '交流', '理解'
]

# ============ 2. TextCNN 模型定义 ============

class TextCNN(nn.Module):
    def __init__(self, vocab_size, embedding_dim, num_classes, filter_sizes, num_filters, dropout=0.5):
        super(TextCNN, self).__init__()

        self.embedding = nn.Embedding(vocab_size, embedding_dim)
        self.convs = nn.ModuleList([
            nn.Conv1d(embedding_dim, num_filters, fs) for fs in filter_sizes
        ])
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(num_filters * len(filter_sizes), num_classes)

    def forward(self, x):
        # x: (batch, seq_len)
        x = self.embedding(x)  # (batch, seq_len, embedding_dim)
        x = x.permute(0, 2, 1)  # (batch, embedding_dim, seq_len)

        conved = [F.relu(conv(x)) for conv in self.convs]
        pooled = [F.max_pool1d(c, c.size(2)).squeeze(2) for c in conved]

        cat = torch.cat(pooled, dim=1)  # (batch, num_filters * len(filter_sizes))
        cat = self.dropout(cat)
        output = self.fc(cat)
        return output


# ============ 3. 简易词典规则分类器（作为TextCNN的替代方案）============

class SentimentAnalyzer:
    def __init__(self):
        # 构建词典
        self.positive_set = set(POSITIVE_WORDS)
        self.negative_set = set(NEGATIVE_WORDS)
        self.neutral_set = set(NEUTRAL_WORDS)

        # 否定词（反转情感用）
        self.negation = {'不', '没', '无', '非', '别', '莫', '勿', '未', '否'}

        # 程度词（增强/减弱）
        self.intensifiers = {'很', '太', '非常', '特别', '极', '超级', '巨', '真', '简直'}
        self.reducers = {'有点', '有些', '稍微', '略微', '一点', '一丝'}

    def tokenize(self, text):
        """中文分词"""
        # 清洗
        # 龥 = U+9FA5 是 CJK 统一表意文字基本区的上界(龥字符在部分终端/字体可能显示为方块,是正常字形)
        text = re.sub(r'[^一-龥a-zA-Z0-9]', ' ', str(text))
        # jieba分词
        words = jieba.cut(text)
        return [w.strip() for w in words if w.strip()]

    def analyze(self, text):
        """分析单条文本的情绪"""
        words = self.tokenize(text)

        pos_score = 0
        neg_score = 0
        neu_score = 0

        negation_flag = False
        intensifier = 1.0

        for i, word in enumerate(words):
            if word in self.positive_set:
                # 检查前方是否有否定或程度词
                if i > 0:
                    prev = words[i-1] if i > 0 else ''
                    if prev in self.negation:
                        negation_flag = True
                    if prev in self.intensifiers:
                        intensifier = 1.5
                    if prev in self.reducers:
                        intensifier = 0.5

                if negation_flag:
                    neg_score += 1 * intensifier
                    negation_flag = False
                else:
                    pos_score += 1 * intensifier
                intensifier = 1.0

            elif word in self.negative_set:
                if i > 0:
                    prev = words[i-1] if i > 0 else ''
                    if prev in self.negation:
                        negation_flag = True
                    if prev in self.intensifiers:
                        intensifier = 1.5
                    if prev in self.reducers:
                        intensifier = 0.5

                if negation_flag:
                    pos_score += 1 * intensifier
                    negation_flag = False
                else:
                    neg_score += 1 * intensifier
                intensifier = 1.0

            elif word in self.neutral_set:
                neu_score += 0.5

        # 计算最终情绪
        total = pos_score + neg_score + neu_score
        if total == 0:
            return {'sentiment': '中性', 'scores': {'positive': 0, 'negative': 0, 'neutral': 0}}

        pos_ratio = pos_score / total
        neg_ratio = neg_score / total

        if pos_ratio > 0.5:
            sentiment = '正面'
        elif neg_ratio > 0.5:
            sentiment = '负面'
        else:
            sentiment = '中性'

        return {
            'sentiment': sentiment,
            'scores': {
                'positive': round(pos_score, 2),
                'negative': round(neg_score, 2),
                'neutral': round(neu_score, 2)
            },
            'tokens': words
        }


def analyze_comments(comments):
    """批量分析评论"""
    analyzer = SentimentAnalyzer()

    results = []
    for comment in comments:
        if not comment.get('message'):
            continue
        result = analyzer.analyze(comment['message'])
        result['author'] = comment.get('author', {}).get('name', 'unknown')
        result['like'] = comment.get('like', 0)
        result['message'] = comment['message'][:50]  # 截断显示
        results.append(result)

    return results


def summarize_results(results):
    """汇总分析结果"""
    total = len(results)
    if total == 0:
        return "无有效评论"

    sentiment_counts = Counter(r['sentiment'] for r in results)

    print(f"\n{'='*60}")
    print(f"散户情绪定量分析报告")
    print(f"{'='*60}")
    print(f"总评论数: {total}")
    print(f"-"*60)

    for sentiment in ['正面', '中性', '负面']:
        count = sentiment_counts.get(sentiment, 0)
        pct = count / total * 100
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        print(f"{sentiment}: {count:4d} ({pct:5.1f}%) |{bar}|")

    print(f"-"*60)

    # 高赞评论分析
    print(f"\n【高赞评论情绪分布】(点赞>10)")
    high_like = [r for r in results if r['like'] > 10]
    if high_like:
        hl_counts = Counter(r['sentiment'] for r in high_like)
        for sentiment in ['正面', '中性', '负面']:
            count = hl_counts.get(sentiment, 0)
            pct = count / len(high_like) * 100 if high_like else 0
            print(f"  {sentiment}: {count} ({pct:.1f}%)")

    # 按点赞加权统计
    print(f"\n【点赞加权情绪分布】")
    weighted_pos = sum(r['scores']['positive'] * r['like'] for r in results)
    weighted_neg = sum(r['scores']['negative'] * r['like'] for r in results)
    weighted_neu = sum(r['scores']['neutral'] * r['like'] for r in results)
    total_weighted = weighted_pos + weighted_neg + weighted_neu

    if total_weighted > 0:
        for sentiment, score in [('正面', weighted_pos), ('中性', weighted_neu), ('负面', weighted_neg)]:
            pct = score / total_weighted * 100
            print(f"  {sentiment}: {pct:.1f}%")

    print(f"\n{'='*60}")

    return sentiment_counts


if __name__ == "__main__":
    # 测试代码
    analyzer = SentimentAnalyzer()

    test_texts = [
        "A股大涨，赚钱了，太开心了！",
        "又跌了，割肉跑路，心态崩了",
        "观望一下，等跌到位再买",
        "这波行情就是机构抱团，散户都是接盘侠",
        "利好白酒，科技都是骗局",
        "稳住不动，长期持有价值投资",
        "从1万赚到200万，及时收手才是王道"
    ]

    print("TextCNN情绪分析器测试")
    print("-"*50)
    for text in test_texts:
        result = analyzer.analyze(text)
        print(f"文本: {text}")
        print(f"分词: {result['tokens']}")
        print(f"情绪: {result['sentiment']} | 得分: 正{result['scores']['positive']} 负{result['scores']['negative']} 中{result['scores']['neutral']}")
        print("-"*50)