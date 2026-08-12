from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MediaImageObservation(BaseModel):
    image_index: int = Field(description="图片序号，从1开始")
    summary: str = Field(default="", description="图片可见内容的客观摘要")
    ocr_text: str = Field(default="", description="图片中可辨认的原始文字")
    tickers: list[str] = Field(default_factory=list, description="图片明确出现的投资标的代码")
    entities: list[str] = Field(default_factory=list, description="图片明确出现的公司、人物、机构或产品")
    numeric_facts: list[str] = Field(default_factory=list, description="图片明确显示的价格、比例、日期等数字事实")
    visual_evidence: list[str] = Field(default_factory=list, description="支持判断的具体可见证据")
    uncertainties: list[str] = Field(default_factory=list, description="模糊、遮挡或无法确认的内容")


class TweetMediaAnalysisOutput(BaseModel):
    is_financial: bool = Field(default=False, description="图文整体是否包含金融或投资信息")
    combined_summary: str = Field(default="", description="结合推文文字与全部图片的事实摘要")
    images: list[MediaImageObservation] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list, description="图文整体明确涉及的投资标的")
    key_points: list[str] = Field(default_factory=list, description="图文共同表达的关键事实或观点")
    risk_signals: list[str] = Field(default_factory=list, description="图文中明确可见的风险信号")
    sentiment: Literal["bullish", "bearish", "neutral", "mixed", "unclear"] = "unclear"
    text_image_consistency: Literal[
        "consistent", "complementary", "conflict", "image_only", "unclear"
    ] = "unclear"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("tickers", mode="before")
    @classmethod
    def _normalize_tickers(cls, value):
        if not isinstance(value, list):
            return []
        return [str(item).strip().lstrip("$").upper() for item in value if item]

    @field_validator("key_points", "risk_signals", mode="before")
    @classmethod
    def _normalize_strings(cls, value):
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if item]
