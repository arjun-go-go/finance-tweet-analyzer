from app.services import instrument_resolver
from app.services.instrument_resolver import (
    is_downstream_verified_ticker,
    resolve_analysis_tickers,
)


def _analysis(symbol="CRCL", *, asset_type="equity", market_hint="US"):
    return [{
        "tickers": [{
            "symbol": symbol,
            "original_name": symbol,
            "asset_type": asset_type,
            "market_hint": market_hint,
            "sentiment": "bullish",
            "horizon": "medium",
        }]
    }]


def _disable_unrelated_providers(monkeypatch):
    monkeypatch.setattr(instrument_resolver, "_akshare_match", lambda _symbol: None)
    monkeypatch.setattr(instrument_resolver, "_binance_match", lambda _symbol: None)


def test_authoritative_and_supporting_matches_share_one_contract(monkeypatch):
    _disable_unrelated_providers(monkeypatch)
    monkeypatch.setattr(
        instrument_resolver,
        "_sec_match",
        lambda symbol: {
            "symbol": symbol,
            "market": "US",
            "name": "Circle Internet Group, Inc.",
            "source": "sec_edgar",
            "external_ids": {"cik": "1876042"},
        },
    )
    monkeypatch.setattr(
        instrument_resolver,
        "_openfigi_matches",
        lambda _symbols: {
            "CRCL": {"ticker": "CRCL", "name": "CIRCLE INTERNET GROUP", "figi": "BBGTEST", "exchCode": "XNYS"}
        },
    )

    item = resolve_analysis_tickers(_analysis())[0]["tickers"][0]
    verification = item["verification"]

    assert verification["schema_version"] == "v1"
    assert verification["status"] == "verified"
    assert verification["authoritative_source"] == "sec_edgar"
    assert verification["sources"] == ["sec_edgar", "openfigi"]
    assert verification["downstream_eligible"] is True
    assert item["market"] == "US"
    assert item["external_ids"] == {"cik": "1876042", "figi": "BBGTEST"}
    assert is_downstream_verified_ticker(item) is True


def test_openfigi_only_match_is_ambiguous_not_tradable(monkeypatch):
    _disable_unrelated_providers(monkeypatch)
    monkeypatch.setattr(instrument_resolver, "_sec_match", lambda _symbol: None)
    monkeypatch.setattr(
        instrument_resolver,
        "_openfigi_matches",
        lambda _symbols: {
            "TEST": {"ticker": "TEST", "name": "Same Name Candidate", "figi": "BBGAMB", "exchCode": "XNAS"}
        },
    )

    item = resolve_analysis_tickers(_analysis("TEST"))[0]["tickers"][0]

    assert item["market"] == "US"
    assert item["exchange"] == "XNAS"
    assert item["verification"]["status"] == "ambiguous"
    assert item["verification"]["reason_code"] == "supporting_match_without_authority"
    assert item["tradable"] is False
    assert is_downstream_verified_ticker(item) is False


def test_invalid_candidate_remains_visible_with_structured_reason(monkeypatch):
    monkeypatch.setattr(instrument_resolver, "_openfigi_matches", lambda _symbols: {})

    analysis = resolve_analysis_tickers(_analysis("BAD SYMBOL"))[0]
    item = analysis["tickers"][0]

    assert item["verification"]["status"] == "invalid"
    assert item["verification"]["reason"] == "标的代码格式无效，无法调用公开数据源核验"
    assert isinstance(item["verification"]["reason"], str)
    assert analysis["rejected_tickers"] == [
        {"raw": "BAD SYMBOL", "reason": "invalid_symbol_format"}
    ]


def test_unsupported_asset_has_distinct_status(monkeypatch):
    monkeypatch.setattr(instrument_resolver, "_openfigi_matches", lambda _symbols: {})

    item = resolve_analysis_tickers(
        _analysis("DXY", asset_type="index", market_hint="US")
    )[0]["tickers"][0]

    assert item["verification"]["status"] == "unsupported"
    assert item["verification"]["reason_code"] == "unsupported_asset_type"


def test_provider_outage_is_not_reported_as_symbol_not_found(monkeypatch):
    monkeypatch.setattr(
        instrument_resolver,
        "_PROVIDER_AVAILABILITY",
        {"sec_edgar": False, "openfigi": False},
    )
    _disable_unrelated_providers(monkeypatch)
    monkeypatch.setattr(instrument_resolver, "_sec_match", lambda _symbol: None)
    monkeypatch.setattr(instrument_resolver, "_openfigi_matches", lambda _symbols: {})

    item = resolve_analysis_tickers(_analysis("OUTAGE"))[0]["tickers"][0]

    assert item["verification"]["status"] == "provider_unavailable"
    assert item["verification"]["reason_code"] == "all_providers_unavailable"
    assert all(
        evidence["status"] == "unavailable"
        for evidence in item["verification"]["evidence"]
    )


def test_nested_verification_is_authoritative_over_legacy_flat_fields():
    item = {
        "symbol": "CRCL",
        "market": "US",
        "asset_type": "equity",
        "validation_status": "verified",
        "tradable": True,
        "verification": {
            "status": "ambiguous",
            "downstream_eligible": False,
            "tradable": False,
        },
    }

    assert is_downstream_verified_ticker(item) is False
