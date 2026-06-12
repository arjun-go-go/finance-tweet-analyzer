"""
RAG 多路召回融合模块 — Reciprocal Rank Fusion (RRF)
============================================================
职责：将多条检索路径（document / tweet / analysis / structured）的结果
     融合为一个统一的排序列表。

为什么用 RRF 而不是简单合并：
- 各路径的相似度分数量纲不同（向量余弦 vs SQL 固定分数），不可直接比较
- RRF 只看排名（rank），不看绝对分数，天然解决了异构分数融合问题
- 论文证明 RRF 在多路召回场景下效果稳定优于加权求和

RRF 算法公式：
  score(doc) = Σ 1 / (k + rank_i + 1)
  其中 k 是平滑参数（默认 60），rank_i 是该文档在第 i 条路径中的排名

参数选择：
- k=60：论文推荐值，平衡头部和尾部文档的贡献
- top_n=30：融合后保留前 30 条送入 reranker 精排

在管线中的位置：
  multi_retrieve（4 路并行） → **RRF fuse** → rerank → generate_sections
"""

from __future__ import annotations

from collections import defaultdict


def reciprocal_rank_fusion(
    results_per_path: list[list[dict]],
    k: int = 60,
    top_n: int = 30,
) -> list[dict]:
    """将多路检索结果通过 RRF 算法融合为统一排序。

    Args:
        results_per_path: 每条路径的检索结果列表，每个 item 必须包含 "unique_id" 键
        k: RRF 平滑参数，值越大则排名靠后的文档权重下降越缓慢
        top_n: 融合排序后保留的最大文档数

    Returns:
        按 RRF 分数降序排列的 top_n 个文档（保留原始 dict 结构）
    """
    # 累积每个文档在所有路径中的 RRF 分数
    scores: dict[str, float] = defaultdict(float)
    # 保存文档原始数据（相同 unique_id 只保留首次出现的版本）
    items: dict[str, dict] = {}

    for path_results in results_per_path:
        for rank, item in enumerate(path_results):
            uid = item["unique_id"]
            # RRF 公式：1 / (k + rank + 1)，rank 从 0 开始
            scores[uid] += 1.0 / (k + rank + 1)
            if uid not in items:
                items[uid] = item

    # 按 RRF 分数降序排列，取 top_n
    ranked = sorted(items.values(), key=lambda x: scores[x["unique_id"]], reverse=True)
    return ranked[:top_n]
