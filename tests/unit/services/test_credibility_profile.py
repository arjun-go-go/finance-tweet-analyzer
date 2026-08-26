import pytest

from app.services.credibility import score_profile


@pytest.mark.parametrize(
    ("correct_sum", "total", "status", "confidence"),
    [
        (0.0, 0, "no_data", 0.0),
        (1.0, 2, "early", 0.1),
        (4.0, 8, "developing", 0.4),
        (12.0, 20, "established", 1.0),
    ],
)
def test_score_profile_exposes_sample_maturity(correct_sum, total, status, confidence):
    result = score_profile(correct_sum, total)

    assert result["score_status"] == status
    assert result["sample_confidence"] == confidence
    assert result["verified_samples"] == total


def test_unrated_profile_keeps_neutral_prior_internal_but_has_no_accuracy():
    result = score_profile(0.0, 0)

    assert result["credibility_score"] == 50.0
    assert result["raw_accuracy"] is None
    assert result["score_label"] == "暂无已验证预测"
