import json
from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import object_session, Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.deps import get_db
from app.models.user import User
from app.rag.parsers.base import ParserError
from app.rag.parsers.docx_parser import parse_docx
from app.rag.parsers.markdown_parser import parse_markdown
from app.rag.parsers.paste_parser import parse_paste
from app.rag.parsers.pdf_parser import parse_pdf
from app.rag.parsers.url_parser import fetch_url
from app.rag.repository import UserDocumentRepository
from app.rag.storage import DocumentStorage
from app.rag.embeddings import get_embedder
from app.rag.vector_store import get_vector_store
from app.scheduler.tasks import ingest_document_task
from app.schemas.document import (
    DocumentListResponse,
    DocumentPasteRequest,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUrlRequest,
)
from app.services.document_service import (
    DuplicateDocument,
    QuotaExceeded,
    create_document_record,
    delete_document,
    get_document_status,
    list_documents,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _handle_duplicate(doc, parsed_text, storage, user):
    """If a duplicate document exists and previously failed, retry ingestion."""
    if doc.status == "failed":
        doc.status = "pending"
        doc.error_detail = None
        storage.save(str(user.id), str(doc.id), parsed_text.encode("utf-8"), ".txt")
        db_session = object_session(doc)
        if db_session:
            db_session.commit()
        ingest_document_task.delay(str(doc.id))
    return doc


def _check_rag_enabled():
    if not settings.feature_rag_enabled:
        raise HTTPException(404, "RAG feature is not enabled")


def _get_storage() -> DocumentStorage:
    return DocumentStorage(settings.document_storage_root)


# 1. POST /upload — file upload (pdf, docx, md, txt)
@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    tickers: str = Form(default="[]"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.allowed_file_extensions:
        raise HTTPException(415, f"Unsupported file extension: {ext}")

    raw = await file.read()
    if len(raw) > settings.max_document_size_mb * 1024 * 1024:
        raise HTTPException(413, "File too large")

    # Parse
    try:
        if ext == ".pdf":
            parsed = parse_pdf(raw)
        elif ext == ".docx":
            parsed = parse_docx(raw)
        elif ext == ".md":
            parsed = parse_markdown(raw)
        else:  # .txt
            parsed = parse_paste(raw.decode("utf-8"))
    except (ParserError, UnicodeDecodeError) as e:
        raise HTTPException(422, f"Failed to parse file: {e}")

    storage = _get_storage()
    ticker_list = json.loads(tickers) if isinstance(tickers, str) else tickers
    try:
        doc = create_document_record(
            db,
            user_id=user.id,
            title=title or file.filename or "Untitled",
            text=parsed.text,
            source_type=ext.lstrip("."),
            raw_content=raw if ext in (".pdf", ".docx") else None,
            tickers=ticker_list,
            storage=storage,
        )
        # For text-based types, also save the parsed text as .txt for the Celery task
        if ext not in (".pdf", ".docx"):
            storage.save(str(user.id), str(doc.id), parsed.text.encode("utf-8"), ".txt")
        db.commit()
    except DuplicateDocument as e:
        return _handle_duplicate(e.document, parsed.text, storage, user)
    except QuotaExceeded as e:
        raise HTTPException(429, detail=e.reason)

    ingest_document_task.delay(str(doc.id))
    return doc


# 2. POST /paste — paste raw text
@router.post("/paste", response_model=DocumentResponse, status_code=201)
def paste_document(
    body: DocumentPasteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    parsed = parse_paste(body.content)
    storage = _get_storage()
    try:
        doc = create_document_record(
            db,
            user_id=user.id,
            title=body.title,
            text=parsed.text,
            source_type="paste",
            tickers=body.tickers,
            publish_date=body.publish_date,
            storage=storage,
        )
        storage.save(str(user.id), str(doc.id), parsed.text.encode("utf-8"), ".txt")
        db.commit()
    except DuplicateDocument as e:
        return _handle_duplicate(e.document, parsed.text, storage, user)
    except QuotaExceeded as e:
        raise HTTPException(429, detail=e.reason)

    ingest_document_task.delay(str(doc.id))
    return doc


# 3. POST /url — fetch and parse a URL
@router.post("/url", response_model=DocumentResponse, status_code=201)
def ingest_url(
    body: DocumentUrlRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    try:
        parsed = fetch_url(
            str(body.url),
            blocked_hosts=settings.url_blocked_hosts,
            timeout=settings.url_fetch_timeout_sec,
        )
    except (ParserError, ValueError) as e:
        raise HTTPException(422, f"Failed to fetch URL: {e}")

    storage = _get_storage()
    # Extract publish_date from URL parser metadata (ISO 8601 string → date)
    publish_date = None
    pt = parsed.metadata.get("publish_time", "")
    if pt:
        try:
            publish_date = date.fromisoformat(pt[:10])
        except (ValueError, IndexError):
            pass
    try:
        doc = create_document_record(
            db,
            user_id=user.id,
            title=body.title or parsed.metadata.get("title", str(body.url)),
            text=parsed.text,
            source_type="url",
            source_uri=str(body.url),
            tickers=body.tickers,
            publish_date=publish_date,
            storage=storage,
        )
        storage.save(str(user.id), str(doc.id), parsed.text.encode("utf-8"), ".txt")
        db.commit()
    except DuplicateDocument as e:
        return _handle_duplicate(e.document, parsed.text, storage, user)
    except QuotaExceeded as e:
        raise HTTPException(429, detail=e.reason)

    ingest_document_task.delay(str(doc.id))
    return doc


# 4. GET / — list documents
@router.get("", response_model=DocumentListResponse)
def list_user_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    items, total = list_documents(db, user_id=user.id, page=page, page_size=page_size)
    return DocumentListResponse(items=items, total=total, page=page, page_size=page_size)


# 5. GET /{document_id} — single document detail
@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    doc = get_document_status(db, user_id=user.id, document_id=document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


# 6. DELETE /{document_id}
@router.delete("/{document_id}", status_code=204)
def remove_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    storage = _get_storage()
    repo = UserDocumentRepository(get_vector_store(), get_embedder())
    try:
        delete_document(
            db, user_id=user.id, document_id=document_id, storage=storage, repo=repo
        )
    except ValueError:
        raise HTTPException(404, "Document not found")


# 7. GET /{document_id}/status
@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_doc_status(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    doc = get_document_status(db, user_id=user.id, document_id=document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc
