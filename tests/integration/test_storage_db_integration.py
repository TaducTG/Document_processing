import io
import uuid
import pytest
from sqlalchemy import select

from src.infrastructure.db.models import Document, DocumentStatus


@pytest.mark.asyncio
async def test_storage_and_db_persistence_integration(async_db_session, storage_service, sample_pdf_bytes):
    """Integration test verifying end-to-end file upload and DB metadata registration."""
    doc_id = str(uuid.uuid4())
    filename = "q3_financial_report.pdf"
    object_name = f"{doc_id}_{filename}"

    # 1. Upload to storage
    file_stream = io.BytesIO(sample_pdf_bytes)
    storage_path = storage_service.upload_file(
        file_obj=file_stream,
        object_name=object_name,
        bucket_name="raw-documents",
        content_type="application/pdf",
    )

    # 2. Persist in database
    new_doc = Document(
        id=doc_id,
        filename=filename,
        file_size_bytes=len(sample_pdf_bytes),
        mime_type="application/pdf",
        storage_path=storage_path,
        status=DocumentStatus.PENDING,
        doc_metadata={"department": "finance", "quarter": "Q3"},
    )
    async_db_session.add(new_doc)
    await async_db_session.commit()

    # 3. Retrieve and verify consistency
    query = select(Document).where(Document.id == doc_id)
    result = await async_db_session.execute(query)
    saved_doc = result.scalar_one()

    assert saved_doc.id == doc_id
    assert saved_doc.status == DocumentStatus.PENDING
    assert saved_doc.storage_path == "raw-documents/" + object_name
    assert saved_doc.doc_metadata["department"] == "finance"

    # 4. Verify file can be read back from storage using the persisted path
    downloaded_bytes = storage_service.download_file(object_name=object_name, bucket_name="raw-documents")
    assert downloaded_bytes == sample_pdf_bytes

