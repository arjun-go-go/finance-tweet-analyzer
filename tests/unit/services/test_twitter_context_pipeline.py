import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.agents import analysis_agent
from app.schemas.signal import TweetAnalysis
from app.services.tweet_context_service import build_tweet_contexts
from app.services.twitter_service import _parse_tweet_entry, convert_tweets_to_import


CREATED_AT = "Thu Aug 13 12:00:00 +0000 2026"


def _tweet_object(tweet_id, handle, text, **legacy_fields):
    legacy = {
        "full_text": text,
        "created_at": CREATED_AT,
        "conversation_id_str": legacy_fields.pop("conversation_id_str", tweet_id),
        **legacy_fields,
    }
    return {
        "rest_id": tweet_id,
        "legacy": legacy,
        "core": {
            "user_results": {
                "result": {
                    "rest_id": f"user-{handle}",
                    "legacy": {"screen_name": handle, "name": handle.title()},
                }
            }
        },
        "views": {"count": "42"},
    }


def _entry(tweet):
    return {
        "entryId": f"tweet-{tweet['rest_id']}",
        "content": {"itemContent": {"tweet_results": {"result": tweet}}},
    }


def test_retweet_keeps_followed_blogger_and_captures_original_reference():
    original = _tweet_object("source-1", "source_author", "BTC will reach 150000")
    outer = _tweet_object(
        "outer-1",
        "followed_blogger",
        "RT @source_author: BTC will reach 150000",
        retweeted_status_result={"result": original},
    )

    parsed = _parse_tweet_entry(_entry(outer))
    imported = convert_tweets_to_import([parsed])[0]

    assert imported["tweet_id"] == "outer-1"
    assert imported["author_handle"] == "followed_blogger"
    assert imported["tweet_type"] == "retweet"
    assert imported["reposted_tweet_id"] == "source-1"
    assert imported["referenced_tweets"][0]["author_handle"] == "source_author"
    assert imported["referenced_tweets"][0]["content"] == "BTC will reach 150000"


def test_quote_and_reply_relationships_are_preserved():
    quoted = _tweet_object("quoted-1", "other", "Gold is breaking out")
    quote = _tweet_object(
        "quote-1",
        "alice",
        "I disagree with this target",
        quoted_status_id_str="quoted-1",
    )
    quote["quoted_status_result"] = {"result": quoted}
    reply = _tweet_object(
        "reply-1",
        "alice",
        "My invalidation level is 2300",
        conversation_id_str="thread-1",
        in_reply_to_status_id_str="thread-1",
    )

    parsed_quote = _parse_tweet_entry(_entry(quote))
    parsed_reply = _parse_tweet_entry(_entry(reply))

    assert parsed_quote["tweet_type"] == "quote"
    assert parsed_quote["quoted_tweet_id"] == "quoted-1"
    assert parsed_quote["referenced_tweets"][0]["type"] == "quoted"
    assert parsed_reply["tweet_type"] == "reply"
    assert parsed_reply["conversation_tweet_id"] == "thread-1"
    assert parsed_reply["in_reply_to_tweet_id"] == "thread-1"


class _ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.execute_count = 0

    def execute(self, _statement):
        self.execute_count += 1
        return _ScalarRows(self.rows)


def _stored_tweet(tweet_id, content, published_at, references=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tweet_id=tweet_id,
        tweet_type="reply" if tweet_id != "thread-1" else "original",
        author_handle="alice",
        content=content,
        published_at=published_at,
        conversation_tweet_id="thread-1",
        in_reply_to_tweet_id="thread-1" if tweet_id != "thread-1" else None,
        quoted_tweet_id=None,
        reposted_tweet_id=None,
        referenced_tweets=references or [],
    )


def test_context_builder_batches_thread_query_and_separates_references():
    first = _stored_tweet("thread-1", "Gold setup part one", datetime(2026, 8, 13, tzinfo=timezone.utc))
    second = _stored_tweet(
        "thread-2",
        "Gold setup part two",
        datetime(2026, 8, 13, 1, tzinfo=timezone.utc),
        references=[{"type": "quoted", "author_handle": "bob", "content": "Third party claim"}],
    )
    db = _FakeDb([first, second])

    contexts = build_tweet_contexts(db, [second])
    context = contexts[second.id]

    assert db.execute_count == 1
    assert [item["tweet_id"] for item in context["author_thread"]] == ["thread-1", "thread-2"]
    assert context["references"][0]["author_handle"] == "bob"
    assert "must not be attributed" in context["attribution_rule"]


def test_analysis_agent_receives_relationship_context(monkeypatch):
    captured = {}

    def fake_prompt(_name, **kwargs):
        captured.update(kwargs)
        return [{"role": "human", "content": "analyze"}]

    class FakeStructuredLlm:
        async def ainvoke(self, _messages):
            return TweetAnalysis(is_investment_relevant=False)

    monkeypatch.setattr(analysis_agent, "get_chat_prompt", fake_prompt)
    tweet = {
        "id": str(uuid.uuid4()),
        "author_handle": "alice",
        "content": "RT @bob: NVDA to 200",
        "conversation_context": {
            "tweet_type": "retweet",
            "references": [{"author_handle": "bob", "content": "NVDA to 200"}],
        },
    }

    result = asyncio.run(
        analysis_agent.analyze_tweet_with_llm(FakeStructuredLlm(), tweet, "")
    )

    assert result is not None
    assert '"tweet_type": "retweet"' in captured["conversation_context"]
    assert '"author_handle": "bob"' in captured["conversation_context"]
