"""
RAG 多路检索器包
============================================================
包含 5 条独立的检索路径，各自负责不同数据源：

1. document_retriever — 用户私有文档（user_documents collection）
2. tweet_retriever   — 公共推文信号（public_signals, source_type='tweet'）
3. analysis_retriever — 分析结果信号（public_signals, source_type='analysis'）
4. structured_retriever — PostgreSQL 结构化数据（predictions / analysis_results 表）
5. bm25_retriever    — PostgreSQL 全文检索（doc_chunks.search_vector, jieba 分词）

所有检索器输出统一格式：
  {"unique_id": str, "content": str, "source_type": str, "metadata": dict, "score": float}

这样下游 RRF 融合可以无差别处理各路径结果。
"""

from app.rag.retrievers.document_retriever import retrieve_documents
from app.rag.retrievers.tweet_retriever import retrieve_tweets
from app.rag.retrievers.analysis_retriever import retrieve_analyses
from app.rag.retrievers.structured_retriever import retrieve_structured
from app.rag.retrievers.bm25_retriever import retrieve_bm25

__all__ = [
    "retrieve_documents",
    "retrieve_tweets",
    "retrieve_analyses",
    "retrieve_structured",
    "retrieve_bm25",
]
