import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.db.models import Base
from src.infrastructure.db.session import get_db_session
from src.infrastructure.storage.minio_adapter import MinIOStorageService, get_storage_service
from src.main import create_app


@pytest.fixture
async def app_with_db(mock_s3_client):
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
async def test_list_and_get_document_flow(app_with_db):
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Upload a document
        md_content = b"# Architecture Notes\n\nHigh-performance document processing platform."
        files = {"file": ("architecture.md", io.BytesIO(md_content), "text/markdown")}
        upload_resp = await client.post("/api/v1/documents/upload", files=files)
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        # 2. List documents
        list_resp = await client.get("/api/v1/documents")
        assert list_resp.status_code == 200
        docs = list_resp.json()
        assert len(docs) == 1
        assert docs[0]["id"] == doc_id
        assert docs[0]["filename"] == "architecture.md"

        # 3. Retrieve single document by ID
        get_resp = await client.get(f"/api/v1/documents/{doc_id}")
        assert get_resp.status_code == 200
        single_doc = get_resp.json()
        assert single_doc["id"] == doc_id
        assert single_doc["doc_metadata"]["title"] == "Architecture Notes"

        # 4. Non-existent document 404 check
        not_found_resp = await client.get("/api/v1/documents/non-existent-id")
        assert not_found_resp.status_code == 404


@pytest.mark.asyncio
async def test_presigned_upload_endpoint(app_with_db):
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "filename": "large_manual.pdf",
            "file_size_bytes": 104857600,
            "content_type": "application/pdf",
        }
        resp = await client.post("/api/v1/documents/presigned-upload", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "upload_url" in data
        assert "document_id" in data
        assert data["expires_in_seconds"] == 3600

