from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TweetClassification(BaseModel):
    """单条推文的路由分类结果。"""
    tweet_id: str
    category: Literal["investment", "market_commentary", "risk_warning", "non_financial"] = Field(
        description="分类类别"
    )
    needs_risk_analysis: bool = Field(default=False, description="是否需要深入风险分析")
    confidence: float = Field(default=0.5, description="分类置信度 0-1")

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v):
        """容错：LLM 可能返回中文或非标准值。"""
        if not isinstance(v, str):
            return "market_commentary"
        mapping = {
            "投资": "investment", "投资信号": "investment", "买卖": "investment",
            "市场评论": "market_commentary", "评论": "market_commentary",
            "风险": "risk_warning", "风险预警": "risk_warning", "预警": "risk_warning",
            "非金融": "non_financial", "闲聊": "non_financial", "无关": "non_financial",
        }
        normalized = v.strip().lower()
        return mapping.get(normalized, normalized) if normalized else "market_commentary"

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v):
        """将 confidence 钳位到 [0, 1]。"""
        if v is None:
            return 0.5
        return max(0.0, min(1.0, float(v)))


class BatchClassificationResult(BaseModel):
    """批量分类结果。"""
    classifications: list[TweetClassification] = Field(default_factory=list)
    has_investment_content: bool = Field(default=False, description="批次中是否存在投资相关内容")

    @field_validator("classifications", mode="before")
    @classmethod
    def _ensure_list(cls, v):
        """兼容 LLM 返回 null 或非数组。"""
        return v if isinstance(v, list) else []
