"""Synthetic coverage checks for the local S3 workbook reader."""

from __future__ import annotations

import pytest

from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import Factor, FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading

from .s3_book import MONTHS, Workbook, month_columns, monthly_physical
from .test_s3_prelucrare import ReviewContext, _expected_or_match, _tep_cells


def _tep_book(label: str) -> Workbook:
    return Workbook(
        {
            "TEP": [
                [None, None, 2024],
                [None, None, None, *MONTHS],
                [None, None, label, *([1.0] * 12), 12.0],
                [None, None, "Total TEP", *([1.0] * 12), 12.0],
            ]
        }
    )


def test_tep_rows_must_be_mapped_or_explicitly_ignored() -> None:
    cells = _tep_cells(_tep_book("Gaz TEP"), (2024,), "synthetic")
    assert (2024, Carrier.natural_gas, 1, 1.0) in cells
    with pytest.raises(AssertionError, match="unmapped TEP row"):
        _tep_cells(_tep_book("Unfamiliar energy"), (2024,), "synthetic")


def test_duplicate_labels_fail_loudly() -> None:
    book = _tep_book("Gaz TEP")
    book.sheets["TEP"].insert(3, book.sheets["TEP"][2].copy())
    with pytest.raises(AssertionError, match="duplicate TEP carrier row"):
        _tep_cells(book, (2024,), "synthetic")
    rows = [
        [2024, None, None, *MONTHS],
        [None, None, "Motorina [t]", *([1.0] * 12)],
        [None, None, "Motorina [t]", *([2.0] * 12)],
    ]
    with pytest.raises(AssertionError, match="duplicate physical label"):
        monthly_physical(rows, "Motorina [t]", "t", (2024,))
    with pytest.raises(AssertionError, match="duplicate month label"):
        month_columns([*MONTHS, "ianuarie"])


def test_expected_difference_checks_value_and_missing_reason() -> None:
    context = ReviewContext(
        set(),
        [],
        _tep_book("Gaz TEP"),
        EnergyDataset((2022,), {}),
        FactorTable("synthetic", 2022, (), ()),
    )
    key = ("piee-case-a", "TEP", "purchased_heat", 2022, None)
    assert _expected_or_match(key, None, ("carrier.purchased_heat.2022",), 0, context) == (0, 1)
    with pytest.raises(AssertionError, match="expected missing value"):
        _expected_or_match(key, 1, (), 0, context)
    with pytest.raises(AssertionError, match="missing reason changed"):
        _expected_or_match(key, None, ("wrong.reason",), 0, context)
    with pytest.raises(AssertionError, match="expected filed zero"):
        _expected_or_match(key, None, ("carrier.purchased_heat.2022",), 1, context)
    total_key = ("piee-case-b", "TEP", "total", 2024, 1)
    with pytest.raises(AssertionError, match="expected filed relation failed"):
        _expected_or_match(total_key, None, ("carrier.lpg.2024.01",), 2, context)
    relation_key = ("audit-case-c", "Chelt-Cifra afaceri", "intensity", 2024, None)
    relation_context = ReviewContext(
        set(),
        [],
        context.book,
        EnergyDataset(
            (2024,),
            {Carrier.electricity_grid: {2024: CarrierSeries(annual=Reading(100, "MWh"))}},
            turnover_lei={2024: Reading(1000, "lei")},
        ),
        FactorTable(
            "synthetic", 2024, (Factor(Carrier.electricity_grid, "MWh", 1, "synthetic"),), ()
        ),
    )
    with pytest.raises(AssertionError, match="expected filed relation failed"):
        _expected_or_match(relation_key, 100, (), 999, relation_context)
    with pytest.raises(AssertionError, match="expected Ema relation failed"):
        _expected_or_match(relation_key, 101, (), 100000, relation_context)
