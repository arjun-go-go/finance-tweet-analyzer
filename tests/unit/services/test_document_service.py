"""Unit tests for document_service — quota checks and deduplication."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.document_service import (
    check_quota,
    create_document_record,
    QuotaExceeded,
    DuplicateDocument,
)


@patch("app.services.document_service.settings")
def test_quota_max_documents(mock_settings):
    mock_settings.max_documents_per_user = 5
    mock_settings.max_document_size_mb = 20
    mock_settings.max_total_size_mb_per_user = 500
    db = MagicMock()
    db.scalar.side_effect = [5, 0]  # count=5 (at limit), total_size=0
    with pytest.raises(QuotaExceeded, match="max_documents_per_user"):
        check_quota(db, uuid.uuid4(), 100)


@patch("app.services.document_service.settings")
def test_quota_file_too_large(mock_settings):
    mock_settings.max_documents_per_user = 200
    mock_settings.max_document_size_mb = 1
    mock_settings.max_total_size_mb_per_user = 500
    db = MagicMock()
    db.scalar.side_effect = [0, 0]  # count=0, total=0
    with pytest.raises(QuotaExceeded, match="max_document_size_mb"):
        check_quota(db, uuid.uuid4(), 2 * 1024 * 1024)  # 2MB > 1MB limit


@patch("app.services.document_service.settings")
def test_quota_total_size_exceeded(mock_settings):
    mock_settings.max_documents_per_user = 200
    mock_settings.max_document_size_mb = 20
    mock_settings.max_total_size_mb_per_user = 1  # 1MB total
    db = MagicMock()
    db.scalar.side_effect = [0, 900_000]  # count=0, existing=900KB
    with pytest.raises(QuotaExceeded, match="max_total_size_mb_per_user"):
        check_quota(db, uuid.uuid4(), 200_000)  # +200KB > 1MB


@patch("app.services.document_service.settings")
def test_quota_passes(mock_settings):
    mock_settings.max_documents_per_user = 200
    mock_settings.max_document_size_mb = 20
    mock_settings.max_total_size_mb_per_user = 500
    db = MagicMock()
    db.scalar.side_effect = [5, 1000]
    # Should not raise
    check_quota(db, uuid.uuid4(), 1000)


@patch("app.services.document_service.settings")
def test_duplicate_raises(mock_settings):
    mock_settings.max_documents_per_user = 200
    mock_settings.max_document_size_mb = 20
    mock_settings.max_total_size_mb_per_user = 500
    db = MagicMock()
    existing_doc = MagicMock()
    existing_doc.id = uuid.uuid4()
    # First scalar call: dedupe check returns existing doc
    # Second scalar call would be for count (if reached), but it won't be reached
    db.scalar.return_value = existing_doc
    storage = MagicMock()
    with pytest.raises(DuplicateDocument):
        create_document_record(
            db,
            user_id=uuid.uuid4(),
            title="test",
            text="hello",
            source_type="paste",
            storage=storage,
        )
