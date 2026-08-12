from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from PIL import Image
from langchain_core.messages import HumanMessage

from app.agents.supervisor import supervisor_merge_node
from app.models import OutboxEvent, Tweet, TweetMediaAnalysis, TweetMediaAsset
from app.schemas.media_analysis import MediaImageObservation, TweetMediaAnalysisOutput
from app.schemas.tweet import TweetImportItem
from app.services import tweet_media_analysis_service, tweet_media_service
from app.services.tweet_service import import_tweets


def _png_bytes(width: int = 40, height: int = 20) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "red").save(output, format="PNG")
    return output.getvalue()


def _tweet(*, media_urls=None, status="pending") -> Tweet:
    return Tweet(
        tweet_id=f"tweet-{uuid4()}",
        author_handle="analyst",
        content="NVDA revenue accelerated",
        published_at=datetime.now(timezone.utc),
        media_urls=media_urls,
        status=status,
    )


def test_import_routes_text_and_media_tweets_to_distinct_outbox_flows(db_session):
    items = [
        TweetImportItem(
            tweet_id=f"text-{uuid4()}",
            author_handle="analyst",
            content="text only",
            published_at=datetime.now(timezone.utc),
        ),
        TweetImportItem(
            tweet_id=f"media-{uuid4()}",
            author_handle="analyst",
            content="see chart",
            published_at=datetime.now(timezone.utc),
            media_urls=[{"media_url": "https://pbs.twimg.com/media/chart.png"}],
        ),
    ]

    imported, skipped, tweet_ids = import_tweets(db_session, items, return_ids=True)

    assert (imported, skipped) == (2, 0)
    tweets = db_session.query(Tweet).filter(Tweet.id.in_(tweet_ids)).order_by(Tweet.tweet_id).all()
    assert {tweet.status for tweet in tweets} == {"pending", "media_pending"}
    events = db_session.query(OutboxEvent).all()
    event_types = [event.event_type for event in events]
    assert event_types.count("tweet.index_requested") == 2
    assert event_types.count("tweet.analysis_requested") == 1
    assert event_types.count("tweet.media_archive_requested") == 1


def test_archive_media_persists_asset_and_requests_vision(db_session, monkeypatch):
    tweet = _tweet(
        media_urls=[{"media_url": "https://pbs.twimg.com/media/chart.png", "media_status_id": "m1"}],
        status="media_pending",
    )
    db_session.add(tweet)
    db_session.commit()

    class Storage:
        backend = "local"

        def save(self, tweet_external_id, content_hash, content, extension, content_type):
            assert tweet_external_id == tweet.tweet_id
            assert extension == ".png"
            assert content_type == "image/png"
            return f"tweets/{tweet_external_id}/{content_hash}.png"

    monkeypatch.setattr(tweet_media_service, "TweetMediaStorage", Storage)
    monkeypatch.setattr(
        tweet_media_service,
        "_download_image",
        lambda url: (_png_bytes(), "image/png"),
    )

    result = tweet_media_service.archive_tweet_media(db_session, tweet.id)

    assert result["downloaded"] == 1
    asset = db_session.query(TweetMediaAsset).filter_by(tweet_id=tweet.id).one()
    assert asset.status == "downloaded"
    assert (asset.width, asset.height, asset.content_type) == (40, 20, "image/png")
    event = db_session.query(OutboxEvent).filter_by(event_type="tweet.media_analyze_requested").one()
    assert event.payload["tweet_id"] == str(tweet.id)


def test_vision_analyzes_all_archived_images_then_uses_cache(db_session, monkeypatch):
    tweet = _tweet(status="media_pending")
    db_session.add(tweet)
    db_session.flush()
    assets = [
        TweetMediaAsset(
            tweet_id=tweet.id,
            source_url=f"https://pbs.twimg.com/media/{index}.png",
            object_key=f"asset-{index}",
            content_hash=f"hash-{index}",
            storage_backend="local",
            status="downloaded",
        )
        for index in (1, 2)
    ]
    db_session.add_all(assets)
    db_session.commit()

    class Storage:
        def load(self, key):
            return _png_bytes()

    captured = []

    class StructuredVision:
        def with_structured_output(self, schema, *, include_raw=False):
            assert schema is TweetMediaAnalysisOutput
            assert include_raw is True
            return self

        def invoke(self, messages):
            captured.append(messages)
            parsed = TweetMediaAnalysisOutput(
                is_financial=True,
                combined_summary="Revenue chart confirms acceleration.",
                images=[
                    MediaImageObservation(
                        image_index=1,
                        summary="Revenue chart",
                        numeric_facts=["Revenue +25%"],
                        visual_evidence=["Bars rise year over year"],
                    )
                ],
                tickers=["nvda"],
                sentiment="bullish",
                text_image_consistency="consistent",
                confidence=0.91,
            )
            raw = type(
                "RawResponse",
                (),
                {
                    "usage_metadata": {
                        "input_tokens": 100,
                        "output_tokens": 25,
                        "total_tokens": 125,
                    },
                    "response_metadata": {},
                },
            )()
            return {"parsed": parsed, "raw": raw, "parsing_error": None}

    vision = StructuredVision()
    monkeypatch.setattr(tweet_media_analysis_service, "TweetMediaStorage", Storage)
    monkeypatch.setattr(tweet_media_analysis_service, "get_vision_llm", lambda: vision)

    completed = tweet_media_analysis_service.analyze_tweet_media(db_session, tweet.id)
    cached = tweet_media_analysis_service.analyze_tweet_media(db_session, tweet.id)

    assert completed["status"] == "completed"
    assert completed["image_count"] == 2
    assert cached["status"] == "cached"
    assert len(captured) == 1
    human = next(message for message in captured[0] if isinstance(message, HumanMessage))
    assert sum(part["type"] == "image_url" for part in human.content) == 2
    record = db_session.query(TweetMediaAnalysis).filter_by(tweet_id=tweet.id).one()
    assert record.result["tickers"] == ["NVDA"]
    assert record.result["asset_ids"] == [str(asset.id) for asset in assets]
    assert record.usage == {"input_tokens": 100, "output_tokens": 25, "total_tokens": 125}
    assert tweet.status == "pending"
    event = db_session.query(OutboxEvent).filter_by(event_type="tweet.analysis_requested").one()
    assert event.payload["tweet_id"] == str(tweet.id)


def test_supervisor_merges_visual_evidence_into_final_analysis():
    tweet_id = str(uuid4())
    result = supervisor_merge_node(
        {
            "tweets": [
                {
                    "id": tweet_id,
                    "media_context": {
                        "combined_summary": "Chart confirms margin expansion.",
                        "images": [
                            {
                                "visual_evidence": ["Gross margin trend rises"],
                                "numeric_facts": ["Margin reached 55%"],
                            }
                        ],
                        "text_image_consistency": "consistent",
                        "confidence": 0.93,
                    },
                }
            ],
            "classification": {},
            "partial_analyses": [{"tweet_id": tweet_id, "summary": "Margin improved"}],
            "risk_assessments": [],
        }
    )

    analysis = result["analyses"][0]
    assert analysis["media_summary"] == "Chart confirms margin expansion."
    assert analysis["media_evidence"] == ["Gross margin trend rises", "Margin reached 55%"]
    assert analysis["text_image_consistency"] == "consistent"
    assert analysis["media_confidence"] == 0.93
