"""Document service — quota enforcement, deduplication, and status orchestration."""

from __future__ import annotations

import hashlib
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.rag.repository import UserDocumentRepository
from app.rag.storage import DocumentStorage


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class QuotaExceeded(Exception):
    """Raised when user exceeds document storage quotas."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class DuplicateDocument(Exception):
    """Raised when same content_hash already exists for the user (idempotent)."""

    def __init__(self, existing_document: Document):
        self.document = existing_document
        super().__init__(f"Duplicate: {existing_document.id}")


# ---------------------------------------------------------------------------
# Quota check
# ---------------------------------------------------------------------------


def check_quota(db: Session, user_id: UUID, incoming_size_bytes: int) -> None:
    """Raise QuotaExceeded if adding incoming_size_bytes would violate limits."""

    count = db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.user_id == user_id, Document.status != "deleted")
    )
    if count >= settings.max_documents_per_user:
        raise QuotaExceeded("max_documents_per_user")

    total = db.scalar(
        select(func.coalesce(func.sum(Document.file_size_bytes), 0)).where(
            Document.user_id == user_id, Document.status != "deleted"
        )
    )
    if total + incoming_size_bytes > settings.max_total_size_mb_per_user * 1024 * 1024:
        raise QuotaExceeded("max_total_size_mb_per_user")

    if incoming_size_bytes > settings.max_document_size_mb * 1024 * 1024:
        raise QuotaExceeded("max_document_size_mb")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_document_record(
    db: Session,
    *,
    user_id: UUID,
    title: str,
    text: str,
    source_type: str,
    source_uri: str | None = None,
    raw_content: bytes | None = None,
    tickers: list[str] | None = None,
    publish_date: date | None = None,
    storage: DocumentStorage,
) -> Document:
    """Insert a new Document row with deduplication and quota checks.

    Runs within the caller's transaction (no commit issued here).
    Returns the persisted Document instance with its generated id.
    """

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    existing = db.scalar(
        select(Document)
        .where(Document.user_id == user_id, Document.content_hash == content_hash)
        .where(Document.status != "deleted")
    )
    if existing:
        raise DuplicateDocument(existing)

    # Hard-delete any soft-deleted documents with the same hash so the
    # partial unique index doesn't block the new INSERT.
    deleted_dupes = db.execute(
        select(Document)
        .where(Document.user_id == user_id, Document.content_hash == content_hash)
        .where(Document.status == "deleted")
    ).scalars().all()
    for dupe in deleted_dupes:
        db.delete(dupe)

    file_size = len(raw_content) if raw_content else len(text.encode("utf-8"))
    check_quota(db, user_id, file_size)

    doc = Document(
        user_id=user_id,
        title=title,
        source_type=source_type,
        source_uri=source_uri,
        content_hash=content_hash,
        char_count=len(text),
        file_size_bytes=file_size,
        tickers=tickers or [],
        publish_date=publish_date,
        status="pending",
    )
    db.add(doc)
    db.flush()  # materialise doc.id

    if raw_content:
        ext = {"pdf": ".pdf", "docx": ".docx"}.get(source_type, ".bin")
        storage.save(str(user_id), str(doc.id), raw_content, ext)

    return doc


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def delete_document(
    db: Session,
    *,
    user_id: UUID,
    document_id: UUID,
    storage: DocumentStorage,
    repo: UserDocumentRepository,
) -> None:
    """Soft-delete a document, purge its vectors and disk blobs."""

    doc = db.scalar(
        select(Document).where(
            Document.id == document_id, Document.user_id == user_id
        )
    )
    if not doc:
        raise ValueError("Document not found")

    doc.status = "deleted"

    # Vector cleanup
    repo.delete_document(user_id=user_id, document_id=document_id)

    # Disk cleanup
    if doc.source_uri and doc.source_type in ("pdf", "docx"):
        storage.delete(doc.source_uri)

    db.commit()


# ---------------------------------------------------------------------------
# Read / List
# ---------------------------------------------------------------------------


def get_document_status(
    db: Session, *, user_id: UUID, document_id: UUID
) -> Document | None:
    """Fetch a single document scoped to user_id."""
    return db.scalar(
        select(Document).where(
            Document.id == document_id, Document.user_id == user_id
        )
    )


def list_documents(
    db: Session, *, user_id: UUID, page: int = 1, page_size: int = 20
) -> tuple[list[Document], int]:
    """Paginated listing of non-deleted documents for a user."""

    base = select(Document).where(
        Document.user_id == user_id, Document.status != "deleted"
    )
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    items = db.scalars(
        base.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total
