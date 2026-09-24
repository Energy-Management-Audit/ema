"""Label anchored consumption and production blocks in Necesar info."""

from __future__ import annotations

from typing import Literal, cast

from ema.core.office.sheets import CellRef, Sheet
from ema.energy_data.carriers import WATER_CARRIERS, Carrier, carrier_for
from ema.energy_data.necesar_model import Consumption, NecesarInfo, Production, YearValues
from ema.energy_data.source import Located, ReaderIssue, cell_at, normal, number

_MONTHS = (
    "ianuarie",
    "februarie",
    "martie",
    "aprilie",
    "mai",
    "iunie",
    "iulie",
    "august",
    "septembrie",
    "octombrie",
    "noiembrie",
    "decembrie",
)


def _year(value: object) -> int | None:
    if isinstance(value, int | float) and 2000 <= value <= 2100 and value == int(value):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        if 2000 <= parsed <= 2100:
            return parsed
    return None


def _months(sheet: Sheet, row: int, issues: list[ReaderIssue], start: int) -> bool:
    return all(
        normal(str(cell_at(sheet, row, start + index, issues).value or "")) == month
        for index, month in enumerate(_MONTHS)
    )


def _values(
    sheet: Sheet,
    row: int,
    issues: list[ReaderIssue],
    unit: str,
    start: int,
    *,
    check: Literal["physical", "none"] = "physical",
) -> tuple[tuple[Located | None, ...], Located | None]:
    months = tuple(
        number(cell_at(sheet, row, col, issues), issues, unit=unit)
        for col in range(start, start + 12)
    )
    total = number(cell_at(sheet, row, start + 12, issues), issues, unit=unit)
    if (
        check == "physical"
        and total is not None
        and all(value is not None for value in months)
        and abs(
            sum(float(cast(int | float, value.value)) for value in months if value)
            - float(cast(int | float, total.value))
        )
        > 0.01
    ):
        issues.append(
            ReaderIssue("total_mismatch", "monthly sum differs from filed total", total.ref)
        )
    if check == "physical" and total is None and all(value is None for value in months):
        issues.append(
            ReaderIssue("values_missing", "year group has no values", CellRef(sheet.name, row, 1))
        )
    return months, total


def _unit(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    key = normal(value)
    if key == "tone":
        return "t"
    if key in {"mwh", "kwh", "gcal", "nm3", "m3", "tep"}:
        return {"mwh": "MWh", "kwh": "kWh", "gcal": "Gcal", "nm3": "Nm3", "m3": "m³", "tep": "tep"}[
            key
        ]
    return None


def _year_values(
    sheet: Sheet, year_row: int, issues: list[ReaderIssue], *, water: bool
) -> YearValues | None:
    if water and not _unit(cell_at(sheet, year_row + 1, 1, issues).value):
        row, unit = year_row, "m³"
    else:
        row = year_row + 1
        unit = _unit(cell_at(sheet, row, 1, issues).value)
        if unit is None:
            issues.append(
                ReaderIssue("unit_missing", "consumption year", CellRef(sheet.name, row, 1))
            )
            return None
    months, total = _values(sheet, row, issues, unit, 2)
    tep_months: tuple[Located | None, ...] = (None,) * 12
    tep_total = None
    if not water and _unit(cell_at(sheet, row + 1, 1, issues).value) == "tep":
        tep_months, tep_total = _values(sheet, row + 1, issues, "tep", 2, check="none")
    return YearValues(months, total, tep_months, tep_total)


def _installed_power(sheet: Sheet, row: int, block: Consumption, issues: list[ReaderIssue]) -> None:
    power = cell_at(sheet, row, 2, issues)
    unit = cell_at(sheet, row, 3, issues).value
    if power.value is None:
        issues.append(ReaderIssue("value_missing", "installed power", power.ref))
    else:
        suffix = (
            str(unit).strip()
            if isinstance(unit, str) and normal(unit) in {"kw", "kwp", "mwt"}
            else None
        )
        block.installed_power.append(Located(power.value, power.ref, suffix))


def _read_consumption_block(
    sheet: Sheet, info: NecesarInfo, start: int, end: int, label: str, ambiguous: set[Carrier]
) -> None:
    carrier = carrier_for(label)
    if carrier is None:
        info.issues.append(ReaderIssue("carrier_unknown", label, CellRef(sheet.name, start, 1)))
        return
    target = info.water if carrier in WATER_CARRIERS else info.carriers
    if carrier in target or carrier in ambiguous:
        info.issues.append(ReaderIssue("carrier_ambiguous", label, CellRef(sheet.name, start, 1)))
        target.pop(carrier)
        ambiguous.add(carrier)
        return
    block = Consumption(Located(label, CellRef(sheet.name, start, 1)))
    target[carrier] = block
    for row in range(start + 1, end):
        value = cell_at(sheet, row, 1, info.issues).value
        key = normal(value) if isinstance(value, str) else ""
        if key.startswith("puterea "):
            _installed_power(sheet, row, block, info.issues)
            continue
        year = _year(value)
        if year is None:
            continue
        if year in block.years:
            info.issues.append(
                ReaderIssue("year_ambiguous", str(year), CellRef(sheet.name, row, 1))
            )
            continue
        header_row = (
            start if carrier in WATER_CARRIERS and _months(sheet, start, info.issues, 2) else row
        )
        if not _months(sheet, header_row, info.issues, 2):
            info.issues.append(
                ReaderIssue("month_header_missing", label, CellRef(sheet.name, row, 1))
            )
            continue
        values = _year_values(sheet, row, info.issues, water=carrier in WATER_CARRIERS)
        if values is not None:
            block.years[year] = values
    if not block.years:
        info.issues.append(ReaderIssue("year_missing", label, block.label.ref))


def read_consumption(sheet: Sheet, info: NecesarInfo) -> None:
    anchors: list[tuple[int, str]] = []
    ambiguous: set[Carrier] = set()
    for row in range(1, sheet.max_row + 1):
        value = cell_at(sheet, row, 1, info.issues).value
        if isinstance(value, str) and normal(value).startswith("consum "):
            anchors.append((row, value))
    if not anchors:
        info.issues.append(ReaderIssue("label_missing", "Consum blocks"))
    for index, (start, label) in enumerate(anchors):
        end = anchors[index + 1][0] if index + 1 < len(anchors) else sheet.max_row + 1
        _read_consumption_block(sheet, info, start, end, label, ambiguous)


def _production_row(
    sheet: Sheet,
    info: NecesarInfo,
    row: int,
    year: int,
    by_name: dict[tuple[str, str], Production],
) -> bool:
    unit_cell = cell_at(sheet, row, 2, info.issues)
    name_cell = cell_at(sheet, row, 1, info.issues)
    if not isinstance(unit_cell.value, str) or not unit_cell.value.strip():
        return isinstance(name_cell.value, str) and bool(name_cell.value.strip())
    if not any(
        cell_at(sheet, row, col, info.issues).value is not None
        for col in range(3, min(sheet.max_col, 15) + 1)
    ):
        return False
    name = name_cell if name_cell.value is not None else unit_cell
    name_value = name.value
    if name_value is None:
        return False
    key = (normal(str(name_value)), normal(unit_cell.value))
    if key not in by_name:
        current = Production(Located(name_value, name.ref), Located(unit_cell.value, unit_cell.ref))
        by_name[key] = current
        info.production.append(current)
        if name_cell.value is None:
            info.issues.append(ReaderIssue("label_from_unit_cell", "production", unit_cell.ref))
    else:
        current = by_name[key]
    months, total = _values(sheet, row, info.issues, unit_cell.value, 3)
    if year in current.years:
        info.issues.append(ReaderIssue("production_ambiguous", str(year), name.ref))
    else:
        current.years[year] = YearValues(months, total)
    return False


def read_production(sheet: Sheet, info: NecesarInfo) -> None:
    by_name: dict[tuple[str, str], Production] = {}
    for row in range(1, sheet.max_row + 1):
        year = _year(cell_at(sheet, row, 2, info.issues).value)
        if year is None or not _months(sheet, row, info.issues, 3):
            continue
        for data_row in range(row + 1, sheet.max_row + 1):
            if _year(cell_at(sheet, data_row, 2, info.issues).value) is not None and _months(
                sheet, data_row, info.issues, 3
            ):
                break
            if _production_row(sheet, info, data_row, year, by_name):
                break
    if not info.production:
        info.issues.append(ReaderIssue("label_missing", "production rows"))
