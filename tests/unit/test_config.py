import pytest
from pydantic import ValidationError


def test_settings_load_defaults():
    from src.core.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/test_db",
        _env_file=None,
    )

    assert settings.APP_NAME == "Enterprise Document Processing Platform"
    assert settings.S3_BUCKET_RAW == "raw-documents"
    assert settings.S3_BUCKET_PROCESSED == "processed-output"
    assert "postgresql+asyncpg" in str(settings.DATABASE_URL)


def test_settings_custom_env(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Custom Processor")
    monkeypatch.setenv("S3_BUCKET_RAW", "custom-bucket")

    from src.core.config import get_settings

    # Clear lru_cache if any
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.APP_NAME == "Custom Processor"
    assert settings.S3_BUCKET_RAW == "custom-bucket"

