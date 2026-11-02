from abc import ABC, abstractmethod
from typing import BinaryIO, Optional


class StorageService(ABC):
    """Abstract interface for object storage operations (S3 / MinIO)."""

    @abstractmethod
    def upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        bucket_name: Optional[str] = None,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Uploads a binary stream to object storage and returns the storage path."""
        pass

    @abstractmethod
    def download_file(self, object_name: str, bucket_name: Optional[str] = None) -> bytes:
        """Downloads object bytes from storage."""
        pass

    @abstractmethod
    def generate_presigned_url(
        self,
        object_name: str,
        bucket_name: Optional[str] = None,
        expiry_seconds: int = 3600,
        method: str = "get_object",
    ) -> str:
        """Generates a temporary presigned URL for direct client access."""
        pass

    @abstractmethod
    def delete_file(self, object_name: str, bucket_name: Optional[str] = None) -> bool:
        """Deletes an object from storage."""
        pass

