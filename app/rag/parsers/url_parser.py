import ipaddress
import socket
from urllib.parse import urlparse

from curl_cffi import requests as cffi_requests
from gne import GeneralNewsExtractor
from lxml.html import fromstring as lxml_fromstring

from app.core.config import settings
from app.rag.parsers.base import ParsedDocument, ParserError
from app.rag.parsers.desc_extractor import (
    desc_extractor,
    time_extractor,
    author_extractor,
    _normalize_time,
)


def _is_private_ip(host: str) -> bool:
    try:
        addrs = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for entry in addrs:
        ip_str = entry[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def _extract_meta(html: str) -> dict:
    """Extract rich metadata: author (name only), publish_time (ISO 8601),
    keywords, description, site_name."""
    try:
        element = lxml_fromstring(html)
    except Exception:
        return {}
    meta = {}
    author = author_extractor.extractor(element)
    if author:
        meta["author"] = author
    raw_time = time_extractor.extractor(element)
    if raw_time:
        iso_time = _normalize_time(raw_time)
        if iso_time:
            meta["publish_time"] = iso_time
    keywords = desc_extractor.extract_desc("keywords", element)
    if keywords:
        meta["keywords"] = keywords
    description = desc_extractor.extract_desc("description", element)
    if description:
        meta["description"] = description
    site_name = desc_extractor.extract_site_name(element)
    if site_name:
        meta["site_name"] = site_name
    return meta


def fetch_url(
    url: str,
    *,
    blocked_hosts: list[str],
    timeout: int,
) -> ParsedDocument:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ParserError(f"Only http/https URLs are allowed, got scheme {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ParserError("URL is missing a host")
    if host in {h.lower() for h in blocked_hosts}:
        raise ParserError(f"Host {host} is in the blocklist")
    if _is_private_ip(host):
        raise ParserError(f"Host {host} resolves to a private/internal address")

    proxies = {"http": settings.http_proxy, "https": settings.http_proxy} if settings.http_proxy else None

    try:
        resp = cffi_requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            impersonate="chrome",
            proxies=proxies,
        )
        resp.raise_for_status()
    except cffi_requests.RequestsError as e:
        raise ParserError(f"Failed to fetch URL: {e}") from e

    final_url = resp.url if isinstance(resp.url, str) else str(resp.url)
    final_host = (urlparse(final_url).hostname or "").lower()
    if final_host and final_host != host:
        if final_host in {h.lower() for h in blocked_hosts} or _is_private_ip(final_host):
            raise ParserError(f"Redirected to disallowed host {final_host}")

    html = resp.text
    gne = GeneralNewsExtractor()
    result = gne.extract(html, with_body_html=False)
    print(result)
    text = result.get("content", "").strip()
    if not text:
        raise ParserError("URL extraction returned empty content")

    # GNE result 优先，自定义提取器补缺
    meta = _extract_meta(html)

    metadata = {"source_uri": final_url}

    # title: GNE > custom
    metadata["title"] = result.get("title") or meta.get("title", "")

    # author: GNE > custom（GNE 无 author 字段，直接用 custom）
    metadata["author"] = result.get("author") or meta.get("author", "")

    # publish_time: GNE > custom，统一转 ISO 8601
    raw_time = result.get("publish_time") or meta.get("publish_time", "")
    metadata["publish_time"] = _normalize_time(raw_time) if raw_time else ""

    # keywords: GNE meta.keywords > custom
    gne_meta = result.get("meta") or {}
    metadata["keywords"] = gne_meta.get("keywords") or meta.get("keywords", "")

    # description: GNE meta.description / og:description > custom
    metadata["description"] = (
        gne_meta.get("description")
        or gne_meta.get("og:description")
        or meta.get("description", "")
    )
    # site_name: GNE 无此字段，用 custom
    metadata["site_name"] = meta.get("site_name", "")
    print(metadata)

    return ParsedDocument(text=text, metadata=metadata)


if __name__ == '__main__':
      url_blocked_hosts: list[str] = [
      "localhost", "127.0.0.1", "0.0.0.0", "::1",
      "169.254.169.254",
       ]
      fetch_url("https://www.voachinese.com/a/senate-panel-advances-ndaa-authorizing-taiwan-war-reserve-stockpile-20260611/8159790.html",blocked_hosts=url_blocked_hosts,timeout=20 )