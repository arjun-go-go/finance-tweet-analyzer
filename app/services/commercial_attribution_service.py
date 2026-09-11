from __future__ import annotations

import re


_COMMERCIAL_CUE_RE = re.compile(
    r"(?:(?:本条|本文|本内容|此内容|本篇|本期)\s*"
    r"(?:由|获)?\s*@?[A-Za-z0-9_\-\u4e00-\u9fff]{1,48}\s*"
    r"(?:赞助|支持|合作)"
    r"|(?:由|获)\s*@?[A-Za-z0-9_\-\u4e00-\u9fff]{1,48}\s*"
    r"(?:赞助|商业支持)"
    r"|@[A-Za-z0-9_]{1,64}\s*(?:赞助|推广合作)"
    r"|(?:广告内容|商业推广|推广内容))",
    re.IGNORECASE,
)
_HANDLE_RE = re.compile(r"@([A-Za-z0-9_]{1,64})")
_SPONSOR_NAME_RE = re.compile(
    r"(?:由|获)\s*(?P<name>@?[A-Za-z0-9_\-\u4e00-\u9fff]{1,48})\s*"
    r"(?:赞助|支持|合作)",
    re.IGNORECASE,
)
_VALID_RELATIONS = {"none", "unrelated", "direct", "unclear"}


def detect_commercial_disclosure(content: str) -> dict:
    """Find an explicit commercial disclosure and expose a safe editorial hint."""
    source = str(content or "")
    matches = list(_COMMERCIAL_CUE_RE.finditer(source))
    if not matches:
        return {
            "has_commercial_content": False,
            "editorial_text": source,
            "disclosure_text": "",
            "placement": "none",
            "sponsor_name": "",
            "sponsor_handle": "",
        }

    marker = matches[-1]
    prefix = source[:marker.start()].rstrip()
    is_footer = marker.start() >= max(0, int(len(source) * 0.40)) or bool(
        prefix and prefix[-1] in "。！？!?\n"
    )
    disclosure_text = source[marker.start():].strip() if is_footer else marker.group(0).strip()
    editorial_text = source[:marker.start()].strip() if is_footer else source
    handle_match = _HANDLE_RE.search(disclosure_text)
    name_match = _SPONSOR_NAME_RE.search(disclosure_text)
    sponsor_name = name_match.group("name").lstrip("@") if name_match else ""
    sponsor_handle = f"@{handle_match.group(1)}" if handle_match else ""
    return {
        "has_commercial_content": True,
        "editorial_text": editorial_text,
        "disclosure_text": disclosure_text[:1000],
        "placement": "footer" if is_footer else "body",
        "sponsor_name": sponsor_name,
        "sponsor_handle": sponsor_handle,
    }


def normalize_commercial_attribution(analysis: dict, source_text: str) -> dict:
    """Merge deterministic disclosure evidence with model claim attribution."""
    payload = dict(analysis)
    detected = detect_commercial_disclosure(source_text)
    raw_disclosure = payload.get("commercial_disclosure")
    disclosure = dict(raw_disclosure) if isinstance(raw_disclosure, dict) else {}
    has_commercial_content = bool(
        payload.get("is_sponsored")
        or disclosure.get("has_commercial_content")
        or detected["has_commercial_content"]
    )

    disclosure["has_commercial_content"] = has_commercial_content
    for field in (
        "sponsor_name",
        "sponsor_handle",
        "disclosure_text",
        "placement",
    ):
        if not disclosure.get(field) and detected.get(field):
            disclosure[field] = detected[field]
    if not has_commercial_content:
        disclosure["placement"] = "none"

    claims: list[dict] = []
    for raw_claim in payload.get("claims") or []:
        if not isinstance(raw_claim, dict):
            continue
        claim = dict(raw_claim)
        relation = str(claim.get("sponsor_relation") or "none").lower()
        if not has_commercial_content:
            relation = "none"
        elif relation not in _VALID_RELATIONS or relation == "none":
            relation = "unclear"
        claim["sponsor_relation"] = relation
        claims.append(claim)

    payload["is_sponsored"] = has_commercial_content
    payload["commercial_disclosure"] = disclosure
    payload["claims"] = claims
    return payload
