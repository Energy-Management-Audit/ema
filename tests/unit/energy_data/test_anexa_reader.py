"""Reader failures retain cell locations and cannot silently replace other data."""

from __future__ import annotations

from typing import cast

from ema.core.office.errors import OfficeError
from ema.core.office.sheets import Book, CellRef, CellValue
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.anexa_monthly import read_monthly
from ema.energy_data.source import number


class GridSheet:
    name = "Date lunare"
    max_col = 13

    def __init__(self, rows: list[list[str | float | None]], error: tuple[int, int] | None = None):
        self.rows = rows
        self.max_row = len(rows)
        self.error = error

    def value(self, row: int, col: int) -> CellValue:
        if row < 1 or col < 1:
            raise ValueError("Excel coordinates are one-based")
        if (row, col) == self.error:
            raise OfficeError("cell_error", "bad cell")
        value = self.rows[row - 1][col - 1] if col <= len(self.rows[row - 1]) else None
        return CellValue(value, CellRef(self.name, row, col))


class GridBook:
    def __init__(self, sheet: GridSheet):
        self.grid = sheet

    def sheet(self, name: str) -> GridSheet:
        assert name == "Date lunare"
        return self.grid


def _block() -> list[list[str | float | None]]:
    return [
        ["ENERGIE ELECTRICĂ – Consumul total anual"],
        [
            "Luna",
            "Ian",
            "Feb",
            "Mar",
            "Apr",
            "Mai",
            "Iun",
            "Iul",
            "Aug",
            "Sep",
            "Oct",
            "Noi",
            "Dec",
        ],
        ["[MWh]", *[float(i) for i in range(1, 13)]],
    ]


def test_cell_error_keeps_other_months_and_location() -> None:
    result = AnexaData()
    read_monthly(cast(Book, GridBook(GridSheet(_block(), (3, 2)))), result)
    assert set(result.monthly["electricity_grid"]) == set(range(2, 13))
    assert any(
        issue.code == "cell_error" and issue.ref == CellRef("Date lunare", 3, 2)
        for issue in result.issues
    )


def test_repeated_monthly_carrier_is_reported_without_overwrite() -> None:
    result = AnexaData()
    read_monthly(cast(Book, GridBook(GridSheet(_block() * 2))), result)
    assert "electricity_grid" not in result.monthly
    assert any(issue.code == "carrier_ambiguous" for issue in result.issues)


def test_month_header_in_first_row_has_no_negative_cell_read() -> None:
    result = AnexaData()
    read_monthly(cast(Book, GridBook(GridSheet(_block()[1:]))), result)
    assert "electricity_grid" not in result.monthly
    assert any(issue.code == "carrier_unknown" for issue in result.issues)


def test_ambiguous_grouped_number_is_not_guessed() -> None:
    result = AnexaData()
    ref = CellRef("Date anuale", 4, 7)
    assert number(CellValue("1.234", ref), result.issues) is None
    assert result.issues[-1].code == "number_ambiguous"
    assert result.issues[-1].ref == ref
    assert number(CellValue("1\u00a0234,56", ref), result.issues) is not None
