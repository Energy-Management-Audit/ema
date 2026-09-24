"""Level 1: compare Anexa extraction with an independent source-workbook dump.

This is regression evidence from workbook inputs, not a delivered or approved output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ema.energy_data.anexa import parse_anexa
from ema.energy_data.source import normal

pytestmark = pytest.mark.golden


def _annexes(reference_library: Path) -> list[Path]:
    root = reference_library / "piee"
    batch = list((root / "anexa-2-3-2025").glob("*.xls*"))
    corrections = [
        path
        for case in ("piee-case-a", "piee-case-b")
        for path in (root / "cases" / case / "received").glob("*Anexa*.xlsx")
    ]
    return sorted([*batch, *corrections])


def _case(reference_library: Path, fragment: str) -> Path:
    return next(path for path in _annexes(reference_library) if fragment in path.name)


def test_all_38_annexes_read_with_traceable_core_values(reference_library: Path) -> None:
    paths = _annexes(reference_library)
    assert len(paths) == 38
    for path in paths:
        parsed = parse_anexa(path)
        assert parsed.year is not None, path.name
        assert parsed.year.value == 2025, path.name
        required = {"address", "cui", "phone", "fax", "caen_code", "caen_description"}
        assert required <= set(parsed.identity), path.name
        assert "name" in parsed.identity or any(
            issue.code == "name_is_address" for issue in parsed.issues
        ), path.name
        assert "total_tep" in parsed.annual, path.name
        assert parsed.annual["total_tep"].ref.sheet == "Date anuale", path.name
        assert len(parsed.monthly["electricity_grid"]) == 12, path.name
        assert parsed.monthly["electricity_grid"][1].unit == "MWh", path.name
        assert not any(issue.code == "sheet_missing" for issue in parsed.issues), path.name


def _snapshot(reference_library: Path, path: Path) -> dict[str, list[list[str]]]:
    source = reference_library / "_analysis" / "anexa_dump.json"
    return json.loads(source.read_text())[str(path.relative_to(reference_library))]


@pytest.mark.parametrize("filename", ["CLIENT-P1", "CLIENT-X3", "CLIENT-P2", "CLIENT-X1", "CLIENT-X2"])
def test_five_layouts_match_independent_snapshot(reference_library: Path, filename: str) -> None:
    path = _case(reference_library, filename)
    parsed = parse_anexa(path)
    sheets = _snapshot(reference_library, path)
    contact = sheets.get("Date generale") or sheets["Info companie"]
    name_row = next(row for row in contact if row and row[0].startswith("Denumirea"))
    cui_row = next(row for row in contact if row and row[0] == "CUI")
    assert parsed.identity["name"].value == next(value for value in name_row[1:] if value)
    assert parsed.identity["cui"].value == next(value for value in cui_row[1:] if value)
    address_row = next(row for row in contact if row and normal(row[0]) == "adresa postala")
    assert parsed.identity["address"].value == next(value for value in address_row[1:] if value)

    annual = sheets["Date anuale"]
    total_row = next(i for i, row in enumerate(annual) if "CONSUM DE ENERGIE TOTAL ANUAL" in row)
    total_values = annual[total_row + 1]
    unit_col = next(
        i
        for i, value in enumerate(total_values)
        if value.strip().lower().startswith(("[tep", "[ tep"))
    )
    assert float(parsed.annual["total_tep"].value) == pytest.approx(
        float(total_values[unit_col + 1])
    )
    fuel_row = next(i for i, row in enumerate(annual) if "Gaze naturale" in row)
    gas_col = annual[fuel_row].index("Gaze naturale")
    assert float(parsed.annual["natural_gas_raw"].value) == pytest.approx(
        float(annual[fuel_row + 3][gas_col])
    )
    assert parsed.existing_measures
    assert parsed.planned_measures
    assert parsed.existing_measures[0].commissioning_year is not None
    assert parsed.existing_measures[0].commissioning_year.value == 2025
    monthly = sheets["Date lunare"]
    grid_row = next(
        i
        for i, row in enumerate(monthly)
        if row and normal(row[0]) == "energie electrica consumul total anual"
    )
    month_row = next(
        i for i in range(grid_row + 1, grid_row + 4) if normal(monthly[i][0]) == "luna"
    )
    assert float(parsed.monthly["electricity_grid"][1].value) == pytest.approx(
        float(monthly[month_row + 1][1])
    )
    first = parsed.existing_measures[0]
    measure_sheet = sheets[first.description.ref.sheet]
    saving = first.values["saving_mwh"]
    assert normal(measure_sheet[saving.ref.row - 2][saving.ref.col - 1]).startswith("mwh an")
    assert float(saving.value) == pytest.approx(
        float(measure_sheet[saving.ref.row - 1][saving.ref.col - 1])
    )


def test_shifted_measure_columns_and_missing_year_remain_visible(reference_library: Path) -> None:
    shifted = parse_anexa(_case(reference_library, "CLIENT-X1"))
    assert shifted.existing_measures[0].commissioning_year is not None
    assert shifted.existing_measures[0].commissioning_year.ref.a1.endswith("D5")
    assert shifted.existing_measures[0].location is not None
    assert shifted.existing_measures[0].description.ref.a1.endswith("C5")

    extra_column = parse_anexa(_case(reference_library, "CLIENT-X5"))
    assert len(extra_column.planned_measures) == 4
    assert [
        item.commissioning_year.value
        for item in extra_column.planned_measures
        if item.commissioning_year
    ] == [2026, 2026, 2026, 2032]
    assert extra_column.planned_measures[0].commissioning_year is not None
    assert extra_column.planned_measures[0].commissioning_year.ref.a1.endswith("D6")

    long_list = parse_anexa(_case(reference_library, "CLIENT-X4"))
    assert len(long_list.existing_measures) == 121


def test_monthly_utility_block_does_not_overwrite_previous_fuel(reference_library: Path) -> None:
    public_water = parse_anexa(_case(reference_library, "CLIENT-X1"))
    assert sum(float(item.value) for item in public_water.monthly["coal"].values()) == 0
    assert sum(float(item.value) for item in public_water.monthly["water_potable"].values()) > 0

    industrial_water = parse_anexa(_case(reference_library, "Oras"))
    assert sum(float(item.value) for item in industrial_water.monthly["coal"].values()) == 0
    assert (
        sum(float(item.value) for item in industrial_water.monthly["water_industrial"].values()) > 0
    )
