"""Deduplication service implementing SHA-256 content hashing and idempotency checks."""
import hashlib
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import logger
from src.infrastructure.db.models import Document, DocumentStatus


class DeduplicationService:
    """Service to detect identical document uploads and prevent redundant ETL processing."""

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        """Compute hexadecimal SHA-256 digest of raw byte content."""
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest()

    @classmethod
    async def find_duplicate(
        cls,
        db: AsyncSession,
        sha256_hash: str,
    ) -> Optional[Document]:
        """Find an existing successfully completed document with matching SHA-256 hash."""
        # Query documents where status is COMPLETED
        stmt = select(Document).where(Document.status == DocumentStatus.COMPLETED)
        result = await db.execute(stmt)
        completed_docs = result.scalars().all()

        for doc in completed_docs:
            if doc.doc_metadata and doc.doc_metadata.get("sha256") == sha256_hash:
                logger.info(f"Duplicate document detected! Matches existing doc_id={doc.id}")
                return doc

        return None

    @classmethod
    async def check_content_duplicate(
        cls,
        db: AsyncSession,
        content: bytes,
    ) -> Tuple[bool, str, Optional[Document]]:
        """Calculate content hash and check if an identical completed document exists."""
        content_hash = cls.compute_sha256(content)
        existing_doc = await cls.find_duplicate(db, content_hash)
        is_dup = existing_doc is not None
        return is_dup, content_hash, existing_doc

