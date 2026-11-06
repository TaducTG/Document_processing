import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.db.models import Base
from src.infrastructure.db.session import get_db_session
from src.infrastructure.storage.minio_adapter import MinIOStorageService, get_storage_service
from src.main import create_app


@pytest.fixture
async def app_with_storage(mock_s3_client):
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
async def test_delete_document_success(app_with_storage, mock_s3_client):
    transport = ASGITransport(app=app_with_storage)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Upload a document
        files = {"file": ("test_delete.md", io.BytesIO(b"# Temporary Document"), "text/markdown")}
        upload_resp = await client.post("/api/v1/documents/upload", files=files)
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        # 2. Delete the document
        del_resp = await client.delete(f"/api/v1/documents/{doc_id}")
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["success"] is True
        assert del_data["id"] == doc_id

        # Verify storage delete was called
        mock_s3_client.delete_object.assert_called()

        # 3. Query should now return 404
        get_resp = await client.get(f"/api/v1/documents/{doc_id}")
        assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_reprocess_document_success(app_with_storage):
    transport = ASGITransport(app=app_with_storage)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Upload a document
        md_text = b"# Original Document\n\n- Bullet 1\n- Bullet 2\n\nTotal: 500,000 VND"
        files = {"file": ("test_reprocess.md", io.BytesIO(md_text), "text/markdown")}
        upload_resp = await client.post("/api/v1/documents/upload", files=files)
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        # 2. Trigger reprocess
        reprocess_resp = await client.post(f"/api/v1/documents/{doc_id}/reprocess")
        assert reprocess_resp.status_code == 200
        data = reprocess_resp.json()

        assert data["id"] == doc_id
        assert data["status"] == "COMPLETED"
        assert data["doc_metadata"]["title"] == "Original Document"
        assert len(data["doc_metadata"]["headings"]) == 1

