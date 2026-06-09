from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


MASS_FACTORS_TO_G = {
    "mg": Decimal("0.001"),
    "毫克": Decimal("0.001"),
    "g": Decimal("1"),
    "克": Decimal("1"),
    "kg": Decimal("1000"),
    "公斤": Decimal("1000"),
    "千克": Decimal("1000"),
}

VOLUME_FACTORS_TO_ML = {
    "ml": Decimal("1"),
    "毫升": Decimal("1"),
    "l": Decimal("1000"),
    "L": Decimal("1000"),
    "升": Decimal("1000"),
}

COUNT_UNITS = {
    "个": "each",
    "只": "each",
    "瓶": "bottle",
    "片": "piece",
    "份": "pack",
    "包": "pack",
    "pack": "pack",
    "packs": "pack",
    "桶": "drum",
    "drum": "drum",
    "each": "each",
    "bottle": "bottle",
    "piece": "piece",
}

UNIT_ALIASES = {
    **{unit.lower(): unit for unit in MASS_FACTORS_TO_G},
    **{unit.lower(): unit for unit in VOLUME_FACTORS_TO_ML},
    **{unit.lower(): unit for unit in COUNT_UNITS},
}


@dataclass(frozen=True)
class ParsedQuantity:
    raw_value: str
    quantity_value: Decimal | None
    quantity_unit: str | None
    normalized_quantity: Decimal | None
    normalized_unit: str | None
    convertible: bool


def parse_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def normalize_unit(unit: object) -> str | None:
    if unit is None:
        return None
    raw = str(unit).strip()
    if not raw:
        return None
    return UNIT_ALIASES.get(raw.lower(), raw)


def parse_quantity(value: object, unit: object | None = None) -> ParsedQuantity:
    raw = "" if value is None else str(value).strip()
    explicit_unit = normalize_unit(unit)
    number = parse_decimal(value)
    parsed_unit = explicit_unit

    if number is None and raw:
        match = re.search(r"([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*([A-Za-z\u4e00-\u9fff]+)?", raw)
        if match:
            number = parse_decimal(match.group(1))
            parsed_unit = explicit_unit or normalize_unit(match.group(2))

    if number is None:
        return ParsedQuantity(raw, None, parsed_unit, None, None, False)

    if parsed_unit in MASS_FACTORS_TO_G:
        return ParsedQuantity(raw, number, parsed_unit, number * MASS_FACTORS_TO_G[parsed_unit], "g", True)
    if parsed_unit in VOLUME_FACTORS_TO_ML:
        return ParsedQuantity(raw, number, parsed_unit, number * VOLUME_FACTORS_TO_ML[parsed_unit], "ml", True)
    if parsed_unit in COUNT_UNITS:
        normalized = COUNT_UNITS[parsed_unit]
        return ParsedQuantity(raw, number, parsed_unit, number, normalized, False)

    return ParsedQuantity(raw, number, parsed_unit, number, parsed_unit, False)


def calculate_unit_price(price: Decimal | None, quantity: ParsedQuantity) -> Decimal | None:
    if price is None or not quantity.normalized_quantity:
        return None
    if quantity.normalized_quantity == 0:
        return None
    return price / quantity.normalized_quantity
