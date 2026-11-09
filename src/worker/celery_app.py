"""Celery application factory and configuration."""
from typing import Optional
from celery import Celery
from src.core.config import get_settings


def create_celery_app(
    broker_url: Optional[str] = None,
    result_backend: Optional[str] = None,
    task_always_eager: Optional[bool] = None,
) -> Celery:
    """Create and configure a Celery application instance."""
    settings = get_settings()

    app = Celery("doc_processor_worker")

    broker = broker_url or settings.CELERY_BROKER_URL
    backend = result_backend or settings.CELERY_RESULT_BACKEND

    app.conf.update(
        broker_url=broker,
        result_backend=backend,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        result_expires=3600,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
    )

    if task_always_eager is not None:
        app.conf.task_always_eager = task_always_eager

    # Autodiscover tasks in src.worker.tasks package
    app.autodiscover_tasks(["src.worker.tasks"])

    return app


# Singleton Celery application instance
celery_app = create_celery_app()
