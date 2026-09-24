"""Source locations, reader issues, and spreadsheet value helpers."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from ema.core.office.errors import OfficeError
from ema.core.office.sheets import CellRef, CellValue, Sheet


@dataclass(frozen=True)
class Located:
    value: str | float | int | datetime
    ref: CellRef
    unit: str | None = None


@dataclass(frozen=True)
class ReaderIssue:
    code: str
    detail: str
    ref: CellRef | None = None


def normal(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        re.findall(r"[a-z0-9]+", "".join(c for c in plain if not unicodedata.combining(c)))
    )


def filled(cell: CellValue) -> Located | None:
    value = cell.value
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return Located(value, cell.ref)


def cell_at(sheet: Sheet, row: int, col: int, issues: list[ReaderIssue]) -> CellValue:
    ref = CellRef(sheet.name, row, col)
    try:
        return sheet.value(row, col)
    except OfficeError as exc:
        issues.append(ReaderIssue(exc.code, str(exc), ref))
        return CellValue(None, ref)


def number(
    cell: CellValue, issues: list[ReaderIssue], *, unit: str | None = None
) -> Located | None:
    value = cell.value
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        issues.append(ReaderIssue("invalid_number", str(value), cell.ref))
        return None
    if isinstance(value, str):
        raw = value.strip().replace(" ", "").replace("\u00a0", "")
        if re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+", raw):
            issues.append(ReaderIssue("number_ambiguous", value, cell.ref))
            return None
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            issues.append(ReaderIssue("invalid_number", str(value), cell.ref))
            return None
    if not math.isfinite(value):
        issues.append(ReaderIssue("invalid_number", str(value), cell.ref))
        return None
    return Located(value, cell.ref, unit)


def row_with(
    sheet: Sheet, words: tuple[str, ...], issues: list[ReaderIssue], *, limit: int = 100
) -> int | None:
    targets = tuple(normal(word) for word in words)
    for row in range(1, min(sheet.max_row, limit) + 1):
        for col in range(1, min(sheet.max_col, 3) + 1):
            value = cell_at(sheet, row, col, issues).value
            if isinstance(value, str) and normal(value) in targets:
                return row
    return None


def right_of_label(
    sheet: Sheet, labels: tuple[str, ...], issues: list[ReaderIssue]
) -> Located | None:
    targets = {normal(label) for label in labels}
    matches: list[CellRef] = []
    for row in range(1, min(sheet.max_row, 40) + 1):
        for col in range(1, min(sheet.max_col, 2) + 1):
            value = cell_at(sheet, row, col, issues).value
            if isinstance(value, str) and normal(value) in targets:
                matches.append(CellRef(sheet.name, row, col))
    if not matches:
        issues.append(ReaderIssue("label_missing", "/".join(labels)))
        return None
    if len(matches) > 1:
        issues.append(ReaderIssue("label_ambiguous", "/".join(labels), matches[0]))
        return None
    anchor = matches[0]
    for col in range(anchor.col + 1, min(sheet.max_col, anchor.col + 4) + 1):
        candidate = filled(cell_at(sheet, anchor.row, col, issues))
        if candidate is not None:
            return candidate
    issues.append(ReaderIssue("value_missing", "/".join(labels), anchor))
    return None
