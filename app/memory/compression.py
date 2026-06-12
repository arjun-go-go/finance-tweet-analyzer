from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.core.config import settings

COMPRESSION_THRESHOLD = 40
KEEP_RECENT = 10

SUMMARY_PROMPT = """请将以下对话历史压缩为一段简洁的中文摘要（不超过500字），保留关键信息：
- 用户关注的博主和标的
- 已执行的操作（获取资料、采集推文、分析等）
- 重要的分析结论
- 用户表达的偏好

{existing_summary}

对话内容:
{conversation}

请输出摘要："""


def should_compress(messages: list) -> bool:
    human_count = sum(1 for m in messages if hasattr(m, "type") and m.type == "human")
    return human_count > settings.compression_threshold


def _format_messages(messages: list) -> str:
    lines = []
    for msg in messages:
        if hasattr(msg, "type") and hasattr(msg, "content"):
            role = "用户" if msg.type == "human" else "助手"
            lines.append(f"{role}: {msg.content[:200]}")
    return "\n".join(lines)


def compress_messages(messages: list, llm) -> list:
    if not should_compress(messages):
        return messages

    keep = settings.compression_keep_recent
    older = messages[:-keep]
    recent = messages[-keep:]

    existing_summary = ""
    if older and hasattr(older[0], "content") and older[0].content.startswith("[对话摘要]"):
        existing_summary = f"之前的摘要: {older[0].content}"
        older = older[1:]

    conversation_text = _format_messages(older)

    prompt = SUMMARY_PROMPT.format(
        existing_summary=existing_summary,
        conversation=conversation_text,
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        summary_content = f"[对话摘要] {response.content}"
        logger.info(
            "[Compression] 压缩 {} 条 → {} 条",
            len(messages),
            1 + len(recent),
        )
        return [SystemMessage(content=summary_content)] + recent
    except Exception as e:
        logger.error("[Compression] 压缩失败: {}", e)
        return messages
