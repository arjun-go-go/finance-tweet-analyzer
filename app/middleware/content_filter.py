import re

from loguru import logger
from pydantic import BaseModel


class FilterResult(BaseModel):
    blocked: bool = False
    reason: str = ""


INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
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
