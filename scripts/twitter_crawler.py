# -*- coding: utf-8 -*-
"""
Twitter 推文采集器
基于 curl_cffi 实现，通过 Twitter GraphQL API 获取指定用户推文。
支持翻页、转推识别、完整字段提取。
采集结果直接调用项目 API 导入，或直接写入数据库。

Usage:
    uv run python scripts/twitter_crawler.py --user_ids 946011118555639808,1260553941714186241
    uv run python scripts/twitter_crawler.py --user_ids 946011118555639808 --pages 3
"""
import argparse
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from curl_cffi import requests as cffi_requests
from dotenv import load_dotenv

load_dotenv()

CST = timezone(timedelta(hours=8))

# ══════════════════════════════════════════════════════════════
# 配置 — 从 .env 读取，不硬编码
# ══════════════════════════════════════════════════════════════

_twitter_auth_token = os.getenv("TWITTER_AUTH_TOKEN", "")
_twitter_ct0 = os.getenv("TWITTER_CT0", "")
_twitter_bearer = os.getenv("TWITTER_BEARER_TOKEN", "")
_http_proxy = os.getenv("HTTP_PROXY", "")

COOKIES = {
    "auth_token": _twitter_auth_token,
    "ct0": _twitter_ct0,
}

HEADERS = {
    "authorization": f"Bearer {_twitter_bearer}",
    "x-csrf-token": COOKIES["ct0"],
    "x-twitter-active-user": "yes",
    "x-twitter-auth-type": "OAuth2Session",
    "x-twitter-client-language": "en",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}

PROXIES = {
    "http": _http_proxy,
    "https": _http_proxy,
} if _http_proxy else None

IMPERSONATE_LIST = [
    "chrome131",
    "chrome123",
    "chrome124",
    "chrome120",
    "chrome119",
    "chrome116",
    "chrome110",
]

GRAPHQL_ENDPOINT = "https://twitter.com/i/api/graphql/XicnWRbyQ3WgVY__VataBQ/UserTweets"

FEATURES = {
    "vibe_api_enabled": True,
    "responsive_web_twitter_blue_verified_badge_is_enabled": True,
    "longform_notetweets_richtext_consumption_enabled": True,
    "responsive_web_text_conversations_enabled": True,
    "interactive_text_enabled": True,
    "rweb_lists_timeline_redesign_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": False,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}

API_BASE = "http://localhost:8000"

PROFILE_GRAPHQL_ENDPOINT = "https://x.com/i/api/graphql/laYnJPCAcVo0o6pzcnlVxQ/UserByScreenName"

PROFILE_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}

PROFILE_FIELD_TOGGLES = {"withAuxiliaryUserLabels": False}


# ══════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════

def _parse_twitter_utc(time_str: str) -> datetime:
    """解析 Twitter 'Wed Oct 10 20:19:24 +0000 2018' 为带 UTC 时区的 datetime"""
    naive = datetime.strptime(time_str, "%a %b %d %H:%M:%S +0000 %Y")
    return naive.replace(tzinfo=timezone.utc)


def cst_to_timestamp(time_str: str) -> int:
    """Twitter 时间格式 → UTC epoch 秒（与本机时区无关）"""
    return int(_parse_twitter_utc(time_str).timestamp())


def cst_to_iso(time_str: str) -> str:
    """Twitter 时间格式 → 北京时间 ISO 字符串（含 +08:00）"""
    return _parse_twitter_utc(time_str).astimezone(CST).isoformat()


def now_cst_iso() -> str:
    """当前北京时间 ISO 字符串"""
    return datetime.now(tz=CST).isoformat()


def strip_str(text: str) -> str:
    """清理推文文本"""
    if not text:
        return ""
    text = re.sub(r'https://t\.co/\w+', '', text)
    text = text.strip()
    return text


def build_url(user_id: str, cursor: str | None = None) -> str:
    """构建 GraphQL 请求 URL"""
    variables = {
        "userId": user_id,
        "count": 20,
        "includePromotedContent": True,
        "withDownvotePerspective": False,
        "withReactionsMetadata": False,
        "withQuickPromoteEligibilityTweetFields": True,
        "withReactionsPerspective": False,
        "withSuperFollowsTweetFields": True,
        "withSuperFollowsUserFields": True,
        "withV2Timeline": True,
        "withVoice": True,
    }
    if cursor:
        variables["cursor"] = cursor

    params = f"variables={quote(json.dumps(variables))}&features={quote(json.dumps(FEATURES))}"
    return f"{GRAPHQL_ENDPOINT}?{params}"


def build_profile_url(screen_name: str) -> str:
    """构建 UserByScreenName GraphQL 请求 URL"""
    variables = {"screen_name": screen_name}
    params = (
        f"variables={quote(json.dumps(variables))}"
        f"&features={quote(json.dumps(PROFILE_FEATURES))}"
        f"&fieldToggles={quote(json.dumps(PROFILE_FIELD_TOGGLES))}"
    )
    return f"{PROFILE_GRAPHQL_ENDPOINT}?{params}"


def fetch_user_profile(screen_name: str) -> dict | None:
    """
    通过用户名获取 Twitter 用户详细信息。

    Args:
        screen_name: Twitter 用户名（不含@）

    Returns:
        用户信息 dict，包含 user_id, name, screen_name, followers, following,
        tweets_count, bio, location, verified, image_url, join_date 等字段。
        失败返回 None。
    """
    url = build_profile_url(screen_name)
    impersonate = random.choice(IMPERSONATE_LIST)

    print(f"Fetching profile: @{screen_name}")
    print(f"  impersonate: {impersonate}")

    try:
        response = cffi_requests.get(
            url,
            impersonate=impersonate,
            cookies=COOKIES,
            headers=HEADERS,
            proxies=PROXIES,
            timeout=30,
        )
    except Exception as e:
        print(f"  Request failed: {e}")
        return None

    print(f"  status: {response.status_code}")

    if response.status_code != 200:
        print(f"  Error: {response.text[:200]}")
        return None

    try:
        json_content = response.json()
    except Exception:
        print("  Failed to parse JSON.")
        return None

    if json_content.get("errors"):
        print(f"  API errors: {json_content['errors']}")
        return None

    result_content = json_content.get("data", {}).get("user", {}).get("result", {})
    legacy = result_content.get("legacy", {})
    if not legacy:
        print("  User not found or unavailable.")
        return None

    user_id = result_content.get("rest_id", "")

    info_url = ""
    if legacy.get("url"):
        urls = legacy.get("entities", {}).get("url", {}).get("urls", [])
        if urls:
            info_url = urls[0].get("expanded_url", "")

    profile = {
        "user_id": user_id,
        "screen_name": legacy.get("screen_name", ""),
        "name": legacy.get("name", ""),
        "bio": legacy.get("description", ""),
        "location": legacy.get("location", ""),
        "tweets_count": legacy.get("statuses_count", 0),
        "following": legacy.get("friends_count", 0),
        "followers": legacy.get("followers_count", 0),
        "favorites": legacy.get("favourites_count", 0),
        "join_date": cst_to_iso(legacy["created_at"]) if legacy.get("created_at") else "",
        "verified": legacy.get("verified", False),
        "protected": legacy.get("protected", False),
        "image_url": legacy.get("profile_image_url_https", "").replace("_normal", ""),
        "info_url": info_url,
        "storage_date": now_cst_iso(),
    }
    print(profile)
    print(f"  Found: {profile['name']} (@{profile['screen_name']}) | "
          f"Followers: {profile['followers']} | Tweets: {profile['tweets_count']}")

    return profile


# ══════════════════════════════════════════════════════════════
# 推文解析
# ══════════════════════════════════════════════════════════════

def parse_tweet_entry(entry: dict) -> dict | None:
    """
    解析单条 tweet entry，严格按原爬虫字段提取。
    返回包含所有字段的 dict，或 None（非推文条目）。
    """
    entry_id = entry.get("entryId", "")
    if not entry_id.startswith("tweet"):
        return None

    try:
        tweets = entry["content"]["itemContent"]["tweet_results"]["result"]
    except (KeyError, TypeError):
        return None

    if "tweet" in tweets:
        tweets = tweets["tweet"]

    if "legacy" not in tweets or "core" not in tweets:
        return None

    legacy = tweets["legacy"]
    core = tweets["core"]["user_results"]["result"]

    item = {}

    # 用户信息
    item["user_id"] = core["rest_id"]
    item["name"] = core["legacy"]["name"]
    item["user_name"] = core["legacy"]["screen_name"]

    def get_full_text(tweet_obj):
        """
        尝试从 note_tweet 获取完整文本，如果不存在则回退到 legacy full_text
        """
        # 默认获取 legacy 中的文本（可能被截断）
        text = tweet_obj.get("legacy", {}).get("full_text", "")

        # 检查是否存在 note_tweet (长推文)
        if "note_tweet" in tweet_obj:
            try:
                note_text = tweet_obj["note_tweet"]["note_tweet_results"]["result"]["text"]
                if note_text:
                    return note_text
            except (KeyError, TypeError):
                pass
        return text
    # 推文基础信息
    item["tweet_text"] = strip_str(get_full_text(tweets))
    item["lang"] = legacy.get("lang", "")

    source_info = re.match(r"<a href=(.*)>(.*)</a>", tweets.get("source", ""))
    item["source"] = source_info.group(2) if source_info else ""

    item["views"] = int(tweets.get("views", {}).get("count", 0))
    item["coordinates"] = legacy.get("coordinates")
    item["place"] = legacy.get("place")

    # 媒体
    item["media_images"] = []
    if "extended_entities" in legacy:
        for media in legacy["extended_entities"].get("media", []):
            item["media_images"].append({
                "media_status_id": media["id_str"],
                "media_url": media["media_url_https"],
            })

    # 展开链接
    item["data_expanded_url"] = []
    for url in legacy.get("entities", {}).get("urls", []):
        if url.get("expanded_url"):
            item["data_expanded_url"].append(url["expanded_url"])

    # 引用推文
    if "quoted_status_result" in tweets:
        quoted = tweets["quoted_status_result"].get("result", {})
        if quoted.get("rest_id"):
            item["quoted_status_id"] = quoted["rest_id"]
            item["quoted_user_id"] = quoted.get("core", {}).get("user_results", {}).get("result", {}).get("rest_id", "")
            item["quoted_user_name"] = quoted.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {}).get("screen_name", "")

    # Hashtags
    item["hashtags"] = legacy.get("entities", {}).get("hashtags", [])

    # @提及
    item["tweet_list"] = []
    for mention in legacy.get("entities", {}).get("user_mentions", []):
        mention["id"] = mention.get("id_str", "")
        item["tweet_list"].append(mention)

    # 转推 vs 原创
    if "retweeted_status_result" in legacy:
        retweeted = legacy["retweeted_status_result"]["result"]
        if "tweet" in retweeted:
            retweeted = retweeted["tweet"]

        rt_legacy = retweeted.get("legacy", {})
        rt_core = retweeted.get("core", {}).get("user_results", {}).get("result", {})

        item["tweet_text"] = strip_str(rt_legacy.get("full_text", ""))
        item["data_time"] = cst_to_timestamp(rt_legacy["created_at"])
        item["data_time_iso"] = cst_to_iso(rt_legacy["created_at"])
        item["retweeted_times"] = cst_to_timestamp(legacy["created_at"])
        item["retweeted_times_iso"] = cst_to_iso(legacy["created_at"])
        item["tweet_name"] = rt_core.get("legacy", {}).get("screen_name", "")
        item["tweet_id"] = rt_core.get("rest_id", "")
        item["data_id"] = retweeted.get("rest_id", "")
        item["retweets"] = rt_legacy.get("retweet_count", 0)
        item["favorites"] = rt_legacy.get("favorite_count", 0)
        item["replies"] = rt_legacy.get("reply_count", 0)
        item["bookmark_count"] = rt_legacy.get("bookmark_count", 0)
        item["quote_count"] = rt_legacy.get("quote_count", 0)
        item["views"] = int(retweeted.get("views", {}).get("count", 0))
        item["data_retweeter"] = item["user_id"]
        item["data_retweet_id"] = tweets.get("rest_id", "")
        item["is_retweet"] = True
    else:
        item["data_time"] = cst_to_timestamp(legacy["created_at"])
        item["data_time_iso"] = cst_to_iso(legacy["created_at"])
        item["retweeted_times"] = None
        item["retweeted_times_iso"] = None
        item["tweet_name"] = item["user_name"]
        item["tweet_id"] = item["user_id"]
        item["data_id"] = tweets.get("rest_id", "")
        item["retweets"] = legacy.get("retweet_count", 0)
        item["favorites"] = legacy.get("favorite_count", 0)
        item["replies"] = legacy.get("reply_count", 0)
        item["bookmark_count"] = legacy.get("bookmark_count", 0)
        item["quote_count"] = legacy.get("quote_count", 0)
        item["data_retweeter"] = None
        item["data_retweet_id"] = None
        item["is_retweet"] = False

    item["url"] = f"https://x.com/{item['tweet_name']}/status/{item['data_id']}"
    item["storage_date"] = now_cst_iso()
    print(item)
    return item


def parse_response(data: dict) -> tuple[list[dict], str | None]:
    """
    解析 API 响应，返回 (推文列表, 下一页 cursor)。
    """
    tweets = []
    next_cursor = None

    user = data.get("data", {}).get("user")
    if not user:
        return tweets, None

    result = user.get("result", {})
    if result.get("__typename") == "UserUnavailable":
        return tweets, None

    instructions = result.get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
    entries = []
    for instruction in instructions:
        if instruction.get("type") == "TimelineAddEntries":
            entries = instruction.get("entries", [])

    if not entries:
        return tweets, None

    # 检查是否只剩 cursor 条目（无更多数据）
    is_bottom = entries[-1].get("entryId", "").startswith("cursor-bottom") if entries else False
    is_top = len(entries) >= 2 and entries[-2].get("entryId", "").startswith("cursor-top") if entries else False
    if len(entries) == 2 and is_bottom and is_top:
        return tweets, None

    for entry in entries:
        entry_id = entry.get("entryId", "")

        # 提取翻页 cursor
        if entry_id.startswith("cursor-bottom"):
            content = entry.get("content", {})
            if content.get("itemContent"):
                next_cursor = content["itemContent"].get("value")
            elif content.get("value"):
                next_cursor = content["value"]
            continue

        # 解析推文
        tweet = parse_tweet_entry(entry)
        if tweet:
            tweets.append(tweet)

    return tweets, next_cursor


# ══════════════════════════════════════════════════════════════
# 采集逻辑
# ══════════════════════════════════════════════════════════════

def fetch_user_tweets(user_id: str, max_pages: int = 1, delay: float = 2.0) -> list[dict]:
    """
    采集指定用户的推文，支持翻页。

    Args:
        user_id: Twitter 用户 ID
        max_pages: 最大翻页数
        delay: 每次请求间隔（秒）

    Returns:
        推文列表
    """
    all_tweets = []
    cursor = None

    for page in range(max_pages):
        url = build_url(user_id, cursor)
        impersonate = random.choice(IMPERSONATE_LIST)

        print(f"[Page {page + 1}] Fetching user {user_id}...")
        print(f"  impersonate: {impersonate}")
        print(f"  url: {url[:120]}...")

        try:
            response = cffi_requests.get(
                url,
                impersonate=impersonate,
                cookies=COOKIES,
                headers=HEADERS,
                proxies=PROXIES,
                timeout=30,
            )
        except Exception as e:
            print(f"  Request failed: {e}")
            break

        print(f"  status: {response.status_code}")

        if response.status_code == 429:
            print("  Rate limited. Stopping.")
            break
        if response.status_code in (401, 403):
            print(f"  Auth error ({response.status_code}). Check cookies.")
            break
        if response.status_code != 200:
            print(f"  Unexpected status: {response.status_code}")
            break

        try:
            data = response.json()
        except Exception:
            print("  Failed to parse JSON response.")
            break

        tweets, next_cursor = parse_response(data)
        print(f"  Got {len(tweets)} tweets.")
        all_tweets.extend(tweets)

        if not next_cursor:
            print("  No more pages.")
            break

        cursor = next_cursor
        if page < max_pages - 1:
            time.sleep(delay)

    return all_tweets


# ══════════════════════════════════════════════════════════════
# 导入到项目
# ══════════════════════════════════════════════════════════════

def convert_to_import_format(raw_tweets: list[dict]) -> list[dict]:
    """
    将原始采集数据转换为项目 Tweet Import API 格式。
    原始完整字段保存在 raw_json 中。
    """
    import_items = []
    for tweet in raw_tweets:
        item = {
            "tweet_id": tweet["data_id"],
            "author_handle": f"@{tweet['tweet_name']}",
            "author_name": tweet.get("name", ""),
            "content": tweet["tweet_text"],
            "published_at": tweet.get("data_time_iso", ""),
            "metrics": {
                "likes": tweet.get("favorites", 0),
                "retweets": tweet.get("retweets", 0),
                "replies": tweet.get("replies", 0),
                "views": tweet.get("views", 0),
                "bookmarks": tweet.get("bookmark_count", 0),
                "quotes": tweet.get("quote_count", 0),
            },
            "media_urls": tweet.get("media_images") or None,
            "raw_json": tweet,
        }
        import_items.append(item)
    return import_items


def push_to_api(import_items: list[dict]) -> dict:
    """调用项目 API 导入推文"""
    response = httpx.post(
        f"{API_BASE}/api/tweets/import",
        json={"tweets": import_items},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def convert_profile_to_upsert(raw: dict) -> dict:
    """将 fetch_user_profile 的原始 dict 映射为 BloggerProfile 入参"""
    return {
        "handle": f"@{raw['screen_name']}",
        "name": raw.get("name", ""),
        "bio": raw.get("bio", ""),
        "avatar_url": raw.get("image_url"),
        "followers_count": raw.get("followers", 0),
        "twitter_user_id": raw.get("user_id"),
        "location": raw.get("location") or None,
        "tweets_count": raw.get("tweets_count", 0),
        "following_count": raw.get("following", 0),
        "favorites_count": raw.get("favorites", 0),
        "joined_at": raw.get("join_date") or None,
        "verified": raw.get("verified", False),
        "protected": raw.get("protected", False),
        "profile_url": raw.get("info_url") or None,
    }


def push_profile_to_api(raw_profile: dict) -> dict:
    """将用户信息推送到 /api/bloggers/upsert"""
    payload = convert_profile_to_upsert(raw_profile)
    response = httpx.post(
        f"{API_BASE}/api/bloggers/upsert",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# ══════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Twitter 推文采集器 + 用户信息获取")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 子命令: tweets - 采集推文
    tweets_parser = subparsers.add_parser("tweets", help="通过 user_id 采集推文")
    tweets_parser.add_argument("--user_ids", required=True, help="逗号分隔的 Twitter 用户 ID 列表")
    tweets_parser.add_argument("--pages", type=int, default=1, help="每个用户最大翻页数 (默认: 1)")
    tweets_parser.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数 (默认: 2.0)")
    tweets_parser.add_argument("--no-import", action="store_true", help="仅采集不导入，输出 JSON")

    # 子命令: profile - 获取用户信息
    profile_parser = subparsers.add_parser("profile", help="通过用户名获取用户信息")
    profile_parser.add_argument("--screen_names", required=True, help="逗号分隔的用户名列表（不含@）")
    profile_parser.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数 (默认: 2.0)")
    profile_parser.add_argument("--no-import", action="store_true", help="仅获取不导入，输出 JSON")

    # 子命令: full - 通过用户名获取信息+推文（先查 user_id 再采集推文）
    full_parser = subparsers.add_parser("full", help="通过用户名获取信息并采集推文")
    full_parser.add_argument("--screen_names", required=True, help="逗号分隔的用户名列表（不含@）")
    full_parser.add_argument("--pages", type=int, default=1, help="每个用户最大翻页数 (默认: 1)")
    full_parser.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数 (默认: 2.0)")
    full_parser.add_argument("--no-import", action="store_true", help="仅采集不导入，输出 JSON")

    args = parser.parse_args()

    if args.command == "tweets":
        _cmd_tweets(args)
    elif args.command == "profile":
        _cmd_profile(args)
    elif args.command == "full":
        _cmd_full(args)
    else:
        parser.print_help()


def _cmd_tweets(args):
    """采集推文子命令"""
    user_ids = [uid.strip() for uid in args.user_ids.split(",") if uid.strip()]

    all_tweets = []
    for user_id in user_ids:
        print(f"\n{'='*50}")
        print(f"Crawling user: {user_id}")
        print(f"{'='*50}")
        tweets = fetch_user_tweets(user_id, max_pages=args.pages, delay=args.delay)
        all_tweets.extend(tweets)
        if len(user_ids) > 1:
            time.sleep(args.delay)

    print(f"\nTotal tweets collected: {len(all_tweets)}")
    _handle_import(all_tweets, args.no_import)


def _cmd_profile(args):
    """获取用户信息子命令"""
    screen_names = [s.strip().lstrip("@") for s in args.screen_names.split(",") if s.strip()]

    profiles = []
    for name in screen_names:
        profile = fetch_user_profile(name)
        if profile:
            profiles.append(profile)
        if len(screen_names) > 1:
            time.sleep(args.delay)

    print(f"\nTotal profiles fetched: {len(profiles)}")

    if args.no_import:
        print(json.dumps(profiles, ensure_ascii=False, indent=2))
        return

    for profile in profiles:
        try:
            result = push_profile_to_api(profile)
            print(f"  Upserted @{profile['screen_name']}: {result.get('handle', 'ok')}")
        except Exception as e:
            print(f"  Failed to upsert @{profile['screen_name']}: {e}")


def _cmd_full(args):
    """通过用户名获取信息+推文"""
    screen_names = [s.strip().lstrip("@") for s in args.screen_names.split(",") if s.strip()]

    all_tweets = []
    for name in screen_names:
        print(f"\n{'='*50}")
        print(f"Processing: @{name}")
        print(f"{'='*50}")

        profile = fetch_user_profile(name)
        if not profile:
            print(f"  Skipping @{name}: profile not found.")
            continue

        if not args.no_import:
            try:
                push_profile_to_api(profile)
                print(f"  Upserted profile @{name}")
            except Exception as e:
                print(f"  Profile upsert failed: {e}")

        user_id = profile["user_id"]
        print(f"  user_id: {user_id}, fetching tweets...")
        time.sleep(args.delay)

        tweets = fetch_user_tweets(user_id, max_pages=args.pages, delay=args.delay)
        all_tweets.extend(tweets)

        if len(screen_names) > 1:
            time.sleep(args.delay)

    print(f"\nTotal tweets collected: {len(all_tweets)}")
    _handle_import(all_tweets, args.no_import)


def _handle_import(all_tweets: list[dict], no_import: bool):
    """处理导入逻辑"""
    if no_import:
        print(json.dumps(all_tweets, ensure_ascii=False, indent=2))
        return

    import_items = convert_to_import_format(all_tweets)
    if not import_items:
        print("No tweets to import.")
        return

    print(f"Importing {len(import_items)} tweets to API...")
    try:
        result = push_to_api(import_items)
        print(f"Import result: {result}")
    except Exception as e:
        print(f"Import failed: {e}")
        print("Saving to tweets_export.json instead...")
        with open("tweets_export.json", "w", encoding="utf-8") as f:
            json.dump(import_items, f, ensure_ascii=False, indent=2)
        print("Saved.")


if __name__ == "__main__":
    main()
