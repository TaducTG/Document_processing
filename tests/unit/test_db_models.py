import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base


@pytest.mark.asyncio
async def test_create_and_query_document():
    from src.infrastructure.db.models import Base, Document, DocumentStatus, ProcessingJob

    # In-memory async SQLite engine for lightning-fast testing
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    doc_id = str(uuid.uuid4())
    async with async_session() as session:
        new_doc = Document(
            id=doc_id,
            filename="invoice_2026.pdf",
            file_size_bytes=10240,
            mime_type="application/pdf",
            storage_path=f"raw-documents/{doc_id}.pdf",
            status=DocumentStatus.PENDING,
            doc_metadata={"pages": 3, "vendor": "Acme Corp"},
        )
        session.add(new_doc)

        job = ProcessingJob(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            step="INITIALIZATION",
            retry_count=0,
        )
        session.add(job)
        await session.commit()

    # Query back through the public interface
    async with async_session() as session:
        result = await session.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one()

        assert doc.id == doc_id
        assert doc.filename == "invoice_2026.pdf"
        assert doc.status == DocumentStatus.PENDING
        assert doc.doc_metadata["vendor"] == "Acme Corp"
        assert len(doc.jobs) == 1
        assert doc.jobs[0].step == "INITIALIZATION"

    await test_engine.dispose()

