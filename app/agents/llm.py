"""LLM 工厂 —— 三模型分工策略。

所有模型通过 OpenRouter 统一网关接入，经本地 HTTP 代理转发。
模型分工平衡成本、响应时间和关键信号准确性：
    - signal_model: 高频分类、逐标的提取、风险评估和查询意图识别
    - review_model: 跨模型独立复核和图文理解
    - report_model: 仅处理关键字段冲突仲裁及复杂生成
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.core.config import settings

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


def get_signal_llm() -> ChatOpenAI:
    """信号模型 —— 快速判别型任务（分类、分析、风险评估）。

    temperature=0.1 保证输出确定性，timeout=30s 适配短文本快速响应。
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.signal_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.1,
        timeout=settings.signal_llm_timeout_seconds,
        max_retries=settings.signal_llm_max_retries,
        max_completion_tokens=settings.signal_llm_max_completion_tokens,
        extra_body={"reasoning": {"effort": settings.signal_llm_reasoning_effort}},
        http_client=httpx.Client(proxy=settings.http_proxy),
    )


def get_report_llm() -> ChatOpenAI:
    """仲裁模型 —— 关键字段冲突裁决和复杂生成。

    temperature=0.1 降低仲裁漂移，timeout=120s 容忍复杂结构化输出延迟。
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.report_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.1,
        timeout=120,
        http_client=httpx.Client(proxy=settings.http_proxy),
    )


def get_review_llm() -> ChatOpenAI:
    """独立复核模型 —— 用不同模型家族复核关键提取结果。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.review_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.0,
        timeout=settings.signal_llm_timeout_seconds,
        max_retries=settings.signal_llm_max_retries,
        max_completion_tokens=settings.signal_llm_max_completion_tokens,
        http_client=httpx.Client(proxy=settings.http_proxy),
    )


def get_vision_llm() -> ChatOpenAI:
    """Multimodal model used to extract evidence from tweet text and images."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.vision_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.0,
        max_tokens=settings.vision_max_output_tokens,
        timeout=120,
        extra_body={"reasoning": {"effort": settings.vision_llm_reasoning_effort}},
        http_client=httpx.Client(proxy=settings.http_proxy),
    )
