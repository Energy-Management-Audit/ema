"""The cells of the ch. 2-3 tables, from the reviewed Necesar info fields."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from ema.audit.read_equipment import EQUIPMENT_ROW, FORKLIFT, TRANSFORMER, VEHICLE
from ema.core.office.numbers_ro import format_number
from ema.core.review.models import Field

EMPLOYEES = "audit.employees."
TURNOVER = "turnover."
# What the render reads (the stage binds each family, so a new row makes the render stale); the
# transformers have no table, the ch. 3 draft cites them.
FAMILIES = (EMPLOYEES, TURNOVER, EQUIPMENT_ROW, FORKLIFT, VEHICLE, TRANSFORMER)

# None is a value the sources do not hold: the table shows a red n.d.
type Cell = str | None


@dataclass(frozen=True)
class YearlyTable:
    years: list[int]
    cells: list[Cell]
    values: list[float | None]

    @property
    def rows(self) -> list[list[Cell]]:
        return [[str(year), cell] for year, cell in zip(self.years, self.cells, strict=True)]


def _value(field: Field | None) -> object:
    if field is None or field.review == "rejected" or field.presence != "found":
        return None
    return field.value


def _number(field: Field | None) -> float | None:
    value = _value(field)
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return None
    return float(value)


def shown(field: Field | None) -> Cell:
    value = _value(field)
    if value is None:
        return None
    if field is not None and _number(field) is not None:
        return format_number(value, field.decimals, None, field.grouping)  # type: ignore[arg-type]
    text = " ".join(str(value).split())
    return text or None


def yearly(fields: Iterable[Field], family: str) -> YearlyTable:
    """One entry per year the sources hold, oldest first."""
    pattern = re.compile(rf"^{re.escape(family)}(\d{{4}})$")
    found = {
        int(match.group(1)): field
        for field in fields
        if (match := pattern.match(field.key)) is not None
    }
    years = sorted(found)
    return YearlyTable(
        years,
        [shown(found[year]) for year in years],
        [_number(found[year]) for year in years],
    )


def numbered(fields: Iterable[Field], family: str) -> list[dict[str, Field]]:
    """The rows of one family in sheet order, each by role."""
    pattern = re.compile(rf"^{re.escape(family)}(\d+)\.(\w+)$")
    rows: dict[int, dict[str, Field]] = {}
    for field in fields:
        if (match := pattern.match(field.key)) is not None:
            rows.setdefault(int(match.group(1)), {})[match.group(2)] = field
    return [rows[number] for number in sorted(rows)]


def _joined(*parts: Cell) -> Cell:
    text = " ".join(part for part in parts if part)
    return text or None


def boiler_rows(fields: Iterable[Field]) -> list[list[Cell]]:
    """Rows for the general equipment table in Necesar sheet order."""
    return [
        [
            shown(row.get("name")),
            shown(row.get("process")),
            shown(row.get("count")),
            shown(row.get("power")),
            shown(row.get("resource")),
        ]
        for row in numbered(fields, EQUIPMENT_ROW)
    ]


def _brand(text: Cell) -> Cell:
    return re.sub(r"(?i)^\s*marca\s*:\s*", "", text).strip() or None if text else None


def _model(text: Cell) -> Cell:
    """The model the sheet prints after "TIP :", without the serial that follows it."""
    if not text:
        return None
    head = re.split(r"\s*/\s*seria\b", text, flags=re.IGNORECASE)[0]
    return re.sub(r"(?i)^\s*tip\s*:\s*", "", head).strip() or None


def vehicle_rows(fields: Iterable[Field]) -> list[list[Cell]]:
    """Tip autovehicul, nr. buc. and consum: the vehicles, then the forklifts (one row each).

    The sheets hold no consumption, so that column is a red n.d.
    """
    rows: list[list[Cell]] = [
        [
            _joined(shown(row.get("name")), shown(row.get("maker")), shown(row.get("type"))),
            shown(row.get("count")),
            None,
        ]
        for row in numbered(fields, VEHICLE)
    ]
    for row in numbered(fields, FORKLIFT):
        fuel = shown(row.get("fuel"))
        name = _joined(_brand(shown(row.get("name"))), _model(shown(row.get("type"))))
        label = _joined("Autostivuitor", name, f"({fuel})" if fuel else None) if name else None
        rows.append([label, "1", None])
    return rows
