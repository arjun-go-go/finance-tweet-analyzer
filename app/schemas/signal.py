from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PriceTarget(BaseModel):
    """推文或图片中明确出现的价格水平。"""

    symbol: str = Field(default="", description="关联的标准化标的代码")
    target_type: Literal["entry", "target", "stop", "support", "resistance", "other"] = "other"
    value: str = Field(default="", description="保留原文中的价格、区间和单位")
    currency: str = ""
    condition: str = ""

    @field_validator("symbol", mode="before")
    @classmethod
    def _clean_symbol(cls, value):
        return str(value or "").strip().lstrip("$").upper()


class TickerDetail(BaseModel):
    """单个候选投资标的及作者对它表达的关系。"""

    symbol: str = Field(..., description="候选标准代码，如 BTC、AAPL、600519.SH、XAU、WTI")
    original_name: str = Field(default="", description="推文中出现的原始名称或黑话")
    asset_type: Literal["equity", "crypto", "commodity", "unknown"] = "unknown"
    market_hint: Literal["CN", "HK", "US", "CRYPTO", "COMMODITY", "unknown"] = "unknown"
    sentiment: Literal["bullish", "bearish", "neutral"] = "neutral"
    horizon: Literal["short", "medium", "long", "unknown"] = "unknown"
    mention_type: Literal[
        "recommendation", "prediction", "reference", "news", "benchmark", "unknown"
    ] = Field(
        default="unknown",
        description="作者如何使用该标的；提及、新闻转述不等于推荐",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="将该标的与作者态度关联起来的原文证据或忠实转述",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def _clean_symbol(cls, value):
        return str(value or "").strip().lstrip("$").upper()

    @field_validator("evidence", mode="before")
    @classmethod
    def _ensure_evidence_list(cls, value):
        return [str(item) for item in value if item] if isinstance(value, list) else []

    @model_validator(mode="after")
    def _normalize_asset_market_pair(self):
        if self.asset_type == "commodity":
            self.market_hint = "COMMODITY"
        elif self.asset_type == "crypto":
            self.market_hint = "CRYPTO"
        return self


class TweetAnalysis(BaseModel):
    """Twitter 投资信息提取协议 v2。"""

    reasoning: str = Field(default="", description="简要说明识别、归因和判断依据")

    # v2 使用 is_investment_relevant；related 暂时保留给现有下游消费方。
    is_investment_relevant: bool = Field(
        default=False,
        description="是否包含可供投资研究或决策使用的实质信息",
    )
    is_investment_related: bool = Field(default=False, description="v1 兼容字段")
    statement_type: Literal[
        "recommendation", "prediction", "news_relay", "recap", "risk_warning",
        "fact", "opinion", "non_investment",
    ] = "non_investment"
    opinion_source: Literal["author", "quoted", "third_party", "unclear"] = "unclear"
    markets: list[Literal["CN", "HK", "US", "COMMODITY", "CRYPTO"]] = Field(default_factory=list)

    overall_sentiment: Literal["bullish", "bearish", "neutral", "mixed"] = "neutral"
    tickers: list[TickerDetail] = Field(default_factory=list)
    thesis: str = Field(default="", description="作者的核心投资论点")
    key_points: list[str] = Field(default_factory=list, description="v1 兼容的核心观点列表")
    catalysts: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    entry_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    price_targets: list[PriceTarget] = Field(default_factory=list)
    text_evidence: list[str] = Field(default_factory=list)
    is_prediction: bool = Field(
        default=False,
        description="是否包含有方向、可在未来用外部行情验证的判断",
    )
    is_sponsored: bool = Field(default=False)

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    media_summary: str = ""
    media_evidence: list[str] = Field(default_factory=list)
    text_image_consistency: Literal[
        "consistent", "complementary", "conflict", "image_only", "unclear", "no_media"
    ] = "no_media"
    media_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    analysis_schema_version: Literal["v2"] = "v2"

    @model_validator(mode="before")
    @classmethod
    def _sync_relevance_flags(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "is_investment_relevant" not in normalized and "is_investment_related" in normalized:
            normalized["is_investment_relevant"] = normalized["is_investment_related"]
        if "is_investment_related" not in normalized and "is_investment_relevant" in normalized:
            normalized["is_investment_related"] = normalized["is_investment_relevant"]
        if "statement_type" not in normalized:
            relevant = normalized.get("is_investment_relevant", normalized.get("is_investment_related", False))
            normalized["statement_type"] = "opinion" if relevant else "non_investment"
        return normalized

    @field_validator("tickers", mode="before")
    @classmethod
    def _ensure_tickers_list(cls, value):
        return value if isinstance(value, list) else []

    @field_validator(
        "key_points", "catalysts", "risk_factors", "entry_conditions",
        "invalidation_conditions", "text_evidence", "media_evidence",
        mode="before",
    )
    @classmethod
    def _ensure_str_list(cls, value):
        return [str(item) for item in value if item] if isinstance(value, list) else []

    @field_validator("markets", mode="before")
    @classmethod
    def _normalize_markets(cls, value):
        if not isinstance(value, list):
            return []
        allowed = {"CN", "HK", "US", "COMMODITY", "CRYPTO"}
        return list(dict.fromkeys(str(item).upper() for item in value if str(item).upper() in allowed))

    @field_validator("confidence", "media_confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value):
        if value is None:
            return 0.0
        return max(0.0, min(1.0, float(value)))

    @field_validator("overall_sentiment", mode="before")
    @classmethod
    def _normalize_sentiment(cls, value):
        if not isinstance(value, str):
            return "neutral"
        mapping = {
            "看多": "bullish", "看好": "bullish", "买入": "bullish",
            "看空": "bearish", "看衰": "bearish", "卖出": "bearish",
            "中性": "neutral", "观望": "neutral",
        }
        normalized = value.strip().lower()
        return mapping.get(normalized, normalized) if normalized else "neutral"

    @model_validator(mode="after")
    def _derive_compatible_fields(self):
        self.is_investment_related = self.is_investment_relevant
        if self.statement_type == "non_investment":
            self.is_investment_relevant = False
            self.is_investment_related = False
            self.is_prediction = False
        ticker_markets = [item.market_hint for item in self.tickers if item.market_hint != "unknown"]
        if ticker_markets:
            self.markets = list(dict.fromkeys(ticker_markets))
        if not self.thesis and self.key_points:
            self.thesis = self.key_points[0]
        if self.thesis and not self.key_points:
            self.key_points = [self.thesis]
        return self


class TickerSummary(BaseModel):
    """按标的聚合的投资观点摘要。"""

    ticker: str
    mention_count: int
    bloggers: list[str]
    consensus: str
    bullish_count: int
    bearish_count: int
    recommendation_score: float
    summary: str
