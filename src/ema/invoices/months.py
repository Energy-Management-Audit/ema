"""Calendar month extraction for invoice periods."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, cast

_DATE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})|(\d{4})-(\d{2})-(\d{2})(?!\d)")


def month_from_value(value: object) -> str | None:
    if value is None:
        return None
    dates: list[date] = []
    for match in _DATE.finditer(str(value)):
        try:
            if match.group(1):
                dates.append(date(int(match.group(3)), int(match.group(2)), int(match.group(1))))
            else:
                dates.append(date(int(match.group(4)), int(match.group(5)), int(match.group(6))))
        except ValueError:
            continue
    return dates[-1].strftime("%Y-%m") if dates else None


def invoice_month(fields: dict[str, Any]) -> str | None:
    for key in ("consumption_period", "billing_period", "invoice_date"):
        field = cast("dict[str, Any]", fields.get(key) or {})
        month = month_from_value(field.get("value"))
        if month is not None:
            return month
    return None


def missing_months(months: set[str]) -> list[str]:
    if len(months) < 2:
        return []
    first, last = min(months), max(months)
    year, month = map(int, first.split("-"))
    missing: list[str] = []
    while (year, month) < tuple(map(int, last.split("-"))):
        current = f"{year:04d}-{month:02d}"
        if current not in months:
            missing.append(current)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return missing
