"""Redis Pub/Sub event broadcaster for real-time document processing updates."""
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import redis
import redis.asyncio as aioredis
from loguru import logger

from src.core.config import get_settings


class EventPublisher:
    """Publishes progress events over Redis Pub/Sub channels."""

    def __init__(self, redis_url: Optional[str] = None):
        self.settings = get_settings()
        self.redis_url = redis_url or self.settings.REDIS_URL
        self._sync_client: Optional[redis.Redis] = None
        self._async_client: Optional[aioredis.Redis] = None

    @property
    def sync_client(self) -> redis.Redis:
        """Lazy-loaded synchronous Redis client."""
        if self._sync_client is None:
            self._sync_client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._sync_client

    @property
    def async_client(self) -> aioredis.Redis:
        """Lazy-loaded asynchronous Redis client."""
        if self._async_client is None:
            self._async_client = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._async_client

    @staticmethod
    def get_channel(job_id: str) -> str:
        """Format Pub/Sub channel key for a specific job."""
        return f"job_events:{job_id}"

    @classmethod
    def format_event(
        cls,
        job_id: str,
        step: str,
        progress: int,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Construct normalized event dictionary."""
        return {
            "job_id": job_id,
            "step": step,
            "progress": max(0, min(100, progress)),
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

    def publish_progress(
        self,
        job_id: str,
        step: str,
        progress: int,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Synchronously broadcast progress event over Redis (used in Celery workers)."""
        channel = self.get_channel(job_id)
        event_data = self.format_event(job_id, step, progress, message, metadata)
        payload = json.dumps(event_data)

        try:
            receivers = self.sync_client.publish(channel, payload)
            logger.debug(f"[EventPublisher] Published to {channel} ({receivers} listeners): {event_data['step']} {progress}%")
            return receivers
        except Exception as exc:
            logger.warning(f"[EventPublisher] Failed to broadcast event for job_id={job_id}: {exc}")
            return 0

    async def publish_progress_async(
        self,
        job_id: str,
        step: str,
        progress: int,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Asynchronously broadcast progress event over Redis (used in FastAPI endpoints)."""
        channel = self.get_channel(job_id)
        event_data = self.format_event(job_id, step, progress, message, metadata)
        payload = json.dumps(event_data)

        try:
            receivers = await self.async_client.publish(channel, payload)
            return receivers
        except Exception as exc:
            logger.warning(f"[EventPublisher] Async broadcast error for job_id={job_id}: {exc}")
            return 0


# Singleton instance
event_publisher = EventPublisher()

