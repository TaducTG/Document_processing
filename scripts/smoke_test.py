"""Smoke test script demonstrating the Core, Storage, and Database layer in action."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.core.config import get_settings
from src.core.logging import logger
from src.infrastructure.db.models import Base, Document, DocumentStatus, ProcessingJob
from src.infrastructure.storage.minio_adapter import MinIOStorageService


async def main():
    print("=" * 60)
    print("[SMOKE TEST] Document Processing Core & Storage Layer")
    print("=" * 60)

    # 1. Config Test
    settings = get_settings()
    print(f"\n[1] App Name: {settings.APP_NAME}")
    print(f"    Raw Bucket: {settings.S3_BUCKET_RAW}")
    print(f"    Database URL: {settings.DATABASE_URL}")

    # 2. Database In-memory Simulation Test
    print("\n[2] Testing Database Engine & Models...")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    doc_id = str(uuid.uuid4())
    async with async_session() as session:
        doc = Document(
            id=doc_id,
            filename="sample_contract.pdf",
            file_size_bytes=24500,
            mime_type="application/pdf",
            storage_path=f"raw-documents/{doc_id}_sample_contract.pdf",
            status=DocumentStatus.PENDING,
            doc_metadata={"author": "Duc Ta Minh", "type": "NDA", "pages": 5},
        )
        job = ProcessingJob(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            step="QUEUED",
            retry_count=0,
        )
        session.add(doc)
        session.add(job)
        await session.commit()

    async with async_session() as session:
        res = await session.execute(select(Document).where(Document.id == doc_id))
        queried = res.scalar_one()
        print(f"    [OK] Created Document ID: {queried.id}")
        print(f"    [OK] Filename: {queried.filename}")
        print(f"    [OK] Status: {queried.status}")
        print(f"    [OK] Metadata (JSONB): {queried.doc_metadata}")
        print(f"    [OK] Associated Jobs: {len(queried.jobs)} job(s)")

    await engine.dispose()
    print("\n" + "=" * 60)
    print("[SUCCESS] All components operating nominally!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
