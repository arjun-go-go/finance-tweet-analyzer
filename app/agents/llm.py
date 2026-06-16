"""LLM 工厂 —— 多模型分工策略。

所有模型通过 OpenRouter 统一网关接入，经本地 HTTP 代理转发。
双模型设计实现成本与质量平衡：
    - signal_model (Qwen3.7-Max): 低成本高速度，用于分类/分析/评分等判别型任务
    - report_model (Claude Opus): 高质量生成，用于报告/聊天/复杂推理
"""
import httpx
from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_signal_llm() -> ChatOpenAI:
    """信号模型 —— 快速判别型任务（分类、分析、风险评估）。

    temperature=0.1 保证输出确定性，timeout=30s 适配短文本快速响应。
    """
    return ChatOpenAI(
        model=settings.signal_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.1,
        timeout=90,
        http_client=httpx.Client(proxy=settings.http_proxy),
    )


def get_report_llm() -> ChatOpenAI:
    """报告模型 —— 高质量生成型任务（聊天、报告撰写、SQL 重试）。

    temperature=0.3 允许适度创造性，timeout=120s 容忍长文本生成延迟。
    """
    return ChatOpenAI(
        model=settings.report_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.1,
        timeout=120,
        http_client=httpx.Client(proxy=settings.http_proxy),
    )
