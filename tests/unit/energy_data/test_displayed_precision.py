"""Precision for the annual filing reconciliation comes from the source cell."""

from __future__ import annotations

from ema.core.office.sheets import CellRef, CellValue
from ema.energy_data.source import displayed_decimals, number


def test_fixed_excel_format_precision_is_retained() -> None:
    assert displayed_decimals('#,##0.00 "tep"') == 2
    assert displayed_decimals("0") == 0
    assert displayed_decimals("0.0000") == 4
    assert displayed_decimals("0.##") is None
    assert displayed_decimals("General") is None
    assert displayed_decimals("0.00%") is None
    cell = CellValue(1234.5, CellRef("Date anuale", 7, 8), number_format="#,##0.00")
    found = number(cell, [], unit="tep/an")
    assert found is not None
    assert found.displayed_decimals == 2
