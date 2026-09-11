from app.services.prediction_contract_math import (
    parse_numeric_target,
    scale_observed_value,
    score_numeric_target,
)


def test_parses_range_and_financial_scale():
    percent = parse_numeric_target("70-100", "%")
    amount = parse_numeric_target("2000", "亿美元")

    assert (percent.low, percent.high, percent.is_percent) == (70.0, 100.0, True)
    assert amount.multiplier == 100_000_000.0
    assert scale_observed_value(215_938_000_000, amount) == 2159.38


def test_scores_numeric_threshold_without_llm_judgement():
    target = parse_numeric_target("60", "%")

    assert score_numeric_target(65, target, "gte")[:2] == ("correct", 1.0)
    assert score_numeric_target(58, target, "gte")[:2] == ("partial", 0.5)
    assert score_numeric_target(50, target, "gte")[:2] == ("incorrect", 0.0)
