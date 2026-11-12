"""Unit tests for SHA-256 deduplication and task dispatcher routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.deduplication_service import DeduplicationService
from src.infrastructure.db.models import Document, DocumentStatus
from src.worker.celery_app import create_celery_app
from src.worker.tasks.dispatcher import dispatch_document


def test_sha256_computation_deterministic():
    """Verify SHA-256 computation produces consistent hashes for identical byte payloads."""
    payload_a = b"Sample Invoice Content #12345"
    payload_b = b"Sample Invoice Content #12345"
    payload_c = b"Different Invoice Content #67890"

    hash_a = DeduplicationService.compute_sha256(payload_a)
    hash_b = DeduplicationService.compute_sha256(payload_b)
    hash_c = DeduplicationService.compute_sha256(payload_c)

    assert hash_a == hash_b
    assert hash_a != hash_c
    assert len(hash_a) == 64


@pytest.mark.asyncio
async def test_find_duplicate_with_matching_hash():
    """Verify deduplication service detects matching completed document."""
    mock_db = MagicMock()
    
    doc1 = Document(
        id="doc-original-1",
        filename="contract.pdf",
        status=DocumentStatus.COMPLETED,
        doc_metadata={"sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"},
    )
    doc2 = Document(
        id="doc-other-2",
        filename="invoice.pdf",
        status=DocumentStatus.COMPLETED,
        doc_metadata={"sha256": "different_hash"},
    )
    
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [doc1, doc2]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    target_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    duplicate = await DeduplicationService.find_duplicate(mock_db, target_hash)
    
    assert duplicate is not None
    assert duplicate.id == "doc-original-1"


@pytest.mark.asyncio
async def test_find_duplicate_returns_none_when_unmatched():
    """Verify deduplication returns None if no completed document matches the hash."""
    mock_db = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    duplicate = await DeduplicationService.find_duplicate(mock_db, "unmatched_hash_123")
    assert duplicate is None


def test_dispatcher_skips_duplicate():
    """Verify task dispatcher short-circuits execution when duplicate is flagged."""
    test_app = create_celery_app(task_always_eager=True)
    
    result = dispatch_document.apply(
        kwargs={
            "document_id": "doc-duplicate-01",
            "sha256_hash": "hash123",
            "is_duplicate": True,
            "force_reprocess": False,
        }
    ).get()

    assert result["status"] == "SKIPPED_DUPLICATE"
    assert result["action"] == "reused_cached_output"
    assert result["document_id"] == "doc-duplicate-01"


def test_dispatcher_routes_new_document():
    """Verify task dispatcher dispatches new documents to the processing pipeline."""
    test_app = create_celery_app(task_always_eager=True)
    
    with patch("src.worker.celery_app.celery_app.send_task") as mock_send_task:
        mock_task_instance = MagicMock()
        mock_task_instance.id = "pipeline-task-uuid-456"
        mock_send_task.return_value = mock_task_instance

        result = dispatch_document.apply(
            kwargs={
                "document_id": "doc-new-02",
                "sha256_hash": "hash_brand_new",
                "is_duplicate": False,
                "force_reprocess": False,
            }
        ).get()

        assert result["status"] == "DISPATCHED"
        assert result["pipeline_task_id"] == "pipeline-task-uuid-456"
        assert result["action"] == "queued_for_processing"
        mock_send_task.assert_called_once_with(
            "tasks.process_document_pipeline",
            args=["doc-new-02"],
            kwargs={"sha256_hash": "hash_brand_new"},
        )
