from types import SimpleNamespace

import pytest

from app.models.analysis_job import AnalysisJob
from app.services.analysis_job_service import (
    AnalysisJobInvalidState,
    transition_analysis_job_state,
)
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


def test_media_to_analysis_state_path_is_explicit_and_observable():
    tweet = _tweet()

    transition_tweet_state(tweet, TweetProcessingState.MEDIA_ARCHIVING)
    transition_tweet_state(tweet, TweetProcessingState.MEDIA_ANALYSIS_PENDING)
    transition_tweet_state(tweet, TweetProcessingState.MEDIA_ANALYZING)
    transition_tweet_state(tweet, TweetProcessingState.ANALYSIS_PENDING)
    transition_tweet_state(tweet, TweetProcessingState.ANALYZING)
    transition_tweet_state(tweet, TweetProcessingState.ANALYZED)

    assert tweet.status == "analyzed"
    assert tweet.processing_updated_at is not None
    assert tweet.failure_stage is None


def test_failure_state_records_stage_and_reanalysis_clears_error():
    tweet = _tweet("analyzing")

    transition_tweet_state(
        tweet,
        TweetProcessingState.FAILED,
        failure_stage="text_analysis",
        error="model unavailable",
    )
    assert tweet.failure_stage == "text_analysis"
    assert tweet.analysis_last_error == "model unavailable"

    transition_tweet_state(tweet, TweetProcessingState.ANALYSIS_PENDING)
    assert tweet.failure_stage is None
    assert tweet.analysis_last_error is None


def test_invalid_tweet_state_jump_is_rejected():
    with pytest.raises(TweetStateTransitionError):
        transition_tweet_state(_tweet("pending"), TweetProcessingState.ANALYZED)


def test_completed_analysis_job_cannot_restart():
    job = AnalysisJob(status="completed", kind="tweet_analysis", request_payload={})

    with pytest.raises(AnalysisJobInvalidState):
        transition_analysis_job_state(job, "running")
