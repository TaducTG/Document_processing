import io
import uuid
import pytest
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.db.models import Base
from src.infrastructure.storage.minio_adapter import MinIOStorageService


@pytest.fixture
def mock_s3_client():
    client = MagicMock()
    # In-memory storage mock dict
    storage_dict = {}

    def fake_upload(Fileobj, Bucket, Key, ExtraArgs=None):
        storage_dict[f"{Bucket}/{Key}"] = Fileobj.read()

    def fake_download(Bucket, Key, Fileobj):
        key = f"{Bucket}/{Key}"
        if key in storage_dict:
            Fileobj.write(storage_dict[key])
        else:
            Fileobj.write(b"Default test payload")

    client.upload_fileobj.side_effect = fake_upload
    client.download_fileobj.side_effect = fake_download
    client.generate_presigned_url.return_value = "http://localhost:9000/test-presigned"
    client._storage_dict = storage_dict
    return client


@pytest.fixture
def storage_service(mock_s3_client):
    return MinIOStorageService(s3_client=mock_s3_client)


@pytest.fixture
async def async_db_session() -> AsyncGenerator[AsyncSession, None]:
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await test_engine.dispose()


@pytest.fixture
def sample_pdf_bytes():
    return b"%PDF-1.4 simulated binary document content for test"

