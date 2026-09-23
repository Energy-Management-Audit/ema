"""Test-only, label-anchored access to the auditor's Prelucrare date workbooks."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl
import xlrd

from ema.energy_data.model import CarrierSeries, Reading

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


def norm(value: object) -> str:
    if value is None:
        return ""
    plain = unicodedata.normalize("NFKD", str(value).casefold())
    return " ".join(
        re.findall(r"[a-z0-9]+", "".join(char for char in plain if not unicodedata.combining(char)))
    )


def number(value: object) -> float | None:
    return float(value) if isinstance(value, float | int) and not isinstance(value, bool) else None


def year(value: object) -> int | None:
    value_num = number(value)
    if value_num is not None and value_num.is_integer() and 2020 <= value_num <= 2030:
        return int(value_num)
    match = re.match(r"^(20[2-3][0-9])(?:\b|\()", str(value).strip())
    return int(match.group(1)) if match else None


@dataclass
class Workbook:
    sheets: dict[str, list[list[Any]]]

    @classmethod
    def open(cls, path: Path) -> Workbook:
        if path.suffix == ".xls":
            book = xlrd.open_workbook(path)
            sheets = {
                name: [
                    [sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)
                ]
                for name in book.sheet_names()
                for sheet in [book.sheet_by_name(name)]
            }
        else:
            book = openpyxl.load_workbook(path, read_only=True, data_only=True)
            sheets = {name: [list(row) for row in book[name].values] for name in book.sheetnames}
            book.close()
        return cls(sheets)

    def sheet(self, label: str) -> list[list[Any]]:
        found = [rows for name, rows in self.sheets.items() if norm(name) == norm(label)]
        if len(found) != 1:
            raise AssertionError(f"sheet label {label!r}: {len(found)} matches")
        return found[0]


def month_columns(row: list[Any]) -> dict[int, int]:
    columns = {
        MONTHS.index(norm(value)) + 1: column
        for column, value in enumerate(row)
        if norm(value) in MONTHS
    }
    if sum(norm(value) in MONTHS for value in row) != len(columns):
        raise AssertionError("duplicate month label")
    return columns


def _year_blocks(rows: list[list[Any]]) -> list[tuple[int, int, dict[int, int]]]:
    blocks = []
    for i, row in enumerate(rows):
        found = next((year(value) for value in row[:3] if year(value) is not None), None)
        columns = month_columns(row)
        if found is not None and len(columns) == 12:
            blocks.append((found, i, columns))
    return blocks


def monthly_physical(
    rows: list[list[Any]], label: str, unit: str, years: tuple[int, ...]
) -> dict[int, CarrierSeries]:
    """Find a year/month header, then its uniquely labelled physical row."""
    blocks = _year_blocks(rows)
    result = {}
    for block_index, (block_year, start, columns) in enumerate(blocks):
        if block_year not in years:
            continue
        if any(previous_year == block_year for previous_year, _, _ in blocks[:block_index]):
            raise AssertionError(f"duplicate year block: {block_year}")
        end = blocks[block_index + 1][1] if block_index + 1 < len(blocks) else len(rows)
        candidates = [
            row
            for row in rows[start + 1 : end]
            if any(norm(cell) == norm(label) for cell in row[:3])
        ]
        if not candidates:
            continue
        if len(candidates) != 1:
            raise AssertionError(f"duplicate physical label {label!r} in {block_year}")
        row = candidates[0]
        months = {
            month: Reading(number(row[column]), unit)
            for month, column in columns.items()
            if column < len(row)
        }
        if any(reading.value is not None for reading in months.values()):
            result[block_year] = CarrierSeries(months)
    return result
