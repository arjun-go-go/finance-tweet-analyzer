"""清空 doc_chunks 表 + 同步清空 Chroma 向量。

清理范围：
    1. PostgreSQL: TRUNCATE doc_chunks
    2. Chroma: 删除 user_documents / public_signals 两个 collection 中所有向量

注意：
    - documents 表保留（其 chunk_count 等字段会与实际不一致，需要的话另行处理）
    - 用户上传的原始文件（uploads/）保留
"""
from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import settings


def clear_postgres() -> int:
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM doc_chunks")).scalar() or 0
        conn.execute(text("TRUNCATE TABLE doc_chunks"))
        after = conn.execute(text("SELECT COUNT(*) FROM doc_chunks")).scalar() or 0
    print(f"  ✓ doc_chunks: {before} -> {after}")
    return before


def clear_chroma() -> dict[str, int]:
    import chromadb

    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    results: dict[str, int] = {}
    for name in ("user_documents", "public_signals"):
        try:
            col = client.get_or_create_collection(name)
            ids = col.get()["ids"]
            if ids:
                col.delete(ids=ids)
            results[name] = len(ids)
            print(f"  ✓ Chroma {name}: {len(ids)} vectors deleted")
        except Exception as e:
            results[name] = -1
            print(f"  ! Chroma {name}: {e}")
    return results


if __name__ == "__main__":
    print("开始清空 doc_chunks 与对应向量...")
    pg = clear_postgres()
    chr_ = clear_chroma()
    print("\n完成。")
    print(f"  PG  : 删除 {pg} 行")
    print(f"  Chroma: {chr_}")
