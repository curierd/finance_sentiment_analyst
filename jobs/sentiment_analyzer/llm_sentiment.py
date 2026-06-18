"""
散户评论情绪分析 (LLM)

基于大模型 (OpenAI 兼容 API) 的中文三分类情绪分析。
替换原有的词典规则方案，保持接口完全一致。

Usage:
    from llm_sentiment import SentimentAnalyzer
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze("A股大涨，赚钱了！")

环境变量:
    LLM_API_KEY     - API 密钥 (必填)
    LLM_BASE_URL    - API 地址 (默认 https://api.deepseek.com)
    LLM_MODEL       - 模型名称 (默认 deepseek-chat)
"""
import json
import os

import openai


class SentimentAnalyzer:
    """基于大模型的散户评论情绪分析器，接口兼容原有 SentimentAnalyzer。"""

    SENTIMENTS: tuple[str, ...] = ("正面", "中性", "负面")

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
        self.model = model or os.environ.get("LLM_MODEL", "deepseek-chat")

        if not self.api_key:
            raise ValueError(
                "未设置 LLM_API_KEY 或 DEEPSEEK_API_KEY 环境变量"
            )

        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def analyze(self, text: str) -> dict:
        """分析单条文本情绪，返回与原有接口一致的结果。"""
        if not text or not text.strip():
            return {
                "sentiment": "中性",
                "scores": {"positive": 0.0, "negative": 0.0, "neutral": 0.0},
            }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个中文散户评论情绪分析助手。分析用户输入的评论，判断情绪倾向，"
                            "并给出正/负/中性的置信度分数（0-1之间的小数，三者和为1）。\n\n"
                            "返回纯 JSON，不要包含 markdown 代码块或额外文字：\n"
                            '{"sentiment": "正面", "scores": {"positive": 0.8, "negative": 0.1, "neutral": 0.1}}\n\n'
                            'sentiment 只能是 "正面"、"中性"、"负面" 之一。'
                        ),
                    },
                    {"role": "user", "content": f"评论：{text}"},
                ],
                temperature=0.0,
                max_tokens=200,
            )
            raw = response.choices[0].message.content.strip()
            return _parse_response(raw)
        except Exception as e:
            return {
                "sentiment": "中性",
                "scores": {"positive": 0.0, "negative": 0.0, "neutral": 0.0},
            }


def _parse_response(raw: str) -> dict:
    """解析 LLM 返回的 JSON 字符串，兜底返回中性。"""
    # 去掉可能的 markdown 代码块包裹
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.endswith("```"):
            text = text[:-3]
    try:
        data = json.loads(text)
        sentiment = data.get("sentiment", "中性")
        if sentiment not in SentimentAnalyzer.SENTIMENTS:
            sentiment = "中性"
        scores = data.get("scores", {})
        return {
            "sentiment": sentiment,
            "scores": {
                "positive": round(float(scores.get("positive", 0)), 4),
                "negative": round(float(scores.get("negative", 0)), 4),
                "neutral": round(float(scores.get("neutral", 0)), 4),
            },
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "sentiment": "中性",
            "scores": {"positive": 0.0, "negative": 0.0, "neutral": 0.0},
        }
