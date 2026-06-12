"""
Self-Query 意图解析模块
============================================================
职责：从用户的自然语言查询中提取结构化检索参数（QueryIntent）。

为什么需要 Self-Query：
- 用户查询是自由文本："帮我看看这周 TSLA 的看空观点"
- 检索需要结构化参数：ticker=TSLA, time_range=本周, sentiment=bearish
- Self-Query 在检索前将自然语言转为可执行的过滤条件

双策略设计：
1. 主策略 — LLM 结构化输出：
   - 使用 Signal LLM + with_structured_output(QueryIntent)
   - 注入时间锚点（今天/本周/本月），让 LLM 正确计算相对时间
   - 直接输出 Pydantic 模型，类型安全

2. 兜底策略 — 正则提取：
   - LLM 调用失败（超时/限流/解析错误）时启用
   - 正则匹配 ticker（1-5 位大写字母或 XX/XX 格式）
   - 默认 7 天时间窗口 + 通用 focus_aspects

在管线中的位置：
  用户查询 → **parse_intent** → QueryIntent → 4 路 retriever → RRF → rerank
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.agents.llm import get_signal_llm


class QueryIntent(BaseModel):
    """结构化查询意图，作为下游检索器的过滤参数。"""

    ticker: str = Field(..., description="金融标的代码，如 TSLA, BTC, AAPL")
    time_range_start: datetime | None = Field(None, description="时间范围起始")
    time_range_end: datetime | None = Field(None, description="时间范围结束")
    sentiment_filter: list[str] = Field(default_factory=list, description="情感过滤: bullish/bearish/neutral")
    horizon_filter: list[str] = Field(default_factory=list, description="投资周期: short/medium/long")
    focus_aspects: list[str] = Field(default_factory=lambda: ["sentiment", "risk", "technical"])
    keywords: list[str] = Field(default_factory=list, description="关键词")
    blogger_filter: list[str] = Field(default_factory=list, description="博主过滤，如 ['qinbafrank', 'LinQingV']")


# 匹配 ticker 的正则：1-5 位大写字母（如 TSLA）或 XX/XX 格式（如 BTC/USDT）
_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b|([A-Z]+/[A-Z]+)")
_BLOGGER_RE = re.compile(r"@(\w+)")

# LLM System Prompt：注入当前时间锚点，确保相对时间（"本周""最近3天"）正确解析
_SYSTEM_PROMPT = """你是一个金融查询意图解析器。从用户的自然语言请求中提取结构化查询参数。

时间锚点：
- 今天: {today}
- "本周" = {week_start} ~ {today}
- "本月" = {month_start} ~ {today}
- "最近N天" = 从今天往前推N天

如果用户没有明确指定时间范围，默认使用最近7天。
如果用户没有明确指定 ticker，从文本中提取最可能的金融标的代码。
如果用户提到特定博主（如 @xxx、"qinbafrank 的观点"、"LinQingV 怎么看"），提取博主 handle 到 blogger_filter 列表中（不含 @ 符号）。

请返回结构化的 JSON 格式结果。"""


def _fallback_parse(query: str) -> QueryIntent:
    """正则兜底解析：LLM 失败时从文本中提取 ticker + 默认参数。"""
    now = datetime.now(timezone.utc)
    tickers = _TICKER_RE.findall(query)
    ticker = ""
    for match in tickers:
        t = match[0] or match[1]
        if t and len(t) >= 2:
            ticker = t
            break

    return QueryIntent(
        ticker=ticker or "UNKNOWN",
        time_range_start=now - timedelta(days=7),
        time_range_end=now,
        focus_aspects=["sentiment", "risk", "technical"],
        keywords=[w for w in query.split() if len(w) > 1],
        blogger_filter=_BLOGGER_RE.findall(query),
    )


def parse_intent(user_query: str) -> QueryIntent:
    """解析用户查询为结构化 QueryIntent（主入口）。

    流程：
      1. 注入时间锚点到 system prompt
      2. 调用 Signal LLM 的 with_structured_output 获得 QueryIntent
      3. 补全缺失的时间范围字段（默认 7 天）
      4. 失败则走 _fallback_parse 正则兜底
    """
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.replace(day=1).strftime("%Y-%m-%d")

    try:
        llm = get_signal_llm()
        structured_llm = llm.with_structured_output(QueryIntent)
        prompt = _SYSTEM_PROMPT.format(
            today=today_str,
            week_start=week_start,
            month_start=month_start,
        )
        result = structured_llm.invoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_query},
        ])
        if result and result.ticker:
            # 补全未指定的时间范围为默认 7 天
            if not result.time_range_start:
                result.time_range_start = now - timedelta(days=7)
            if not result.time_range_end:
                result.time_range_end = now
            return result
    except Exception:
        pass

    return _fallback_parse(user_query)
