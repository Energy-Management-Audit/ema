"""Label-based audit metadata and measure reader for Anexa 2–3."""

from __future__ import annotations

from ema.core.office.sheets import Book, Sheet
from ema.energy_data.anexa_cells import AnexaData, Measure
from ema.energy_data.source import (
    Located,
    ReaderIssue,
    cell_at,
    filled,
    normal,
    number,
    right_of_label,
    skip_placeholder,
)


def _header(sheet: Sheet, result: AnexaData) -> tuple[int, dict[int, str]] | None:
    for row in range(1, min(sheet.max_row, 30) + 1):
        labels = {
            col: normal(value)
            if isinstance(value := cell_at(sheet, row, col, result.issues).value, str)
            else ""
            for col in range(1, min(sheet.max_col, 20) + 1)
        }
        if any(label.startswith("masura") for label in labels.values()) and any(
            label.startswith("costuri") for label in labels.values()
        ):
            return row, labels
    return None


def _columns(sheet: Sheet, row: int, labels: dict[int, str], result: AnexaData) -> dict[str, int]:
    columns: dict[str, int] = {}
    for key, prefix in (
        ("investment_thousand_lei", "costuri"),
        ("saving_tep", "economii tep"),
        ("saving_thousand_lei", "economii de cost"),
    ):
        headings = [col for col, label in labels.items() if label.startswith(prefix)]
        if len(headings) != 1:
            result.issues.append(ReaderIssue("label_ambiguous", f"Audit energetic: {prefix}"))
            continue
        start = headings[0]
        following = min(
            (col for col in labels if col > start and labels[col]), default=sheet.max_col + 1
        )
        choices: list[int] = []
        for col in range(start, following):
            value = cell_at(sheet, row + 1, col, result.issues).value
            if isinstance(value, str) and normal(value).startswith("estimate"):
                choices.append(col)
        if len(choices) == 1:
            columns[key] = choices[0]
        else:
            result.issues.append(
                ReaderIssue("label_missing", f"Audit energetic: {prefix} estimate")
            )
    return columns


def _measures(sheet: Sheet, result: AnexaData) -> None:
    header = _header(sheet, result)
    if header is None:
        result.issues.append(ReaderIssue("label_missing", "Audit energetic: măsuri"))
        return
    row, labels = header
    description_col = next(col for col, label in labels.items() if label.startswith("masura"))
    columns = _columns(sheet, row, labels, result)
    for data_row in range(row + 2, min(sheet.max_row, 400) + 1):
        description = filled(cell_at(sheet, data_row, description_col, result.issues))
        if description is None or not isinstance(description.value, str):
            continue
        label = normal(description.value)
        if not label or label.startswith(("masura", "total")):
            continue
        row_issues: list[ReaderIssue] = []
        raw_values = {
            key: cell_at(sheet, data_row, col, row_issues) for key, col in columns.items()
        }
        if skip_placeholder(description, raw_values.values(), result.issues):
            continue
        result.issues.extend(row_issues)
        values: dict[str, Located] = {}
        for key in columns:
            found = number(raw_values[key], result.issues)
            if found is not None:
                values[key] = found
        result.audit_measures.append(Measure("audit", description, None, values))


def read_audit(book: Book, result: AnexaData) -> None:
    sheet = book.sheet("Audit energetic")
    for key, labels in {
        "last_audit": ("Data ultimului audit energetic efectuat",),
        "auditor": ("Persoana fizică / persoana juridică  care a efectuat auditul energetic",),
        "boundary": ("Contur bilanț energetic",),
    }.items():
        value = right_of_label(sheet, labels, result.issues)
        if value is not None:
            result.audit[key] = value
    _measures(sheet, result)
