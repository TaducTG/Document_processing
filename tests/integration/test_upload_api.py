import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.db.models import Base
from src.infrastructure.db.session import get_db_session
from src.infrastructure.storage.minio_adapter import MinIOStorageService, get_storage_service
from src.main import create_app


@pytest.fixture
async def integration_app(mock_s3_client):
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
async def test_full_markdown_document_lifecycle(integration_app):
    """End-to-End API Lifecycle test: Upload -> Query by ID -> List -> Check Extracted Content."""
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Upload Markdown Document
        raw_md = (
            b"# Project Specification\n\n"
            b"## System Architecture\n"
            b"The platform handles real-time ingestion.\n\n"
            b"### Security Principles\n"
            b"- Zero-trust network\n"
            b"- Data encryption at rest\n"
        )
        files = {"file": ("project_spec.md", io.BytesIO(raw_md), "text/markdown")}
        upload_res = await client.post("/api/v1/documents/upload", files=files)
        assert upload_res.status_code == 201
        data = upload_res.json()
        doc_id = data["id"]

        assert data["filename"] == "project_spec.md"
        assert data["doc_metadata"]["title"] == "Project Specification"
        assert len(data["doc_metadata"]["headings"]) == 3

        # 2. Query Detail Endpoint
        detail_res = await client.get(f"/api/v1/documents/{doc_id}")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert detail_data["id"] == doc_id
        assert "Zero-trust network" in detail_data["extracted_text"]

        # 3. Verify in List
        list_res = await client.get("/api/v1/documents")
        assert list_res.status_code == 200
        items = list_res.json()
        assert any(item["id"] == doc_id for item in items)

