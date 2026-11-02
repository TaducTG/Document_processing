import io
import pytest
from unittest.mock import MagicMock
from botocore.exceptions import ClientError


def test_storage_adapter_upload_and_download_mocked():
    from src.domain.interfaces.storage import StorageService
    from src.infrastructure.storage.minio_adapter import MinIOStorageService

    mock_s3 = MagicMock()
    # Mock download_fileobj
    def fake_download(Bucket, Key, Fileobj):
        Fileobj.write(b"Hello document content")

    mock_s3.download_fileobj.side_effect = fake_download
    mock_s3.generate_presigned_url.return_value = "http://localhost:9000/raw-documents/test.pdf?signature=123"

    adapter = MinIOStorageService(s3_client=mock_s3)
    assert isinstance(adapter, StorageService)

    # 1. Upload
    file_bytes = b"Sample PDF binary"
    result_path = adapter.upload_file(
        file_obj=io.BytesIO(file_bytes),
        object_name="test.pdf",
        bucket_name="raw-documents",
        content_type="application/pdf",
    )
    assert result_path == "raw-documents/test.pdf"
    mock_s3.upload_fileobj.assert_called_once()

    # 2. Download
    content = adapter.download_file(object_name="test.pdf", bucket_name="raw-documents")
    assert content == b"Hello document content"

    # 3. Presigned URL
    url = adapter.generate_presigned_url(object_name="test.pdf", bucket_name="raw-documents", expiry_seconds=3600)
    assert "signature=123" in url


def test_storage_adapter_error_handling():
    from src.infrastructure.storage.minio_adapter import MinIOStorageService
    from src.core.exceptions import StorageException

    mock_s3 = MagicMock()
    error_response = {"Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist"}}
    mock_s3.upload_fileobj.side_effect = ClientError(error_response, "PutObject")

    adapter = MinIOStorageService(s3_client=mock_s3)

    with pytest.raises(StorageException) as exc_info:
        adapter.upload_file(
            file_obj=io.BytesIO(b"data"),
            object_name="error.pdf",
            bucket_name="non-existent",
        )

    assert "Storage operation failed" in str(exc_info.value)

