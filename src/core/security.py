from typing import Optional
from fastapi import Header, HTTPException, status
from src.core.config import get_settings


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> bool:
    """Validates X-API-Key header against configured application key if configured."""
    settings = get_settings()
    configured_key = getattr(settings, "API_KEY", None)

    # If no key configured or in development mode without explicit key, allow access
    if not configured_key or settings.APP_ENV == "development":
        return True

    if x_api_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key authentication header",
        )
    return True

