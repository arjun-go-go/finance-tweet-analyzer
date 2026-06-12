"""Unit tests for PDF parser."""

import pytest

from app.rag.parsers.pdf_parser import parse_pdf
from app.rag.parsers.base import ParserError


def test_corrupted_bytes_raises():
    with pytest.raises(ParserError):
        parse_pdf(b"not a pdf")


def test_blank_pdf_raises_empty():
    """A blank PDF page has no extractable text — parser should raise ParserError."""
    from io import BytesIO
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    # Parser raises for empty/scanned PDFs
    with pytest.raises(ParserError, match="empty or scanned"):
        parse_pdf(buf.getvalue())


def test_valid_pdf_with_text():
    """Create a PDF with actual text content and verify extraction."""
    # Minimal valid PDF with embedded text (no external deps needed)
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n441\n%%EOF"
    )

    result = parse_pdf(pdf_bytes)
    assert "Hello World" in result.text
