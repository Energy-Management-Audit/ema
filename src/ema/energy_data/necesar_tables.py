"""Economic rows and generic inventory tables from Necesar info."""

from __future__ import annotations

from ema.core.office.sheets import CellRef, Sheet
from ema.energy_data.necesar_model import GenericRow, GenericTable, NecesarInfo
from ema.energy_data.source import ReaderIssue, cell_at, filled, normal, number


def _year(value: object) -> int | None:
    if isinstance(value, int | float) and 2000 <= value <= 2100 and value == int(value):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        year = int(value.strip())
        if 2000 <= year <= 2100:
            return year
    return None


def _economic_key(label: str) -> str | None:
    key = normal(label)
    for prefix, result in (
        ("cifra de afaceri", "turnover_lei"),
        ("valoarea totala a productiei", "production_value_lei"),
        ("venituri totale din exploatare", "operating_revenue_lei"),
        ("cheltuieli de exploatare", "operating_costs_lei"),
        ("cheltuieli de productie", "operating_costs_lei"),
        ("ponderea energiei in costuri", "energy_cost_share"),
        ("cheltuieli energetice totale lei", "energy_costs_lei"),
        ("cheltuieli energie electrica lei", "electricity_costs_lei"),
        ("cheltuieli energie termica", "heat_costs_lei"),
        ("cheltuieli gaze lei", "gas_costs_lei"),
        ("cheltuieli motorina lei", "diesel_costs_lei"),
        ("cheltuieli benzina lei", "petrol_costs_lei"),
        ("cheltuieli gpl lei", "lpg_costs_lei"),
    ):
        if key.startswith(prefix):
            return result
    if "cost" in key and "energie" in key and "lei" in key:
        return "energy_costs_lei"
    return None


def _economic_years(sheet: Sheet, issues: list[ReaderIssue]) -> dict[int, int]:
    years: dict[int, int] = {}
    for row in range(1, sheet.max_row + 1):
        label = cell_at(sheet, row, 1, issues).value
        if isinstance(label, str) and normal(label) == "anul":
            for col in range(2, sheet.max_col + 1):
                year = _year(cell_at(sheet, row, col, issues).value)
                if year is not None:
                    years[col] = year
            break
    return years


def read_economics(sheet: Sheet, info: NecesarInfo) -> None:
    years = _economic_years(sheet, info.issues)
    if not years:
        info.issues.append(ReaderIssue("year_missing", "Cifre economice"))
        return
    for row in range(1, sheet.max_row + 1):
        label = cell_at(sheet, row, 1, info.issues).value
        if not isinstance(label, str):
            continue
        key = _economic_key(label)
        if key is None:
            continue
        for col, year in years.items():
            found = number(
                cell_at(sheet, row, col, info.issues),
                info.issues,
                unit="lei" if key.endswith("_lei") else "%",
            )
            if found is not None:
                if year in info.economics.get(key, {}):
                    info.issues.append(ReaderIssue("economic_ambiguous", key, found.ref))
                else:
                    info.economics.setdefault(key, {})[year] = found


def read_employees(sheet: Sheet, info: NecesarInfo) -> None:
    years: dict[int, int] = {}
    for row in range(1, sheet.max_row + 1):
        for col in range(2, sheet.max_col + 1):
            year = _year(cell_at(sheet, row, col, info.issues).value)
            if year is not None:
                years[col] = year
        label = cell_at(sheet, row, 1, info.issues).value
        if isinstance(label, str) and normal(label).startswith("numar de salariati"):
            for col, year in years.items():
                found = number(cell_at(sheet, row, col, info.issues), info.issues, unit="persons")
                if found is not None:
                    info.employees[year] = found
            return
    info.issues.append(ReaderIssue("label_missing", "Număr de salariați"))


def read_other(sheet: Sheet, info: NecesarInfo) -> None:
    header = next(
        (
            row
            for row in range(1, sheet.max_row + 1)
            if any(
                normal(str(cell_at(sheet, row, col, info.issues).value or "")) in {"u m", "valoare"}
                for col in range(2, min(sheet.max_col, 4) + 1)
            )
        ),
        None,
    )
    if header is None:
        info.issues.append(ReaderIssue("label_missing", "Alte consumuri headers"))
        return
    for row in range(header + 1, sheet.max_row + 1):
        values = {
            key: found
            for key, col in (("item", 2), ("unit", 3), ("value", 4))
            if (found := filled(cell_at(sheet, row, col, info.issues))) is not None
        }
        if values:
            info.other_consumption.append(values)


def _header_row(sheet: Sheet, issues: list[ReaderIssue]) -> int | None:
    labels = (
        "nr",
        "denumire",
        "marca",
        "producator",
        "tip",
        "an fabricatie",
        "putere",
        "suprafata",
        "consum",
        "capacitate",
        "combustibil",
        "numar",
        "model",
    )
    for row in range(1, min(sheet.max_row, 12) + 1):
        matched = sum(
            isinstance(value, str) and normal(value).startswith(labels)
            for col in range(1, sheet.max_col + 1)
            if (value := cell_at(sheet, row, col, issues).value) is not None
        )
        if matched >= 2:
            return row
    return None


def _is_subheader(sheet: Sheet, row: int, columns: list[int], issues: list[ReaderIssue]) -> bool:
    values = [cell_at(sheet, row, col, issues).value for col in columns]
    text = [value for value in values if isinstance(value, str) and value.strip()]
    return (
        bool(text)
        and not any(isinstance(value, int | float) for value in values)
        and all(
            value.strip().startswith(("[", "("))
            or normal(value) in {"crt", "ridicare", "u m", "unitate de masura"}
            for value in text
        )
    )


def read_generic(sheet: Sheet, issues: list[ReaderIssue]) -> GenericTable:
    header = _header_row(sheet, issues)
    if header is None:
        issues.append(ReaderIssue("table_header_missing", sheet.name))
        return GenericTable(sheet.name, [])
    names: dict[int, str] = {}
    used: set[str] = set()
    top_columns = [
        col
        for col in range(1, sheet.max_col + 1)
        if cell_at(sheet, header, col, issues).value is not None
    ]
    subheader = _is_subheader(sheet, header + 1, top_columns, issues)
    for col in range(1, sheet.max_col + 1):
        top = cell_at(sheet, header, col, issues).value
        sub = cell_at(sheet, header + 1, col, issues).value if subheader else None
        if top is None and sub is None:
            continue
        name = str(top).strip() if top is not None else f"column_{col}"
        if isinstance(sub, str) and sub.strip() and sub.strip() != name:
            name = f"{name} / {sub.strip()}"
        if name in used:
            issues.append(
                ReaderIssue("table_header_ambiguous", name, CellRef(sheet.name, header, col))
            )
            name = f"{name} ({col})"
        used.add(name)
        names[col] = name
    rows: list[GenericRow] = []
    for row in range(header + 2 if subheader else header + 1, sheet.max_row + 1):
        values = {
            name: found
            for col, name in names.items()
            if (found := filled(cell_at(sheet, row, col, issues))) is not None
        }
        if not values:
            continue
        if normal(sheet.name) == "echipamente 1" and rows:
            detail = cell_at(sheet, row, 3, issues).value
            primary = cell_at(sheet, row, 2, issues).value
            if (
                primary is None
                and isinstance(detail, str)
                and normal(detail).startswith(("tip ", "seria ", "model "))
            ):
                rows[-1].continuation.extend(values.values())
                continue
        rows.append(GenericRow(values))
    return GenericTable(sheet.name, rows)
