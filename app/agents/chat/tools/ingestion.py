from __future__ import annotations

from app.core.resilience import resilient_tool


@resilient_tool(
    retries=3,
    backoff_base=2.0,
    circuit_name="twitter_api",
    failure_threshold=5,
    recovery_timeout=120.0,
    fallback_message="Twitter API 暂时不可用，请稍后重试。",
    retryable_exceptions=(ConnectionError, TimeoutError, OSError),
)
def fetch_profile_impl(handle: str) -> dict | None:
    from app.services.twitter_service import fetch_user_profile

    return fetch_user_profile(handle)


@resilient_tool(
    retries=3,
    backoff_base=2.0,
    circuit_name="twitter_api",
    failure_threshold=5,
    recovery_timeout=120.0,
    fallback_message="Twitter API 暂时不可用，请稍后重试。",
    retryable_exceptions=(ConnectionError, TimeoutError, OSError),
)
def fetch_tweets_impl(user_id: str, max_pages: int) -> list:
    from app.services.twitter_service import fetch_user_tweets

    return fetch_user_tweets(user_id, max_pages=max_pages)
