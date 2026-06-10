from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db
from app import auth
from app.config import get_settings
from app.services.chemical_resolver import resolve_chemical
from app.services.importer import build_preview
from app.services.pdf_parser import extract_text_pdf
from app.services.quotation_excel import parse_quotation_workbook
from app.services.quotation_repository import (
    archive_quotation,
    compare_quotations,
    create_quotation,
    get_catalog_history,
    get_quotation_detail,
    get_quotation_summary,
    list_quotations,
    quotation_dashboard,
)
from app.services.quote_engine import choose_price_source, estimate_cost
from app.storage import get_storage
from app.services.units import calculate_unit_price, parse_decimal, parse_quantity, quantize_money

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ManualRecord(BaseModel):
    material_name: str = Field(min_length=1)
    price: Decimal
    currency: str = "CNY"
    quantity: str | Decimal | None = None
    unit: str | None = None
    record_type: str = Field(pattern="^(inquiry|purchase)$")
    record_date: str | None = None
    requester: str | None = None
    supplier: str | None = None
    remark: str | None = None
    cas_number: str | None = None


class ConfirmImport(BaseModel):
    filename: str
    import_type: str = Field(pattern="^(inquiry|purchase)$")
    rows: list[dict[str, Any]]
    mapping: dict[str, str] = {}
    uploaded_by: str | None = None
    stored_file_id: int | None = None


class QuoteRequest(BaseModel):
    material_query: str
    required_quantity: str | Decimal
    required_unit: str | None = None


class QuoteBatchRequest(BaseModel):
    items: list[QuoteRequest] = Field(min_length=1)


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class FxRatePayload(BaseModel):
    base_currency: str
    quote_currency: str
    rate: Decimal
    effective_on: str


def get_request_user(authorization: str | None, x_user_role: str | None) -> dict | None:
    return auth.current_user(authorization=authorization, x_user_role=x_user_role)


def require_admin(authorization: str | None, role: str | None) -> dict | None:
    user = get_request_user(authorization, role)
    auth.require_role(user, "admin")
    return user


def require_login(authorization: str | None, role: str | None) -> dict:
    user = get_request_user(authorization, role)
    auth.require_authenticated(user)
    return user or {}


def decimal_to_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def remember_stored_file(filename: str, content: bytes, content_type: str | None, created_by: int | None = None) -> dict:
    stored = get_storage().put(filename, content, content_type)
    with db.connect() as conn:
        duplicate_row = conn.execute("select id from stored_files where sha256 = ? limit 1", (stored.sha256,)).fetchone()
        cur = conn.execute(
            """
            insert into stored_files (
                original_filename, storage_backend, bucket, object_key, sha256, mime_type, size_bytes, created_by
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (filename, stored.storage_backend, stored.bucket, stored.key, stored.sha256, content_type, stored.size, created_by),
        )
    return {
        "id": int(cur.lastrowid),
        "original_filename": filename,
        "storage_backend": stored.storage_backend,
        "bucket": stored.bucket,
        "object_key": stored.key,
        "sha256": stored.sha256,
        "size_bytes": stored.size,
        "is_duplicate": duplicate_row is not None,
    }


@app.on_event("startup")
def startup() -> None:
    db.init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment, "storage_backend": settings.storage_backend}


@app.get("/health")
def root_health() -> dict:
    return health()


@app.post("/api/quotations/import")
async def import_quotation(
    file: UploadFile = File(...),
    customer: str | None = Form(default=None),
    quoted_on: str | None = Form(default=None),
    currency: str | None = Form(default=None),
) -> dict:
    filename = file.filename or "quotation.xlsx"
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xlsm quotation files are supported.")

    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded file is too large.")
    try:
        parsed = parse_quotation_workbook(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unable to parse quotation workbook.") from exc

    if not parsed.line_items:
        raise HTTPException(status_code=400, detail="No importable quotation line items found.")

    stored = remember_stored_file(filename, content, file.content_type)
    quotation_id = create_quotation(filename, parsed, customer, quoted_on, currency, stored["id"], stored["sha256"])
    quotation = get_quotation_summary(quotation_id)
    return {
        "quotation_id": quotation_id,
        "imported_rows": len(parsed.line_items),
        "skipped_rows": parsed.skipped_rows,
        "stored_file": stored,
        "quotation": quotation,
    }


@app.get("/api/quotations")
def quotation_list() -> dict:
    return {"quotations": list_quotations()}


@app.get("/api/quotations/{quotation_id}")
def quotation_detail(quotation_id: int) -> dict:
    quotation = get_quotation_detail(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found.")
    return {"quotation": quotation}


@app.get("/api/history/{catalog_no}")
def catalog_history(catalog_no: str) -> dict:
    history = get_catalog_history(catalog_no)
    if not history:
        raise HTTPException(status_code=404, detail="No quotation history found for catalog number.")
    return {"catalog_no": catalog_no, "history": history}


@app.post("/api/auth/register")
def register(payload: RegisterRequest, authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict:
    db.init_db()
    with db.connect() as conn:
        has_users = conn.execute("select id from users limit 1").fetchone() is not None
    role = "admin" if not has_users else "user"
    if has_users:
        require_admin(authorization, x_user_role)
    user = auth.create_user(payload.email, payload.password, payload.name, role)
    token = auth.issue_token(int(user["id"]))
    return {"user": user, "token": token}


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict:
    user = auth.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"user": user, "token": auth.issue_token(int(user["id"]))}


@app.get("/api/auth/me")
def me(authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict:
    user = get_request_user(authorization, x_user_role)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return {"user": user}


@app.post("/api/import/preview")
async def import_preview(file: UploadFile = File(...), authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict:
    user = require_admin(authorization, x_user_role)
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded file is too large.")
    stored = remember_stored_file(file.filename or "upload.xlsx", content, file.content_type, user.get("id") if user else None)
    try:
        preview = await build_preview(file.filename or "upload.xlsx", content)
        preview["stored_file"] = stored
        preview["stored_file_id"] = stored["id"]
        preview["is_duplicate"] = stored["is_duplicate"]
        return preview
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import/confirm")
async def import_confirm(payload: ConfirmImport, authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict:
    user = require_admin(authorization, x_user_role)
    uploaded_by = str(user.get("email") or user.get("name") or user.get("id"))
    db.init_db()
    success = 0
    failed = 0
    with db.connect() as conn:
        stored = None
        if payload.stored_file_id:
            stored = db.row_to_dict(conn.execute("select * from stored_files where id = ?", (payload.stored_file_id,)).fetchone())
        duplicate = 0
        if stored:
            existing = conn.execute("select id from import_files where file_sha256 = ? and archived_at is null limit 1", (stored["sha256"],)).fetchone()
            duplicate = 1 if existing else 0
        cur = conn.execute(
            """
            insert into import_files (filename, uploaded_by, import_type, status, total_rows, stored_file_id, file_sha256, is_duplicate)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload.filename, uploaded_by, payload.import_type, "confirmed", len(payload.rows), payload.stored_file_id, stored["sha256"] if stored else None, duplicate),
        )
        file_id = int(cur.lastrowid)

        for header, field in payload.mapping.items():
            conn.execute(
                """
                insert into field_mappings (excel_header, system_field, confirmed_by, updated_at)
                values (?, ?, ?, current_timestamp)
                on conflict(excel_header) do update set system_field = excluded.system_field, updated_at = current_timestamp
                """,
                (header, field, uploaded_by),
            )

    for item in payload.rows:
        normalized = item.get("normalized", item)
        try:
            await create_record_from_normalized(normalized, payload.import_type, uploaded_by, file_id)
            success += 1
        except Exception:
            failed += 1

    with db.connect() as conn:
        conn.execute("update import_files set success_rows = ?, failed_rows = ? where id = ?", (success, failed, file_id))

    return {"source_file_id": file_id, "success_rows": success, "failed_rows": failed}


@app.post("/api/records")
async def create_record(record: ManualRecord, authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict:
    user = require_login(authorization, x_user_role)
    requester = str(user.get("name") or user.get("email") or user.get("id"))
    normalized = {
        "material_name": record.material_name,
        "price": str(record.price),
        "currency": record.currency,
        "quantity": record.quantity,
        "unit": record.unit,
        "record_date": date.today().isoformat(),
        "requester": requester,
        "supplier": record.supplier,
        "remark": record.remark,
        "cas_number": record.cas_number,
    }
    record_id = await create_record_from_normalized(normalized, record.record_type, str(user.get("id")), None)
    return {"id": record_id}


async def create_record_from_normalized(normalized: dict[str, Any], record_type: str, created_by: str | None, source_file_id: int | None) -> int:
    raw_name = str(normalized.get("material_name") or normalized.get("raw_name") or "").strip()
    if not raw_name:
        raise ValueError("Missing material name.")

    candidate_obj = await resolve_chemical(str(normalized.get("cas_number") or raw_name))
    candidate = candidate_obj.__dict__ if candidate_obj else {"standard_name": raw_name, "synonyms": [raw_name], "match_status": "unresolved"}
    material_id = db.find_or_create_material(candidate, raw_name)
    quantity = parse_quantity(normalized.get("quantity") or normalized.get("quantity_value"), normalized.get("unit") or normalized.get("quantity_unit"))
    price = quantize_money(parse_decimal(normalized.get("price")))
    unit_price = quantize_money(parse_decimal(normalized.get("unit_price"))) or calculate_unit_price(price, quantity)

    with db.connect() as conn:
        cur = conn.execute(
            """
            insert into procurement_records (
                material_id, raw_name, price, currency, quantity_value, quantity_unit, normalized_quantity,
                normalized_unit, unit_price, record_type, remark, record_date, requester, supplier, source_file_id, created_by
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material_id,
                raw_name,
                decimal_to_str(price),
                normalized.get("currency") or "CNY",
                decimal_to_str(quantity.quantity_value),
                quantity.quantity_unit,
                decimal_to_str(quantity.normalized_quantity),
                quantity.normalized_unit,
                decimal_to_str(unit_price),
                record_type,
                normalized.get("remark"),
                normalized.get("record_date"),
                normalized.get("requester"),
                normalized.get("supplier"),
                source_file_id,
                created_by,
            ),
        )
        return int(cur.lastrowid)


@app.get("/api/materials/search")
def search_materials(q: str = "", record_type: str | None = None) -> dict:
    db.init_db()
    like = f"%{q.lower()}%"
    sql = """
        select distinct m.*
        from materials m
        left join procurement_records r on r.material_id = m.id
        where lower(m.standard_name) like ?
           or lower(coalesce(m.chinese_name, '')) like ?
           or lower(coalesce(m.english_name, '')) like ?
           or lower(coalesce(m.cas_number, '')) like ?
           or lower(m.synonyms) like ?
    """
    params: list[Any] = [like, like, like, like, like]
    if record_type:
        sql += " and r.record_type = ?"
        params.append(record_type)
    sql += " order by m.updated_at desc limit 50"
    with db.connect() as conn:
        materials = db.rows_to_dicts(conn.execute(sql, params).fetchall())
    return {"materials": materials}


@app.get("/api/materials/{material_id}/records")
def material_records(material_id: int) -> dict:
    with db.connect() as conn:
        material = db.row_to_dict(conn.execute("select * from materials where id = ?", (material_id,)).fetchone())
        rows = db.rows_to_dicts(
            conn.execute("select * from procurement_records where material_id = ? and archived_at is null order by coalesce(record_date, cast(created_at as text)) desc", (material_id,)).fetchall()
        )
    if not material:
        raise HTTPException(status_code=404, detail="Material not found.")
    return {"material": material, "records": rows, "stats": summarize_records(rows)}


def summarize_records(records: list[dict]) -> dict:
    prices = [parse_decimal(row.get("unit_price")) for row in records if parse_decimal(row.get("unit_price")) is not None]
    latest_purchase = choose_price_source([row for row in records if row.get("record_type") == "purchase"])
    latest_inquiry = choose_price_source([row for row in records if row.get("record_type") == "inquiry"])
    return {
        "latest_purchase_unit_price": latest_purchase.get("unit_price") if latest_purchase else None,
        "latest_inquiry_unit_price": latest_inquiry.get("unit_price") if latest_inquiry else None,
        "min_unit_price": str(min(prices)) if prices else None,
        "max_unit_price": str(max(prices)) if prices else None,
        "avg_unit_price": str(sum(prices) / len(prices)) if prices else None,
    }


def calculate_quote_item(payload: QuoteRequest, persist: bool = True) -> dict:
    materials = search_materials(payload.material_query)["materials"]
    if not materials:
        return {"input": payload.model_dump(mode="json"), "material": None, "source_record": None, "result": {"estimated_cost": None, "warning": "未找到匹配物料。"}}
    material = materials[0]
    with db.connect() as conn:
        records = db.rows_to_dicts(conn.execute("select * from procurement_records where material_id = ?", (material["id"],)).fetchall())
    source = choose_price_source(records)
    result = estimate_cost(source, payload.required_quantity, payload.required_unit)
    if persist and source and result.get("estimated_cost") is not None:
        with db.connect() as conn:
            conn.execute(
                """
                insert into quotation_items (material_id, required_quantity, required_unit, latest_unit_price, estimated_cost, price_source_record_id)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    material["id"],
                    str(payload.required_quantity),
                    payload.required_unit or "",
                    result.get("latest_unit_price"),
                    result.get("estimated_cost"),
                    result.get("price_source_record_id"),
                ),
            )
    return {"input": payload.model_dump(mode="json"), "material": material, "source_record": source, "result": result}


@app.post("/api/quotations/calculate")
def calculate_quote(payload: QuoteRequest) -> dict:
    item = calculate_quote_item(payload, persist=True)
    return {"material": item["material"], "source_record": item["source_record"], "result": item["result"]}


@app.post("/api/quotations/calculate-batch")
def calculate_quote_batch(payload: QuoteBatchRequest) -> dict:
    return {"items": [calculate_quote_item(item, persist=False) for item in payload.items]}


@app.delete("/api/quotations/{quotation_id}")
def quotation_archive(quotation_id: int, authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict:
    require_admin(authorization, x_user_role)
    if not archive_quotation(quotation_id):
        raise HTTPException(status_code=404, detail="Quotation not found.")
    return {"archived": True}


@app.get("/api/quotation-comparison")
def quotation_compare(left_id: int, right_id: int) -> dict:
    comparison = compare_quotations(left_id, right_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="One or both quotations were not found.")
    return comparison


@app.get("/api/analytics/dashboard")
def analytics_dashboard() -> dict:
    return quotation_dashboard()


@app.post("/api/fx-rates")
def create_fx_rate(payload: FxRatePayload, authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict:
    user = require_admin(authorization, x_user_role)
    with db.connect() as conn:
        cur = conn.execute(
            """
            insert into fx_rates (base_currency, quote_currency, rate, effective_on, created_by)
            values (?, ?, ?, ?, ?)
            on conflict(base_currency, quote_currency, effective_on) do update set rate = excluded.rate
            """,
            (
                payload.base_currency.upper(),
                payload.quote_currency.upper(),
                str(payload.rate),
                payload.effective_on,
                user.get("id") if user else None,
            ),
        )
    return {"id": cur.lastrowid, "saved": True}


@app.get("/api/fx-rates")
def list_fx_rates() -> dict:
    with db.connect() as conn:
        rows = conn.execute("select * from fx_rates order by effective_on desc, base_currency, quote_currency").fetchall()
    return {"fx_rates": db.rows_to_dicts(rows)}


@app.post("/api/pdf/import")
async def import_pdf(file: UploadFile = File(...), authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict:
    require_admin(authorization, x_user_role)
    if not settings.enable_pdf_import:
        raise HTTPException(status_code=400, detail="PDF import is disabled.")
    filename = file.filename or "quotation.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    content = await file.read()
    stored = remember_stored_file(filename, content, file.content_type)
    try:
        text = extract_text_pdf(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"stored_file": stored, "text_preview": text[:4000], "status": "text-extracted"}


@app.get("/api/records/export.csv")
def export_records() -> StreamingResponse:
    with db.connect() as conn:
        rows = db.rows_to_dicts(
            conn.execute(
                """
                select m.cas_number, m.standard_name, r.raw_name, r.price, r.currency, r.quantity_value, r.quantity_unit,
                       r.normalized_quantity, r.normalized_unit, r.unit_price, r.record_type, r.record_date, r.supplier,
                       r.requester, r.remark
                from procurement_records r
                left join materials m on m.id = r.material_id
                order by coalesce(r.record_date, cast(r.created_at as text)) desc
                """
            ).fetchall()
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()) if rows else ["standard_name", "price"])
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=quotation_records.csv"})


@app.get("/api/history/{catalog_no}/export.xlsx")
def export_catalog_history(catalog_no: str) -> StreamingResponse:
    history = get_catalog_history(catalog_no)
    if not history:
        raise HTTPException(status_code=404, detail="No quotation history found for catalog number.")
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "History"
    headers = ["catalog_no", "product_name", "unit_price", "quantity", "unit", "customer", "quoted_on", "currency", "filename"]
    sheet.append(headers)
    for row in history:
        sheet.append([row.get(header) for header in headers])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={catalog_no}_history.xlsx"},
    )
