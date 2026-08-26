from datetime import datetime, timezone
from enum import StrEnum

from app.models.tweet import Tweet


class TweetStateTransitionError(ValueError):
    pass


class TweetProcessingState(StrEnum):
    MEDIA_PENDING = "media_pending"
    MEDIA_ARCHIVING = "media_archiving"
    MEDIA_ANALYSIS_PENDING = "media_analysis_ready"
    MEDIA_ANALYZING = "media_analyzing"
    ANALYSIS_PENDING = "pending"
    ANALYZING = "analyzing"
    RETRYING = "retrying"
    ANALYZED = "analyzed"
    FAILED = "failed"


MEDIA_STATES = {
    TweetProcessingState.MEDIA_PENDING,
    TweetProcessingState.MEDIA_ARCHIVING,
    TweetProcessingState.MEDIA_ANALYSIS_PENDING,
    TweetProcessingState.MEDIA_ANALYZING,
}

ANALYSIS_READY_STATES = {
    TweetProcessingState.ANALYSIS_PENDING,
    TweetProcessingState.RETRYING,
    TweetProcessingState.ANALYZING,
}

_ALLOWED_TRANSITIONS = {
    TweetProcessingState.MEDIA_PENDING: {
        TweetProcessingState.MEDIA_ARCHIVING,
        TweetProcessingState.MEDIA_ANALYZING,
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.FAILED,
    },
    TweetProcessingState.MEDIA_ARCHIVING: {
        TweetProcessingState.MEDIA_ANALYSIS_PENDING,
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.FAILED,
    },
    TweetProcessingState.MEDIA_ANALYSIS_PENDING: {
        TweetProcessingState.MEDIA_ARCHIVING,
        TweetProcessingState.MEDIA_ANALYZING,
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.FAILED,
    },
    TweetProcessingState.MEDIA_ANALYZING: {
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.FAILED,
    },
    TweetProcessingState.ANALYSIS_PENDING: {
        TweetProcessingState.MEDIA_ARCHIVING,
        TweetProcessingState.MEDIA_ANALYZING,
        TweetProcessingState.ANALYZING,
        TweetProcessingState.FAILED,
    },
    TweetProcessingState.ANALYZING: {
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.ANALYZED,
        TweetProcessingState.RETRYING,
        TweetProcessingState.FAILED,
    },
    TweetProcessingState.RETRYING: {
        TweetProcessingState.ANALYZING,
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.FAILED,
    },
    TweetProcessingState.ANALYZED: {
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.MEDIA_ARCHIVING,
        TweetProcessingState.MEDIA_ANALYZING,
    },
    TweetProcessingState.FAILED: {
        TweetProcessingState.MEDIA_ARCHIVING,
        TweetProcessingState.MEDIA_ANALYZING,
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.ANALYZING,
    },
}


def transition_tweet_state(
    tweet: Tweet,
    target: TweetProcessingState | str,
    *,
    failure_stage: str | None = None,
    error: str | None = None,
) -> Tweet:
    """Apply one explicit, observable processing-state transition."""
    target_state = TweetProcessingState(target)
    current_state = TweetProcessingState(tweet.status or TweetProcessingState.ANALYSIS_PENDING)
    if target_state != current_state and target_state not in _ALLOWED_TRANSITIONS[current_state]:
        raise TweetStateTransitionError(
            f"Invalid tweet state transition: {current_state.value} -> {target_state.value}"
        )

    tweet.status = target_state.value
    tweet.processing_updated_at = datetime.now(timezone.utc)
    if target_state in {TweetProcessingState.FAILED, TweetProcessingState.RETRYING}:
        tweet.failure_stage = failure_stage
        if error is not None:
            tweet.analysis_last_error = str(error)[:2000]
    elif target_state in {
        TweetProcessingState.ANALYSIS_PENDING,
        TweetProcessingState.ANALYZING,
        TweetProcessingState.ANALYZED,
    }:
        tweet.failure_stage = None
        tweet.analysis_last_error = None
    return tweet
