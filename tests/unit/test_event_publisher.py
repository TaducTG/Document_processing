"""Unit tests for Redis Pub/Sub event broadcaster."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.infrastructure.events.publisher import EventPublisher, event_publisher


def test_format_event_structure():
    """Verify event payload schema and progress clamping (0 - 100)."""
    event = EventPublisher.format_event(
        job_id="job-123",
        step="EXTRACTING_TEXT",
        progress=150,  # Should clamp to 100
        message="Text extraction underway",
        metadata={"page_count": 10},
    )

    assert event["job_id"] == "job-123"
    assert event["step"] == "EXTRACTING_TEXT"
    assert event["progress"] == 100
    assert event["message"] == "Text extraction underway"
    assert event["metadata"]["page_count"] == 10
    assert "timestamp" in event


def test_format_event_clamps_negative_progress():
    """Verify negative progress is clamped to 0."""
    event = EventPublisher.format_event(
        job_id="job-123",
        step="INIT",
        progress=-20,
        message="Initializing",
    )
    assert event["progress"] == 0


def test_sync_publish_progress_success():
    """Verify sync publish publishes JSON payload to formatted Redis channel."""
    publisher = EventPublisher(redis_url="redis://localhost:6380/0")
    
    mock_redis = MagicMock()
    mock_redis.publish.return_value = 2  # 2 active listeners
    publisher._sync_client = mock_redis

    listeners = publisher.publish_progress(
        job_id="job-abc-456",
        step="RUNNING_OCR",
        progress=60,
        message="OCR processing page 3",
    )

    assert listeners == 2
    mock_redis.publish.assert_called_once()
    channel_called, payload_called = mock_redis.publish.call_args[0]
    assert channel_called == "job_events:job-abc-456"
    
    parsed_payload = json.loads(payload_called)
    assert parsed_payload["step"] == "RUNNING_OCR"
    assert parsed_payload["progress"] == 60


def test_sync_publish_graceful_exception_handling():
    """Verify publisher catches connection failure gracefully without re-raising."""
    publisher = EventPublisher(redis_url="redis://localhost:6380/0")
    
    mock_redis = MagicMock()
    mock_redis.publish.side_effect = ConnectionError("Redis unreachable")
    publisher._sync_client = mock_redis

    listeners = publisher.publish_progress(
        job_id="job-fail-789",
        step="FAILED",
        progress=0,
        message="Fatal error",
    )
    assert listeners == 0


@pytest.mark.asyncio
async def test_async_publish_progress():
    """Verify async publish properly awaits Redis publish coroutine."""
    publisher = EventPublisher(redis_url="redis://localhost:6380/0")
    
    mock_aioredis = MagicMock()
    mock_aioredis.publish = AsyncMock(return_value=1)
    publisher._async_client = mock_aioredis

    listeners = await publisher.publish_progress_async(
        job_id="job-async-101",
        step="COMPLETED",
        progress=100,
        message="Done",
    )

    assert listeners == 1
    mock_aioredis.publish.assert_called_once()

