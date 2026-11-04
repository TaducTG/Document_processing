import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import InvalidFileFormatException
from src.core.logging import logger
from src.domain.interfaces.storage import StorageService
from src.infrastructure.db.models import Document, DocumentStatus
from src.infrastructure.db.session import get_db_session
from src.infrastructure.storage.minio_adapter import get_storage_service
from src.schemas.document import DocumentResponse, PresignedUploadRequest, PresignedUploadResponse
from src.services.ingestion_service import IngestionService

try:
    from src.etl.parsers.complex_pdf_parser import ComplexPDFParser
except ImportError:
    ComplexPDFParser = None

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentResponse:
    """Uploads a document (supports .md, .txt, .pdf, .docx), parses markdown metadata and stages in storage."""
    service = IngestionService(db=db, storage=storage)
    try:
        doc = await service.ingest_file(
            file_obj=file.file,
            filename=file.filename or "unnamed_document",
            mime_type=file.content_type or "application/octet-stream",
        )
        return DocumentResponse.model_validate(doc)
    except InvalidFileFormatException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> List[DocumentResponse]:
    """Lists ingested documents ordered by creation time descending."""
    query = select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    docs = result.scalars().all()
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    """Retrieves document details and extracted metadata by ID."""
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return DocumentResponse.model_validate(doc)


@router.post("/presigned-upload", response_model=PresignedUploadResponse)
async def create_presigned_upload(
    req: PresignedUploadRequest,
    storage: StorageService = Depends(get_storage_service),
) -> PresignedUploadResponse:
    """Generates a temporary S3/MinIO presigned upload URL for large direct client uploads."""
    import uuid
    doc_id = str(uuid.uuid4())
    safe_name = f"{doc_id}_{req.filename}"

    upload_url = storage.generate_presigned_url(
        object_name=safe_name,
        method="put_object",
        expiry_seconds=3600,
    )

    return PresignedUploadResponse(
        document_id=doc_id,
        storage_path=f"raw-documents/{safe_name}",
        upload_url=upload_url,
        expires_in_seconds=3600,
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageService = Depends(get_storage_service),
) -> dict:
    """Deletes a document from both PostgreSQL database and MinIO storage."""
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    # 1. Delete binary object from storage if path exists
    settings = get_settings()
    if doc.storage_path and "/" in doc.storage_path:
        bucket, obj_name = doc.storage_path.split("/", 1)
        try:
            storage.delete_file(object_name=obj_name, bucket_name=bucket)
        except Exception as e:
            logger.warning(f"Storage delete warning for raw file {doc.storage_path}: {e}")

    # Also clean up processed-output artifact if it exists
    processed_artifact_name = f"{document_id}_extracted.json"
    try:
        storage.delete_file(object_name=processed_artifact_name, bucket_name=settings.S3_BUCKET_PROCESSED)
    except Exception as e:
        logger.warning(f"Storage delete warning for processed artifact: {e}")

    # 2. Delete database record (cascades to processing_jobs)
    await db.delete(doc)
    await db.commit()

    return {
        "success": True,
        "message": f"Document '{doc.filename}' deleted successfully",
        "id": document_id,
    }


@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: str,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentResponse:
    """Re-extracts structured metadata, tables, and entities from raw stored file."""
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    if not doc.storage_path or "/" not in doc.storage_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no valid storage path to reprocess",
        )

    bucket, obj_name = doc.storage_path.split("/", 1)
    file_bytes = storage.download_file(object_name=obj_name, bucket_name=bucket)

    service = IngestionService(db=db, storage=storage)
    ext = service.validate_filename(doc.filename)

    if ext in {".md", ".txt"}:
        doc.doc_metadata = service.parse_markdown_metadata(file_bytes)
        doc.extracted_text = file_bytes.decode("utf-8", errors="replace")
        doc.status = DocumentStatus.COMPLETED
    elif ext == ".pdf":
        pdf_parser = ComplexPDFParser()
        parsed = pdf_parser.parse(file_bytes)
        doc.extracted_text = parsed.extracted_text
        doc.doc_metadata = {
            "title": parsed.title,
            "page_count": parsed.page_count,
            "word_count": parsed.word_count,
            "char_count": parsed.char_count,
            "has_tables": parsed.has_tables,
            "tables": parsed.tables,
            "entities": parsed.entities.model_dump(),
            "confidence_score": parsed.confidence_score,
            "format": "PDF",
        }
        doc.status = DocumentStatus.COMPLETED

    # Export updated structured JSON to processed-output bucket
    try:
        output_payload = {
            "document_id": document_id,
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "file_size_bytes": doc.file_size_bytes,
            "metadata": doc.doc_metadata,
            "extracted_text": doc.extracted_text,
        }
        json_bytes = json.dumps(output_payload, ensure_ascii=False, indent=2).encode("utf-8")
        output_name = f"{document_id}_extracted.json"
        processed_path = storage.upload_file(
            file_obj=io.BytesIO(json_bytes),
            object_name=output_name,
            bucket_name=settings.S3_BUCKET_PROCESSED,
            content_type="application/json",
        )
        doc.doc_metadata["processed_output_path"] = processed_path
    except Exception as e:
        logger.warning(f"Could not export processed artifact during reprocess: {e}")

    await db.commit()
    await db.refresh(doc)
    return DocumentResponse.model_validate(doc)

