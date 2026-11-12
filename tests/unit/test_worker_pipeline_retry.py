"""Unit tests for pipeline task execution, retry backoff, and DLQ handling."""
import pytest
from unittest.mock import MagicMock, patch
from celery.exceptions import Retry

from src.worker.celery_app import create_celery_app
from src.worker.tasks.pipeline import (
    DeadLetterQueueHandler,
    process_document_pipeline,
)


def test_pipeline_successful_execution():
    """Verify document pipeline executes successfully and completes all steps."""
    test_app = create_celery_app(task_always_eager=True)
    
    result = process_document_pipeline.apply(
        kwargs={"document_id": "doc-success-101", "sha256_hash": "abc12345"}
    ).get()

    assert result["status"] == "COMPLETED"
    assert result["document_id"] == "doc-success-101"
    assert "EXTRACTING_TEXT" in result["steps_completed"]
    assert result["retry_count"] == 0


def test_pipeline_retry_trigger_on_transient_error():
    """Verify pipeline initiates retry when error occurs and retry limit is not reached."""
    process_document_pipeline.push_request(retries=0, id="task-retry-test-01")
    try:
        with patch.object(process_document_pipeline, "retry", side_effect=Retry("Task scheduled for retry")) as mock_retry:
            with pytest.raises(Retry):
                process_document_pipeline.run(
                    document_id="doc-retry-001",
                    simulate_failure=True,
                )
            mock_retry.assert_called_once()
    finally:
        process_document_pipeline.pop_request()


def test_pipeline_dlq_escalation_on_max_retries_exceeded():
    """Verify pipeline sends task to Dead Letter Queue when max retries is reached."""
    DeadLetterQueueHandler.dlq_records.clear()

    process_document_pipeline.push_request(retries=3, id="task-dlq-exhausted-99")
    try:
        with pytest.raises(RuntimeError, match="Simulated processing error"):
            process_document_pipeline.run(
                document_id="doc-dlq-failed-99",
                simulate_failure=True,
            )

        # Verify DLQ record was created
        assert len(DeadLetterQueueHandler.dlq_records) == 1
        dlq_entry = DeadLetterQueueHandler.dlq_records[0]
        assert dlq_entry["document_id"] == "doc-dlq-failed-99"
        assert dlq_entry["status"] == "DLQ_EXHAUSTED"
        assert dlq_entry["retry_count"] == 3
        assert "Simulated processing error" in dlq_entry["error_message"]
    finally:
        process_document_pipeline.pop_request()
