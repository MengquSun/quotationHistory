from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable


SYSTEM_FIELDS = {
    "material_name": {"required": True, "label": "物料名称"},
    "price": {"required": True, "label": "价格"},
    "quantity": {"required": False, "label": "数量"},
    "unit": {"required": False, "label": "单位"},
    "currency": {"required": False, "label": "币种"},
    "remark": {"required": False, "label": "备注"},
    "record_date": {"required": False, "label": "日期"},
    "requester": {"required": False, "label": "询价/采购人"},
    "supplier": {"required": False, "label": "供应商"},
    "cas_number": {"required": False, "label": "CAS"},
}

FIELD_ALIASES = {
    "material_name": ["产品名称", "名称", "名字", "化学品名", "品名", "物料", "化合物名称", "name", "product name", "material"],
    "price": ["价格", "报价", "单价", "金额", "单价 rmb", "报价金额", "price", "quote", "amount"],
    "quantity": ["数量", "用量", "规格", "采购数量", "qty", "quantity", "size"],
    "unit": ["单位", "计量单位", "unit"],
    "currency": ["币种", "货币", "currency"],
    "remark": ["备注", "说明", "备注信息", "note", "remark", "comment"],
    "record_date": ["日期", "询价日期", "采购日期", "date"],
    "requester": ["询价人", "采购人", "谁寻的", "requester", "buyer"],
    "supplier": ["供应商", "厂家", "vendor", "supplier"],
    "cas_number": ["cas", "cas号", "cas 号", "cas number", "cas registry number"],
}


def normalize_header(value: object) -> str:
    return str(value or "").strip().lower().replace("_", " ").replace("-", " ")


def _score(header: str, alias: str) -> float:
    header_norm = normalize_header(header)
    alias_norm = normalize_header(alias)
    if not header_norm or not alias_norm:
        return 0
    if header_norm == alias_norm:
        return 1
    if alias_norm in header_norm or header_norm in alias_norm:
        return 0.94
    return SequenceMatcher(None, header_norm, alias_norm).ratio()


def detect_field_mapping(headers: Iterable[object], threshold: float = 0.62) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used_fields: set[str] = set()

    for header in headers:
        best_field = ""
        best_score = 0.0
        for field, aliases in FIELD_ALIASES.items():
            if field in used_fields:
                continue
            field_score = max(_score(str(header), alias) for alias in aliases)
            if field_score > best_score:
                best_field = field
                best_score = field_score
        if best_field and best_score >= threshold:
            mapping[str(header)] = best_field
            used_fields.add(best_field)

    return mapping


def missing_required_fields(mapping: dict[str, str]) -> list[str]:
    mapped = set(mapping.values())
    return [field for field, meta in SYSTEM_FIELDS.items() if meta["required"] and field not in mapped]
