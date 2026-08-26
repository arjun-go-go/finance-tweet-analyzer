import pytest

from app.services.intelligence_projection_service import evaluate_intelligence_eligibility


@pytest.mark.parametrize(
    ("result", "tweet_type", "expected"),
    [
        (
            {
                "is_investment_relevant": True,
                "statement_type": "opinion",
                "opinion_source": "author",
                "is_sponsored": False,
            },
            "original",
            (True, "eligible"),
        ),
        (
            {
                "is_investment_relevant": True,
                "statement_type": "news_relay",
                "opinion_source": "third_party",
                "is_sponsored": False,
            },
            "retweet",
            (True, "eligible"),
        ),
        (
            {
                "is_investment_relevant": True,
                "statement_type": "prediction",
                "opinion_source": "quoted",
                "is_sponsored": False,
            },
            "quote",
            (False, "opinion_not_from_author"),
        ),
        (
            {
                "is_investment_relevant": True,
                "statement_type": "opinion",
                "opinion_source": "author",
                "is_sponsored": True,
            },
            "original",
            (False, "sponsored_content"),
        ),
        (
            {
                "is_investment_relevant": False,
                "statement_type": "non_investment",
                "opinion_source": "unclear",
                "is_sponsored": False,
            },
            "original",
            (False, "not_investment_relevant"),
        ),
    ],
)
def test_intelligence_projection_eligibility(result, tweet_type, expected):
    assert evaluate_intelligence_eligibility(result, tweet_type=tweet_type) == expected
