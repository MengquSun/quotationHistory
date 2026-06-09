from decimal import Decimal

from app.services.field_mapping import detect_field_mapping
from app.services.quote_engine import choose_price_source, estimate_cost
from app.services.units import parse_quantity


def test_detect_field_mapping_chinese_headers():
    mapping = detect_field_mapping(["化合物名称", "单价 RMB", "采购数量", "备注信息"])

    assert mapping["化合物名称"] == "material_name"
    assert mapping["单价 RMB"] == "price"
    assert mapping["采购数量"] == "quantity"
    assert mapping["备注信息"] == "remark"


def test_parse_quantity_mass_to_grams():
    parsed = parse_quantity("1.5 kg")

    assert parsed.quantity_value == Decimal("1.5")
    assert parsed.quantity_unit == "kg"
    assert parsed.normalized_quantity == Decimal("1500.0")
    assert parsed.normalized_unit == "g"


def test_quote_prefers_latest_purchase_over_inquiry():
    records = [
        {"id": 1, "record_type": "inquiry", "record_date": "2026-06-07", "unit_price": "0.8", "normalized_unit": "g"},
        {"id": 2, "record_type": "purchase", "record_date": "2026-05-01", "unit_price": "0.6", "normalized_unit": "g"},
    ]

    source = choose_price_source(records)
    result = estimate_cost(source, "500g", None)

    assert source["id"] == 2
    assert result["estimated_cost"] == "300.0000"
