import io
from functools import lru_cache
from typing import Any, BinaryIO, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.core.config import get_settings
from src.core.exceptions import StorageException
from src.core.logging import logger
from src.domain.interfaces.storage import StorageService


class MinIOStorageService(StorageService):
    """S3-compatible Object Storage Service backed by MinIO or AWS S3."""

    def __init__(self, s3_client: Optional[Any] = None):
        self.settings = get_settings()
        if s3_client is not None:
            self._client = s3_client
        else:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.settings.S3_ENDPOINT_URL,
                aws_access_key_id=self.settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=self.settings.S3_SECRET_ACCESS_KEY,
                region_name=self.settings.S3_REGION_NAME,
                config=Config(signature_version="s3v4"),
            )

    def _resolve_bucket(self, bucket_name: Optional[str]) -> str:
        return bucket_name or self.settings.S3_BUCKET_RAW

    def ensure_buckets(self) -> None:
        """Ensures that the default required buckets exist in the storage."""
        for bucket in [self.settings.S3_BUCKET_RAW, self.settings.S3_BUCKET_PROCESSED]:
            try:
                self._client.head_bucket(Bucket=bucket)
            except (ClientError, BotoCoreError):
                try:
                    self._client.create_bucket(Bucket=bucket)
                    logger.info(f"Initialized S3 bucket: {bucket}")
                except Exception as e:
                    logger.warning(f"Could not initialize bucket {bucket}: {e}")

    def upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        bucket_name: Optional[str] = None,
        content_type: str = "application/octet-stream",
    ) -> str:
        target_bucket = self._resolve_bucket(bucket_name)
        try:
            extra_args = {"ContentType": content_type}
            self._client.upload_fileobj(file_obj, target_bucket, object_name, ExtraArgs=extra_args)
            storage_path = f"{target_bucket}/{object_name}"
            logger.info(f"File uploaded successfully to {storage_path}")
            return storage_path
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to upload file {object_name} to bucket {target_bucket}: {str(e)}")
            raise StorageException(f"Storage operation failed during upload: {str(e)}") from e

    def download_file(self, object_name: str, bucket_name: Optional[str] = None) -> bytes:
        target_bucket = self._resolve_bucket(bucket_name)
        buffer = io.BytesIO()
        try:
            self._client.download_fileobj(target_bucket, object_name, buffer)
            buffer.seek(0)
            return buffer.read()
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to download file {object_name} from bucket {target_bucket}: {str(e)}")
            raise StorageException(f"Storage operation failed during download: {str(e)}") from e

    def generate_presigned_url(
        self,
        object_name: str,
        bucket_name: Optional[str] = None,
        expiry_seconds: int = 3600,
        method: str = "get_object",
    ) -> str:
        target_bucket = self._resolve_bucket(bucket_name)
        try:
            url: str = self._client.generate_presigned_url(
                ClientMethod=method,
                Params={"Bucket": target_bucket, "Key": object_name},
                ExpiresIn=expiry_seconds,
            )
            return url
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to generate presigned URL for {object_name}: {str(e)}")
            raise StorageException(f"Presigned URL generation failed: {str(e)}") from e

    def delete_file(self, object_name: str, bucket_name: Optional[str] = None) -> bool:
        target_bucket = self._resolve_bucket(bucket_name)
        try:
            self._client.delete_object(Bucket=target_bucket, Key=object_name)
            logger.info(f"Deleted object {object_name} from bucket {target_bucket}")
            return True
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to delete file {object_name}: {str(e)}")
            raise StorageException(f"Storage delete failed: {str(e)}") from e


@lru_cache()
def get_storage_service() -> StorageService:
    """Dependency provider for storage adapter singleton."""
    return MinIOStorageService()

