"""对比分块新旧逻辑：从 DB 抽样推文，分别用旧版（纯递归）和新版（清洗+结构感知+递归）切块，输出统计与差异样例。

用法：
  uv run python scripts/compare_chunking.py [--limit 200] [--min-len 300] [--show 3]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select

from app.core.deps import SessionLocal
from app.models.tweet import Tweet
from app.rag.chunking import (
    _SEPARATORS,
    _split_text_recursive,
    chunk_tweet as chunk_tweet_new,
)


# ---- 旧逻辑（提交前的基线版本）----
def chunk_tweet_old(text: str, *, long_tweet_threshold: int = 512) -> list[str]:
    """旧版本：仅做长度路由 + 递归切，不清洗、不结构感知。"""
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= long_tweet_threshold:
        return [text]
    raw = _split_text_recursive(text, _SEPARATORS, 500, 50)
    return [c.strip() for c in raw if c.strip()]


# ---- 评估辅助 ----
_ENUMERATION_HEAD = re.compile(
    r"^(\d+[、\.\)]|\(\d+\)|[一二三四五六七八九十]+[、\.])"
)


def stats(name: str, all_chunks: list[list[str]]) -> dict:
    flat = [c for chunks in all_chunks for c in chunks]
    if not flat:
        return {}
    lengths = [len(c) for c in flat]
    starts_with_enum = sum(1 for c in flat if _ENUMERATION_HEAD.match(c))
    return {
        "name": name,
        "tweets": len(all_chunks),
        "chunks": len(flat),
        "avg_chunks_per_tweet": round(len(flat) / len(all_chunks), 2),
        "min_len": min(lengths),
        "max_len": max(lengths),
        "avg_len": round(sum(lengths) / len(lengths), 1),
        "chunks_starting_with_enum": starts_with_enum,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200, help="抽样推文数")
    ap.add_argument("--min-len", type=int, default=300, help="只对比长度 >= 该值的推文")
    ap.add_argument("--show", type=int, default=3, help="展示差异最大的前 N 条样例")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(
            select(Tweet.id, Tweet.author_handle, Tweet.content)
            .where(Tweet.content.is_not(None))
            .order_by(Tweet.published_at.desc())
            .limit(args.limit * 4)
        ).all()
    finally:
        db.close()

    samples = [r for r in rows if r.content and len(r.content) >= args.min_len][: args.limit]
    if not samples:
        print(f"没有找到长度 >= {args.min_len} 的推文")
        return

    old_results, new_results = [], []
    diffs = []
    for r in samples:
        co = chunk_tweet_old(r.content)
        cn = chunk_tweet_new(r.content)
        old_results.append(co)
        new_results.append(cn)
        if co != cn:
            diffs.append((r, co, cn, abs(len(cn) - len(co))))

    print("=" * 70)
    print(f"样本：{len(samples)} 条推文（content >= {args.min_len} 字）")
    print("=" * 70)
    for s in (stats("OLD (recursive only)", old_results), stats("NEW (clean+structure+recursive)", new_results)):
        print(f"\n[{s['name']}]")
        for k, v in s.items():
            if k == "name":
                continue
            print(f"  {k:30s} {v}")

    same = len(samples) - len(diffs)
    print(f"\n输出一致的推文：{same}/{len(samples)}  不一致：{len(diffs)}")

    diffs.sort(key=lambda x: -x[3])
    print(f"\n--- 差异最大的前 {min(args.show, len(diffs))} 条样例 ---")
    for i, (r, co, cn, _) in enumerate(diffs[: args.show], 1):
        print(f"\n[{i}] tweet_id={r.id}  @{r.author_handle}  len={len(r.content)}")
        print(f"    OLD -> {len(co)} chunks: lengths={[len(c) for c in co]}")
        print(f"    NEW -> {len(cn)} chunks: lengths={[len(c) for c in cn]}")
        print(f"    OLD chunks 头部预览：")
        for j, c in enumerate(co[:4]):
            print(f"      [{j}] {c[:60].replace(chr(10),'⏎')}…")
        print(f"    NEW chunks 头部预览：")
        for j, c in enumerate(cn[:4]):
            print(f"      [{j}] {c[:60].replace(chr(10),'⏎')}…")


if __name__ == "__main__":
    main()
