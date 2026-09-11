from app.services.commercial_attribution_service import (
    detect_commercial_disclosure,
    normalize_commercial_attribution,
)


def test_platform_footer_is_disclosed_without_excluding_unrelated_nvda_claim():
    content = (
        "英伟达AI需求和产品确定性强于市场预期，但资本占用和信用风险上升。"
        "此内容由@BITstocks_CN赞助，买美股上BIT。"
    )

    disclosure = detect_commercial_disclosure(content)
    result = normalize_commercial_attribution(
        {
            "claims": [
                {
                    "instrument": {"symbol": "NVDA"},
                    "sponsor_relation": "unrelated",
                }
            ]
        },
        content,
    )

    assert disclosure["placement"] == "footer"
    assert "英伟达AI需求" in disclosure["editorial_text"]
    assert disclosure["sponsor_handle"] == "@BITstocks_CN"
    assert result["is_sponsored"] is True
    assert result["claims"][0]["sponsor_relation"] == "unrelated"


def test_normal_company_cooperation_is_not_treated_as_an_ad():
    disclosure = detect_commercial_disclosure("英伟达与微软扩大AI基础设施合作。")

    assert disclosure["has_commercial_content"] is False
