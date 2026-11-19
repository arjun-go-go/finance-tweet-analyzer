from copy import deepcopy

from app.agents.model_review_agent import critical_conflicts


def test_forecast_disagreement_compares_attribution_and_numeric_target():
    claim = {
        "instrument": {"symbol": "NVDA", "asset_type": "equity", "market_hint": "US"},
        "direction": "bullish", "opinion_source": "author", "claim_type": "prediction",
        "forecast": {
            "prediction_type": "price_target", "forecast_source": "author",
            "target_value": "120", "target_unit": "USD", "target_operator": "gte",
        },
    }
    primary = {"claims": [claim]}
    review = deepcopy(primary)
    review["claims"][0]["forecast"]["target_value"] = "120.00"
    review["claims"].append(deepcopy(review["claims"][0]))
    assert not critical_conflicts(primary, review)
    review["claims"][0]["forecast"]["target_value"] = "121"
    assert critical_conflicts(primary, review) == ["instrument_claims"]
    review = deepcopy(primary)
    review["claims"][0]["forecast"]["forecast_source"] = "quoted"
    assert critical_conflicts(primary, review) == ["instrument_claims"]


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
