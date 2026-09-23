from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_ROMANIAN_NUMBER = re.compile(r"^-?(?:[0-9]+|[1-9][0-9]{0,2}(?:\.[0-9]{3})+)(?:,[0-9]+)?$")
_ENGLISH_NUMBER = re.compile(r"^-?(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?$")


def parse_romanian_decimal(raw: str, *, decimal_dot: bool = False) -> Decimal:
    cleaned = (
        raw.strip()
        .replace(" ", "")
        .replace("\u00a0", "")
        .replace("\u2212", "-")
        .replace("\u2013", "-")
    )
    if decimal_dot:
        if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", cleaned):
            raise ValueError(f"Invalid machine decimal: {raw!r}")
        return Decimal(cleaned)
    if not _ROMANIAN_NUMBER.fullmatch(cleaned):
        raise ValueError(f"Ambiguous Romanian decimal: {raw!r}")
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError(f"Invalid Romanian decimal: {raw!r}") from error


def parse_english_decimal(raw: str) -> Decimal:
    cleaned = (
        raw.strip()
        .replace(" ", "")
        .replace("\u00a0", "")
        .replace("\u2212", "-")
        .replace("\u2013", "-")
    )
    if not _ENGLISH_NUMBER.fullmatch(cleaned):
        raise ValueError(f"Invalid English decimal: {raw!r}")
    return Decimal(cleaned.replace(",", ""))


def parse_romanian_date(raw: str) -> date:
    normalized = raw.strip().replace("/", ".").replace("-", ".")
    try:
        return datetime.strptime(normalized, "%d.%m.%Y").date()
    except ValueError as error:
        raise ValueError(f"Invalid Romanian date: {raw!r}") from error


def normalize_quantity_and_price(
    quantity: Decimal,
    unit_price: Decimal,
    source_unit: str,
) -> tuple[Decimal, str, Decimal]:
    normalized_unit = source_unit.strip()
    if normalized_unit.lower() == "mwh":
        return quantity * Decimal("1000"), "kWh", unit_price / Decimal("1000")
    if normalized_unit.lower() == "kwh":
        return quantity, "kWh", unit_price
    if normalized_unit.lower() == "kvarh":
        return quantity, "kVArh", unit_price
    if normalized_unit.lower() == "mvarh":
        return quantity * Decimal("1000"), "kVArh", unit_price / Decimal("1000")
    return quantity, normalized_unit, unit_price
