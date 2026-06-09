from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_url: str
    cors_origins: list[str]
    jwt_secret: str
    token_ttl_minutes: int
    storage_backend: str
    local_storage_dir: Path
    s3_endpoint_url: str | None
    s3_bucket: str | None
    s3_access_key_id: str | None
    s3_secret_access_key: str | None
    s3_region: str
    max_upload_mb: int
    enable_pdf_import: bool
    default_currency: str


def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "QuotationHist"),
        environment=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL") or f"sqlite:///{os.getenv('QUOTATION_DB_PATH', 'quotation_history.db')}",
        cors_origins=_csv(os.getenv("CORS_ORIGINS", "*")),
        jwt_secret=os.getenv("JWT_SECRET", "change-me-in-production"),
        token_ttl_minutes=int(os.getenv("TOKEN_TTL_MINUTES", "1440")),
        storage_backend=os.getenv("STORAGE_BACKEND", "local").lower(),
        local_storage_dir=Path(os.getenv("LOCAL_STORAGE_DIR", ".data/uploads")),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        s3_bucket=os.getenv("S3_BUCKET"),
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
        s3_region=os.getenv("S3_REGION", "auto"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "25")),
        enable_pdf_import=os.getenv("ENABLE_PDF_IMPORT", "true").lower() in {"1", "true", "yes", "on"},
        default_currency=os.getenv("DEFAULT_CURRENCY", "CNY"),
    )
