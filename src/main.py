from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.api.middlewares.request_id import RequestIDMiddleware
from src.api.v1.health import router as health_router
from src.core.config import get_settings
from src.core.logging import logger

try:
    from src.api.v1.documents import router as documents_router
except ImportError:
    documents_router = None

UI_FILE_PATH = Path(__file__).resolve().parent / "ui" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown event management."""
    settings = get_settings()
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] mode...")

    # Automatically verify & initialize database tables if reachable
    try:
        from src.infrastructure.db.models import Base
        from src.infrastructure.db.session import get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL database tables verified and initialized successfully.")
    except Exception as e:
        logger.warning(f"PostgreSQL initialization warning: {e}")

    # Automatically verify & initialize S3/MinIO buckets if reachable
    try:
        from src.infrastructure.storage.minio_adapter import get_storage_service

        storage = get_storage_service()
        if hasattr(storage, "ensure_buckets"):
            storage.ensure_buckets()
        logger.info("Storage buckets verified.")
    except Exception as e:
        logger.warning(f"Storage bucket initialization warning: {e}")

    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")


def create_app() -> FastAPI:
    """Application factory for FastAPI service."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="Scalable Enterprise Document Processing & Workflow Automation Platform",
        lifespan=lifespan,
    )

    # Middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    # Web Dashboard UI Route
    @app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
    async def serve_dashboard():
        if UI_FILE_PATH.exists():
            return HTMLResponse(content=UI_FILE_PATH.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>Enterprise Document Processor UI</h1><p>UI template not found.</p>")

    # API Routers
    app.include_router(health_router)
    if documents_router is not None:
        app.include_router(documents_router)

    return app


app = create_app()
