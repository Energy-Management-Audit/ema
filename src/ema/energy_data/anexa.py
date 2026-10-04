"""Read Anexa 2–3 values with their spreadsheet locations and explicit issues."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ema.core.office.errors import OfficeError
from ema.core.office.sheets import Book, CellRef, CellValue, Sheet, open_book
from ema.energy_data.anexa_audit import read_audit
from ema.energy_data.anexa_cells import (
    AnexaData,
    Measure,
)
from ema.energy_data.anexa_identity import read_identity
from ema.energy_data.anexa_monthly import read_monthly
from ema.energy_data.carriers import Carrier, carrier_for
from ema.energy_data.source import (
    Located,
    ReaderIssue,
    cell_at,
    filled,
    normal,
    number,
    row_with,
    skip_placeholder,
)


def _annual(book: Book, result: AnexaData) -> None:
    sheet = book.sheet("Date anuale")
    _annual_year(sheet, result)
    _annual_totals(sheet, result)
    _annual_fuels(sheet, result)


def _annual_year(sheet: Sheet, result: AnexaData) -> None:
    titles = [
        (row, col)
        for row in range(1, sheet.max_row + 1)
        for col in range(1, sheet.max_col + 1)
        if isinstance((value := cell_at(sheet, row, col, result.issues).value), str)
        and "anului anterior" in normal(value)
    ]
    if len(titles) != 1:
        if titles:
            result.issues.append(ReaderIssue("label_ambiguous", "Date anuale reporting year"))
            return
        result.issues.append(ReaderIssue("label_missing", "Date anuale reporting year"))
        return
    row, title_col = titles[0]
    for col in range(title_col + 1, min(sheet.max_col, title_col + 14) + 1):
        value = cell_at(sheet, row, col, result.issues)
        year = value.value
        if isinstance(year, str) and re.fullmatch(r"20\d\d", year.strip()):
            year = int(year.strip())
        if isinstance(year, int | float) and 2000 <= year <= 2100 and year == int(year):
            result.year = Located(int(year), value.ref)
            break
    if result.year is None:
        result.issues.append(ReaderIssue("year_missing", "Date anuale reporting year"))


def _annual_totals(sheet: Sheet, result: AnexaData) -> None:
    for key, labels, offset, unit in (
        ("total_tep", ("CONSUM DE ENERGIE TOTAL ANUAL",), 1, "tep/an"),
        (
            "electricity_grid_tep",
            ("ENERGIE ELECTRICĂ** – Consumul total anual din SEN",),
            0,
            "tep/an",
        ),
        (
            "electricity_grid_mwh",
            ("ENERGIE ELECTRICĂ** – Consumul total anual din SEN",),
            1,
            "MWh/an",
        ),
        ("purchased_heat_tep", ("ENERGIE TERMICĂ*** – Consumul total anual",), 0, "tep/an"),
        ("purchased_heat_gcal", ("ENERGIE TERMICĂ*** – Consumul total anual",), 1, "Gcal/an"),
        (
            "electricity_pv_mwh",
            (
                "ENERGIE ELECTRICĂ PRODUSĂ DIN SURSE RECUPERABILE ŞI/SAU "
                "REGENERABILE DE ENERGIE – Consumuri totale anuale",
            ),
            0,
            "MWh/an",
        ),
    ):
        row = row_with(sheet, labels, result.issues)
        if row is None:
            result.issues.append(ReaderIssue("label_missing", key))
            continue
        # The form places the annual value beside its unit, to the right of the label.
        for col in range(2, min(sheet.max_col, 12) + 1):
            unit_value = cell_at(sheet, row + offset, col, result.issues).value
            if isinstance(unit_value, str) and normal(unit) in normal(unit_value):
                value_col = next(
                    (
                        candidate
                        for candidate in range(col + 1, min(sheet.max_col, col + 3) + 1)
                        if cell_at(sheet, row + offset, candidate, result.issues).value is not None
                    ),
                    col + 1,
                )
                found = number(
                    cell_at(sheet, row + offset, value_col, result.issues), result.issues, unit=unit
                )
                if found is not None:
                    result.annual[key] = found
                else:
                    result.issues.append(
                        ReaderIssue(
                            "value_missing", key, CellRef(sheet.name, row + offset, value_col)
                        )
                    )
                break
        else:
            result.issues.append(ReaderIssue("unit_missing", key, CellRef(sheet.name, row, 1)))


def _annual_fuels(sheet: Sheet, result: AnexaData) -> None:
    header = row_with(sheet, ("Gaze naturale",), result.issues)
    if header is None:
        result.issues.append(ReaderIssue("label_missing", "fuel headers"))
        return
    seen: set[Carrier] = set()
    for col in range(1, min(sheet.max_col, 12) + 1):
        label = cell_at(sheet, header, col, result.issues)
        if not isinstance(label.value, str) or not label.value.strip():
            continue
        carrier = carrier_for(label.value)
        if carrier is None:
            result.issues.append(ReaderIssue("carrier_unknown", label.value, label.ref))
            continue
        if carrier in seen:
            result.annual.pop(f"{carrier.value}_raw", None)
            result.annual.pop(f"{carrier.value}_tep", None)
            result.issues.append(ReaderIssue("carrier_ambiguous", label.value, label.ref))
            continue
        seen.add(carrier)
        unit_rows = _fuel_unit_rows(sheet, header, col, result)
        if len(unit_rows) < 2:
            result.issues.append(ReaderIssue("unit_missing", label.value, label.ref))
            continue
        raw_unit = cell_at(sheet, header + unit_rows[0], col, result.issues).value
        tep_unit = cell_at(sheet, header + unit_rows[1], col, result.issues).value
        if not isinstance(tep_unit, str) or not normal(tep_unit).startswith("tep"):
            result.issues.append(ReaderIssue("unit_missing", f"{label.value}: tep/an", label.ref))
            continue
        raw = number(cell_at(sheet, header + unit_rows[0] + 1, col, result.issues), result.issues)
        tep = number(
            cell_at(sheet, header + unit_rows[1] + 1, col, result.issues),
            result.issues,
            unit="tep/an",
        )
        if raw is not None:
            unit = raw_unit.strip(" []") if isinstance(raw_unit, str) else None
            result.annual[f"{carrier.value}_raw"] = Located(
                raw.value, raw.ref, unit, displayed_decimals=raw.displayed_decimals
            )
        if tep is not None:
            result.annual[f"{carrier.value}_tep"] = tep


def _fuel_unit_rows(sheet: Sheet, header: int, col: int, result: AnexaData) -> list[int]:
    rows: list[int] = []
    for offset in range(1, 8):
        value = cell_at(sheet, header + offset, col, result.issues).value
        if isinstance(value, str) and normal(value).endswith("an"):
            rows.append(offset)
    return rows


def _measure_header(sheet: Sheet, kind: str, result: AnexaData) -> tuple[int, int, int] | None:
    if kind == "planned":
        row = row_with(
            sheet,
            ("Descrierea măsurii", "Descrierea măsurii aplicate"),
            result.issues,
            limit=20,
        )
        if row is None:
            return None
        description_col = next(
            (
                col
                for col in range(1, min(sheet.max_col, 8) + 1)
                if isinstance((value := cell_at(sheet, row, col, result.issues).value), str)
                and normal(value).startswith("descrierea masurii")
            ),
            None,
        )
        year_col = next(
            (
                col
                for col in range(1, min(sheet.max_col, 8) + 1)
                if isinstance((value := cell_at(sheet, row, col, result.issues).value), str)
                and normal(value).startswith("termenul de aplicare")
            ),
            None,
        )
        if description_col is None or year_col is None or year_col <= description_col:
            return None
        return row, description_col, year_col
    for row in range(1, min(sheet.max_row, 20) + 1):
        for col in range(2, min(sheet.max_col, 5) + 1):
            value = cell_at(sheet, row, col, result.issues).value
            if isinstance(value, str) and "data punerii" in normal(value):
                previous = cell_at(sheet, row, col - 1, result.issues).value
                preceding = cell_at(sheet, row, col - 2, result.issues).value if col > 2 else None
                if isinstance(previous, str) and normal(previous).startswith("descrierea masurii"):
                    return row, col - 1, col
                if (
                    previous is None
                    and isinstance(preceding, str)
                    and normal(preceding).startswith("descrierea masurii")
                ):
                    return row, col - 1, col
    return None


def _measure_year(cell: CellValue) -> Located | None:
    raw = cell.value
    if isinstance(raw, datetime):
        return Located(raw.year, cell.ref)
    if isinstance(raw, int | float) and 1990 <= raw <= 2100 and raw == int(raw):
        return Located(int(raw), cell.ref)
    if isinstance(raw, str) and re.fullmatch(r"20\d\d", raw.strip()):
        return Located(int(raw.strip()), cell.ref)
    if isinstance(raw, str) and (match := re.fullmatch(r"\d{2}\.\d{2}\.(20\d\d)", raw.strip())):
        return Located(int(match.group(1)), cell.ref)
    return None


def _measure_columns(sheet: Sheet, header: int, result: AnexaData) -> dict[str, int]:
    columns: dict[str, int] = {}
    for col in range(1, min(sheet.max_col, 15) + 1):
        heading = cell_at(sheet, header, col, result.issues).value
        unit = cell_at(sheet, header + 1, col, result.issues).value
        name = normal(heading) if isinstance(heading, str) else ""
        measure_unit = normal(unit) if isinstance(unit, str) else ""
        if name.startswith(("durata de recuperare", "estimarea duratei de recuperare")):
            columns["payback_years"] = col
        elif name.startswith(("costul investitiei", "costul aplicarii masurii")):
            columns["investment_thousand_lei"] = col
        elif measure_unit.startswith("mwh an"):
            columns["saving_mwh"] = col
        elif measure_unit.startswith("tep an"):
            columns["saving_tep"] = col
        elif name.startswith("economia de cost"):
            columns["saving_thousand_lei"] = col
    for key in (
        "payback_years",
        "investment_thousand_lei",
        "saving_mwh",
        "saving_tep",
        "saving_thousand_lei",
    ):
        if key not in columns:
            result.issues.append(ReaderIssue("label_missing", f"{sheet.name}: {key}"))
    return columns


def _measure_row_cells(
    sheet: Sheet,
    row: int,
    year_col: int,
    columns: dict[str, int],
    description: Located,
    issues: list[ReaderIssue],
) -> tuple[CellValue, dict[str, CellValue]] | None:
    row_issues: list[ReaderIssue] = []
    year_cell = cell_at(sheet, row, year_col, row_issues)
    raw_values = {key: cell_at(sheet, row, col, row_issues) for key, col in columns.items()}
    if skip_placeholder(description, raw_values.values(), issues):
        return None
    issues.extend(row_issues)
    return year_cell, raw_values


def _measure_values(raw: dict[str, CellValue], issues: list[ReaderIssue]) -> dict[str, Located]:
    values: dict[str, Located] = {}
    for key, unit in (
        ("payback_years", "ani"),
        ("investment_thousand_lei", "mii lei"),
        ("saving_mwh", "MWh/an"),
        ("saving_tep", "tep/an"),
        ("saving_thousand_lei", "mii lei/an"),
    ):
        if key not in raw:
            continue
        value = number(raw[key], issues, unit=unit)
        if value is not None:
            values[key] = value
    return values


def _measures(sheet: Sheet, kind: str, result: AnexaData) -> list[Measure]:
    items: list[Measure] = []
    location = _measure_header(sheet, kind, result)
    if location is None:
        result.issues.append(ReaderIssue("label_missing", f"{sheet.name}: measure header"))
        return items
    header, description_col, year_col = location
    columns = _measure_columns(sheet, header, result)
    for row in range(header + 1, min(sheet.max_row, 400) + 1):
        description = filled(cell_at(sheet, row, description_col, result.issues))
        if description is None or not isinstance(description.value, str):
            continue
        label = normal(description.value)
        if not label or label.startswith(
            ("descrierea", "masuri pe termen", "total", "data trimiterii")
        ):
            continue
        cells = _measure_row_cells(sheet, row, year_col, columns, description, result.issues)
        if cells is None:
            continue
        year_cell, raw_values = cells
        year = _measure_year(year_cell)
        if year is None:
            result.issues.append(
                ReaderIssue("commissioning_year_missing", str(description.value), year_cell.ref)
            )
        values = _measure_values(raw_values, result.issues)
        if not values:
            result.issues.append(
                ReaderIssue("values_missing", str(description.value), description.ref)
            )
        location = (
            filled(cell_at(sheet, row, description_col - 1, result.issues))
            if description_col > 2
            else None
        )
        items.append(Measure(kind, description, year, values, location))
    return items


def read_anexa(book: Book) -> AnexaData:
    """Read independent form sections, retaining usable values when another section fails."""

    result = AnexaData()
    for section in (read_identity, _annual, read_monthly, _measure_sheets, read_audit):
        try:
            section(book, result)
        except OfficeError as exc:
            result.issues.append(ReaderIssue(exc.code, str(exc)))
    return result


def _measure_sheets(book: Book, result: AnexaData) -> None:
    existing = next(
        (
            name
            for name in book.sheet_names
            if normal(name).startswith("solutii ee") and "planificate" not in normal(name)
        ),
        None,
    )
    if existing is not None:
        result.existing_measures = _measures(book.sheet(existing), "existing", result)
    else:
        result.issues.append(ReaderIssue("sheet_missing", "Solutii EE existente"))
    planned = next(
        (name for name in book.sheet_names if normal(name) == "solutii ee planificate"), None
    )
    if planned is not None:
        result.planned_measures = _measures(book.sheet(planned), "planned", result)
    else:
        result.issues.append(ReaderIssue("sheet_missing", "Solutii EE planificate"))


def parse_anexa(path: Path) -> AnexaData:
    """Read an XLS or XLSX annex and close both workbook handles."""

    book = open_book(path)
    try:
        return read_anexa(book)
    finally:
        book.close()
