import io
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.db.models import Base
from src.infrastructure.db.session import get_db_session
from src.infrastructure.storage.minio_adapter import MinIOStorageService, get_storage_service
from src.main import create_app
from tests.unit.test_complex_pdf_parser import create_synthetic_pdf


@pytest.fixture
async def pdf_test_app(mock_s3_client):
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
async def test_pdf_upload_triggers_complex_pipeline(pdf_test_app):
    pdf_bytes = create_synthetic_pdf()
    transport = ASGITransport(app=pdf_test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("enterprise_contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        response = await client.post("/api/v1/documents/upload", files=files)

        assert response.status_code == 201
        data = response.json()

        assert data["filename"] == "enterprise_contract.pdf"
        assert data["status"] == "COMPLETED"
        assert data["file_size_bytes"] == len(pdf_bytes)

        # Verify extracted rich metadata
        meta = data["doc_metadata"]
        assert meta["page_count"] == 2
        assert meta["confidence_score"] >= 0.8
        assert "tables" in meta
        assert len(meta["tables"]) >= 1

        # Verify business entities
        entities = meta["entities"]
        assert "0109998888" in entities["tax_ids"]
        assert "2026-11-01" in entities["dates"]
        assert entities["key_values"].get("Contract No") == "HD-2026/VIP-01"

