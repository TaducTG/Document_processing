"""Storage adapters package."""
from src.infrastructure.storage.minio_adapter import MinIOStorageService, get_storage_service

__all__ = ["MinIOStorageService", "get_storage_service"]

