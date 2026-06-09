from pathlib import Path

from app.config import get_settings
from app.storage import LocalStorage


def test_settings_reads_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@example.com:5432/quotationhist")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    settings = get_settings()

    assert settings.database_url.startswith("postgresql://")
    assert settings.storage_backend == "s3"


def test_local_storage_returns_object_metadata(tmp_path):
    storage = LocalStorage(tmp_path)
    stored = storage.put("quote.xlsx", b"example", "application/octet-stream")

    assert stored.sha256
    assert stored.size == 7
    assert Path(tmp_path / stored.key).read_bytes() == b"example"
