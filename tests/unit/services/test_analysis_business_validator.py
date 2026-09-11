from app.services.analysis_business_validator import (
    normalize_before_resolution,
    validate_after_resolution,
)


TWEET_TEXT = """我从没假设过不加息，我们也不应该假设不加息。
AI 利好 EPS，模型公司上市吸血和加息利空 PE，PE 和 EPS 扳手腕。
所以无论是 SOX 也好，还是 MU 也好，期待 PE 回到以前或者扩张都是不合理的。"""


def _claim(symbol: str, *, direction: str = "bearish") -> dict:
    return {
        "instrument": {
            "symbol": symbol,
            "original_name": symbol,
            "asset_type": "equity",
            "market_hint": "US",
        },
        "direction": direction,
        "horizon": "unknown",
        "claim_type": "opinion",
        "opinion_source": "author",
        "sponsor_relation": "none",
        "thesis": f"{symbol} 的 PE 扩张不合理",
        "evidence": [
            "无论是 SOX 也好，还是 MU 也好，期待 PE 扩张都是不合理的",
            "AI 利好 EPS，模型公司上市吸血和加息利空 PE",
        ],
        "forecast": {"prediction_type": "none"},
        "confidence": 0.85,
    }


def test_business_validation_corrects_sox_and_mu_case():
    analysis = {
        "claims": [_claim("SOX"), _claim("MU")],
        "market_views": [
            {
                "market": "US",
                "benchmark": "",
                "impact": "mixed",
                "horizon": "unknown",
                "topic": "rates",
                "thesis": "AI 支持 EPS，但加息和资金分流压制 PE",
                "evidence": ["AI 利好 EPS，模型公司上市吸血和加息利空 PE"],
                "opinion_source": "author",
                "confidence": 0.9,
            }
        ],
        "risk_context": [
            {
                "category": "market",
                "description": "加息和通胀令估值承压",
                "severity": "medium",
                "urgency": "long_term",
                "related_tickers": ["SOX", "MICRON"],
            }
        ],
    }

    normalized = normalize_before_resolution(analysis, source_text=TWEET_TEXT)

    assert [claim["instrument"]["symbol"] for claim in normalized["claims"]] == ["MU"]
    assert normalized["claims"][0]["direction"] == "none"
    assert any(
        view["benchmark"] == "SOX" and view["impact"] == "mixed"
        for view in normalized["market_views"]
    )

    normalized["claims"][0]["instrument"].update(
        {
            "market": "US",
            "exchange": "Nasdaq",
            "resolved_name": "MICRON TECHNOLOGY INC",
            "verification": {
                "status": "verified",
                "authoritative_source": "sec_edgar",
                "downstream_eligible": True,
                "tradable": True,
            },
        }
    )
    validated = validate_after_resolution(normalized, source_text=TWEET_TEXT)
    claim = validated["claims"][0]

    assert validated["risk_context"][0]["related_tickers"] == ["SOX", "MU"]
    assert claim["risk_level"] == "medium"
    assert claim["risks"][0]["description"] == "加息和通胀令估值承压"
    assert validated["business_validation"]["status"] == "corrected"
    assert {
        correction["code"]
        for correction in validated["business_validation"]["corrections"]
    } >= {
        "benchmark_moved_to_market_view",
        "direction_evidence_insufficient",
        "risk_symbol_canonicalized",
    }


def test_explicit_target_direction_is_preserved():
    analysis = {
        "claims": [
            {
                **_claim("MU", direction="bullish"),
                "thesis": "博主明确看多 MU",
                "evidence": ["我明确看多 MU，后续可能继续上涨"],
            }
        ],
        "market_views": [],
    }

    normalized = normalize_before_resolution(
        analysis,
        source_text="我明确看多 MU，后续可能继续上涨。",
    )

    assert normalized["claims"][0]["direction"] == "bullish"
    assert normalized["business_validation"]["status"] == "accepted"


def test_cross_market_identity_is_not_exposed_as_confirmed_name():
    analysis = {
        "claims": [
            {
                **_claim("TEST"),
                "direction": "none",
                "instrument": {
                    "symbol": "TEST",
                    "original_name": "TEST",
                    "asset_type": "equity",
                    "market_hint": "US",
                    "market": "US",
                    "exchange": "AU",
                    "resolved_name": "UNRELATED AUSTRALIAN COMPANY",
                    "external_ids": {"figi": "BBGTEST"},
                    "verification": {
                        "status": "ambiguous",
                        "authoritative_source": None,
                        "downstream_eligible": False,
                        "tradable": False,
                    },
                },
            }
        ],
        "market_views": [],
    }

    validated = validate_after_resolution(analysis, source_text="TEST")
    instrument = validated["claims"][0]["instrument"]

    assert instrument["resolved_name"] == ""
    assert instrument["verification"]["reason_code"] == "cross_market_symbol_collision"
    assert instrument["verification"]["downstream_eligible"] is False
    assert instrument["rejected_identity_candidate"]["exchange"] == "AU"
