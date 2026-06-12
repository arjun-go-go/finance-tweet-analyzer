import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.rag.parsers.base import ParsedDocument, ParserError


def parse_pdf(content: bytes) -> ParsedDocument:
    try:
        reader = PdfReader(io.BytesIO(content))
    except (PdfReadError, ValueError) as e:
        raise ParserError(f"Failed to open PDF: {e}") from e

    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception as e:
            raise ParserError(f"Failed to extract page text: {e}") from e
        pages.append(text)

    joined = "\n".join(p.strip() for p in pages if p and p.strip())
    if not joined:
        raise ParserError("PDF appears empty or scanned (no extractable text)")

    metadata: dict = {}
    info = getattr(reader, "metadata", None)
    if info is not None:
        title = getattr(info, "title", None)
        if title:
            metadata["title"] = str(title)

    return ParsedDocument(text=joined, metadata=metadata)
