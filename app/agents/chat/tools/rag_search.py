from __future__ import annotations

from uuid import UUID


def search_my_documents_impl(user_id: UUID, query: str, ticker: str = "") -> str:
    """Search the authenticated user's private document vector index."""
    from app.rag.embeddings import get_embedder
    from app.rag.repository import UserDocumentRepository
    from app.rag.vector_store import get_vector_store

    repo = UserDocumentRepository(get_vector_store(), get_embedder())

    try:
        hits = repo.search(
            user_id=user_id,
            query=query,
            k=5,
        )
    except Exception:
        return "文档检索暂时不可用。"

    if not hits:
        return "未找到相关文档内容。"

    results = []
    for i, hit in enumerate(hits, 1):
        meta = hit.metadata or {}
        content_preview = hit.content[:500] if hit.content else meta.get("title", "")
        source_id = meta.get("source_id") or meta.get("document_id") or meta.get("chunk_id")
        source_uri = meta.get("source_uri") or meta.get("url")
        source_parts = [f"来源ID: {source_id}"] if source_id else []
        if source_uri:
            source_parts.append(f"原文: {source_uri}")
        source_line = " | ".join(source_parts)
        results.append(
            f"[{i}] {content_preview}" + (f"\n{source_line}" if source_line else "")
        )
    return "\n\n".join(results)


def search_public_signals_impl(query: str, source_type: str = "analysis", blogger: str = "") -> str:
    """Search the public signal vector index."""
    from app.rag.embeddings import get_embedder
    from app.rag.vector_store import get_vector_store

    if source_type not in ("analysis", "tweet"):
        return "参数错误：source_type 必须是 'analysis' 或 'tweet'。"

    flt: dict = {"source_type": source_type}
    if blogger:
        flt["blogger_handle"] = blogger

    try:
        emb = get_embedder().embed_query(query)
        hits = get_vector_store().query(
            "public_signals",
            query_embedding=emb,
            k=10,
            filter=flt,
        )
    except Exception:
        return "公共信号检索暂时不可用。"

    if not hits:
        blogger_hint = f" 博主 @{blogger}" if blogger else ""
        return f"未在公共信号库中找到与「{query}」相关的 {source_type} 内容{blogger_hint}。"

    results = []
    for i, hit in enumerate(hits, 1):
        meta = hit.metadata
        blogger_handle = meta.get("blogger_handle", "未知博主")
        sentiment = meta.get("sentiment", "")
        horizon = meta.get("horizon", "")
        published_at = meta.get("published_at") or meta.get("created_at")
        source_id = meta.get("source_id") or meta.get("tweet_id") or meta.get("chunk_id")
        source_uri = meta.get("source_uri") or meta.get("url")
        score = hit.score
        content_preview = hit.content[:1000] if hit.content else ""
        header = f"[{i}] 博主: {blogger_handle}"
        if sentiment:
            header += f" | 情感: {sentiment}"
        if horizon:
            header += f" | 周期: {horizon}"
        if published_at:
            header += f" | 时间: {published_at}"
        if source_id:
            header += f" | 来源ID: {source_id}"
        header += f" | 相关度: {score:.3f}"
        source_line = f"\n原文: {source_uri}" if source_uri else ""
        results.append(f"{header}\n{content_preview}{source_line}")
    return "\n\n".join(results)
