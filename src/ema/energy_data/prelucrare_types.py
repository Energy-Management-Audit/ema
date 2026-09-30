"""Shared types and safe sheet access for Prelucrare import."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ema.core.office.errors import OfficeError
from ema.core.office.sheets import Book, CellRef, CellValue, Sheet
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset, Reading
from ema.energy_data.source import Located, ReaderIssue, normal


@dataclass
class PrelucrareData:
    dataset: EnergyDataset
    factors: FactorTable
    located: dict[str, Located] = field(default_factory=lambda: {})
    filed: dict[str, Located] = field(default_factory=lambda: {})
    issues: list[ReaderIssue] = field(default_factory=lambda: [])
    deferred_series: set[tuple[Carrier, int]] = field(default_factory=set[tuple[Carrier, int]])
    deferred_production: set[int] = field(default_factory=set[int])
    previous_annual: dict[str, Reading] = field(default_factory=lambda: {})
    previous_annual_located: dict[str, Located] = field(default_factory=lambda: {})

    def to_dataset(self) -> EnergyDataset:
        return self.dataset


@dataclass(frozen=True)
class SourceConflict:
    field: str
    prelucrare: Reading
    other: Reading


def year_label(value: object) -> int | None:
    text = str(value).strip()
    match = re.match(r"^(20[2-3][0-9])(?:\b|\()", text)
    return int(match.group(1)) if match else None


def numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def cell_or_blank(sheet: Sheet, row: int, col: int) -> CellValue:
    try:
        return sheet.value(row, col)
    except OfficeError:
        return CellValue(None, CellRef(sheet.name, row, col))


def sheet_named(book: Book, name: str, issues: list[ReaderIssue] | None = None) -> Sheet | None:
    matches = [item for item in book.sheet_names if normal(item) == normal(name)]
    if len(matches) > 1 and issues is not None:
        issues.append(ReaderIssue("sheet_ambiguous", name))
    return book.sheet(matches[0]) if len(matches) == 1 else None
