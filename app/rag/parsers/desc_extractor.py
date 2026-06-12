import json
import re
from datetime import datetime

from lxml.html import HtmlElement, fromstring as lxml_fromstring

# ── description / keywords / site_name ────────────────────────

DESC_TIME_META = [
    '//meta[starts-with(@property, "og:description")]/@content',
    '//meta[starts-with(@name, "description")]/@content',
]

SITE_NAME_META = [
    "//meta[starts-with(@property, 'og:site_name')]/@content",
]

KEYWORDS_TAG_META = [
    "//meta[starts-with(@name, 'keywords')]/@content",
    "//meta[starts-with(@name, 'parsely-tags')]/@content",
    "//meta[starts-with(@name, 'news_keywords')]/@content",
    "//meta[starts-with(@property, 'article:tag')]/@content",
]


class DescExtractor:
    def extract_by_xpath(self, element, title_xpath):
        if title_xpath:
            title_list = element.xpath(title_xpath)
            if title_list:
                return title_list[0]
        return ""

    def extract_desc_from_meta(self, tag, element: HtmlElement) -> str:
        if tag == "keywords":
            for xpath in KEYWORDS_TAG_META:
                title = element.xpath(xpath)
                if title:
                    return ",".join(title).strip(",")
            return ""
        if tag == "description":
            for xpath in DESC_TIME_META:
                title = element.xpath(xpath)
                if title:
                    return ",".join(title).strip(",")
            return ""
        return ""

    def extract_sitename_from_meta(self, element: HtmlElement) -> str:
        for xpath in SITE_NAME_META:
            title = element.xpath(xpath)
            if title:
                return "".join(title)
        return ""

    def extract_desc(self, tag, element: HtmlElement, title_xpath: str = "") -> str:
        desc = self.extract_by_xpath(element, title_xpath) or self.extract_desc_from_meta(tag, element)
        return desc.strip()

    def extract_site_name(self, element: HtmlElement, title_xpath: str = "") -> str:
        site_name = self.extract_by_xpath(element, title_xpath) or self.extract_sitename_from_meta(element)
        return site_name.strip()


desc_extractor = DescExtractor()

# ── publish time ───────────────────────────────────────────────

PUBLISH_TIME_META = [
    '//meta[starts-with(@property, "rnews:datePublished")]/@content',
    '//meta[starts-with(@property, "article:published_time")]/@content',
    '//meta[starts-with(@property, "og:published_time")]/@content',
    '//meta[starts-with(@property, "og:article:published_time")]/@content',
    '//meta[starts-with(@property, "og:release_date")]/@content',
    '//meta[starts-with(@itemprop, "datePublished")]/@content',
    '//meta[starts-with(@itemprop, "dateUpdate")]/@content',
    '//meta[starts-with(@itemprop, "dateModified")]/@content',
    '//meta[starts-with(@name, "article:published_time")]/@content',
    '//meta[starts-with(@name, "OriginalPublicationDate")]/@content',
    '//meta[starts-with(@name, "article_date_original")]/@content',
    '//meta[starts-with(@name, "og:time")]/@content',
    '//meta[starts-with(@name, "apub:time")]/@content',
    '//meta[starts-with(@name, "publication_date")]/@content',
    '//meta[starts-with(@name, "publisheddate")]/@content',
    '//meta[starts-with(@name, "sailthru.date")]/@content',
    '//meta[starts-with(@name, "PublishDate")]/@content',
    '//meta[starts-with(@name, "publishdate")]/@content',
    '//meta[starts-with(@name, "PubDate")]/@content',
    '//meta[starts-with(@name, "pubtime")]/@content',
    '//meta[starts-with(@name, "dateLastPubbed")]/@content',
    '//meta[starts-with(@name, "parsely-pub-date")]/@content',
    '//meta[starts-with(@name, "_pubtime")]/@content',
    '//meta[starts-with(@pubdate, "pubdate")]/@content',
    '//meta[starts-with(@property, "og:updated_time")]/@content',
    '//meta[starts-with(@property, "article:modified_time")]/@content',
    '//time[contains(@class,"published")]/@datetime',
    '//time[contains(@class,"date")]/@datetime',
    '//time[contains(@data-testid,"timestamp")]/@datetime',
    '//time[contains(@itemprop,"datePublished")]/@datetime',
    '//time/@datetime',
]

_DATETIME_PATTERN = [
    re.compile(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*?[0-1]?[0-9]:[0-5]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*?[2][0-3]:[0-5]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*?[0-1]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*?[2][0-3]:[0-5]?[0-9])"),
    re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})"),
    re.compile(r"(\d{4}年\d{1,2}月\d{1,2}日\s*?[0-1]?[0-9]:[0-5]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{4}年\d{1,2}月\d{1,2}日\s*?[2][0-3]:[0-5]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{4}年\d{1,2}月\d{1,2}日\s*?[0-1]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{4}年\d{1,2}月\d{1,2}日\s*?[2][0-3]:[0-5]?[0-9])"),
    re.compile(r"(\d{4}年\d{1,2}月\d{1,2}日)"),
    re.compile(r"(\d{2}年\d{1,2}月\d{1,2}日\s*?[0-1]?[0-9]:[0-5]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{2}年\d{1,2}月\d{1,2}日\s*?[2][0-3]:[0-5]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{2}年\d{1,2}月\d{1,2}日\s*?[0-1]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{2}年\d{1,2}月\d{1,2}日)"),
    re.compile(r"(\d{1,2}月\d{1,2}日\s*?[0-1]?[0-9]:[0-5]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{1,2}月\d{1,2}日\s*?[0-1]?[0-9]:[0-5]?[0-9])"),
    re.compile(r"(\d{1,2}月\d{1,2}日)"),
    re.compile(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"),
    # 2-digit year patterns (ambiguous, skip for safety)
]

_DATE_SEP_RE = re.compile(r"[-/.]")

# ── time normalization → ISO 8601 ──────────────────────────────
# Vector DB metadata filtering needs a consistent format.
# Output: YYYY-MM-DDTHH:MM:SSZ  (UTC) or YYYY-MM-DD (date-only)

_ZH_REPLACE = re.compile(r"[年月]")
_ZH_DAY = re.compile(r"日")


def _normalize_time(raw: str) -> str:
    """Convert various date/time formats to ISO 8601 for vector DB filtering."""
    if not raw:
        return ""
    s = raw.strip()
    # Already ISO-ish with timezone: 2026-06-11T08:30:00+08:00
    if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", s):
        try:
            dt = datetime.fromisoformat(s)
            return dt.astimezone(tz=None).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return s[:10]
    # Chinese format: 2026年6月11日 08:30:00
    if "年" in s:
        s2 = _ZH_REPLACE.sub("-", s)
        s2 = _ZH_DAY.sub("", s2).strip()
        # 26年 → assume 2000s
        if s2.startswith(("26", "25", "24", "23", "22", "21", "20", "19")):
            if len(s2.split("-")[0]) == 2:
                s2 = "20" + s2
        try:
            dt = datetime.strptime(s2.strip(), "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            try:
                dt = datetime.strptime(s2.strip(), "%Y-%m-%d %H:%M")
                return dt.strftime("%Y-%m-%dT%H:%MZ")
            except ValueError:
                try:
                    dt = datetime.strptime(s2.strip(), "%Y-%m-%d")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        return ""
    # Slash/dot sep: 2026/06/11 08:30:00  or  2026.06.11
    if re.match(r"\d{4}[/.]\d{1,2}[/.]\d{1,2}", s):
        s2 = _DATE_SEP_RE.sub("-", s.split()[0])
        time_part = s.split()[1] if len(s.split()) > 1 else ""
        try:
            date_str = s2
            if time_part:
                dt = datetime.strptime(f"{date_str} {time_part}", "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            try:
                dt = datetime.strptime(f"{date_str} {time_part}", "%Y-%m-%d %H:%M")
                return dt.strftime("%Y-%m-%dT%H:%MZ")
            except ValueError:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        return ""
    # Bare ISO date: 2026-06-11
    if re.match(r"\d{4}-\d{2}-\d{2}$", s):
        return s
    # Month-day only (no year): 6月11日 — not reliable for filtering, skip
    if re.match(r"\d{1,2}月\d{1,2}日", s) and "年" not in s:
        return ""
    return ""


class TimeExtractor:
    """Extract publish time from HTML — meta → json-ld → <time> tag → text regex.
    No LLM calls. Returns raw string; caller normalizes via _normalize_time."""

    def extractor(self, element: HtmlElement, publish_time_xpath: str = "") -> str:
        return ( self.extract_from_meta(element)
            or self.extract_from_json_ld(element)
            or self.extract_from_time_tag(element)
            or self.extract_from_text(element)
        )

    def extract_from_user_xpath(self, publish_time_xpath: str, element: HtmlElement) -> str:
        if publish_time_xpath:
            result = element.xpath(publish_time_xpath)
            if result:
                return result[0]
        return ""

    def extract_from_meta(self, element: HtmlElement) -> str:
        for xpath in PUBLISH_TIME_META:
            result = element.xpath(xpath)
            if result:
                return result[0]
        return ""

    def extract_from_json_ld(self, element: HtmlElement) -> str:
        scripts = element.xpath('//script[@type="application/ld+json"]/text()')
        for script_text in scripts:
            try:
                data = json.loads(script_text.strip())
                if isinstance(data, list):
                    data = data[0]
                if not isinstance(data, dict):
                    continue
                for key in ("datePublished", "dateCreated"):
                    val = data.get(key, "")
                    if val:
                        return str(val).strip()
                # Nested @graph
                for g in data.get("@graph", []):
                    if isinstance(g, dict):
                        for key in ("datePublished", "dateCreated"):
                            val = g.get(key, "")
                            if val:
                                return str(val).strip()
            except (json.JSONDecodeError, IndexError, TypeError):
                continue
        return ""

    def extract_from_time_tag(self, element: HtmlElement) -> str:
        for attr in ("datetime", "data-published", "data-timestamp"):
            values = element.xpath(f"//time/@{attr}")
            if values:
                return values[0].strip()
        return ""

    def extract_from_text(self, element: HtmlElement) -> str:
        text = "".join(element.xpath(".//text()"))
        for pattern in _DATETIME_PATTERN:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return ""


time_extractor = TimeExtractor()

# ── author (name only) ─────────────────────────────────────────

_AUTHOR_META = [
    "//meta[starts-with(@name, 'author')]/@content",
    "//meta[starts-with(@name, 'Author')]/@content",
    "//meta[starts-with(@name, 'byline')]/@content",
    "//meta[starts-with(@name, 'parsely-author')]/@content",
    "//meta[starts-with(@name, 'byl')]/@content",
    "//meta[contains(@property, 'dable:author')]/@content",
]

_AUTHOR_TEXT_PATTERN = [
    re.compile(r"记者[：:丨/\s]\s*([\u4E00-\u9FA5a-zA-Z]{2,20})"),
    re.compile(r"作者[：:丨/\s]\s*([\u4E00-\u9FA5a-zA-Z]{2,20})"),
    re.compile(r"责编[：:丨/\s]\s*([\u4E00-\u9FA5a-zA-Z]{2,20})"),
    re.compile(r"责任编辑[：:丨/\s]\s*([\u4E00-\u9FA5a-zA-Z]{2,20})"),
    re.compile(r"编辑[：:丨/\s]\s*([\u4E00-\u9FA5a-zA-Z]{2,20})"),
    re.compile(r"原创[：:丨/\s]\s*([\u4E00-\u9FA5a-zA-Z]{2,20})"),
    re.compile(r"撰文[：:丨/\s]\s*([\u4E00-\u9FA5a-zA-Z]{2,20})"),
    re.compile(r"来源[：:丨/\s]\s*([\u4E00-\u9FA5a-zA-Z]{2,20})"),
]

_INVALID_AUTHOR = frozenset(["name", "author", "admin", "editor", "test"])


def _is_valid_author(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if t.isdigit():
        return False
    if "@" in t:
        return False
    if t.lower() in _INVALID_AUTHOR:
        return False
    if len(t) < 2 or len(t) > 30:
        return False
    return True


def _clean_author_name(raw: str) -> str:
    """Strip prefixes like 记者/作者 and return just the name."""
    prefixes = ["记者", "作者", "责编", "责任编辑", "编辑", "原创", "撰文", "来源"]
    s = raw.strip()
    for p in prefixes:
        if s.startswith(p):
            s = s[len(p):].strip()
    return s.strip("'\"")


class AuthorExtractor:
    """Extract author name only — json-ld → meta → itemprop → class/rel → text regex.
    No LLM calls. Returns plain name string."""

    def extractor(self, element: HtmlElement, author_xpath: str = "") -> str:
        if author_xpath:
            result = element.xpath(author_xpath)
            if result and _is_valid_author(result[0]):
                return _clean_author_name(result[0])
        return (
            self.extract_from_json_ld(element)
            or self.extract_from_meta(element)
            or self.extract_from_itemprop(element)
            or self.extract_from_class(element)
            or self.extract_from_text(element)
        )

    def extract_from_json_ld(self, element: HtmlElement) -> str:
        scripts = element.xpath('//script[@type="application/ld+json"]/text()')
        for script_text in scripts:
            try:
                data = json.loads(script_text.strip())
                if isinstance(data, list):
                    data = data[0]
                if not isinstance(data, dict):
                    continue
                author = data.get("author")
                name = self._get_name_from_author(author)
                if name:
                    return name
                for g in data.get("@graph", []):
                    if isinstance(g, dict):
                        name = self._get_name_from_author(g.get("author"))
                        if name:
                            return name
            except (json.JSONDecodeError, IndexError, TypeError):
                continue
        return ""

    def _get_name_from_author(self, author) -> str:
        if isinstance(author, str):
            return _clean_author_name(author) if _is_valid_author(author) else ""
        if isinstance(author, dict):
            name = author.get("name", "")
            return _clean_author_name(name) if _is_valid_author(name) else ""
        if isinstance(author, list) and author:
            first = author[0]
            name = first.get("name", "") if isinstance(first, dict) else str(first)
            return _clean_author_name(name) if _is_valid_author(name) else ""
        return ""

    def extract_from_meta(self, element: HtmlElement) -> str:
        for xpath in _AUTHOR_META:
            result = element.xpath(xpath)
            if result:
                val = result[0].strip()
                if "," in val:
                    # Multiple authors separated by comma — take first
                    val = val.split(",")[0].strip()
                if _is_valid_author(val):
                    return _clean_author_name(val)
        return ""

    def extract_from_itemprop(self, element: HtmlElement) -> str:
        result = element.xpath('//*[@itemprop="author"]//text()')
        if result:
            val = "".join(result).strip()
            if _is_valid_author(val):
                return _clean_author_name(val)
        return ""

    def extract_from_class(self, element: HtmlElement) -> str:
        result = element.xpath(
            '//*[@class="author"]//text() | //a[@rel="author"]//text()'
        )
        if result:
            val = "".join(result).strip()
            if _is_valid_author(val):
                return _clean_author_name(val)
        return ""

    def extract_from_text(self, element: HtmlElement) -> str:
        text = "".join(element.xpath(".//text()"))
        for pattern in _AUTHOR_TEXT_PATTERN:
            match = pattern.search(text)
            if match:
                name = match.group(1).strip()
                if _is_valid_author(name):
                    return name
        return ""


author_extractor = AuthorExtractor()