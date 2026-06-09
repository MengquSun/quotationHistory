from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import db
from app.main import app


def make_workbook(rows: list[list[object]], meta: dict[str, object] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Quote"
    for row in rows:
        sheet.append(row)
    if meta:
        meta_sheet = workbook.create_sheet("Meta", 0)
        for key, value in meta.items():
            meta_sheet.append([key, value])

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_import_quotation_and_catalog_history(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "quotations.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'quotations.db'}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "uploads"))
    db.init_db()
    client = TestClient(app)

    headers = ["catalogNo", "Product Name", "Unit Price", "Qty", "Unit", "Notes"]
    first = make_workbook(
        [
            headers,
            ["ACS6001-10", "Example Product", "120.50", 10, "g", "first quote"],
            [None, "Missing catalog", 8, 1, "g", "skipped"],
        ],
        {"Customer": "Acme Pharma", "Quote Date": "2025-03-01", "Currency": "USD"},
    )
    second = make_workbook([headers, ["ACS6001-10", "Example Product", "115.00", 10, "g", "discounted"]])

    response = client.post("/api/quotations/import", files={"file": ("q1.xlsx", first)}, data={"currency": "USD"})
    assert response.status_code == 200
    assert response.json()["imported_rows"] == 1
    assert response.json()["skipped_rows"] == 1
    assert response.json()["stored_file"]["sha256"]
    first_id = response.json()["quotation_id"]

    response = client.post(
        "/api/quotations/import",
        files={"file": ("q2.xlsx", second)},
        data={"customer": "Acme Pharma", "quoted_on": "2025-06-01", "currency": "USD"},
    )
    assert response.status_code == 200

    history = client.get("/api/history/ACS6001-10")
    assert history.status_code == 200
    points = history.json()["history"]
    assert [point["unit_price"] for point in points] == [120.5, 115.0]
    assert [point["quoted_on"] for point in points] == ["2025-03-01", "2025-06-01"]

    detail = client.get(f"/api/quotations/{first_id}")
    assert detail.status_code == 200
    assert detail.json()["quotation"]["line_item_count"] == 1
    assert detail.json()["quotation"]["line_items"][0]["catalog_no"] == "ACS6001-10"

    listing = client.get("/api/quotations")
    assert listing.status_code == 200
    assert len(listing.json()["quotations"]) == 2


def test_import_quotation_rejects_missing_catalog_column(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "quotations.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'quotations.db'}")
    db.init_db()
    client = TestClient(app)
    workbook = make_workbook([["Product Name", "Unit Price"], ["Example", 10]])

    response = client.post("/api/quotations/import", files={"file": ("bad.xlsx", workbook)})

    assert response.status_code == 400
    assert "catalog number" in response.json()["detail"].lower()


def test_auth_register_login_and_archive_quotation(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "quotations.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'quotations.db'}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "uploads"))
    db.init_db()
    client = TestClient(app)

    register = client.post("/api/auth/register", json={"email": "admin@example.com", "password": "password123", "name": "Admin"})
    assert register.status_code == 200
    token = register.json()["token"]

    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
    assert login.status_code == 200

    workbook = make_workbook([["catalogNo", "Product Name", "Unit Price"], ["ACS6001-10", "Example", 12]])
    imported = client.post("/api/quotations/import", files={"file": ("q.xlsx", workbook)})
    quotation_id = imported.json()["quotation_id"]

    archived = client.delete(f"/api/quotations/{quotation_id}", headers={"Authorization": f"Bearer {token}"})
    assert archived.status_code == 200

    listing = client.get("/api/quotations")
    assert listing.json()["quotations"] == []
