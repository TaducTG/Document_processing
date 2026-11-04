import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.db.models import Base
from src.infrastructure.db.session import get_db_session
from src.infrastructure.storage.minio_adapter import MinIOStorageService, get_storage_service
from src.main import create_app


@pytest.fixture
async def test_app(mock_s3_client):
    app = create_app()

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db_session():
        async with test_session_factory() as session:
            yield session

    test_storage = MinIOStorageService(s3_client=mock_s3_client)

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    yield app
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_upload_markdown_document_success(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        md_content = b"# Document Title\n\nThis is a sample markdown paragraph.\n\n## Section 1\n- Item A\n- Item B"
        files = {"file": ("sample_guide.md", io.BytesIO(md_content), "text/markdown")}

        response = await client.post("/api/v1/documents/upload", files=files)
        assert response.status_code == 201
        data = response.json()

        assert data["filename"] == "sample_guide.md"
        assert data["file_size_bytes"] == len(md_content)
        assert data["status"] in ["PENDING", "COMPLETED"]
        assert "id" in data
        assert "storage_path" in data

        # Check extracted markdown metadata
        meta = data["doc_metadata"]
        assert meta["title"] == "Document Title"
        assert meta["word_count"] > 5
        assert len(meta["headings"]) == 2


@pytest.mark.asyncio
async def test_upload_invalid_extension_rejected(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("malicious.exe", io.BytesIO(b"binary"), "application/octet-stream")}
        response = await client.post("/api/v1/documents/upload", files=files)
        assert response.status_code == 400
        assert "not supported" in response.json()["detail"].lower()
