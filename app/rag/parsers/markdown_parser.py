from app.rag.parsers.base import ParsedDocument, ParserError


def parse_markdown(content: bytes) -> ParsedDocument:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ParserError(f"Markdown/TXT must be UTF-8: {e}") from e

    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    text = text.replace("\x00", "")

    if not text.strip():
        raise ParserError("Markdown/TXT is empty")
    return ParsedDocument(text=text, metadata={})
