"""复现 retrieve_tweets / retrieve_analyses 报错."""
from __future__ import annotations

import sys
import traceback

sys.path.insert(0, ".")

from app.agents.self_query_agent import QueryIntent
from app.rag.retrievers.tweet_retriever import retrieve_tweets
from app.rag.retrievers.analysis_retriever import retrieve_analyses


def make_intent(blogger_filter):
    return QueryIntent(
        ticker="宇树机器人",
        time_range_start="2026-06-03T10:03:11.189149+00:00",
        time_range_end="2026-06-10T10:03:11.189149+00:00",
        sentiment_filter=[],
        horizon_filter=[],
        focus_aspects=["sentiment", "risk", "technical"],
        keywords=[],
        blogger_filter=blogger_filter,
    )


def run(label, intent, fn):
    print(f"\n=== {label} ===")
    try:
        out = fn(intent)
        print(f"OK: {len(out)} hits")
        for h in out[:2]:
            md = h.get("metadata", {})
            print(f"  - score={h.get('score'):.3f} src_type={h.get('source_type')} bh={md.get('blogger_handle')} src_id={md.get('source_id')}")
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    intent_with = make_intent(["qinbafrank"])
    intent_without = make_intent([])

    run("retrieve_tweets WITHOUT blogger_filter", intent_without, retrieve_tweets)
    run("retrieve_tweets WITH blogger_filter=[qinbafrank]", intent_with, retrieve_tweets)
    run("retrieve_analyses WITHOUT blogger_filter", intent_without, retrieve_analyses)
    run("retrieve_analyses WITH blogger_filter=[qinbafrank]", intent_with, retrieve_analyses)
