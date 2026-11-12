"""Task dispatcher coordinating document ingestion, deduplication checks, and pipeline queuing."""
from typing import Any, Dict
from celery import shared_task
from loguru import logger

from src.worker.tasks.base import BaseDocumentTask


@shared_task(base=BaseDocumentTask, bind=True, name="tasks.dispatch_document")
def dispatch_document(
    self,
    document_id: str,
    sha256_hash: str | None = None,
    is_duplicate: bool = False,
    force_reprocess: bool = False,
) -> Dict[str, Any]:
    """Inspect document idempotency state and route to processing pipeline.
    
    If the document has been flagged as duplicate and reprocess is not forced,
    the dispatcher short-circuits the pipeline to conserve computational resources.
    """
    logger.info(
        f"Dispatching document task doc_id={document_id}, duplicate={is_duplicate}, force={force_reprocess}"
    )

    if is_duplicate and not force_reprocess:
        logger.info(f"Skipping redundant processing for duplicate doc_id={document_id}")
        return {
            "status": "SKIPPED_DUPLICATE",
            "document_id": document_id,
            "sha256": sha256_hash,
            "action": "reused_cached_output",
        }

    # In production/full worker flow, trigger downstream pipeline
    # Import lazily to avoid circular imports
    from src.worker.celery_app import celery_app
    pipeline_task = celery_app.send_task(
        "tasks.process_document_pipeline",
        args=[document_id],
        kwargs={"sha256_hash": sha256_hash},
    )

    return {
        "status": "DISPATCHED",
        "document_id": document_id,
        "pipeline_task_id": pipeline_task.id if pipeline_task else None,
        "action": "queued_for_processing",
    }

