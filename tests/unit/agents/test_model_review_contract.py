from app.agents.model_review_agent import critical_conflicts


def test_claim_asset_type_difference_requires_arbitration():
    primary = {
        "is_investment_relevant": True,
        "claims": [
            {
                "instrument": {
                    "symbol": "SOX",
                    "asset_type": "index",
                    "market_hint": "US",
                },
                "direction": "none",
                "claim_type": "opinion",
                "opinion_source": "author",
            }
        ],
    }
    review = {
        "is_investment_relevant": True,
        "claims": [
            {
                "instrument": {
                    "symbol": "SOX",
                    "asset_type": "equity",
                    "market_hint": "US",
                },
                "direction": "none",
                "claim_type": "opinion",
                "opinion_source": "author",
            }
        ],
    }

    assert "instrument_claims" in critical_conflicts(primary, review)


def test_market_benchmark_difference_requires_arbitration():
    primary = {
        "is_investment_relevant": True,
        "market_views": [
            {
                "market": "US",
                "benchmark": "SOX",
                "impact": "mixed",
                "opinion_source": "author",
            }
        ],
    }
    review = {
        "is_investment_relevant": True,
        "market_views": [
            {
                "market": "US",
                "benchmark": "",
                "impact": "mixed",
                "opinion_source": "author",
            }
        ],
    }

    assert "market_views" in critical_conflicts(primary, review)
