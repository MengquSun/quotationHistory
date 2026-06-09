from __future__ import annotations

from decimal import Decimal

from app.services.units import calculate_unit_price, parse_decimal, parse_quantity


def choose_price_source(records: list[dict]) -> dict | None:
    purchases = [row for row in records if row.get("record_type") == "purchase"]
    inquiries = [row for row in records if row.get("record_type") == "inquiry"]

    def sort_key(row: dict) -> tuple[str, int]:
        return (str(row.get("record_date") or ""), int(row.get("id") or 0))

    if purchases:
        return sorted(purchases, key=sort_key, reverse=True)[0]
    if inquiries:
        return sorted(inquiries, key=sort_key, reverse=True)[0]
    return None


def estimate_cost(source_record: dict | None, required_quantity: object, required_unit: object) -> dict:
    if not source_record:
        return {"estimated_cost": None, "warning": "没有可用的历史采购或询价记录。"}

    required = parse_quantity(required_quantity, required_unit)
    source_unit = source_record.get("normalized_unit") or source_record.get("quantity_unit")
    source_unit_price = parse_decimal(source_record.get("unit_price"))

    if source_unit_price is None:
        price = parse_decimal(source_record.get("price"))
        source_quantity = parse_quantity(source_record.get("quantity_value"), source_record.get("quantity_unit"))
        source_unit_price = calculate_unit_price(price, source_quantity)
        source_unit = source_quantity.normalized_unit

    if not source_unit_price or not required.normalized_quantity:
        return {"estimated_cost": None, "price_source_record_id": source_record.get("id"), "warning": "缺少数量或单价，无法自动计算。"}

    if source_unit != required.normalized_unit:
        return {
            "estimated_cost": None,
            "price_source_record_id": source_record.get("id"),
            "latest_unit_price": str(source_unit_price),
            "warning": f"历史价格单位为 {source_unit}，当前需求单位为 {required.normalized_unit}，无法自动换算。",
        }

    cost: Decimal = source_unit_price * required.normalized_quantity
    return {
        "estimated_cost": str(cost.quantize(Decimal("0.0001"))),
        "price_source_record_id": source_record.get("id"),
        "latest_unit_price": str(source_unit_price),
        "warning": None,
    }
