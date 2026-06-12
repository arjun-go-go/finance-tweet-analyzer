from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TickerDetail(BaseModel):
    """单个投资标的的细粒度分析结果。

    每个标的独立 sentiment/horizon，支持"看多BTC同时看空ETH"的多标的分化场景。
    """
    symbol: str = Field(..., description="标准化金融代码(如 BTC, AAPL, 600519.SH, XAUUSD)")
    original_name: str = Field(default="", description="推文中出现的原始名称/黑话(如 大饼, 茅台, 纳指)")
    sentiment: Literal["bullish", "bearish", "neutral"] = Field(
        default="neutral", description="针对该标的的具体情绪"
    )
    horizon: Literal["short", "medium", "long", "unknown"] = Field(
        default="unknown", description="投资周期: short(日内~几天), medium(几周~几月), long(半年+)"
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def _clean_symbol(cls, v):
        """去除 LLM 输出中常见的 $ 前缀和空格。"""
        if not isinstance(v, str):
            return ""
        return v.strip().lstrip("$").upper()


class TweetAnalysis(BaseModel):
    """单条推文的投资分析结果。

    生产级 Schema：
        - Literal 枚举约束情绪/周期值，避免 LLM 自由发挥
        - field_validator 容错 LLM 偶尔返回 null / 超范围值
        - reasoning (CoT) 提升分析准确率并支持审计追溯
        - per-ticker 独立 sentiment/horizon 支持多标的分化
    """
    reasoning: str = Field(
        default="",
        description="分析逻辑链：1.识别标的与黑话 2.判断真实情绪(防反讽) 3.结合博主背景评估置信度",
    )
    is_investment_related: bool = Field(
        default=False, description="是否包含实质投资/交易相关内容"
    )
    overall_sentiment: Literal["bullish", "bearish", "neutral", "mixed"] = Field(
        default="neutral",
        description="推文整体情绪倾向(多标的方向冲突时为 mixed)",
    )
    tickers: list[TickerDetail] = Field(
        default_factory=list, description="提及的投资标的明细列表"
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="核心投资逻辑或催化剂(中文简述，无实质逻辑则留空)",
    )
    risk_factors: list[str] = Field(
        default_factory=list, description="明确提及的风险因素或警告"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="分析置信度(0-1)。非投资/纯闲聊/反讽难断/低信誉博主应<0.3",
    )

    # ----------------------------------------------------------
    # LLM 输出容错 validators
    # ----------------------------------------------------------
    @field_validator("tickers", mode="before")
    @classmethod
    def _ensure_tickers_list(cls, v):
        """兼容 LLM 偶尔返回 null 或非数组。"""
        return v if isinstance(v, list) else []

    @field_validator("key_points", "risk_factors", mode="before")
    @classmethod
    def _ensure_str_list(cls, v):
        """确保列表字段为字符串列表，过滤 None 和空串。"""
        if not isinstance(v, list):
            return []
        return [str(x) for x in v if x]

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v):
        """将 LLM 输出的 confidence 钳位到 [0, 1]。"""
        if v is None:
            return 0.0
        return max(0.0, min(1.0, float(v)))

    @field_validator("overall_sentiment", mode="before")
    @classmethod
    def _normalize_sentiment(cls, v):
        """容错：LLM 可能返回中文或大写。"""
        if not isinstance(v, str):
            return "neutral"
        mapping = {
            "看多": "bullish", "看好": "bullish", "买入": "bullish",
            "看空": "bearish", "看衰": "bearish", "卖出": "bearish",
            "中性": "neutral", "观望": "neutral",
        }
        normalized = v.strip().lower()
        return mapping.get(normalized, normalized) if normalized else "neutral"


class TickerSummary(BaseModel):
    """按标的聚合的投资建议"""
    ticker: str
    mention_count: int = Field(description="被多少条推文/博主提及")
    bloggers: list[str] = Field(description="提及该标的的博主列表")
    consensus: str = Field(description="综合观点: strong_buy, buy, neutral, sell, strong_sell")
    bullish_count: int = Field(description="看好的推文数")
    bearish_count: int = Field(description="看空的推文数")
    recommendation_score: float = Field(description="综合推荐度 0-100")
    summary: str = Field(description="关键观点汇总，中文")
