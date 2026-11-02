from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # General
    APP_NAME: str = "Enterprise Document Processing Platform"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # PostgreSQL Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/doc_processor_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # S3 / MinIO Object Storage
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY_ID: str = "minioadmin"
    S3_SECRET_ACCESS_KEY: str = "minioadminpassword"
    S3_REGION_NAME: str = "us-east-1"
    S3_BUCKET_RAW: str = "raw-documents"
    S3_BUCKET_PROCESSED: str = "processed-output"

    # Celery Workers
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"


@lru_cache()
def get_settings() -> Settings:
    """Singleton getter for cached application settings."""
    return Settings()

