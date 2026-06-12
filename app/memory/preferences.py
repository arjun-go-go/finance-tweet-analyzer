import re
import threading
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.user_preference import UserPreference


# ============================================================
# Rule-based extraction (zero cost) — only preferences, not facts
# ============================================================

WATCH_PATTERNS = [
    re.compile(r"(?:关注|追踪|follow)\s*@?([A-Za-z]\w{1,14})"),
]
UNWATCH_PATTERNS = [
    re.compile(r"(?:取消关注|不再关注|unfollow)\s*@?([A-Za-z]\w{1,14})"),
]
TICKER_PATTERNS = [
    re.compile(r"(?:看好|跟踪|关注标的|关注代币)[：:\s]*([\w,，、\s]+)"),
    re.compile(r"我(?:关注|看好)\s*((?:[A-Z]{2,10}[,，、\s]*)+)"),
]
STYLE_PATTERNS = [
    re.compile(r"(简洁|详细|简短|详尽)\s*(?:一些|一点|点)?(?:回复|回答|输出)"),
]


def _rule_extract(text: str) -> dict | None:
    updates = {}

    for pat in UNWATCH_PATTERNS:
        matches = pat.findall(text)
        if matches:
            updates.setdefault("unwatch_bloggers", []).extend(matches)

    for pat in WATCH_PATTERNS:
        matches = pat.findall(text)
        if matches:
            filtered = [m for m in matches if m not in updates.get("unwatch_bloggers", [])]
            if filtered:
                updates.setdefault("watch_bloggers", []).extend(filtered)

    for pat in TICKER_PATTERNS:
        matches = pat.findall(text)
        for match in matches:
            tickers = re.split(r"[,，、\s]+", match.strip())
            tickers = [t.upper() for t in tickers if re.match(r"^[A-Z\u4e00-\u9fff]{1,10}$", t.upper())]
            if tickers:
                updates.setdefault("interested_tickers", []).extend(tickers)

    for pat in STYLE_PATTERNS:
        match = pat.search(text)
        if match:
            style_word = match.group(1)
            style_map = {"简洁": "concise", "简短": "concise", "详细": "detailed", "详尽": "detailed"}
            updates["reply_style"] = style_map.get(style_word, "concise")

    return updates if updates else None


# ============================================================
# LLM-based extraction — both profile facts AND preferences
# ============================================================

class ProfileFacts(BaseModel):
    """客观事实，写入 user_profile 表。LLM 经常返回 null，全部允许 None。"""
    name: str | None = None
    nickname: str | None = None
    occupation: str | None = None
    birthday: str | None = None  # ISO 格式 YYYY-MM-DD
    location: str | None = None


class PreferenceUpdate(BaseModel):
    """主观偏好，写入 user_preferences 表。"""
    watch_bloggers: list[str] = []
    unwatch_bloggers: list[str] = []
    interested_tickers: list[str] = []
    reply_style: Literal["concise", "detailed", ""] | None = ""
    investment_style: str | list[str] | None = ""

    @field_validator("watch_bloggers", "unwatch_bloggers", "interested_tickers", mode="before")
    @classmethod
    def none_to_empty_list(cls, v):
        return v if v is not None else []

    def get_investment_style(self) -> str:
        v = self.investment_style
        if v is None:
            return ""
        if isinstance(v, list):
            return "、".join(v)
        return v


class MemoryExtraction(BaseModel):
    profile: ProfileFacts = ProfileFacts()
    preferences: PreferenceUpdate = PreferenceUpdate()


PREF_EXTRACT_PROMPT = SystemMessage(content="""根据用户最新消息，提取客观事实和主观偏好。请以 json 格式输出。

【profile - 客观事实，基本不变】
- name: 真实姓名（如"张三"、"曹俊"）
- nickname: 昵称/网名
- occupation: 职业/身份（"量化交易员"、"散户"、"基金经理"、"研究员"、"程序员"）
- birthday: 生日 (ISO 日期 YYYY-MM-DD)
- location: 所在地（"北京"、"上海"、"杭州"）

【preferences - 主观偏好，可变动】
- watch_bloggers: 新关注的博主 Twitter handle（不含@）
- unwatch_bloggers: 取消关注的博主
- interested_tickers: 新关注的标的/代币（大写如 BTC, ETH, MRVL）
- reply_style: "concise" 或 "detailed"
- investment_style: 投资风格（"短线激进"、"长线价值"、"偏好半导体"、"保守型"）

如果消息中没有任何相关表达，所有字段返回空。""")


def _llm_extract(text: str, llm) -> tuple[dict | None, dict | None]:
    """返回 (profile_facts, preference_updates)。"""
    try:
        structured_llm = llm.with_structured_output(MemoryExtraction)
        result = structured_llm.invoke([
            PREF_EXTRACT_PROMPT,
            HumanMessage(content=text),
        ])
        if result is None:
            return None, None

        facts = {}
        if result.profile.name:
            facts["name"] = result.profile.name
        if result.profile.nickname:
            facts["nickname"] = result.profile.nickname
        if result.profile.occupation:
            facts["occupation"] = result.profile.occupation
        if result.profile.birthday:
            facts["birthday"] = result.profile.birthday
        if result.profile.location:
            facts["location"] = result.profile.location

        prefs = {}
        if result.preferences.watch_bloggers:
            prefs["watch_bloggers"] = result.preferences.watch_bloggers
        if result.preferences.unwatch_bloggers:
            prefs["unwatch_bloggers"] = result.preferences.unwatch_bloggers
        if result.preferences.interested_tickers:
            prefs["interested_tickers"] = result.preferences.interested_tickers
        if result.preferences.reply_style:
            prefs["reply_style"] = result.preferences.reply_style
        if result.preferences.get_investment_style():
            prefs["investment_style"] = result.preferences.get_investment_style()

        return (facts or None), (prefs or None)
    except Exception as e:
        logger.warning("[Preferences] LLM extraction failed: {}", e)
        return None, None


# ============================================================
# CRUD operations — preferences
# ============================================================

def get_preferences(db: Session, user_id: str = "default") -> dict:
    rows = db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).scalars().all()

    prefs = {}
    for row in rows:
        if row.preference_type == "watched_bloggers":
            prefs["watched_bloggers"] = row.value.get("handles", [])
        elif row.preference_type == "interested_tickers":
            prefs["interested_tickers"] = row.value.get("tickers", [])
        elif row.preference_type == "reply_style":
            prefs["reply_style"] = row.value.get("style", "concise")
        elif row.preference_type == "investment_style":
            prefs["investment_style"] = row.value.get("style", "")
    return prefs


def upsert_preference(db: Session, user_id: str, pref_type: str, value: dict) -> None:
    stmt = pg_insert(UserPreference).values(
        user_id=user_id,
        preference_type=pref_type,
        value=value,
    ).on_conflict_do_update(
        constraint="uq_user_pref_type",
        set_={"value": value},
    )
    db.execute(stmt)


def _apply_pref_updates(db: Session, user_id: str, updates: dict) -> None:
    if "watch_bloggers" in updates or "unwatch_bloggers" in updates:
        prefs = get_preferences(db, user_id)
        current = set(prefs.get("watched_bloggers", []))
        current.update(updates.get("watch_bloggers", []))
        current -= set(updates.get("unwatch_bloggers", []))
        upsert_preference(db, user_id, "watched_bloggers", {"handles": sorted(current)})

    if "interested_tickers" in updates:
        prefs = get_preferences(db, user_id)
        current = set(prefs.get("interested_tickers", []))
        current.update(updates["interested_tickers"])
        upsert_preference(db, user_id, "interested_tickers", {"tickers": sorted(current)})

    if "reply_style" in updates:
        upsert_preference(db, user_id, "reply_style", {"style": updates["reply_style"]})

    if "investment_style" in updates:
        upsert_preference(db, user_id, "investment_style", {"style": updates["investment_style"]})


# ============================================================
# Main entry point
# ============================================================

def extract_and_save_preferences(
    db: Session,
    user_message: str,
    user_id: str = "default",
    llm=None,
) -> None:
    from app.memory.profile import upsert_profile

    rule_updates = _rule_extract(user_message)
    if rule_updates:
        logger.info("[Preferences] Rule extracted: {}", rule_updates)
        _apply_pref_updates(db, user_id, rule_updates)
        db.commit()
        return

    if llm is None:
        return

    facts, llm_updates = _llm_extract(user_message, llm)
    if facts:
        logger.info("[Profile] LLM extracted: {}", facts)
        upsert_profile(db, user_id, facts)
    if llm_updates:
        logger.info("[Preferences] LLM extracted: {}", llm_updates)
        _apply_pref_updates(db, user_id, llm_updates)
    if facts or llm_updates:
        db.commit()


def extract_preferences_background(user_message: str, user_id: str = "default") -> None:
    from app.agents.llm import get_signal_llm
    from app.core.deps import SessionLocal

    def _run():
        db = SessionLocal()
        try:
            extract_and_save_preferences(db, user_message, user_id, llm=get_signal_llm())
        except Exception as e:
            logger.error("[Preferences] Background extraction error: {}", e)
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()
