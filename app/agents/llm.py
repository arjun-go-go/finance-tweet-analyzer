"""OpenAI 官方 Chat Completions 客户端，按分析角色分配模型。"""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from langchain_core.callbacks import BaseCallbackHandler

from app.core.config import settings
from app.services.analysis_control_service import (
    record_model_failure,
    require_analysis_enabled,
)

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


class _AnalysisModelCallback(BaseCallbackHandler):
    """Persist provider failures even when an Agent applies a local fallback."""

    def __init__(self, model: str):
        self.model = model

    def on_llm_error(self, error: BaseException, **kwargs) -> None:
        exc = error if isinstance(error, Exception) else RuntimeError(str(error))
        record_model_failure(exc, provider="openai", model=self.model)


def _create_openai_llm(
    model: str,
    *,
    reasoning_effort: str,
    max_completion_tokens: int,
    timeout: float,
    max_retries: int | None = None,
) -> ChatOpenAI:
    from langchain_openai import ChatOpenAI

    require_analysis_enabled()
    proxy = settings.http_proxy or None

    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        use_responses_api=False,
        reasoning_effort=reasoning_effort,
        max_completion_tokens=max_completion_tokens,
        timeout=timeout,
        max_retries=max_retries,
        callbacks=[_AnalysisModelCallback(model)],
        http_client=httpx.Client(proxy=proxy),
        http_async_client=httpx.AsyncClient(proxy=proxy),
    )


def get_signal_llm() -> ChatOpenAI:
    """分类、逐标的提取、风险评估与检索意图识别。"""
    return _create_openai_llm(
        settings.signal_model,
        reasoning_effort=settings.signal_llm_reasoning_effort,
        timeout=settings.signal_llm_timeout_seconds,
        max_retries=settings.signal_llm_max_retries,
        max_completion_tokens=settings.signal_llm_max_completion_tokens,
    )


def get_report_llm() -> ChatOpenAI:
    """裁决关键字段的分歧。"""
    return _create_openai_llm(
        settings.report_model,
        reasoning_effort=settings.report_llm_reasoning_effort,
        timeout=settings.report_llm_timeout_seconds,
        max_retries=settings.report_llm_max_retries,
        max_completion_tokens=settings.report_llm_max_completion_tokens,
    )


def get_review_llm() -> ChatOpenAI:
    """用独立模型复核关键提取结果。"""
    return _create_openai_llm(
        settings.review_model,
        reasoning_effort=settings.review_llm_reasoning_effort,
        timeout=settings.signal_llm_timeout_seconds,
        max_retries=settings.signal_llm_max_retries,
        max_completion_tokens=settings.signal_llm_max_completion_tokens,
    )


def get_vision_llm() -> ChatOpenAI:
    """从推文文字和图片中提取结构化证据。"""
    return _create_openai_llm(
        settings.vision_model,
        reasoning_effort=settings.vision_llm_reasoning_effort,
        max_completion_tokens=settings.vision_max_output_tokens,
        timeout=120,
    )
