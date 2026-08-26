from types import SimpleNamespace

import pytest

from app.services.tweet_state_service import (
    TweetProcessingState,
    TweetStateTransitionError,
    transition_tweet_state,
)


def _tweet(status="media_pending"):
    return SimpleNamespace(
        status=status,
        processing_updated_at=None,
        failure_stage=None,
        analysis_last_error=None,
    )


def test_media_to_analysis_state_path_is_explicit():
    tweet = _tweet()
    for state in (
        TweetProcessingState.MEDIA_ARCHIVING,
        TweetProcessingState.MEDIA_ANALYSIS_PENDING,
        TweetProcessingState.MEDIA_ANALYZING,
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.ANALYZING,
        TweetProcessingState.ANALYZED,
    ):
        transition_tweet_state(tweet, state)
    assert tweet.status == "analyzed"
    assert tweet.processing_updated_at is not None


def test_failure_can_return_to_analysis_pending():
    tweet = _tweet("analyzing")
    transition_tweet_state(
        tweet,
        TweetProcessingState.FAILED,
        failure_stage="text_analysis",
        error="model unavailable",
    )
    transition_tweet_state(tweet, TweetProcessingState.ANALYSIS_PENDING)
    assert tweet.failure_stage is None
    assert tweet.analysis_last_error is None


def test_invalid_tweet_state_jump_is_rejected():
    with pytest.raises(TweetStateTransitionError):
        transition_tweet_state(_tweet("pending"), TweetProcessingState.ANALYZED)
