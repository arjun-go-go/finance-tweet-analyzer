"""用真实推文评估切块效果。"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select
from app.core.deps import SessionLocal
from app.models.tweet import Tweet
from app.rag.chunking import chunk_tweet


def main():
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Tweet.id, Tweet.author_handle, Tweet.content)
            .where(Tweet.content.is_not(None))
            .order_by(Tweet.published_at.desc())
            .limit(500)
        ).all()
    finally:
        db.close()

    # 分长短统计
    short_tweets = [r for r in rows if r.content and len(r.content.strip()) <= 500]
    long_tweets = [r for r in rows if r.content and len(r.content.strip()) > 500]

    print(f"总推文: {len(rows)}  短推文(≤500): {len(short_tweets)}  长推文(>500): {len(long_tweets)}")
    print()

    # 展示 5 条长推文的切块效果
    print("=" * 70)
    print("长推文切块效果展示（前 5 条）")
    print("=" * 70)
    for r in long_tweets[:5]:
        text = r.content.strip()
        chunks = chunk_tweet(text)
        print(f"\n{'─' * 60}")
        print(f"@{r.author_handle}  原文长度={len(text)}字  → {len(chunks)} 块")
        print(f"块长度分布: {[len(c) for c in chunks]}")
        print(f"原文前100字: {text[:100].replace(chr(10), '⏎')}")
        print()
        for i, c in enumerate(chunks):
            preview = c[:80].replace("\n", "⏎")
            tail = c[-30:].replace("\n", "⏎") if len(c) > 80 else ""
            print(f"  chunk[{i}] ({len(c)}字): {preview}{'...' + tail if tail else ''}")

    # 展示 5 条短推文（确认不被误切）
    print(f"\n{'=' * 70}")
    print("短推文验证（前 5 条 — 应为单块不切割）")
    print("=" * 70)
    for r in short_tweets[:5]:
        text = r.content.strip()
        chunks = chunk_tweet(text)
        status = "✓ 单块" if len(chunks) == 1 else f"✗ 被切成 {len(chunks)} 块"
        print(f"  @{r.author_handle} ({len(text)}字) → {status}")

    # 总体质量指标
    print(f"\n{'=' * 70}")
    print("全量统计（所有推文）")
    print("=" * 70)
    all_chunks = []
    over_size = 0
    under_30 = 0
    for r in rows:
        if not r.content:
            continue
        chunks = chunk_tweet(r.content.strip())
        all_chunks.extend(chunks)
        for c in chunks:
            if len(c) > 500:
                over_size += 1
            if len(c) < 30:
                under_30 += 1

    total = len(all_chunks)
    lengths = [len(c) for c in all_chunks]
    print(f"  总推文数:        {len(rows)}")
    print(f"  总 chunk 数:     {total}")
    print(f"  平均 chunk 长度: {sum(lengths)/total:.1f} 字")
    print(f"  最小 / 最大:     {min(lengths)} / {max(lengths)} 字")
    print(f"  超长块(>500):    {over_size}")
    print(f"  碎片块(<30):     {under_30}")
    print(f"  碎片块(<50):     {sum(1 for l in lengths if l < 50)}")
    print(f"  质量指标:        超长率={over_size/total*100:.1f}%  碎片率(<50)={sum(1 for l in lengths if l < 50)/total*100:.1f}%")

    # 碎片来源诊断
    print(f"\n{'=' * 70}")
    print("碎片诊断（前 10 个 < 50 字的 chunk）")
    print("=" * 70)
    frag_count = 0
    for r in rows:
        if not r.content:
            continue
        text = r.content.strip()
        chunks = chunk_tweet(text)
        for i, c in enumerate(chunks):
            if len(c) < 50 and frag_count < 10:
                print(f"  @{r.author_handle} 原文{len(text)}字 chunk[{i}/{len(chunks)}] ({len(c)}字): {c[:60].replace(chr(10), '⏎')}")
                frag_count += 1
        if frag_count >= 10:
            break


if __name__ == "__main__":
    main()
