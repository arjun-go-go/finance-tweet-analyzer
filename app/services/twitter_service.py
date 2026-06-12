"""Twitter profile fetching service - importable by agent tools."""
import json
import random
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from curl_cffi import requests as cffi_requests
from loguru import logger

from app.core.config import settings

CST = timezone(timedelta(hours=8))

COOKIES = {
    "auth_token": settings.twitter_auth_token,
    "ct0": settings.twitter_ct0,
}

HEADERS = {
    "authorization": f"Bearer {settings.twitter_bearer_token}",
    "x-csrf-token": COOKIES["ct0"],
    "x-twitter-active-user": "yes",
    "x-twitter-auth-type": "OAuth2Session",
    "x-twitter-client-language": "en",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}

IMPERSONATE_LIST = [
    "chrome131",
    "chrome123",
    "chrome124",
    "chrome120",
    "chrome119",
    "chrome116",
    "chrome110",
]

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


def _parse_twitter_utc(time_str: str) -> datetime:
    naive = datetime.strptime(time_str, "%a %b %d %H:%M:%S +0000 %Y")
    return naive.replace(tzinfo=timezone.utc)


def _cst_to_iso(time_str: str) -> str:
    return _parse_twitter_utc(time_str).astimezone(CST).isoformat()


def _build_profile_url(screen_name: str) -> str:
    variables = {"screen_name": screen_name}
    params = (
        f"variables={quote(json.dumps(variables))}"
        f"&features={quote(json.dumps(PROFILE_FEATURES))}"
        f"&fieldToggles={quote(json.dumps(PROFILE_FIELD_TOGGLES))}"
    )
    return f"{PROFILE_GRAPHQL_ENDPOINT}?{params}"


def fetch_user_profile(screen_name: str) -> dict | None:
    """Fetch Twitter user profile by screen_name (without @).

    Returns profile dict on success, None on failure.
    """
    logger.info("Fetching Twitter profile: @{}", screen_name)
    url = _build_profile_url(screen_name)
    impersonate = random.choice(IMPERSONATE_LIST)
    proxies = {
        "http": settings.http_proxy,
        "https": settings.http_proxy,
    }

    try:
        response = cffi_requests.get(
            url,
            impersonate=impersonate,
            cookies=COOKIES,
            headers=HEADERS,
            proxies=proxies,
            timeout=30,
        )
    except Exception as e:
        logger.warning("Twitter request failed for @{}: {}", screen_name, e)
        return None

    if response.status_code != 200:
        logger.warning("Twitter API returned {} for @{}", response.status_code, screen_name)
        return None

    try:
        json_content = response.json()
    except Exception:
        logger.warning("Failed to parse JSON for @{}", screen_name)
        return None

    if json_content.get("errors"):
        logger.warning("Twitter API errors for @{}: {}", screen_name, json_content["errors"])
        return None

    result_content = json_content.get("data", {}).get("user", {}).get("result", {})
    legacy = result_content.get("legacy", {})
    if not legacy:
        logger.warning("User @{} not found or unavailable", screen_name)
        return None

    user_id = result_content.get("rest_id", "")

    info_url = ""
    if legacy.get("url"):
        urls = legacy.get("entities", {}).get("url", {}).get("urls", [])
        if urls:
            info_url = urls[0].get("expanded_url", "")

    logger.info("Fetched profile: @{} (followers={})", legacy.get("screen_name", ""), legacy.get("followers_count", 0))

    return {
        "user_id": user_id,
        "screen_name": legacy.get("screen_name", ""),
        "name": legacy.get("name", ""),
        "bio": legacy.get("description", ""),
        "location": legacy.get("location", ""),
        "tweets_count": legacy.get("statuses_count", 0),
        "following": legacy.get("friends_count", 0),
        "followers": legacy.get("followers_count", 0),
        "favorites": legacy.get("favourites_count", 0),
        "join_date": _cst_to_iso(legacy["created_at"]) if legacy.get("created_at") else "",
        "verified": legacy.get("verified", False),
        "protected": legacy.get("protected", False),
        "image_url": legacy.get("profile_image_url_https", "").replace("_normal", ""),
        "info_url": info_url,
    }


def convert_profile_to_upsert(raw: dict) -> dict:
    """Map raw profile dict to BloggerProfile schema format."""
    return {
        "handle": raw['screen_name'],
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


# ══════════════════════════════════════════════════════════════
# Tweet fetching
# ══════════════════════════════════════════════════════════════

TWEETS_GRAPHQL_ENDPOINT = "https://twitter.com/i/api/graphql/XicnWRbyQ3WgVY__VataBQ/UserTweets"

TWEETS_FEATURES = {
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


def _build_tweets_url(user_id: str, cursor: str | None = None) -> str:
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
    params = f"variables={quote(json.dumps(variables))}&features={quote(json.dumps(TWEETS_FEATURES))}"
    return f"{TWEETS_GRAPHQL_ENDPOINT}?{params}"


def _strip_text(text: str) -> str:
    import re
    if not text:
        return ""
    text = re.sub(r"https://t\.co/\w+", "", text)
    return text.strip()


def _parse_tweet_entry(entry: dict) -> dict | None:
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
    item["user_id"] = core["rest_id"]
    item["name"] = core["legacy"]["name"]
    item["user_name"] = core["legacy"]["screen_name"]

    def get_full_text(tweet_obj):
        text = tweet_obj.get("legacy", {}).get("full_text", "")
        if "note_tweet" in tweet_obj:
            try:
                note_text = tweet_obj["note_tweet"]["note_tweet_results"]["result"]["text"]
                if note_text:
                    return note_text
            except (KeyError, TypeError):
                pass
        return text

    item["tweet_text"] = _strip_text(get_full_text(tweets))
    item["lang"] = legacy.get("lang", "")
    item["views"] = int(tweets.get("views", {}).get("count", 0))

    item["media_images"] = []
    if "extended_entities" in legacy:
        for media in legacy["extended_entities"].get("media", []):
            item["media_images"].append({
                "media_status_id": media["id_str"],
                "media_url": media["media_url_https"],
            })

    if "retweeted_status_result" in legacy:
        retweeted = legacy["retweeted_status_result"]["result"]
        if "tweet" in retweeted:
            retweeted = retweeted["tweet"]
        rt_legacy = retweeted.get("legacy", {})
        rt_core = retweeted.get("core", {}).get("user_results", {}).get("result", {})

        item["tweet_text"] = _strip_text(rt_legacy.get("full_text", ""))
        item["data_time_iso"] = _cst_to_iso(rt_legacy["created_at"]) if rt_legacy.get("created_at") else ""
        item["tweet_name"] = rt_core.get("legacy", {}).get("screen_name", "")
        item["data_id"] = retweeted.get("rest_id", "")
        item["retweets"] = rt_legacy.get("retweet_count", 0)
        item["favorites"] = rt_legacy.get("favorite_count", 0)
        item["replies"] = rt_legacy.get("reply_count", 0)
        item["bookmark_count"] = rt_legacy.get("bookmark_count", 0)
        item["quote_count"] = rt_legacy.get("quote_count", 0)
        item["views"] = int(retweeted.get("views", {}).get("count", 0))
        item["is_retweet"] = True
    else:
        item["data_time_iso"] = _cst_to_iso(legacy["created_at"]) if legacy.get("created_at") else ""
        item["tweet_name"] = item["user_name"]
        item["data_id"] = tweets.get("rest_id", "")
        item["retweets"] = legacy.get("retweet_count", 0)
        item["favorites"] = legacy.get("favorite_count", 0)
        item["replies"] = legacy.get("reply_count", 0)
        item["bookmark_count"] = legacy.get("bookmark_count", 0)
        item["quote_count"] = legacy.get("quote_count", 0)
        item["is_retweet"] = False

    return item


def _parse_tweets_response(data: dict) -> tuple[list[dict], str | None]:
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

    is_bottom = entries[-1].get("entryId", "").startswith("cursor-bottom")
    is_top = len(entries) >= 2 and entries[-2].get("entryId", "").startswith("cursor-top")
    if len(entries) == 2 and is_bottom and is_top:
        return tweets, None

    for entry in entries:
        entry_id = entry.get("entryId", "")
        if entry_id.startswith("cursor-bottom"):
            content = entry.get("content", {})
            if content.get("itemContent"):
                next_cursor = content["itemContent"].get("value")
            elif content.get("value"):
                next_cursor = content["value"]
            continue
        tweet = _parse_tweet_entry(entry)
        if tweet:
            tweets.append(tweet)

    return tweets, next_cursor


def fetch_user_tweets(user_id: str, max_pages: int = 1) -> list[dict]:
    """Fetch tweets for a user by their numeric Twitter user_id.

    Returns list of parsed tweet dicts, or empty list on failure.
    """
    import time as _time

    logger.info("Fetching tweets for user_id={} (pages={})", user_id, max_pages)
    all_tweets = []
    cursor = None
    proxies = {"http": settings.http_proxy, "https": settings.http_proxy}

    for page in range(max_pages):
        url = _build_tweets_url(user_id, cursor)
        impersonate = random.choice(IMPERSONATE_LIST)

        try:
            response = cffi_requests.get(
                url,
                impersonate=impersonate,
                cookies=COOKIES,
                headers=HEADERS,
                proxies=proxies,
                timeout=30,
            )
        except Exception as e:
            logger.warning("Tweet fetch failed for user_id={}: {}", user_id, e)
            break

        if response.status_code != 200:
            logger.warning("Tweet API returned {} for user_id={}", response.status_code, user_id)
            break

        try:
            data = response.json()
        except Exception:
            logger.warning("Failed to parse tweet JSON for user_id={}", user_id)
            break

        tweets, next_cursor = _parse_tweets_response(data)
        logger.info("Page {}: got {} tweets for user_id={}", page + 1, len(tweets), user_id)
        all_tweets.extend(tweets)

        if not next_cursor:
            break
        cursor = next_cursor
        if page < max_pages - 1:
            _time.sleep(2)

    logger.info("Total {} tweets fetched for user_id={}", len(all_tweets), user_id)
    return all_tweets


def convert_tweets_to_import(raw_tweets: list[dict]) -> list[dict]:
    """Convert raw tweet dicts to TweetImportItem format."""
    items = []
    for tweet in raw_tweets:
        items.append({
            "tweet_id": tweet["data_id"],
            "author_handle": tweet['tweet_name'],
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
        })
    return items
