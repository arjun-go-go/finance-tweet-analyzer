import pytest
from types import SimpleNamespace

from app.services.intelligence_projection_service import (
    evaluate_claim_intelligence_eligibility,
    evaluate_intelligence_eligibility,
)


@pytest.mark.parametrize(
    ("result", "tweet_type", "expected"),
    [
        (
            {
                "is_investment_relevant": True,
                "is_sponsored": False,
            },
            "original",
            (True, "eligible"),
        ),
        (
            {
                "is_investment_relevant": True,
                "is_sponsored": False,
            },
            "retweet",
            (True, "eligible"),
        ),
        (
            {
                "is_investment_relevant": True,
                "is_sponsored": True,
            },
            "original",
            (True, "eligible"),
        ),
        (
            {
                "is_investment_relevant": False,
                "is_sponsored": False,
            },
            "original",
            (False, "not_investment_relevant"),
        ),
    ],
)
def test_intelligence_projection_eligibility(result, tweet_type, expected):
    assert evaluate_intelligence_eligibility(result, tweet_type=tweet_type) == expected


def _claim(**overrides):
    data = {
        "downstream_eligible": True,
        "claim_type": "prediction",
        "opinion_source": "author",
        "thesis": "未来三个月可能继续上涨",
        "evidence": ["未来三个月可能继续上涨"],
        "media_evidence": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_quoted_prediction_is_not_projected_as_author_opinion():
    assert evaluate_claim_intelligence_eligibility(
        _claim(opinion_source="quoted"),
        tweet_type="quote",
    ) == (False, "opinion_not_from_author")


def test_third_party_news_can_be_projected_without_becoming_author_opinion():
    assert evaluate_claim_intelligence_eligibility(
        _claim(claim_type="news", opinion_source="third_party"),
        tweet_type="retweet",
    ) == (True, "eligible")


def test_only_directly_related_commercial_claim_is_excluded():
    assert evaluate_claim_intelligence_eligibility(
        _claim(sponsor_relation="direct"),
        tweet_type="original",
    ) == (False, "sponsor_related")
    assert evaluate_claim_intelligence_eligibility(
        _claim(sponsor_relation="unrelated"),
        tweet_type="original",
    ) == (True, "eligible")
