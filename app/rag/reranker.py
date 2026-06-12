"""
RAG 重排序模块（Reranker）
============================================================
职责：对 RRF 融合后的候选文档进行精排，提高最终输入 LLM 的上下文质量。

原理：
- 粗排（向量检索）：速度快但精度有限（embedding 是压缩表示）
- 精排（Reranker）：用交叉编码器（Cross-Encoder）对 query-doc pair
  逐对计算相关性分数，精度远高于向量余弦距离

使用的模型：DashScope gte-rerank-v2（阿里通义千问重排序模型）
- 通过 langchain-community 的 DashScopeRerank 调用
- 输入：query + N 篇候选文档
- 输出：按 relevance_score 降序排列的 top_n 结果

容错设计（熔断器 + 降级）：
- @resilient_tool 装饰器提供：重试 2 次 + 熔断器保护
- 熔断触发后：降级为"保持原始 RRF 排序，截取 top_n"
  （RRF 排序已经相当不错，降级代价可接受）
- 文档数 <= top_n 时直接跳过 reranker 调用（无需精排）

在管线中的位置：
  multi_retrieve → RRF fuse → **rerank** → generate_sections
"""

from __future__ import annotations

import dashscope

from app.core.config import settings
from app.core.resilience import resilient_tool


def _do_rerank(query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
    """调用 DashScope Reranker API 执行精排。

    直接调用 dashscope.TextReRank.call 而非 LangChain 封装，
    因为 LangChain 的 DashScopeRerank 会强制覆盖 model 为 gte-rerank（403 无权限）。
    """
    result = dashscope.TextReRank.call(
        model=settings.reranker_model,
        query=query,
        documents=documents,
        top_n=top_n,
        return_documents=False,
        api_key=settings.dashscope_api_key,
    )
    if result.status_code != 200:
        raise RuntimeError(f"DashScope Rerank failed: {result.code} - {result.message}")
    return [(r.index, r.relevance_score) for r in result.output.results]


@resilient_tool(
    retries=2,
    circuit_name="reranker",
    fallback_message="__RERANK_FALLBACK__",
)
def _rerank_with_circuit(query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
    """带熔断器保护的 rerank 调用。

    熔断器逻辑（由 @resilient_tool 提供）：
    - 连续失败超过阈值 → 熔断器打开 → 直接返回 fallback_message
    - 熔断恢复后自动半开尝试
    """
    return _do_rerank(query, documents, top_n)


def rerank(query: str, documents: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
    """对候选文档执行重排序（对外主入口）。

    Args:
        query: 用户查询（或从 intent 构造的检索 query）
        documents: 候选文档文本列表（来自 RRF 融合后的 top-30）
        top_n: 精排后保留的文档数（默认取 settings.reranker_top_n = 8）

    Returns:
        list[(原始索引, 相关性分数)]，按分数降序排列

    降级策略：
        熔断触发时返回原始顺序的前 top_n 个，分数递减模拟排序
    """
    if top_n is None:
        top_n = settings.reranker_top_n
    if not documents:
        return []
    # 文档数不超过 top_n，无需精排，全部保留
    if len(documents) <= top_n:
        return [(i, 1.0) for i in range(len(documents))]

    result = _rerank_with_circuit(query, documents, top_n)
    # 熔断降级：保持 RRF 原始排序，用递减分数标记
    if isinstance(result, str) and "RERANK_FALLBACK" in result:
        return [(i, 1.0 - i * 0.01) for i in range(min(top_n, len(documents)))]
    return result


def apply_time_decay(
    items: list[dict],
    *,
    decay_lambda: float = 0.1,
    max_boost: float = 1.5,
) -> list[dict]:
    """对 reranked 结果按时间衰减 + 博主可信度综合加权，重新排序。

    综合公式：final_weight = time_weight * credibility_weight
    - time_weight = exp(-λ * days_ago)，今天≈1.0，7天前≈0.50
    - credibility_weight = 0.5 + 0.5 * credibility_score，范围 [0.5, 1.0]

    Args:
        items: reranked 文档列表，metadata 可含 published_at 和 credibility_score
        decay_lambda: 时间衰减系数
        max_boost: 最大提升倍数

    Returns:
        按综合权重降序重排后的列表
    """
    import math
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    def _get_weight(item: dict) -> float:
        metadata = item.get("metadata") or {}

        # 时间衰减
        published = metadata.get("published_at", "")
        if not published:
            time_weight = 0.7
        else:
            try:
                dt = datetime.fromisoformat(published)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                days_ago = (now - dt).total_seconds() / 86400
                time_weight = math.exp(-decay_lambda * max(days_ago, 0))
                time_weight = min(time_weight, max_boost)
            except (ValueError, TypeError):
                time_weight = 0.7

        # 博主可信度加权
        credibility = metadata.get("credibility_score")
        if credibility is not None:
            try:
                credibility_weight = 0.5 + 0.5 * float(credibility)
            except (ValueError, TypeError):
                credibility_weight = 0.75
        else:
            credibility_weight = 0.75

        return time_weight * credibility_weight

    scored = [(i, _get_weight(item)) for i, item in enumerate(items)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [items[i] for i, _ in scored]
