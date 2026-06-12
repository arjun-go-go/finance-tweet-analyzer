"""复现 blogger_filter 报错: Error finding id

测试三种 filter 组合，看哪种触发 Chroma "Error finding id"。
"""
from __future__ import annotations

import sys
import traceback

sys.path.insert(0, ".")

from app.rag.vector_store import get_vector_store
from app.rag.embeddings import get_embedder


def run(label: str, flt: dict):
    print(f"\n=== {label} ===")
    print(f"filter = {flt}")
    try:
        vs = get_vector_store()
        emb = get_embedder()
        qvec = emb.embed_query("宇树机器人 sentiment risk technical")
        hits = vs.query("public_signals", query_embedding=qvec, k=15, filter=flt)
        print(f"OK: {len(hits)} hits")
        for h in hits[:3]:
            print(f"  - score={h.score:.3f} src={h.metadata.get('source_type')} bh={h.metadata.get('blogger_handle')}")
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    # 1. 仅 source_type
    run("only source_type=tweet", {"source_type": "tweet"})

    # 2. source_type + blogger_handle 等值
    run("source_type=tweet + blogger_handle=qinbafrank (eq)",
        {"source_type": "tweet", "blogger_handle": "qinbafrank"})

    # 3. source_type + blogger_handle $in (现网代码路径)
    run("source_type=tweet + blogger_handle $in [qinbafrank]",
        {"source_type": "tweet", "blogger_handle": {"$in": ["qinbafrank"]}})

    # 4. analysis 同样测
    run("source_type=analysis + blogger_handle $in [qinbafrank]",
        {"source_type": "analysis", "blogger_handle": {"$in": ["qinbafrank"]}})

    # 5. 单 key $in (会暴露 _build_chroma_filter 的不一致)
    run("only blogger_handle $in [qinbafrank]",
        {"blogger_handle": {"$in": ["qinbafrank"]}})
