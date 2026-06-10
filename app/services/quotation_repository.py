from __future__ import annotations

from typing import Any

from app import db
from app.services.quotation_excel import ParsedQuotation


def create_quotation(
    filename: str,
    parsed: ParsedQuotation,
    customer: str | None,
    quoted_on: str | None,
    currency: str | None,
    stored_file_id: int | None = None,
    file_sha256: str | None = None,
) -> int:
    db.init_db()
    metadata = parsed.metadata
    effective_customer = customer or metadata.get("customer")
    effective_quoted_on = quoted_on or metadata.get("quoted_on")
    effective_currency = currency or metadata.get("currency") or "USD"

    with db.connect() as conn:
        duplicate = 0
        if file_sha256:
            existing = conn.execute("select id from quotations where file_sha256 = ? and archived_at is null limit 1", (file_sha256,)).fetchone()
            duplicate = 1 if existing else 0
        cur = conn.execute(
            """
            insert into quotations (filename, customer, quoted_on, currency, stored_file_id, file_sha256, is_duplicate)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (filename, effective_customer, effective_quoted_on, effective_currency, stored_file_id, file_sha256, duplicate),
        )
        quotation_id = int(cur.lastrowid)
        conn.executemany(
            """
            insert into line_items (quotation_id, catalog_no, product_name, unit_price, quantity, unit, notes)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    quotation_id,
                    item["catalog_no"],
                    item.get("product_name"),
                    item.get("unit_price"),
                    item.get("quantity"),
                    item.get("unit"),
                    item.get("notes"),
                )
                for item in parsed.line_items
            ],
        )
    return quotation_id


def get_quotation_summary(quotation_id: int) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute(
            """
            select q.*, count(li.id) as line_item_count
            from quotations q
            left join line_items li on li.quotation_id = q.id
            where q.id = ?
            group by q.id
            """,
            (quotation_id,),
        ).fetchone()
    return db.row_to_dict(row)


def list_quotations() -> list[dict[str, Any]]:
    db.init_db()
    with db.connect() as conn:
        rows = conn.execute(
            """
            select q.*, count(li.id) as line_item_count
            from quotations q
            left join line_items li on li.quotation_id = q.id
            where q.archived_at is null
            group by q.id
            order by coalesce(q.quoted_on, cast(q.imported_at as text)) desc, q.id desc
            """
        ).fetchall()
    return db.rows_to_dicts(rows)


def get_quotation_detail(quotation_id: int) -> dict[str, Any] | None:
    summary = get_quotation_summary(quotation_id)
    if not summary:
        return None
    with db.connect() as conn:
        items = conn.execute("select * from line_items where quotation_id = ? order by id", (quotation_id,)).fetchall()
    summary["line_items"] = db.rows_to_dicts(items)
    return summary


def get_catalog_history(catalog_no: str) -> list[dict[str, Any]]:
    db.init_db()
    with db.connect() as conn:
        rows = conn.execute(
            """
            select
                li.id as line_item_id,
                li.catalog_no,
                li.product_name,
                li.unit_price,
                li.quantity,
                li.unit,
                li.notes,
                q.id as quotation_id,
                q.filename,
                q.customer,
                q.quoted_on,
                q.currency,
                q.imported_at
            from line_items li
            join quotations q on q.id = li.quotation_id
            where lower(li.catalog_no) = lower(?) and q.archived_at is null
            order by coalesce(q.quoted_on, cast(q.imported_at as text)) asc, q.id asc, li.id asc
            """,
            (catalog_no,),
        ).fetchall()
    return db.rows_to_dicts(rows)


def archive_quotation(quotation_id: int) -> bool:
    db.init_db()
    with db.connect() as conn:
        row = conn.execute("select id from quotations where id = ?", (quotation_id,)).fetchone()
        if not row:
            return False
        conn.execute("update quotations set archived_at = current_timestamp where id = ?", (quotation_id,))
    return True


def compare_quotations(left_id: int, right_id: int) -> dict[str, Any] | None:
    left = get_quotation_detail(left_id)
    right = get_quotation_detail(right_id)
    if not left or not right:
        return None
    left_items = {item["catalog_no"].lower(): item for item in left["line_items"]}
    right_items = {item["catalog_no"].lower(): item for item in right["line_items"]}
    rows = []
    for key in sorted(set(left_items) | set(right_items)):
        left_item = left_items.get(key)
        right_item = right_items.get(key)
        left_price = left_item.get("unit_price") if left_item else None
        right_price = right_item.get("unit_price") if right_item else None
        delta = right_price - left_price if isinstance(left_price, (int, float)) and isinstance(right_price, (int, float)) else None
        rows.append(
            {
                "catalog_no": (right_item or left_item or {}).get("catalog_no"),
                "left_unit_price": left_price,
                "right_unit_price": right_price,
                "delta": delta,
                "left_product_name": left_item.get("product_name") if left_item else None,
                "right_product_name": right_item.get("product_name") if right_item else None,
            }
        )
    return {"left": left, "right": right, "items": rows}


def quotation_dashboard() -> dict[str, Any]:
    db.init_db()
    with db.connect() as conn:
        total = conn.execute("select count(*) as value from quotations where archived_at is null").fetchone()
        record_total = conn.execute("select count(*) as value from procurement_records where archived_at is null").fetchone()
        recent = conn.execute(
            """
            select q.*, count(li.id) as line_item_count
            from quotations q
            left join line_items li on li.quotation_id = q.id
            where q.archived_at is null
            group by q.id
            order by q.imported_at desc
            limit 8
            """
        ).fetchall()
        products = conn.execute(
            """
            select min(catalog_no) as catalog_no, max(product_name) as product_name, count(*) as quote_count, avg(unit_price) as avg_unit_price
            from line_items li
            join quotations q on q.id = li.quotation_id
            where q.archived_at is null
            group by lower(catalog_no)
            order by quote_count desc, catalog_no asc
            limit 10
            """
        ).fetchall()
        customers = conn.execute(
            """
            select coalesce(customer, 'Unknown') as customer, count(*) as quotation_count
            from quotations
            where archived_at is null
            group by coalesce(customer, 'Unknown')
            order by quotation_count desc
            limit 10
            """
        ).fetchall()
        recorded_materials = conn.execute(
            """
            select m.standard_name, count(*) as record_count, avg(r.unit_price) as avg_unit_price
            from procurement_records r
            left join materials m on m.id = r.material_id
            where r.archived_at is null
            group by m.id, m.standard_name
            order by record_count desc, m.standard_name asc
            limit 10
            """
        ).fetchall()
        suppliers = conn.execute(
            """
            select coalesce(supplier, 'Unknown') as supplier, count(*) as record_count
            from procurement_records
            where archived_at is null
            group by coalesce(supplier, 'Unknown')
            order by record_count desc
            limit 10
            """
        ).fetchall()
        recent_records = conn.execute(
            """
            select m.standard_name, r.record_type, r.price, r.currency, r.record_date, r.requester, r.supplier
            from procurement_records r
            left join materials m on m.id = r.material_id
            where r.archived_at is null
            order by coalesce(r.record_date, cast(r.created_at as text)) desc, r.id desc
            limit 8
            """
        ).fetchall()
    return {
        "quotation_count": (db.row_to_dict(total) or {}).get("value", 0),
        "record_count": (db.row_to_dict(record_total) or {}).get("value", 0),
        "recent_quotations": db.rows_to_dicts(recent),
        "most_quoted_products": db.rows_to_dicts(products),
        "customer_summary": db.rows_to_dicts(customers),
        "most_recorded_materials": db.rows_to_dicts(recorded_materials),
        "supplier_summary": db.rows_to_dicts(suppliers),
        "recent_records": db.rows_to_dicts(recent_records),
    }
