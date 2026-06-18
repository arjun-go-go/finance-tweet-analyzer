import re

from loguru import logger
from pydantic import BaseModel


class FilterResult(BaseModel):
    blocked: bool = False
    reason: str = ""


INJECTION_PATTERNS = [
    # English patterns
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts|context)", re.IGNORECASE),
    re.compile(r"(forget|disregard|override|discard|bypass)\s+(all|previous|prior|above|earlier)\s+(instructions|rules|context|prompts|settings)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"new\s+role\s*:", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(r"(assistant|user|system)\s*:\s*", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a|an)\s+(unfiltered|unrestricted|different)\s+", re.IGNORECASE),
    # Chinese patterns
    re.compile(r"忽略(所有)?(之前的|上面的|先前的|以前的)?(指令|规则|提示|上下文|设定)", re.IGNORECASE),
    re.compile(r"忘记(之前的|先前的|所有的|上面的)?(指令|规则|提示|设定)", re.IGNORECASE),
    re.compile(r"覆盖(之前的|先前的|原来的)?(指令|规则|提示|设定)", re.IGNORECASE),
    re.compile(r"你(现在)?是(一个|一名)?(不受限制|无过滤|新)", re.IGNORECASE),
    re.compile(r"系统(提示|指令|规则|设定)\s*[:：]", re.IGNORECASE),
    re.compile(r"<\s*/?\s*系统\s*>", re.IGNORECASE),
    re.compile(r"(扮演|充当|模拟)\s*(一个|一名)?(不受限制|无过滤|不同)\s+", re.IGNORECASE),
]

MAX_MESSAGE_LENGTH = 10000


class ContentFilter:
    """Pluggable content safety pipeline. Phase 1: basic length + injection checks."""

    def check_input(self, message: str, user_id: str) -> FilterResult:
        if not message or not message.strip():
            return FilterResult(blocked=True, reason="消息不能为空")

        if len(message) > MAX_MESSAGE_LENGTH:
            logger.warning(
                "[ContentFilter] Message too long: user={} len={}",
                user_id,
                len(message),
            )
            return FilterResult(blocked=True, reason="消息过长，请控制在10000字符以内")

        for pattern in INJECTION_PATTERNS:
            if pattern.search(message):
                logger.warning(
                    "[ContentFilter] Potential injection: user={} pattern={}",
                    user_id,
                    pattern.pattern[:40],
                )
                return FilterResult(blocked=True, reason="检测到异常输入")

        return FilterResult(blocked=False)

    def check_output(self, response: str) -> FilterResult:
        return FilterResult(blocked=False)


content_filter = ContentFilter()
