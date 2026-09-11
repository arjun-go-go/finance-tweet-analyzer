from app.services.instrument_claim_aggregation_service import classify_consensus


def test_single_bearish_blogger_is_not_strong_consensus():
    consensus, score = classify_consensus(
        bullish=0,
        bearish=1,
        neutral=0,
        independent_bloggers=1,
    )

    assert consensus == "sell"
    assert score == 0.0


def test_three_independent_bearish_bloggers_can_form_strong_consensus():
    consensus, _score = classify_consensus(
        bullish=0,
        bearish=3,
        neutral=0,
        independent_bloggers=3,
    )

    assert consensus == "strong_sell"
