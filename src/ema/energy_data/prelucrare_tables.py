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


def _annual_column(sheet: Sheet, row: int, months: dict[int, int]) -> int | None:
    after = max(months.values())
    matches = [
        col
        for col in range(after + 1, sheet.max_col + 1)
        if normal(str(cell_or_blank(sheet, row, col).value or "")) == "total"
    ]
    return matches[0] if len(matches) == 1 else None


def _read_row(  # noqa: PLR0913
    sheet: Sheet,
    row: int,
    year: int,
    months: dict[int, int],
    annual_col: int | None,
    *,
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
    total = cell_or_blank(sheet, row, annual_col) if annual_col is not None else None
    annual_value = numeric(total.value) if total is not None else None
    if annual_value == 0 and all(reading.value is None for reading in readings.values()):
        annual_value = None
    annual = Reading(annual_value, unit) if annual_value is not None else None
    if annual_value is not None and total is not None:
        out.located[f"{key}.{year}"] = located(total, annual_value, unit)
    adjacent = cell_or_blank(sheet, row, max(months.values()) + 1)
    if (prior_value := numeric(adjacent.value)) is not None:
        out.previous_annual[f"{key}.{year}"] = Reading(prior_value, unit)
        out.previous_annual_located[f"{key}.{year}"] = located(adjacent, prior_value, unit)
    return CarrierSeries(readings, annual)


def _row_unit(label: str) -> str | None:
    normalized = normal(label)
    return {"mwh": "MWh", "t": "t", "tone": "t", "m3": "m3", "gcal": "Gcal"}.get(normalized)


def _year_blocks(sheet: Sheet) -> list[tuple[int, int, dict[int, int]]]:
    blocks: list[tuple[int, int, dict[int, int]]] = []
    for row in range(1, sheet.max_row + 1):
        months = months_in(sheet, row)
        if len(months) != 12:
            continue
        year = next(
            (
                item
                for col in range(1, min(sheet.max_col, 3) + 1)
                if (item := year_label(cell_or_blank(sheet, row, col).value)) is not None
            ),
            None,
        )
        if year is not None:
            blocks.append((year, row, months))
    return blocks


def physical(
    sheet: Sheet,
    labels: tuple[str, ...],
    unit: str,
    key: str,
    out: PrelucrareData,
) -> dict[int, CarrierSeries]:
    blocks = _year_blocks(sheet)
    found: dict[int, CarrierSeries] = {}
    ambiguous: set[int] = set()
    targets = {normal(label) for label in labels}
    bare_fuel = {"motorina", "benzina", "gpl"}
    declarations: set[str] = (
        {
            normal(str(cell_or_blank(sheet, row, col).value or ""))
            for row in range(1, blocks[0][1])
            for col in range(1, min(sheet.max_col, 3) + 1)
            if normal(str(cell_or_blank(sheet, row, col).value or "")) in {"tone", "t"}
        }
        if blocks
        else set()
    )
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
        row_units = {_row_unit(str(cell_or_blank(sheet, row, 3).value or "")) for row in matches}
        if len(matches) > 1 or (matches and year in found):
            code = (
                "unit_ambiguous"
                if key == Carrier.coke.value and len(row_units) > 1
                else "label_ambiguous"
            )
            out.issues.append(
                ReaderIssue(code, f"{key}.{year}", CellRef(sheet.name, matches[0], 1))
            )
            ambiguous.add(year)
            found.pop(year, None)
            for field in tuple(out.located):
                if field == f"carrier.{key}.{year}" or field.startswith(f"carrier.{key}.{year}."):
                    out.located.pop(field)
            continue
        if matches and year not in ambiguous:
            source_label = normal(str(cell_or_blank(sheet, matches[0], 3).value or ""))
            if (
                source_label in bare_fuel
                and key in {Carrier.diesel.value, Carrier.petrol.value, Carrier.lpg.value}
                and len(declarations) != 1
            ):
                code = "unit_missing" if not declarations else "unit_ambiguous"
                out.issues.append(
                    ReaderIssue(code, f"{key}.{year}", CellRef(sheet.name, matches[0], 3))
                )
                return {}
            resolved_unit = _row_unit(source_label) if key == Carrier.coke.value else unit
            if resolved_unit is None:
                out.issues.append(
                    ReaderIssue("unit_missing", f"{key}.{year}", CellRef(sheet.name, matches[0], 3))
                )
                continue
            found[year] = _read_row(
                sheet,
                matches[0],
                year,
                months,
                _annual_column(sheet, start, months),
                unit=resolved_unit,
                key=f"carrier.{key}" if key != "production" else "production.main",
                out=out,
            )
            if source_label in bare_fuel and key in {
                Carrier.diesel.value,
                Carrier.petrol.value,
                Carrier.lpg.value,
            }:
                out.deferred_series.add((Carrier(key), year))
    return found


def coke_series(sheet: Sheet, out: PrelucrareData) -> dict[int, CarrierSeries]:
    series = physical(sheet, ("[MWh]", "[t]", "tone"), "", Carrier.coke.value, out)
    if not series and not any(issue.detail.startswith("coke.") for issue in out.issues):
        out.issues.append(ReaderIssue("unit_missing", "coke"))
    return series


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
                sheet,
                later,
                year,
                months,
                annual_col,
                unit="m3",
                key=f"carrier.{carrier.value}",
                out=out,
            )
        if found:
            out.deferred_series.update((carrier, year) for year in series)
        found[carrier] = series
    if not found and not ambiguous:
        out.issues.append(ReaderIssue("month_header_missing", sheet.name))
    return found
