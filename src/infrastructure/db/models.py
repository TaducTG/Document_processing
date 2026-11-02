import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """Document entity tracking stored files and their extraction states."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    storage_path = Column(String(500), nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False, index=True)

    # Use JSONB on PostgreSQL for GIN indexing, fallback to standard JSON for SQLite tests
    doc_metadata = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True, default=dict)
    extracted_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    jobs = relationship("ProcessingJob", back_populates="document", cascade="all, delete-orphan", lazy="selectin")


class ProcessingJob(Base):
    """Audit and execution state for background ETL tasks."""

    __tablename__ = "processing_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    step = Column(String(50), nullable=False, default="QUEUED")
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    document = relationship("Document", back_populates="jobs")

