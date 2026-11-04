from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from src.infrastructure.db.models import DocumentStatus


class DocumentResponse(BaseModel):
    """Schema representing a stored document."""

    id: str
    filename: str
    file_size_bytes: int
    mime_type: str
    storage_path: str
    status: DocumentStatus
    doc_metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PresignedUploadRequest(BaseModel):
    """Request payload for generating direct-to-storage presigned upload URL."""

    filename: str
    file_size_bytes: int
    content_type: str = "text/markdown"


class PresignedUploadResponse(BaseModel):
    """Response containing document ID and direct upload URL."""

    document_id: str
    storage_path: str
    upload_url: str
    expires_in_seconds: int = 3600

