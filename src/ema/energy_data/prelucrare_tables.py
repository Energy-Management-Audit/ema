"""Label-anchored physical and water tables in Prelucrare workbooks."""

from __future__ import annotations

from ema.core.office.errors import OfficeError
from ema.core.office.sheets import Book, CellRef, Sheet
from ema.energy_data.carriers import WATER_CARRIERS, Carrier, carrier_for
from ema.energy_data.model import CarrierSeries, Reading
from ema.energy_data.prelucrare_types import (
    PrelucrareData,
    cell_or_blank,
    numeric,
    sheet_named,
    year_label,
)
from ema.energy_data.source import ReaderIssue, located, normal

MONTHS = (
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


def months_in(sheet: Sheet, row: int) -> dict[int, int]:
    result: dict[int, int] = {}
    for col in range(1, sheet.max_col + 1):
        label = normal(str(cell_or_blank(sheet, row, col).value or ""))
        if label in MONTHS:
            result[MONTHS.index(label) + 1] = col
    return result


def _annual_column(sheet: Sheet, row: int, months: dict[int, int]) -> int:
    after = max(months.values())
    matches = [
        col
        for col in range(after + 1, sheet.max_col + 1)
        if normal(str(cell_or_blank(sheet, row, col).value or "")) == "total"
    ]
    return matches[0] if len(matches) == 1 else after + 1


def _read_row(  # noqa: PLR0913
    sheet: Sheet,
    row: int,
    year: int,
    months: dict[int, int],
    annual_col: int,
    unit: str,
    key: str,
    out: PrelucrareData,
) -> CarrierSeries:
    readings: dict[int, Reading] = {}
    for month, col in months.items():
        try:
            cell = sheet.value(row, col)
        except OfficeError as exc:
            out.issues.append(ReaderIssue(exc.code, str(exc), CellRef(sheet.name, row, col)))
            continue
        value = numeric(cell.value)
        readings[month] = Reading(value, unit)
        if value is not None:
            out.located[f"{key}.{year}.{month:02d}"] = located(cell, value, unit)
    total = cell_or_blank(sheet, row, annual_col)
    annual_value = numeric(total.value)
    if annual_value == 0 and all(reading.value is None for reading in readings.values()):
        annual_value = None
    annual = Reading(annual_value, unit) if annual_value is not None else None
    if annual_value is not None:
        out.located[f"{key}.{year}"] = located(total, annual_value, unit)
    return CarrierSeries(readings, annual)


def physical(  # noqa: C901
    sheet: Sheet,
    labels: tuple[str, ...],
    unit: str,
    key: str,
    out: PrelucrareData,
) -> dict[int, CarrierSeries]:
    blocks: list[tuple[int, int, dict[int, int]]] = []
    for row in range(1, sheet.max_row + 1):
        months = months_in(sheet, row)
        if len(months) == 12:
            year = next(
                (
                    year_label(cell_or_blank(sheet, row, col).value)
                    for col in range(1, min(sheet.max_col, 3) + 1)
                    if year_label(cell_or_blank(sheet, row, col).value) is not None
                ),
                None,
            )
            if year is not None:
                blocks.append((year, row, months))
    found: dict[int, CarrierSeries] = {}
    ambiguous: set[int] = set()
    targets = {normal(label) for label in labels}
    for index, (year, start, months) in enumerate(blocks):
        end = blocks[index + 1][1] if index + 1 < len(blocks) else sheet.max_row + 1
        end = next((row for row in range(start + 1, end) if len(months_in(sheet, row)) == 12), end)
        matches = [
            row
            for row in range(start + 1, end)
            if any(
                normal(str(cell_or_blank(sheet, row, col).value or "")) in targets
                for col in range(1, min(sheet.max_col, 3) + 1)
            )
        ]
        if len(matches) > 1 or (matches and year in found):
            out.issues.append(
                ReaderIssue("label_ambiguous", f"{key}.{year}", CellRef(sheet.name, matches[0], 1))
            )
            ambiguous.add(year)
            found.pop(year, None)
            for field in tuple(out.located):
                if field == f"carrier.{key}.{year}" or field.startswith(f"carrier.{key}.{year}."):
                    out.located.pop(field)
            continue
        if matches and year not in ambiguous:
            source_label = normal(str(cell_or_blank(sheet, matches[0], 3).value or ""))
            if key == Carrier.diesel.value and source_label == "motorina":
                declared = {
                    normal(str(cell_or_blank(sheet, prior, col).value or ""))
                    for prior in range(1, start)
                    for col in range(1, min(sheet.max_col, 3) + 1)
                    if normal(str(cell_or_blank(sheet, prior, col).value or "")) in {"tone", "t"}
                }
                if len(declared) != 1:
                    code = "unit_missing" if not declared else "unit_ambiguous"
                    out.issues.append(
                        ReaderIssue(code, f"{key}.{year}", CellRef(sheet.name, matches[0], 3))
                    )
                    continue
            found[year] = _read_row(
                sheet,
                matches[0],
                year,
                months,
                _annual_column(sheet, start, months),
                unit,
                f"carrier.{key}" if key != "production" else "production.main",
                out,
            )
    return found


def coke_series(sheet: Sheet, out: PrelucrareData) -> dict[int, CarrierSeries]:
    units = {
        normal(str(cell_or_blank(sheet, row, col).value or ""))
        for row in range(1, sheet.max_row + 1)
        for col in range(1, min(sheet.max_col, 3) + 1)
        if normal(str(cell_or_blank(sheet, row, col).value or "")) in {"mwh", "t", "tone"}
    }
    choices = {"MWh" if item == "mwh" else "t" for item in units}
    if len(choices) != 1:
        out.issues.append(ReaderIssue("unit_missing" if not choices else "unit_ambiguous", "coke"))
        return {}
    unit = choices.pop()
    labels = ("[MWh]",) if unit == "MWh" else ("[t]", "tone")
    return physical(sheet, labels, unit, Carrier.coke.value, out)


def water_tables(  # noqa: C901
    book: Book, out: PrelucrareData
) -> dict[Carrier, dict[int, CarrierSeries]]:
    sheet = sheet_named(book, "Consum apa", out.issues)
    if sheet is None:
        return {}
    found: dict[Carrier, dict[int, CarrierSeries]] = {}
    ambiguous: set[Carrier] = set()
    headers = [(row, months_in(sheet, row)) for row in range(1, sheet.max_row + 1)]
    for row, months in headers:
        if len(months) != 12:
            continue
        labels = [
            cell_or_blank(sheet, candidate, 2) for candidate in (row, row - 1) if candidate > 0
        ]
        carrier = next(
            (
                item
                for cell in labels
                if isinstance(cell.value, str)
                if (item := carrier_for(cell.value)) in WATER_CARRIERS
            ),
            None,
        )
        if carrier is None:
            continue
        if carrier in found:
            out.issues.append(
                ReaderIssue("label_ambiguous", f"carrier.{carrier.value}", labels[0].ref)
            )
            ambiguous.add(carrier)
            found.pop(carrier, None)
            for field in tuple(out.located):
                if field.startswith(f"carrier.{carrier.value}."):
                    out.located.pop(field)
            continue
        if carrier in ambiguous:
            continue
        annual_col = _annual_column(sheet, row, months)
        series: dict[int, CarrierSeries] = {}
        for later in range(row + 1, sheet.max_row + 1):
            year = year_label(cell_or_blank(sheet, later, 2).value)
            if year is None:
                break
            series[year] = _read_row(
                sheet, later, year, months, annual_col, "m3", f"carrier.{carrier.value}", out
            )
        found[carrier] = series
    if not found and not ambiguous:
        out.issues.append(ReaderIssue("month_header_missing", sheet.name))
    return found
