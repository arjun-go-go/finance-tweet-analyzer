import uuid
from datetime import datetime, timedelta, timezone

from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.instrument_claim import InstrumentClaim
from app.models.tweet import Tweet
from app.models.user import User
from app.models.user_blogger_follow import UserBloggerFollow


def _post(db, *, post_id, handle, at, content, side=None, horizon="medium",
          source="author", sponsor="none", risks=None, market_views=None):
    tweet = Tweet(
        tweet_id=post_id, author_handle=handle, content=content,
        published_at=at, status="analyzed",
    )
    db.add(tweet)
    db.flush()
    analysis = AnalysisResult(
        tweet_id=tweet.id, analysis_type="tweet_analysis",
        result={"market_views": market_views or []}, model_used="fixture",
    )
    db.add(analysis)
    db.flush()
    if side:
        db.add(InstrumentClaim(
            analysis_result_id=analysis.id, claim_index=0,
            instrument_symbol="NVDA", instrument_snapshot={"symbol": "NVDA", "market": "US", "asset_type": "equity"},
            direction=side, horizon=horizon, claim_type="opinion", opinion_source=source,
            sponsor_relation=sponsor, thesis=content, evidence=[content], risk_factors=risks or [],
            downstream_eligible=True, performance_eligible=True,
        ))
        db.flush()
    return tweet


def test_changes_compare_only_the_users_followed_author_and_matching_horizon(client, db_session, auth):
    now = datetime.now(timezone.utc)
    reader = User(id=uuid.UUID(auth.user_id("reader")), email="reader@example.test",
                  username="reader", password_hash="unused", status="active")
    blogger = Blogger(handle="alice", name="Alice")
    db_session.add_all([reader, blogger])
    db_session.flush()
    db_session.add(UserBloggerFollow(user_id=reader.id, blogger_id=blogger.id))

    def post(post_id, hours, content, side, **facts):
        _post(db_session, post_id=post_id, handle=facts.pop("handle", "alice"),
              at=now - timedelta(hours=hours), content=content, side=side, **facts)

    post("201", 7, "中期看好 NVDA，主要依据是订单增长。", "bullish")
    post("202", 6, "短期看空 NVDA。", "bearish", horizon="short")
    post("203", 5, "引用别人看空 NVDA。", "bearish", source="quoted")
    post("204", 4, "推广 NVDA。", "bearish", sponsor="direct")
    post("205", 3, "中期仍看好 NVDA，但新增估值风险。", "bullish", risks=["估值风险", "原文没有此句"])
    post("206", 2, "中期下调，转为看空 NVDA。", "bearish")
    post("207", 1, "未关注的作者看好 NVDA。", "bullish", handle="unfollowed")

    response = client.get("/api/me/opinion-changes", headers=auth.headers("reader"))
    assert response.status_code == 200
    data = response.json()
    assert data["followed_count"] == 1
    assert [item["kind"] for item in data["items"]] == ["direction_changed", "new_evidence", "first_opinion"]
    direction_change, new_evidence, _ = data["items"]
    assert direction_change["current"]["source_id"] == "206"
    assert direction_change["previous"]["source_id"] == "205"
    assert new_evidence["previous"]["source_id"] == "201"
    assert new_evidence["new_factors"] == ["估值风险"]
    assert client.get("/api/me/opinion-changes", headers=auth.headers("other")).json()["items"] == []


def test_tweet_filters_are_applied_to_latest_analysis_before_pagination(client, db_session, auth):
    now = datetime.now(timezone.utc)
    _post(db_session, post_id="300", handle="alice", at=now,
          content="日常推文")
    _post(db_session, post_id="301", handle="alice", at=now - timedelta(hours=1),
          content="中期看好 NVDA。", side="bullish")
    market = _post(db_session, post_id="302", handle="alice", at=now - timedelta(hours=2),
                   content="预计利率对美国市场有影响。", market_views=[{"market": "US"}])
    stale = _post(db_session, post_id="303", handle="alice", at=now - timedelta(hours=3),
                  content="已重新分析的推文。", market_views=[{"market": "US"}])
    db_session.add(AnalysisResult(
        tweet_id=stale.id, analysis_type="tweet_analysis", result={"market_views": []},
        model_used="fixture", created_at=now + timedelta(days=1),
    ))
    db_session.flush()
    for kind, expected in [("instrument", "301"), ("market", market.tweet_id)]:
        response = client.get("/api/tweets", headers=auth.headers(), params={
            "analysis_kind": kind, "limit": 1, "include_analysis": "true",
        })
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert [item["tweet_id"] for item in payload["items"]] == [expected]
