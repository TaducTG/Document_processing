"""Base task class with structured logging and error handling for Celery workers."""
from typing import Any, Optional
from celery import Task
from loguru import logger


class BaseDocumentTask(Task):
    """Abstract base task for document processing pipeline tasks.
    
    Provides standardized logging, metadata binding, and error tracing
    across all task executions.
    """

    abstract = True

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        """Lifecycle hook triggered when task completes successfully."""
        logger.info(
            f"Task {self.name} succeeded (task_id={task_id})",
            task_id=task_id,
            task_name=self.name,
            args=args,
            kwargs=kwargs,
            return_value=retval,
        )

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Optional[Any],
    ) -> None:
        """Lifecycle hook triggered when task raises an unhandled exception."""
        logger.error(
            f"Task {self.name} failed (task_id={task_id}): {exc}",
            task_id=task_id,
            task_name=self.name,
            args=args,
            kwargs=kwargs,
            exception=str(exc),
            exc_info=exc,
        )

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Optional[Any],
    ) -> None:
        """Lifecycle hook triggered when task is scheduled for retry."""
        logger.warning(
            f"Retrying task {self.name} (task_id={task_id}) due to {exc}",
            task_id=task_id,
            task_name=self.name,
            args=args,
            kwargs=kwargs,
            exception=str(exc),
        )
