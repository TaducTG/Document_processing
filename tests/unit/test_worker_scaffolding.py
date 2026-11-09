"""Unit tests for distributed Celery worker scaffolding and configuration."""
import pytest
from unittest.mock import patch, MagicMock
from celery import Celery
from src.core.config import get_settings
from src.worker.celery_app import celery_app, create_celery_app
from src.worker.tasks.base import BaseDocumentTask


def test_celery_app_instance_type():
    """Verify celery_app is an initialized instance of Celery."""
    assert isinstance(celery_app, Celery)
    assert celery_app.main == "doc_processor_worker"


def test_celery_app_configuration():
    """Verify Celery is configured with Redis broker, result backend and secure JSON serialization."""
    settings = get_settings()
    
    # Check broker and backend URLs
    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert celery_app.conf.result_backend == settings.CELERY_RESULT_BACKEND
    
    # Check serialization safety
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert "json" in celery_app.conf.accept_content
    
    # Check timezone settings
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True


def test_create_celery_app_factory_override():
    """Verify factory allows overriding configuration for test or standalone environments."""
    custom_app = create_celery_app(
        broker_url="redis://localhost:6380/9",
        result_backend="redis://localhost:6380/10",
        task_always_eager=True,
    )
    assert custom_app.conf.broker_url == "redis://localhost:6380/9"
    assert custom_app.conf.result_backend == "redis://localhost:6380/10"
    assert custom_app.conf.task_always_eager is True


def test_base_document_task_success_lifecycle():
    """Verify BaseDocumentTask logs success and document metadata on task completion."""
    test_app = create_celery_app(task_always_eager=True)

    @test_app.task(base=BaseDocumentTask, bind=True, name="test.sample_success_task")
    def sample_success_task(self, doc_id: str):
        return {"status": "SUCCESS", "doc_id": doc_id}

    with patch("src.worker.tasks.base.logger") as mock_logger:
        target_doc_id = "doc-12345"
        res = sample_success_task.delay(doc_id=target_doc_id)
        assert res.get() == {"status": "SUCCESS", "doc_id": target_doc_id}
        
        # Verify logger.info was called on success
        assert mock_logger.info.called
        log_messages = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Task test.sample_success_task succeeded" in msg for msg in log_messages)


def test_base_document_task_failure_lifecycle():
    """Verify BaseDocumentTask intercepts errors and logs structured failure details."""
    test_app = create_celery_app(task_always_eager=True)

    @test_app.task(base=BaseDocumentTask, bind=True, name="test.sample_failing_task")
    def sample_failing_task(self, doc_id: str):
        raise ValueError(f"Corrupt document payload: {doc_id}")

    with patch("src.worker.tasks.base.logger") as mock_logger:
        res = sample_failing_task.delay(doc_id="doc-bad-999")
        with pytest.raises(ValueError, match="Corrupt document payload"):
            res.get()
            
        # Verify logger.error was called on failure
        assert mock_logger.error.called
        log_messages = [str(call) for call in mock_logger.error.call_args_list]
        assert any("Task test.sample_failing_task failed" in msg for msg in log_messages)


def test_base_document_task_retry_lifecycle():
    """Verify BaseDocumentTask on_retry hook logs warning with retry details."""
    task_instance = BaseDocumentTask()
    task_instance.name = "test.retry_task"
    
    exc = ConnectionError("Redis timeout during lock acquisition")
    
    with patch("src.worker.tasks.base.logger") as mock_logger:
        task_instance.on_retry(
            exc=exc,
            task_id="task-retry-001",
            args=("doc-retry-123",),
            kwargs={},
            einfo=None,
        )
        assert mock_logger.warning.called
        log_messages = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("Retrying task test.retry_task" in msg for msg in log_messages)

