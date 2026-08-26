from datetime import datetime, timezone
from uuid import uuid4

from app.services import intelligence_service


def _item(*, kind="opinion", lifecycle="new", bucket="personalized", score=80):
    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid4()),
        "kind": kind,
        "title": "测试情报",
        "summary": "来自原始推文的结构化结论",
        "direction": "bullish",
        "tickers": ["AAPL"],
        "author": "analyst",
        "confidence": 0.8,
        "source_credibility": 70.0,
        "importance_score": score,
        "score_breakdown": {},
        "score_explanation": [],
        "risk_factors": [],
        "key_points": [],
        "published_at": now,
        "first_seen_at": now,
        "last_seen_at": now,
        "time_bucket": "今日",
        "lifecycle": lifecycle,
        "event_count": 1,
        "match_reasons": ["关注博主"],
        "feed_bucket": bucket,
        "corroboration_count": 2,
        "evidence": {
            "source_type": "tweet",
            "source_id": "tweet-1",
            "author": "analyst",
            "published_at": now,
            "excerpt": "原始推文",
            "source_url": "https://x.com/analyst/status/1",
        },
        "supporting_evidence": [
            {
                "source_type": "tweet",
                "source_id": "tweet-1",
                "author": "analyst",
                "published_at": now,
                "excerpt": "原始推文",
                "source_url": "https://x.com/analyst/status/1",
            }
        ],
    }


def test_daily_digest_uses_personalized_evidence_and_counts_risk(monkeypatch):
    now = datetime.now(timezone.utc)
    opinion = _item()
    risk = _item(kind="risk", lifecycle="reversed", score=90)
    context = {
        "followed_bloggers": 1,
        "tracked_tickers": 1,
        "personalized": True,
        "fallback_to_market": False,
        "candidate_total": 2,
        "personalized_candidates": 2,
        "market_candidates": 0,
        "window": "24h",
        "kind": "all",
        "generated_at": now,
    }
    monkeypatch.setattr(
        intelligence_service,
        "build_user_intelligence_feed",
        lambda *args, **kwargs: ([opinion, risk], context),
    )

    digest = intelligence_service.build_user_daily_digest(object(), uuid4())

    assert digest["status"] == "ready"
    assert digest["metrics"]["personalized_count"] == 2
    assert digest["metrics"]["risk_count"] == 1
    assert digest["metrics"]["reversal_count"] == 1
    assert digest["attention"][0]["id"] == risk["id"]
    assert digest["highlights"][0]["evidence"]["source_url"].startswith("https://x.com/")


def test_daily_digest_explains_missing_research_scope(monkeypatch):
    now = datetime.now(timezone.utc)
    context = {
        "followed_bloggers": 0,
        "tracked_tickers": 0,
        "personalized": False,
        "fallback_to_market": False,
        "candidate_total": 0,
        "personalized_candidates": 0,
        "market_candidates": 0,
        "window": "24h",
        "kind": "all",
        "generated_at": now,
    }
    monkeypatch.setattr(
        intelligence_service,
        "build_user_intelligence_feed",
        lambda *args, **kwargs: ([], context),
    )

    digest = intelligence_service.build_user_daily_digest(object(), uuid4())

    assert digest["status"] == "scope_empty"
    assert digest["highlights"] == []
    assert "关注博主" in digest["executive_summary"]
