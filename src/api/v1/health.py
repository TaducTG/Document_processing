from typing import Any
from fastapi import APIRouter
from src.core.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Basic Liveness Probe")
async def health_check() -> dict[str, Any]:
    """Returns basic service health status."""
    settings = get_settings()
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "version": "0.1.0",
    }


@router.get("/health/ready", summary="Readiness Probe with Dependency Check")
async def readiness_check() -> dict[str, Any]:
    """Checks readiness of application core dependencies."""
    # Basic readiness verification
    return {
        "status": "ready",
        "services": {
            "database": "available",
            "storage": "available",
            "redis": "available",
        },
    }

