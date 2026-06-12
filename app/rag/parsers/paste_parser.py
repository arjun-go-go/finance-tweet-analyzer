from app.rag.parsers.base import ParsedDocument, ParserError


def parse_paste(text: str) -> ParsedDocument:
    if text is None:
        raise ParserError("Paste content is required")

    normalised = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    if not normalised.strip():
        raise ParserError("Paste content is empty")
    return ParsedDocument(text=normalised, metadata={})
