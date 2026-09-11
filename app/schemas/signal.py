from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PriceTarget(BaseModel):
    """原文或图片中明确出现的价格水平。"""

    symbol: str = Field(default="", description="关联的标准化标的代码")
    target_type: Literal[
        "entry", "target", "stop", "support", "resistance", "other"
    ] = "other"
    value: str = Field(default="", description="保留原文中的价格、区间和单位")
    currency: str = ""
    condition: str = ""

    @field_validator("symbol", mode="before")
    @classmethod
    def _clean_symbol(cls, value):
        return str(value or "").strip().lstrip("$").upper()


class InstrumentIdentity(BaseModel):
    """LLM 提取出的候选标的；正式身份由后续确定性校验服务补全。"""

    symbol: str = Field(..., description="候选代码，如 BTC、AAPL、600519.SH、XAU、WTI")
    original_name: str = Field(default="", description="推文中的原始名称、代码或黑话")
    asset_type: Literal["equity", "crypto", "commodity", "unknown"] = "unknown"
    market_hint: Literal["CN", "HK", "US", "CRYPTO", "COMMODITY", "unknown"] = "unknown"

    @field_validator("symbol", mode="before")
    @classmethod
    def _clean_symbol(cls, value):
        return str(value or "").strip().lstrip("$").upper()

    @model_validator(mode="after")
    def _normalize_asset_market_pair(self):
        if self.asset_type == "commodity":
            self.market_hint = "COMMODITY"
        elif self.asset_type == "crypto":
            self.market_hint = "CRYPTO"
        return self


class ForecastSpec(BaseModel):
    """原文中可被外部数据验证的预测目标，不包含系统计算结果。"""

    prediction_type: Literal[
        "price_direction",
        "price_target",
        "fundamental_metric",
        "event_outcome",
        "none",
    ] = "none"
    forecast_source: Literal[
        "author",
        "quoted",
        "third_party",
        "market_consensus",
        "company_guidance",
        "unclear",
    ] = Field(
        default="unclear",
        description="预测目标的原始提出者；与整项观点的 opinion_source 分开记录",
    )
    source_name: str = Field(
        default="",
        description="原文明确出现的预测者，例如黄仁勋、NVIDIA 管理层、市场一致预期",
    )
    author_adopted: bool = Field(
        default=False,
        description="博主是否用明确措辞采纳该预测目标；不得根据转述或正面语气推断",
    )
    temporal_expression: str = Field(
        default="",
        description="原文中的时间表达，例如未来三个月、年底、FY2028；不得补写",
    )
    target_metric: str = Field(
        default="",
        description="被预测的指标，例如 price、revenue_growth、ipo_status",
    )
    target_operator: Literal[
        "up",
        "down",
        "gte",
        "lte",
        "equals",
        "range",
        "occurs",
        "not_occurs",
        "unknown",
    ] = "unknown"
    target_value: str = Field(
        default="",
        description="原文明确给出的目标值或区间，保持原始表达",
    )
    target_unit: str = Field(default="", description="目标值单位或币种")
    target_condition: str = Field(
        default="",
        description="原文明确给出的触发、截止或成功条件",
    )

    @field_validator(
        "temporal_expression",
        "target_metric",
        "target_value",
        "target_unit",
        "target_condition",
        "source_name",
        mode="before",
    )
    @classmethod
    def _normalize_forecast_text(cls, value):
        return str(value or "").strip()


class InstrumentClaim(BaseModel):
    """一个标的的一项独立立场；事实和风险优先作为主观点的支撑信息。"""

    instrument: InstrumentIdentity
    direction: Literal["bullish", "bearish", "neutral", "none"] = Field(
        default="none",
        description="仅描述投资立场；事实、新闻、引用和一般风险必须为 none",
    )
    horizon: Literal["short", "medium", "long", "unknown"] = "unknown"
    claim_type: Literal[
        "recommendation",
        "prediction",
        "opinion",
        "risk_warning",
        "fact",
        "news",
        "recap",
        "reference",
    ] = "reference"
    opinion_source: Literal["author", "quoted", "third_party", "unclear"] = Field(
        default="unclear",
        description="观点实际表达者；某人说/市场认为不能自动归为当前博主",
    )
    sponsor_relation: Literal["none", "unrelated", "direct", "unclear"] = Field(
        default="none",
        description=(
            "该标的观点与商业推广的关系；通用券商/平台尾部广告且未推广该标的为 "
            "unrelated，推广对象或广告商与该标的直接相关为 direct"
        ),
    )
    thesis: str = Field(default="", description="只描述该标的的核心论点")
    evidence: list[str] = Field(
        default_factory=list,
        description="能把该标的、观点方向和作者归属连接起来的正文证据",
    )
    media_evidence: list[str] = Field(
        default_factory=list,
        description="只与该标的观点相关的图片证据",
    )
    catalysts: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    entry_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    price_targets: list[PriceTarget] = Field(default_factory=list)
    forecast: ForecastSpec = Field(default_factory=ForecastSpec)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator(
        "evidence",
        "media_evidence",
        "catalysts",
        "risk_factors",
        "entry_conditions",
        "invalidation_conditions",
        mode="before",
    )
    @classmethod
    def _ensure_str_list(cls, value):
        return [str(item) for item in value if item] if isinstance(value, list) else []

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value):
        if value is None:
            return 0.0
        return max(0.0, min(1.0, float(value)))

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction(cls, value):
        if not isinstance(value, str):
            return "none"
        mapping = {
            "看多": "bullish",
            "看好": "bullish",
            "买入": "bullish",
            "看空": "bearish",
            "看衰": "bearish",
            "卖出": "bearish",
            "中性": "neutral",
            "观望": "neutral",
            "无方向": "none",
        }
        normalized = value.strip().lower()
        return mapping.get(normalized, normalized) if normalized else "none"

    @model_validator(mode="after")
    def _keep_context_separate_from_stance(self):
        """Facts and risks provide context; they are not investment directions."""
        if self.claim_type in {"fact", "news", "recap", "reference", "risk_warning"}:
            self.direction = "none"
        return self


class MarketView(BaseModel):
    """无法归入单一标的、但对市场有明确含义的宏观判断。"""

    market: Literal["CN", "HK", "US", "COMMODITY", "CRYPTO", "GLOBAL"]
    benchmark: str = Field(
        default="",
        description="原文明示的大盘、指数或市场对象；未说明时留空",
    )
    impact: Literal["positive", "negative", "mixed", "unclear"] = "unclear"
    horizon: Literal["short", "medium", "long", "unknown"] = "unknown"
    topic: Literal[
        "rates",
        "inflation",
        "liquidity",
        "policy",
        "growth",
        "geopolitics",
        "earnings",
        "supply_demand",
        "regulation",
        "other",
    ] = "other"
    thesis: str = Field(default="", description="作者对该市场影响的简要判断")
    evidence: list[str] = Field(default_factory=list)
    opinion_source: Literal["author", "quoted", "third_party", "unclear"] = "unclear"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("evidence", mode="before")
    @classmethod
    def _ensure_evidence_list(cls, value):
        return [str(item) for item in value if item] if isinstance(value, list) else []

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value):
        if value is None:
            return 0.0
        return max(0.0, min(1.0, float(value)))


class CommercialDisclosure(BaseModel):
    """推文级商业披露；仅表示含推广，不直接决定标的观点能否统计。"""

    has_commercial_content: bool = False
    sponsor_name: str = ""
    sponsor_handle: str = ""
    disclosure_text: str = Field(
        default="",
        description="只保留原文中的广告或商业披露片段",
    )
    placement: Literal["none", "footer", "body", "image", "multiple", "unknown"] = "none"

    @field_validator("sponsor_name", "sponsor_handle", "disclosure_text", mode="before")
    @classmethod
    def _normalize_text(cls, value):
        return str(value or "").strip()


class TweetAnalysis(BaseModel):
    """Twitter 逐标的观点、宏观市场判断与预测契约提取协议 v4。"""

    reasoning: str = Field(default="", description="简要说明识别、归因和拆分依据")
    tweet_summary: str = Field(default="", description="不带投资方向的推文事实摘要")
    is_investment_relevant: bool = Field(
        default=False,
        description="是否包含产品支持市场中的实质投资信息",
    )
    is_investment_related: bool = Field(default=False, description="兼容字段")
    markets: list[Literal["CN", "HK", "US", "COMMODITY", "CRYPTO"]] = Field(
        default_factory=list
    )
    claims: list[InstrumentClaim] = Field(
        default_factory=list,
        description="逐标的观点；同标的事实、风险和催化剂不要机械拆成多个冲突方向",
    )
    market_views: list[MarketView] = Field(
        default_factory=list,
        description="无法归入单一标的的市场或宏观判断",
    )
    is_sponsored: bool = Field(
        default=False,
        description="兼容字段：仅表示推文含商业推广，不能作为整条推文的统计排除开关",
    )
    commercial_disclosure: CommercialDisclosure = Field(
        default_factory=CommercialDisclosure
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="整次结构化提取的可靠度，不表示观点正确概率",
    )
    media_summary: str = ""
    text_image_consistency: Literal[
        "consistent", "complementary", "conflict", "image_only", "unclear", "no_media"
    ] = "no_media"
    media_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    analysis_schema_version: Literal["v4"] = "v4"

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
        return normalized

    @field_validator("claims", mode="before")
    @classmethod
    def _ensure_claims_list(cls, value):
        return value if isinstance(value, list) else []

    @field_validator("market_views", mode="before")
    @classmethod
    def _ensure_market_views_list(cls, value):
        return value if isinstance(value, list) else []

    @field_validator("markets", mode="before")
    @classmethod
    def _normalize_markets(cls, value):
        if not isinstance(value, list):
            return []
        allowed = {"CN", "HK", "US", "COMMODITY", "CRYPTO"}
        return list(
            dict.fromkeys(
                str(item).upper() for item in value if str(item).upper() in allowed
            )
        )

    @field_validator("confidence", "media_confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value):
        if value is None:
            return 0.0
        return max(0.0, min(1.0, float(value)))

    @model_validator(mode="after")
    def _derive_container_fields(self):
        if self.commercial_disclosure.has_commercial_content:
            self.is_sponsored = True
        elif self.is_sponsored:
            self.commercial_disclosure.has_commercial_content = True
            if self.commercial_disclosure.placement == "none":
                self.commercial_disclosure.placement = "unknown"
        for claim in self.claims:
            if not self.is_sponsored:
                claim.sponsor_relation = "none"
            elif claim.sponsor_relation == "none":
                # 有商业披露但模型没有完成逐标的归因时，保守进入待确认，
                # 避免把旧的推文级判断误当成“无商业关联”。
                claim.sponsor_relation = "unclear"
        if self.claims or self.market_views:
            self.is_investment_relevant = True
        self.is_investment_related = self.is_investment_relevant
        claim_markets = [
            claim.instrument.market_hint
            for claim in self.claims
            if claim.instrument.market_hint != "unknown"
        ]
        view_markets = [
            view.market for view in self.market_views if view.market != "GLOBAL"
        ]
        extracted_markets = claim_markets + view_markets
        if extracted_markets:
            self.markets = list(dict.fromkeys(extracted_markets))
        return self


class TickerSummary(BaseModel):
    """旧聚合接口的响应结构；新业务由 instrument_claims 实时聚合。"""

    ticker: str
    mention_count: int
    bloggers: list[str]
    consensus: str
    bullish_count: int
    bearish_count: int
    recommendation_score: float | None = None
    summary: str
